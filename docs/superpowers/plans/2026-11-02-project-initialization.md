# Project Initialization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the minimal Python + uv package and documented configuration-check entry point for issue #1.

**Architecture:** Standard-library CLI and TOML configuration in a small src package. Deployment remains independent; no HTTP server yet.

**Tech Stack:** Python >=3.12, uv/uv_build, unittest, Ruff.

**Spec:** `docs/superpowers/specs/2026-11-02-project-initialization-design.md`

## Global Constraints

- No runtime dependencies for initialization. Use argparse and tomllib.
- No deployment method is required or implemented in this issue.
- Checking creates no files. Private data stays out of version control and build artifacts.

## Review Focus

- Relative data paths must resolve against the configuration file, including from another working directory.
- Missing or malformed config files must fail without echoing sensitive contents.
- Empty or non-string data_dir values must fail clearly.
- Help must work without a configuration file.
- Source and wheel distributions must exclude local private files.

## Task 1: Runnable package and config check

**Files:** `pyproject.toml`, `src/monocloud_subscription/{__init__,cli,config}.py`, `tests/test_cli.py`, `tests/test_config.py`.

**Interfaces:** `load_config(path: Path) -> Config`, `Config.data_dir: Path`, `main(argv: list[str] | None = None) -> int`.

- [x] Write tests for relative/absolute paths, invalid data_dir, malformed/missing config, CLI help and check success/failure. Run with PYTHONPATH=src and confirm missing implementation failures.
- [x] Implement the config loader and CLI; run the same tests to green.
- [x] Add package metadata, entry point, uv_build configuration, Ruff settings and lock file. Run `uv sync --locked`, `uv run python -m unittest discover -s tests -v`, `uv run ruff check .`, and `uv run ruff format --check .`.

## Task 2: Documentation and clean-install verification

**Files:** `README.md`, `config.example.toml`, `.gitignore`, `uv.lock`.

**Interfaces:** Documents the Task 1 CLI, with config-relative data paths.

- [x] Write the five README sections requested by the user, clarify current implementation status, and add a generic example config.
- [x] Follow quick-start commands; build wheel and source distributions with `uv build` and inspect their contents for private files.
- [x] Verify the wheel entry point in a separate clean environment, run all checks, and update issue #1 with the accepted architecture and results.

## Verification record

- Nine behavioral tests passed on Python 3.14.4; Python 3.12 remains the declared minimum, not an independently tested interpreter in this environment.
- Ruff lint and formatting passed; wheel and source distributions built and contained no private config or local directories.
- Wheel installed without dependencies in a separate environment; installed CLI help and configuration check worked.
- Independent read-only review reported no important or critical findings.
- User subsequently authorized committing, pushing, and closing issue #1 after verification.

## Execution notes

Execute in this initial repository without creating a worktree. No existing implementation or baseline tests exist. User authorized initialization, then explicitly requested committing, pushing, and closing #1 once verified. Keep process proportional to the small bootstrap task.
