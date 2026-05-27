from __future__ import annotations

import fnmatch
import os
from pathlib import Path

CODE_MAP_NAME = "CODE_MAP.md"
IGNORE_FILE = Path(".codex") / "code_map_ignore"


def find_repo_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for path in (current, *current.parents):
        if (path / ".git").exists():
            return path
    return current


def load_ignore_patterns(root: Path) -> list[str]:
    ignore_path = root / IGNORE_FILE
    if not ignore_path.exists():
        return []

    patterns: list[str] = []
    for line in ignore_path.read_text(encoding="utf-8").splitlines():
        pattern = line.strip()
        if not pattern or pattern.startswith("#"):
            continue
        patterns.append(pattern.replace("\\", "/"))
    return patterns


def path_to_posix(path: Path) -> str:
    return path.as_posix()


def matches_dir_pattern(path: str, pattern: str) -> bool:
    name = pattern.rstrip("/")
    if "/" not in name:
        return name in path.split("/")
    return path == name or path.startswith(f"{name}/")


def matches_pattern(path: str, pattern: str, *, is_dir: bool) -> bool:
    if pattern.endswith("/"):
        return matches_dir_pattern(path, pattern)

    if pattern.endswith("/**"):
        prefix = pattern[:-3].rstrip("/")
        return path == prefix or path.startswith(f"{prefix}/")

    basename = path.rsplit("/", 1)[-1]
    if any(char in pattern for char in "*?["):
        if "/" in pattern:
            return fnmatch.fnmatch(path, pattern)
        return fnmatch.fnmatch(basename, pattern)

    if "/" in pattern:
        return path == pattern or (is_dir and path.startswith(f"{pattern}/"))

    parts = path.split("/")
    return basename == pattern or pattern in parts


def is_ignored(path: str, patterns: list[str], *, is_dir: bool) -> bool:
    return any(matches_pattern(path, pattern, is_dir=is_dir) for pattern in patterns)


def iter_visible_files(root: Path) -> list[str]:
    patterns = load_ignore_patterns(root)
    visible: list[str] = []

    for current_dir, dirnames, filenames in os.walk(root):
        current_path = Path(current_dir)
        rel_dir = current_path.relative_to(root)

        kept_dirs: list[str] = []
        for dirname in sorted(dirnames):
            rel = path_to_posix(rel_dir / dirname) if rel_dir != Path(".") else dirname
            if not is_ignored(rel, patterns, is_dir=True):
                kept_dirs.append(dirname)
        dirnames[:] = kept_dirs

        for filename in sorted(filenames):
            rel_path = rel_dir / filename if rel_dir != Path(".") else Path(filename)
            rel = path_to_posix(rel_path)
            if rel == CODE_MAP_NAME:
                continue
            if not is_ignored(rel, patterns, is_dir=False):
                visible.append(rel)

    return sorted(visible)


def insert_path(tree: dict[str, dict], parts: list[str]) -> None:
    current = tree
    for part in parts:
        current = current.setdefault(part, {})


def render_tree(paths: list[str]) -> str:
    tree: dict[str, dict] = {}
    for path in paths:
        insert_path(tree, path.split("/"))

    lines = ["."]

    def walk(node: dict[str, dict], prefix: str = "") -> None:
        items = sorted(node.items(), key=lambda item: (bool(item[1]), item[0].lower()))
        for index, (name, child) in enumerate(items):
            is_last = index == len(items) - 1
            connector = "`-- " if is_last else "|-- "
            display = f"{name}/" if child else name
            lines.append(f"{prefix}{connector}{display}")
            if child:
                walk(child, f"{prefix}{'    ' if is_last else '|   '}")

    walk(tree)
    return "\n".join(lines)


def render_code_map(root: Path) -> str:
    paths = iter_visible_files(root)
    return f"{render_tree(paths)}\n"


def write_code_map(root: Path | None = None) -> bool:
    repo_root = find_repo_root(root)
    code_map_path = repo_root / CODE_MAP_NAME
    content = render_code_map(repo_root)
    if code_map_path.exists() and code_map_path.read_text(encoding="utf-8") == content:
        return False
    code_map_path.write_text(content, encoding="utf-8")
    return True


def main() -> int:
    write_code_map()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
