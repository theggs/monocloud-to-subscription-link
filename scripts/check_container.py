"""Opt-in Docker Compose smoke check using disposable state and fake credentials."""

import argparse
import base64
import json
import os
import secrets
import socket
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="monocloud-subscription:local")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="subscription-container-") as directory:
        temporary = Path(directory)
        private = temporary / ".local"
        private.mkdir(mode=0o700)
        config = private / "container.toml"
        config.write_text(
            (root / "deploy/config.example.toml")
            .read_text()
            .replace(
                "[monocloud]\n",
                '[monocloud]\nclient_id = "fixture-client"\nclient_secret = "fixture-secret"\n',
            )
        )
        # Writable file under a private parent: only the read-only mount should
        # prevent writes inside the container, not host-file ownership/mode.
        config.chmod(0o666)
        # Constructed fixture, never an actual account or management credential.
        (private / "service.env").write_text("MONOCLOUD_WEB_PASSWORD=container-test\n")
        (private / "service.env").chmod(0o600)
        compose = (root / "compose.yaml").read_text()
        compose = compose.replace("build: .", f"build: {json.dumps(str(root))}")
        compose = compose.replace("monocloud-subscription:local", args.image)
        # Only the external API boundary is substituted. The real CLI, app,
        # Uvicorn and Compose stop settings are exercised without real accounts.
        fixture = """
import time
from pathlib import Path
from monocloud_subscription.cli import main
from monocloud_subscription.monocloud import MonoCloudClient
def slow_login(self, email, password):
    Path('/data/inflight').touch()
    time.sleep(12)
    return 'fixture-token-updated'
MonoCloudClient.login = slow_login
raise SystemExit(main(['--config', '/config/config.toml', 'serve']))
"""
        compose = compose.replace(
            "    restart: unless-stopped\n",
            "    restart: unless-stopped\n"
            f"    entrypoint: {json.dumps(['python', '-c', fixture])}\n"
            "    command: []\n",
        )
        (temporary / "compose.yaml").write_text(compose)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        environment = dict(os.environ, BIND_ADDRESS="127.0.0.1", PORT=str(port))
        command = ["docker", "compose", "-p", f"container-check-{secrets.token_hex(4)}"]

        def run(*arguments):
            return subprocess.run(
                command + list(arguments),
                cwd=temporary,
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            ).stdout

        origin = f"http://127.0.0.1:{port}"

        def request(path, *, authenticated=True, data=None, timeout=2):
            headers = {}
            if authenticated:
                value = base64.b64encode(b"admin:container-test").decode()
                headers["Authorization"] = f"Basic {value}"
            if data is not None:
                headers.update({"Content-Type": "application/json", "Origin": origin})
                data = json.dumps(data).encode()
            with urlopen(
                Request(origin + path, data=data, headers=headers), timeout=timeout
            ) as response:
                return response.read()

        def wait_ready():
            for _ in range(60):
                try:
                    return request("/")
                except (URLError, TimeoutError, ConnectionError):
                    time.sleep(0.5)
            raise RuntimeError("Container did not become ready")

        try:
            run("config", "--quiet")
            run("up", "-d", "--no-build")
            assert "Clash Mi" in wait_ready().decode()
            assert request("/assets/login.js")
            try:
                request("/", authenticated=False)
                raise AssertionError("Management page allowed unauthenticated access")
            except HTTPError as error:
                assert error.code == 401
            original = json.loads(request("/api/subscription"))
            request("/api/subscription", data={"tailscale_enabled": True})
            probe = """
import errno, importlib.util, os
from pathlib import Path
from monocloud_subscription.tokens import TokenStore
assert os.getuid() == 10001
assert not Path('/app/.local').exists()
assert not Path('/app/src').exists()
assert importlib.util.find_spec('ruff') is None
try:
    Path('/config/config.toml').write_text('must not be writable')
except OSError as error:
    assert error.errno == errno.EROFS
else:
    raise AssertionError('Configuration is writable')
store = TokenStore(Path('/data/token.json'))
store.save('fixture-token')
store.save('fixture-token-updated')
assert store.load() == 'fixture-token-updated'
assert Path('/data/token.json').stat().st_mode & 0o777 == 0o600
"""
            run("exec", "-T", "subscription", "python", "-c", probe)
            with ThreadPoolExecutor(max_workers=1) as pool:
                pending = pool.submit(
                    request,
                    "/api/login",
                    data={
                        "email": "fixture@example.invalid",
                        "password": "fixture-password",
                    },
                    timeout=30,
                )
                for _ in range(60):
                    if (
                        run(
                            "exec",
                            "-T",
                            "subscription",
                            "python",
                            "-c",
                            "from pathlib import Path; print(Path('/data/inflight').exists())",
                        ).strip()
                        == "True"
                    ):
                        break
                    time.sleep(0.1)
                else:
                    raise RuntimeError("Fixture login did not start")
                run("stop")  # Use the service's actual stop grace, not an override.
                assert json.loads(pending.result())["token_saved"] is True
            container = run("ps", "-a", "-q", "subscription").strip()
            exit_code = subprocess.check_output(
                ["docker", "inspect", "--format", "{{.State.ExitCode}}", container],
                env=environment,
                text=True,
            ).strip()
            assert exit_code == "0", "Service did not stop gracefully"
            run("up", "-d", "--no-build", "--force-recreate")
            wait_ready()
            current = json.loads(request("/api/subscription"))
            assert current["url"] == original["url"]
            assert current["tailscale_enabled"] is True
            run(
                "exec",
                "-T",
                "subscription",
                "python",
                "-c",
                "from pathlib import Path; from monocloud_subscription.tokens import TokenStore; "
                "assert TokenStore(Path('/data/token.json')).load() == 'fixture-token-updated'",
            )
            print(
                "PASS: auth, UI, non-root, read-only config, atomic token writes, "
                "persistent URL/settings/token, in-flight graceful stop"
            )
        finally:
            run("down", "-v")  # Only this randomly named disposable project.


if __name__ == "__main__":
    main()
