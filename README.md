# Fork to add some functionalities that im using

1. Log file

Logfile in this project grows without limit, so ive added `from logging.handlers import RotatingFileHandler` to have 2 files, each with 20mb (last file had 2gb...)

2. uv "support"

While it was possible to write some scripts to run uv back to google colab, in my case it was simpler just to built it in for easy access

The following command is now possible:

## colab uv run [UV_ARGS...]

Runs your project via `uv run` inside a mirrored Google Colab VM workspace:
- Syncs the local workspace to `/content/<current_dir_name>` on the Colab VM using `rsync --delete` (or archive sync fallback).
- Passes all arguments directly to `uv run` on the remote machine (e.g. `colab uv run train.py --epochs 10` runs `uv run train.py --epochs 10`).

- Propagates remote exit codes back to your local shell.

- Automatically tears down the VM when finished (unless `--keep` is specified).

### Flags & Options:
- `--keep`: Keeps the Colab VM alive after execution finishes, to use it in the next run use `-s <name>`.

Ex:

```shell
colab uv run random-uv --keep
[...]
[colab] Session kept: 'uv-3de2e7'. Re-run with -s uv-3de2e7 --keep
colab uv run random-uv -s uv-3de2e7 --keep
```

- `-s, --session, --name <name>`: Reuses an active session or gives the new session a specific name.

- `--gpu <T4|L4|G4|A100|H100>`: select a GPU accelerator, skipping the interactive shell.

- `--tpu <v5e1|v6e1>`: Pre-selects a TPU accelerator. This is missing from the interactive shell.

- `--high-mem`: Requests a high-RAM machine shape.

- `--mount-drive / --no-mount-drive`: Mounts Google Drive at `/content/drive`.

- `--sync-back / --no-sync-back`: Syncs modified/generated files from the remote workspace back to local on completion.

- `--remote-dir <path>`: Custom destination path on Colab (default: `/content/<folder_name>`).

- `-i, --identity <path>`: SSH key for rsync, normally not necessary.

- `--gitignore` / `--colabignore`: Creates a `.colabignore` file in the current directory. Works similar to how .gitignore would work but to not send files to colab.
Ex:

```shell
colab uv --colabignore
```

still more tests and documentation, so far tested a little