
import os
import signal
import uuid
from typing import List, Optional

import typer
from typing_extensions import Annotated

from colab_cli.commands.execution import is_stdin_tty
from colab_cli.commands.run import _exit_code_from_outputs, _make_run_output_hook
from colab_cli.commands.session import (
    GpuOption,
    HighMemOption,
    SessionOption,
    TpuOption,
)
from colab_cli.commands.uv_prompt import prompt_accelerator
from colab_cli.ignore import generate_ignore_file, get_ignore_file
from colab_cli.runtime import ColabRuntime
from colab_cli.sync import sync_local_to_remote, sync_remote_to_local

uv_app = typer.Typer(
    name="uv",
    help="Manage and run uv workflows on Google Colab.",
    no_args_is_help=True,
)


@uv_app.callback(invoke_without_command=True)
def uv_callback(
    ctx: typer.Context,
    gitignore: Annotated[
        bool,
        typer.Option(
            "--gitignore",
            "--colabignore",
            help="Generate standard .colabignore template in the current directory and exit.",
        ),
    ] = False,
):
    if gitignore:
        path = generate_ignore_file(os.getcwd())
        typer.echo(f"[colab] Generated ignore template at {path}")
        raise typer.Exit(0)


@uv_app.command(
    name="run",
    context_settings={
        "allow_extra_args": True,
        "ignore_unknown_options": True,
    },
)
def uv_run(
    ctx: typer.Context,
    uv_args: Annotated[
        Optional[List[str]],
        typer.Argument(
            help=(
                "Arguments forwarded directly to `uv run ...` on the remote Colab VM. "
                "All arguments after `colab uv run` are passed through."
            ),
        ),
    ] = None,
    session: SessionOption = None,
    tpu: TpuOption = None,
    gpu: GpuOption = None,
    high_mem: HighMemOption = False,
    mount_drive: Annotated[
        Optional[bool],
        typer.Option(
            "--mount-drive/--no-mount-drive",
            help="Mount Google Drive on the Colab VM (default: /content/drive).",
        ),
    ] = None,
    sync_back: Annotated[
        Optional[bool],
        typer.Option(
            "--sync-back/--no-sync-back",
            help="Sync modified/created files back to the local workspace when run finishes.",
        ),
    ] = None,
    remote_dir: Annotated[
        Optional[str],
        typer.Option(
            "--remote-dir",
            help="Remote destination path on Colab (default: /content/<current_dir_name>).",
        ),
    ] = None,
    keep: Annotated[
        bool,
        typer.Option(
            "--keep",
            help="Keep the session VM alive after uv finishes (allows fast incremental re-runs).",
        ),
    ] = False,
    identity: Annotated[
        Optional[str],
        typer.Option(
            "-i",
            "--identity",
            help="SSH identity key forwarded for rsync transfers.",
        ),
    ] = None,
    timeout: Annotated[
        Optional[float],
        typer.Option("--timeout", help="Timeout in seconds for remote execution."),
    ] = None,
):
    """Execute a command via `uv run` in a synced Colab VM workspace."""
    from colab_cli.commands import automation as automation_cmd
    from colab_cli.commands import session as session_cmd
    from colab_cli.common import state

    collected_args: List[str] = list(uv_args or [])
    if ctx.args:
        collected_args.extend(ctx.args)

    folder_name = os.path.basename(os.path.abspath(os.getcwd()))
    dest_remote = remote_dir or f"/content/{folder_name}"

    sess_name = session or f"uv-{uuid.uuid4().hex[:6]}"
    existing = state.get_session(sess_name, ignore_missing_session=True)

    if existing:
        typer.echo(f"[colab] Reusing active session '{sess_name}'.")
        s = existing
    else:
        if not (gpu or tpu):
            if is_stdin_tty():
                chosen_gpu, chosen_tpu, chosen_hm = prompt_accelerator(
                    high_mem_default=high_mem,
                    skip_high_mem_prompt=high_mem,
                )
                gpu = chosen_gpu
                tpu = chosen_tpu
                if not high_mem:
                    high_mem = chosen_hm
            else:
                gpu = None

        session_cmd.new(
            session=sess_name,
            gpu=gpu,
            tpu=tpu,
            high_mem=high_mem,
        )
        s = state.get_session(sess_name)

    stopped = {"done": False}

    def _teardown():
        if not keep and not stopped["done"]:
            stopped["done"] = True
            try:
                session_cmd.stop(session=sess_name)
            except Exception:
                pass

    active_runtime = {"runtime": None}

    def _on_signal(signum, frame):
        if active_runtime["runtime"]:
            try:
                active_runtime["runtime"].interrupt()
            except Exception:
                pass
        _teardown()
        os._exit(128 + signum if isinstance(signum, int) else 130)

    for name in ("SIGHUP", "SIGTERM", "SIGINT"):
        sig = getattr(signal, name, None)
        if sig is not None:
            try:
                signal.signal(sig, _on_signal)
            except (ValueError, OSError):
                pass

    exit_code = 0
    try:
        if mount_drive is None:
            if not existing and is_stdin_tty():
                ans = (
                    input("Mount Google Drive to /content/drive? [y/N]: ")
                    .strip()
                    .lower()
                )
                mount_drive = ans in ("y", "yes")
            else:
                mount_drive = False

        if mount_drive:
            automation_cmd.drivemount(session=sess_name, path="/content/drive")

        if sync_back is None:
            if is_stdin_tty():
                ans = (
                    input(
                        "Sync files back to local workspace on completion? [y/N]: "
                    )
                    .strip()
                    .lower()
                )
                sync_back = ans in ("y", "yes")
            else:
                sync_back = False

        if not get_ignore_file(os.getcwd()):
            typer.echo(
                "[colab] Notice: No .colabignore found. All files (including .git) will be synced. "
                "Run 'colab uv --gitignore' to generate a .colabignore template.",
                err=True,
            )

        sync_local_to_remote(s, os.getcwd(), dest_remote, identity=identity)

        uv_cmd_parts = ["uv", "run"] + collected_args

        exec_code = f"""
import subprocess, sys
p = subprocess.Popen({uv_cmd_parts!r}, cwd={dest_remote!r}, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
for line in p.stdout:
    print(line, end="", flush=True)
if p.wait() != 0:
    raise SystemExit(p.returncode)
"""
        runtime = ColabRuntime(
            s.url,
            s.token,
            session_name=s.name,
            history=state.history,
        )
        active_runtime["runtime"] = runtime
        try:
            outputs = runtime.execute_code(
                exec_code,
                output_hook=_make_run_output_hook(),
                timeout=timeout,
            )
            exit_code = _exit_code_from_outputs(outputs)
        finally:
            active_runtime["runtime"] = None
            runtime.stop()

        if sync_back:
            sync_remote_to_local(s, dest_remote, os.getcwd(), identity=identity)

        if keep:
            typer.echo(f"[colab] Session kept: '{sess_name}'. Re-run with -s {sess_name} --keep")

    finally:
        _teardown()

    if exit_code != 0:
        raise typer.Exit(code=exit_code)


def register(app: typer.Typer):
    app.add_typer(uv_app)

