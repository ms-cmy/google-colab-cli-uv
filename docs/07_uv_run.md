---
log:
2026-10-27: Initial design and implementation of `colab uv run [UV_ARGS...]` and `colab uv --gitignore`. Syncs local workspace to remote `/content/<dir>` via rsync mirror sync with .colabignore support, passes all arguments to remote `uv run`, handles interactive accelerator prompting (defaulting to CPU), supports session reuse and `--keep`, and propagates remote exit codes.
---

# Design: `colab uv run` — Remote uv Workspace Execution

## Motivation
Modern Python projects increasingly leverage `uv` for fast dependency resolution and execution. While notebooks and single-file scripts are well supported by `colab exec` and `colab run`, multi-file project repositories with project configuration (`pyproject.toml`, `uv.lock`) require syncing an entire workspace and running commands in the project's virtual environment.

`colab uv run` provides a seamless workflow:
1. Syncs the current local workspace to `/content/<folder_name>` on the Colab VM using `rsync` with `--delete` mirror semantics (falling back to tarball Contents API sync if rsync is unavailable).
2. Runs `uv run [UV_ARGS...]` remotely in the synced workspace directory.
3. Streams stdout and stderr live, properly handling terminal line updates and progress bars.
4. Suppresses kernel-level `SystemExit` tracebacks while accurately propagating the process exit code back to the local shell.
5. Automatically stops the ephemeral VM on completion (or keeps it alive when `--keep` is specified for fast iterative re-runs).

## User Surface

```bash
colab uv run [OPTIONS] [UV_ARGS...]
colab uv [--gitignore|--colabignore]
```

| Option | Type | Default | Description |
|---|---|---|---|
| `UV_ARGS` | variadic | `[]` | Arguments passed directly to `uv run` on the remote Colab VM. |
| `-s`, `--session`, `--name` | str | `auto` | Session name to reuse or create (default: `uv-<6 hex>`). |
| `--gpu` | str | `None` | GPU accelerator (`T4`, `L4`, `G4`, `A100`, `H100`). |
| `--tpu` | str | `None` | TPU accelerator (`v5e1`, `v6e1`). |
| `--high-mem` | bool | `False` | Request high-RAM machine shape. |
| `--mount-drive / --no-mount-drive` | bool | interactive / `False` | Mount Google Drive at `/content/drive`. |
| `--sync-back / --no-sync-back` | bool | interactive / `False` | Sync modified files from Colab back to the local workspace. |
| `--keep` | bool | `False` | Keep session VM alive after command finishes. |
| `--remote-dir` | str | `/content/<dir>` | Custom remote destination path. |
| `-i`, `--identity` | str | `None` | SSH identity key forwarded for rsync transfers. |
| `--timeout` | float | `None` | Timeout in seconds for remote execution. |
| `--gitignore`, `--colabignore` | flag | — | Generate a default `.colabignore` file in the current directory and exit. |

## Ignore Configuration (`.colabignore`)
To avoid synchronizing large or local-only directories (e.g. `.git/`, local `.venv/`, caches), `colab uv` uses `.colabignore`. Running `colab uv --gitignore` writes a standard template:
```
.git/
.venv/
venv/
__pycache__/
*.pyc
.pytest_cache/
.mypy_cache/
.ruff_cache/
.idea/
.vscode/
.DS_Store
*.tar.gz
```
Rsync passes this via `--exclude-from=.colabignore`. The fallback archive sync applies matching using `pathlib.PurePosixPath`.

