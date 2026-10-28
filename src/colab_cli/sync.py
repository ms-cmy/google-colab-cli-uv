import os
import shlex
import subprocess
import tarfile
from typing import List, Optional

import typer

from colab_cli.ignore import get_ignore_file, load_ignore_patterns, should_ignore
from colab_cli.state import SessionState

echo = typer.echo


def build_rsync_command(
    session: SessionState,
    source_dir: str,
    target_dir: str,
    upload: bool = True,
    ignore_file: Optional[str] = None,
    identity: Optional[str] = None,
) -> List[str]:
    """Builds the rsync command executed over colab ssh proxy-mode."""
    from colab_cli.commands import ssh as ssh_cmd

    proxy_cmd = ssh_cmd._proxy_command(session, identity)
    ssh_opts = ssh_cmd._ssh_base_args(proxy_cmd, identity)

    rsh_str = shlex.join(ssh_opts)
    cmd = ["rsync", "-az", "-e", rsh_str]

    if upload:
        # Full mirror sync behavior matching gcloud storage rsync --delete-unmatched-destination-objects -r
        cmd.append("--delete")
    else:
        # Do not overwrite newer local files when syncing back
        cmd.append("-u")

    if ignore_file and os.path.isfile(ignore_file):
        cmd.append(f"--exclude-from={ignore_file}")

    src = source_dir if source_dir.endswith("/") else f"{source_dir}/"
    dst = target_dir if target_dir.endswith("/") else f"{target_dir}/"

    if upload:
        cmd.extend([src, f"root@colab-runtime:{dst}"])
    else:
        cmd.extend([f"root@colab-runtime:{src}", dst])

    return cmd


def create_local_archive(
    source_dir: str, target_tar_path: str, patterns: List[str]
) -> List[str]:
    """Creates a .tar.gz archive of source_dir excluding patterns, returns list of included relative paths."""
    manifest: List[str] = []
    source_dir = os.path.abspath(source_dir)

    with tarfile.open(target_tar_path, "w:gz") as tar:
        for root, dirs, files in os.walk(source_dir):
            rel_root = os.path.relpath(root, source_dir)
            if rel_root == ".":
                rel_root = ""

            dirs[:] = [
                d
                for d in dirs
                if not should_ignore(
                    os.path.join(rel_root, d) if rel_root else d, patterns
                )
            ]

            for file in files:
                rel_path = os.path.join(rel_root, file) if rel_root else file
                if not should_ignore(rel_path, patterns):
                    full_path = os.path.join(root, file)
                    tar.add(full_path, arcname=rel_path)
                    manifest.append(rel_path)

    return manifest


def get_remote_list_code(remote_dir: str) -> str:
    """Remote code printing a JSON list of all file paths relative to remote_dir."""
    return (
        "import json, os\n"
        f"d = {remote_dir!r}\n"
        "print(json.dumps([os.path.relpath(os.path.join(r, f), d)\n"
        "                  for r, _, fs in os.walk(d) for f in fs]))\n"
    )


def get_remote_delete_code(remote_dir: str, relpaths: List[str]) -> str:
    """Remote code deleting exactly relpaths (and any directories left empty)."""
    return (
        "import os\n"
        f"d = {remote_dir!r}\n"
        f"for p in {list(relpaths)!r}:\n"
        "    try:\n"
        "        os.remove(os.path.join(d, p))\n"
        "    except OSError:\n"
        "        pass\n"
        "for r, _, _ in os.walk(d, topdown=False):\n"
        "    if r != d and not os.listdir(r):\n"
        "        os.rmdir(r)\n"
    )


def get_remote_archive_code(remote_dir: str, relpaths: List[str], tar_out: str) -> str:
    """Remote code archiving exactly relpaths of remote_dir into tar_out."""
    return (
        "import os, tarfile\n"
        f"d = {remote_dir!r}\n"
        f"with tarfile.open({tar_out!r}, 'w:gz') as t:\n"
        f"    for p in {list(relpaths)!r}:\n"
        "        t.add(os.path.join(d, p), arcname=p)\n"
    )


def _remote_list_files(runtime, remote_dir: str) -> List[str]:
    """Runs the listing code on the VM and returns the parsed relative paths."""
    import json

    chunks: List[str] = []

    def hook(out, output_image=None):
        if out.get("output_type") == "stream" and out.get("name") != "stderr":
            chunks.append(out.get("text", ""))

    runtime.execute_code(get_remote_list_code(remote_dir), output_hook=hook)
    text = "".join(chunks).strip()
    return json.loads(text.splitlines()[-1]) if text else []


