from unittest.mock import patch
import pytest
from typer.testing import CliRunner

from colab_cli.cli import app
from colab_cli.state import SessionState

runner = CliRunner()


def _mock_session(name="test-uv"):
    return SessionState(
        name=name,
        token="tok123",
        url="https://colab.research.google.com/tun/m/test",
        endpoint="ep123",
    )


@pytest.fixture(autouse=True)
def dict_backed_store(mock_common_state):
    sessions = {}
    mock_common_state.store.get.side_effect = sessions.get
    mock_common_state.store.add.side_effect = lambda s: sessions.__setitem__(s.name, s)
    return sessions


def test_uv_gitignore_flag(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    res = runner.invoke(app, ["uv", "--gitignore"])
    assert res.exit_code == 0
    assert (tmp_path / ".colabignore").exists()


@patch("colab_cli.commands.uv.sync_local_to_remote", return_value=True)
@patch("colab_cli.commands.uv.sync_remote_to_local", return_value=True)
@patch("colab_cli.commands.uv.ColabRuntime")
@patch("colab_cli.commands.session.stop")
@patch("colab_cli.commands.session.new")
def test_uv_run_reuses_existing_session(
    mock_new, mock_stop, mock_runtime_cls, mock_sync_down, mock_sync_up, monkeypatch
):
    from colab_cli.common import state

    state.store.add(_mock_session("existing-sess"))

    res = runner.invoke(
        app,
        ["uv", "run", "-s", "existing-sess", "--no-mount-drive", "--no-sync-back", "--keep", "pytest"],
    )

    assert res.exit_code == 0
    # Should reuse existing session and NOT call new
    mock_new.assert_not_called()
    # --keep was passed, so stop should NOT be called
    mock_stop.assert_not_called()


@patch("colab_cli.commands.uv.sync_local_to_remote", return_value=True)
@patch("colab_cli.commands.uv.sync_remote_to_local", return_value=True)
@patch("colab_cli.commands.uv.ColabRuntime")
@patch("colab_cli.commands.session.stop")
@patch("colab_cli.commands.session.new")
def test_uv_run_creates_and_stops_by_default(
    mock_new, mock_stop, mock_runtime_cls, mock_sync_down, mock_sync_up
):
    from colab_cli.common import state

    def fake_new(**kwargs):
        name = kwargs.get("session") or "new-sess"
        state.store.add(_mock_session(name))

    mock_new.side_effect = fake_new

    res = runner.invoke(
        app,
        ["uv", "run", "--gpu", "T4", "--no-mount-drive", "--no-sync-back", "train.py"],
    )

    assert res.exit_code == 0
    mock_new.assert_called_once()
    # By default (without --keep), session is stopped
    mock_stop.assert_called_once()


@patch("colab_cli.commands.automation.drivemount")
@patch("colab_cli.commands.uv.sync_local_to_remote", return_value=True)
@patch("colab_cli.commands.uv.sync_remote_to_local", return_value=True)
@patch("colab_cli.commands.uv.ColabRuntime")
@patch("colab_cli.commands.session.stop")
@patch("colab_cli.commands.session.new")
def test_uv_run_mount_drive(
    mock_new, mock_stop, mock_runtime_cls, mock_sync_down, mock_sync_up, mock_drivemount
):
    from colab_cli.common import state

    state.store.add(_mock_session("drive-sess"))

    res = runner.invoke(
        app,
        ["uv", "run", "-s", "drive-sess", "--mount-drive", "--no-sync-back", "--keep", "run.py"],
    )

    assert res.exit_code == 0
    mock_drivemount.assert_called_once_with(session="drive-sess", path="/content/drive")


@patch("colab_cli.commands.uv.sync_local_to_remote", return_value=True)
@patch("colab_cli.commands.uv.sync_remote_to_local", return_value=True)
@patch("colab_cli.commands.uv.ColabRuntime")
@patch("colab_cli.commands.session.stop")
@patch("colab_cli.commands.session.new")
def test_uv_run_propagates_remote_exit_code(
    mock_new, mock_stop, mock_runtime_cls, mock_sync_down, mock_sync_up
):
    from colab_cli.common import state

    state.store.add(_mock_session("exit-code-sess"))
    mock_instance = mock_runtime_cls.return_value
    mock_instance.execute_code.return_value = [
        {"output_type": "error", "ename": "SystemExit", "evalue": "42"}
    ]

    res = runner.invoke(
        app,
        ["uv", "run", "-s", "exit-code-sess", "--no-mount-drive", "--no-sync-back", "--keep", "fail.py"],
    )

    assert res.exit_code == 42


@patch("colab_cli.commands.uv.prompt_accelerator")
@patch("colab_cli.commands.uv.is_stdin_tty", return_value=True)
@patch("colab_cli.commands.uv.sync_local_to_remote", return_value=True)
@patch("colab_cli.commands.uv.ColabRuntime")
@patch("colab_cli.commands.session.stop")
@patch("colab_cli.commands.session.new")
def test_uv_run_preserves_high_mem_flag_without_overwriting(
    mock_new, mock_stop, mock_runtime, mock_sync_up, mock_tty, mock_prompt
):
    from colab_cli.common import state

    def fake_new(**kwargs):
        name = kwargs.get("session") or "hm-sess"
        state.store.add(_mock_session(name))

    mock_new.side_effect = fake_new
    # prompt returns choice with high_mem=False if prompted naively, but prompt should be passed skip_high_mem
    mock_prompt.return_value = (None, None, False)

    res = runner.invoke(
        app,
        ["uv", "run", "--high-mem", "--no-mount-drive", "--no-sync-back", "--keep", "main.py"],
    )

    assert res.exit_code == 0
    # verify high_mem was passed as True to session_cmd.new
    _, kwargs = mock_new.call_args
    assert kwargs.get("high_mem") is True


