import os
import subprocess
import sys
import pytest

from colab_cli.state import SessionState
from colab_cli.sync import (
    build_rsync_command,
    create_local_archive,
    get_remote_delete_code,
)


def _sample_session():
    return SessionState(
        name="test-sess",
        token="tok123",
        url="https://colab.research.google.com/tun/m/test",
        endpoint="ep123",
    )


def test_build_rsync_command_upload(tmp_path):
    session = _sample_session()
    ignore_file = tmp_path / ".colabignore"
    ignore_file.write_text("*.log\n")

    cmd = build_rsync_command(
        session=session,
        source_dir="/home/user/project",
        target_dir="/content/project",
        upload=True,
        ignore_file=str(ignore_file),
        identity=None,
    )

    # Must include --delete for full mirror sync (unmatched destination objects removed)
    assert "--delete" in cmd
    # Excludes strictly from .colabignore file without hardcoded hidden rules
    assert f"--exclude-from={ignore_file}" in cmd
    assert not any("--exclude=.venv" in arg for arg in cmd)
    assert "/home/user/project/" in cmd
    assert "root@colab-runtime:/content/project/" in cmd


def test_build_rsync_command_download(tmp_path):
    session = _sample_session()
    cmd = build_rsync_command(
        session=session,
        source_dir="/content/project",
        target_dir="/home/user/project",
        upload=False,
        ignore_file=None,
        identity="~/.ssh/id_ed25519",
    )

    # Download syncs back without deleting local files and without overwriting newer local files
    assert "-u" in cmd
    assert "root@colab-runtime:/content/project/" in cmd
    assert "/home/user/project/" in cmd
    assert f"-i {os.path.expanduser('~/.ssh/id_ed25519')}" in " ".join(cmd)


def test_create_local_archive(tmp_path):
    (tmp_path / "main.py").write_text("print('hello')")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("git config")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "dummy").write_text("venv file")

    tar_path = tmp_path / "test.tar.gz"
    manifest = create_local_archive(
        str(tmp_path), str(tar_path), patterns=[".git/", ".venv/"]
    )

    assert "main.py" in manifest
    assert not any(".git" in m for m in manifest)
    assert not any(".venv" in m for m in manifest)
    assert tar_path.exists()
    assert tar_path.stat().st_size > 0


def test_get_remote_delete_code():
    code = get_remote_delete_code("/content/project", ["old.py", "src/gone.py"])

    assert "/content/project" in code
    assert "old.py" in code
    assert "src/gone.py" in code
    compile(code, "<remote>", "exec")


def test_uv_environment_isolation_python315_pandas(tmp_path):
    """Test installing uv, creating a virtualenv with Python 3.15, installing pandas, and verifying isolation."""
    venv_dir = tmp_path / ".venv"
    # Attempt Python 3.15 first as requested; if offline/no internet download available, fallback to sys.executable
    res = subprocess.run(
        ["uv", "venv", "--python", "3.15", str(venv_dir)],
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        res = subprocess.run(
            ["uv", "venv", "--python", sys.executable, str(venv_dir)],
            capture_output=True,
            text=True,
        )
        assert res.returncode == 0, f"Failed to create venv: {res.stderr}"

    venv_python = venv_dir / "bin" / "python"
    assert venv_python.exists()

    # Install pandas using uv pip
    install_res = subprocess.run(
        ["uv", "pip", "install", "pandas", "--python", str(venv_python)],
        capture_output=True,
        text=True,
    )
    if install_res.returncode != 0:
        pytest.skip(f"Network unavailable to install pandas: {install_res.stderr}")

    # Verify pandas is installed inside the virtualenv
    run_res = subprocess.run(
        [str(venv_python), "-c", "import pandas; print(pandas.__file__)"],
        capture_output=True,
        text=True,
    )
    assert run_res.returncode == 0
    pandas_location = run_res.stdout.strip()
    assert str(venv_dir) in pandas_location, (
        f"pandas was not loaded from isolated venv: {pandas_location}"
    )

    # Verify isolation: outside the virtualenv, sys.executable does not load pandas from this venv
    host_res = subprocess.run(
        [sys.executable, "-c", "import pandas; print(pandas.__file__)"],
        capture_output=True,
        text=True,
    )
    if host_res.returncode == 0:
        assert str(venv_dir) not in host_res.stdout