def sync_local_to_remote(
    session: SessionState,
    local_dir: str,
    remote_dir: str,
    identity: Optional[str] = None,
) -> bool:
    """Syncs local_dir to remote_dir. Tries rsync first, falls back to Contents archive sync."""
    ignore_file = get_ignore_file(local_dir)
    patterns = load_ignore_patterns(local_dir)

    try:
        rsync_cmd = build_rsync_command(
            session=session,
            source_dir=local_dir,
            target_dir=remote_dir,
            upload=True,
            ignore_file=ignore_file,
            identity=identity,
        )
        echo("[colab] Syncing workspace with rsync --delete...")
        res = subprocess.run(rsync_cmd, capture_output=True, text=True)
        if res.returncode == 0:
            echo("[colab] Workspace mirror synced successfully.")
            return True
        if res.stderr:
            echo(f"[colab] Warning: rsync error:\n{res.stderr.strip()}", err=True)
    except Exception:
        pass

    echo("[colab] (rsync unavailable, using archive mirror sync fallback)...")
    import tempfile
    from colab_cli.common import state
    from colab_cli.contents import ContentsClient
    from colab_cli.runtime import ColabRuntime

    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tf:
        tar_path = tf.name

    try:
        manifest = create_local_archive(local_dir, tar_path, patterns)
        contents = ContentsClient(session)
        remote_tar = "content/_workspace_upload.tar.gz"
        contents.upload(tar_path, remote_tar)

        runtime = ColabRuntime(
            session.url,
            session.token,
            session_name=session.name,
            history=state.history,
        )
        try:
            runtime.execute_code(f"import os; os.makedirs({remote_dir!r}, exist_ok=True)")
            stale = [
                p
                for p in _remote_list_files(runtime, remote_dir)
                if p not in set(manifest) and not should_ignore(p, patterns)
            ]
            if stale:
                runtime.execute_code(get_remote_delete_code(remote_dir, stale))
            unpack_code = f"""
import os, tarfile
with tarfile.open('/{remote_tar}', 'r:gz') as tar:
    try:
        tar.extractall({remote_dir!r}, filter='data')
    except TypeError:
        tar.extractall({remote_dir!r})
os.remove('/{remote_tar}')
print('[colab] Workspace unpacked and mirror synced.')
"""
            runtime.execute_code(unpack_code)
        finally:
            runtime.stop()
        return True
    finally:
        if os.path.exists(tar_path):
            os.remove(tar_path)


def sync_remote_to_local(
    session: SessionState,
    remote_dir: str,
    local_dir: str,
    identity: Optional[str] = None,
) -> bool:
    """Syncs modified files from remote_dir back to local_dir."""
    ignore_file = get_ignore_file(local_dir)

    try:
        rsync_cmd = build_rsync_command(
            session=session,
            source_dir=remote_dir,
            target_dir=local_dir,
            upload=False,
            ignore_file=ignore_file,
            identity=identity,
        )
        echo("[colab] Syncing files back to local with rsync...")
        res = subprocess.run(rsync_cmd, capture_output=True, text=True)
        if res.returncode == 0:
            echo("[colab] Files synced back successfully.")
            return True
        if res.stderr:
            echo(f"[colab] Warning: rsync error:\n{res.stderr.strip()}", err=True)
    except Exception:
        pass

    echo("[colab] (rsync unavailable, using archive sync back fallback)...")
    import tempfile
    from colab_cli.common import state
    from colab_cli.contents import ContentsClient
    from colab_cli.runtime import ColabRuntime

    patterns = load_ignore_patterns(local_dir)
    runtime = ColabRuntime(
        session.url,
        session.token,
        session_name=session.name,
        history=state.history,
    )
    try:
        files = [
            f
            for f in _remote_list_files(runtime, remote_dir)
            if not should_ignore(f, patterns)
        ]
        runtime.execute_code(
            get_remote_archive_code(
                remote_dir, files, "/content/_workspace_download.tar.gz"
            )
        )
    finally:
        runtime.stop()

    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tf:
        local_tar = tf.name

    try:
        contents = ContentsClient(session)
        contents.download("content/_workspace_download.tar.gz", local_tar)
        with tarfile.open(local_tar, "r:gz") as tar:
            try:
                tar.extractall(local_dir, filter="data")
            except TypeError:
                tar.extractall(local_dir)
        echo(f"[colab] Artifacts extracted to {local_dir}")
        return True
    except Exception as e:
        echo(f"[colab] Warning: sync back fallback failed: {e}", err=True)
        return False
    finally:
        if os.path.exists(local_tar):
            os.remove(local_tar)
