FROM ghcr.io/astral-sh/uv:0.11.6 AS uv
FROM python:3.12-slim-bookworm AS build
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src/ src/
RUN uv sync --locked --no-dev --no-editable --no-cache

FROM python:3.12-slim-bookworm AS runtime
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home app \
    && mkdir /data /config \
    && chown app:app /data \
    && chmod 700 /data
COPY --from=build /app/.venv /app/.venv
USER 10001:10001
WORKDIR /app
EXPOSE 8080
ENTRYPOINT ["monocloud-subscription"]
CMD ["--config", "/config/config.toml", "serve"]
