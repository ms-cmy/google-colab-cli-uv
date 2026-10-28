import os
from pathlib import Path, PurePosixPath
from typing import List, Optional

DEFAULT_IGNORE_PATTERNS = [
    ".git/",
    ".venv/",
    "venv/",
    "__pycache__/",
    "*.pyc",
    ".pytest_cache/",
    ".mypy_cache/",
    ".ruff_cache/",
    ".idea/",
    ".vscode/",
    ".DS_Store",
    "*.tar.gz",
]

GITIGNORE_TEMPLATE = "# Colab CLI & Python defaults\n" + "\n".join(DEFAULT_IGNORE_PATTERNS) + "\n"



def generate_ignore_file(target_dir: str, filename: str = ".colabignore") -> str:
    """Generate or update an ignore file with standard defaults."""
    target_path = os.path.join(target_dir, filename)
    if not os.path.exists(target_path):
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(GITIGNORE_TEMPLATE)
        return target_path

    with open(target_path, "r", encoding="utf-8") as f:
        existing = f.read()

    lines = [line.strip() for line in existing.splitlines()]
    to_add = [
        p
        for p in DEFAULT_IGNORE_PATTERNS
        if p.strip("/") not in [entry.strip("/") for entry in lines]
    ]

    if to_add:
        with open(target_path, "a", encoding="utf-8") as f:
            if not existing.endswith("\n"):
                f.write("\n")
            f.write("# Added by colab uv\n")
            for p in to_add:
                f.write(f"{p}\n")

    return target_path


def get_ignore_file(workspace_dir: str) -> Optional[str]:
    """Finds .colabignore in workspace_dir without inferring or falling back to other files."""
    colab_ignore = os.path.join(workspace_dir, ".colabignore")
    if os.path.isfile(colab_ignore):
        return colab_ignore
    return None


def load_ignore_patterns(workspace_dir: str) -> List[str]:
    """Load ignore patterns strictly from .colabignore without inferring or injecting hidden rules."""
    ignore_file = get_ignore_file(workspace_dir)
    patterns: List[str] = []
    if ignore_file and os.path.isfile(ignore_file):
        with open(ignore_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    patterns.append(line)
    return patterns


def should_ignore(rel_path: str, patterns: List[str]) -> bool:
    """Checks whether rel_path matches any of the ignore patterns using built-in pathlib."""
    path = PurePosixPath(Path(rel_path).as_posix())
    posix_str = path.as_posix().lstrip("/")

    for pattern in patterns:
        pat = pattern.strip()
        if not pat:
            continue

        is_dir_pat = pat.endswith("/")
        clean_pat = pat.rstrip("/").lstrip("/")

        if path.match(clean_pat):
            return True

        if any(
            part == clean_pat or PurePosixPath(part).match(clean_pat)
            for part in path.parts
        ):
            return True

        if is_dir_pat and (
            posix_str == clean_pat or posix_str.startswith(f"{clean_pat}/")
        ):
            return True

    return False
