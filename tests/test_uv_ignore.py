import os
from colab_cli.ignore import (
    generate_ignore_file,
    get_ignore_file,
    load_ignore_patterns,
    should_ignore,
)


def test_generate_ignore_file_creates_file(tmp_path):
    path = generate_ignore_file(str(tmp_path), filename=".colabignore")
    assert os.path.isfile(path)
    content = open(path).read()
    assert ".git" in content
    assert ".venv" in content
    assert "__pycache__" in content


def test_generate_ignore_file_idempotent(tmp_path):
    ignore_path = tmp_path / ".colabignore"
    ignore_path.write_text("my_custom_folder/\n")

    generate_ignore_file(str(tmp_path), filename=".colabignore")
    content = ignore_path.read_text()
    assert "my_custom_folder/" in content
    assert ".git/" in content
    assert ".venv/" in content


def test_get_ignore_file_only_colabignore(tmp_path):
    assert get_ignore_file(str(tmp_path)) is None

    # .gitignore alone is not picked up (no hidden fallback)
    git_ignore = tmp_path / ".gitignore"
    git_ignore.write_text("build/\n")
    assert get_ignore_file(str(tmp_path)) is None

    colab_ignore = tmp_path / ".colabignore"
    colab_ignore.write_text("dist/\n")
    assert get_ignore_file(str(tmp_path)) == str(colab_ignore)


def test_load_ignore_patterns_no_hidden_rules(tmp_path):
    colab_ignore = tmp_path / ".colabignore"
    colab_ignore.write_text("# comment\n\nnode_modules/\n*.log\n")

    patterns = load_ignore_patterns(str(tmp_path))
    assert patterns == ["node_modules/", "*.log"]
    # No hidden or inferred rules (e.g. .git/ is NOT injected)
    assert ".git/" not in patterns
    assert not any(".git" in p for p in patterns)


def test_should_ignore():
    patterns = [".git/", ".venv/", "__pycache__/", "*.pyc", "experiments/"]

    assert should_ignore(".git", patterns)
    assert should_ignore(".git/config", patterns)
    assert should_ignore(".venv/bin/python", patterns)
    assert should_ignore("src/__pycache__/mod.cpython-312.pyc", patterns)
    assert should_ignore("test.pyc", patterns)
    assert should_ignore("experiments/out.csv", patterns)

    assert not should_ignore("src/main.py", patterns)
    assert not should_ignore("pyproject.toml", patterns)
    assert not should_ignore("README.md", patterns)

