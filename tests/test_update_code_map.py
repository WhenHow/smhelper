from __future__ import annotations

import importlib.util
from pathlib import Path


def load_update_code_map_module():
    module_path = (
        Path(__file__).resolve().parents[1]
        / ".codex"
        / "scripts"
        / "update_code_map.py"
    )
    spec = importlib.util.spec_from_file_location("update_code_map", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_generate_code_map_uses_real_tree_and_hides_ignored_paths(
    tmp_path: Path,
) -> None:
    write(tmp_path / ".codex" / "code_map_ignore", "tmp/\n*.log\n")
    write(tmp_path / ".env", "SECRET=hidden\n")
    write(tmp_path / "src" / "smhelper" / "__init__.py")
    write(tmp_path / "tmp" / "scratch.py")
    write(tmp_path / "debug.log")
    write(tmp_path / "CODE_MAP.md", "old map")

    module = load_update_code_map_module()
    content = module.render_code_map(tmp_path)

    assert ".env" in content
    assert "SECRET=hidden" not in content
    assert "# CODE_MAP.md" not in content
    assert "自动生成" not in content
    assert "```" not in content
    assert "# local config" not in content
    assert "src/" in content
    assert "__init__.py" in content
    assert "tmp/" not in content
    assert "debug.log" not in content
    assert "-- CODE_MAP.md" not in content


def test_generate_code_map_hides_runtime_data_paths(tmp_path: Path) -> None:
    write(tmp_path / ".codex" / "code_map_ignore", "data/**\n")
    write(tmp_path / "data" / ".gitkeep")
    write(tmp_path / "data" / "auth" / "account-1" / "storage_state.json", "{}")
    write(tmp_path / "src" / "smhelper" / "__init__.py")

    module = load_update_code_map_module()
    content = module.render_code_map(tmp_path)

    assert "src/" in content
    assert "__init__.py" in content
    assert "data/" not in content
    assert "storage_state.json" not in content


def test_write_code_map_is_idempotent(tmp_path: Path) -> None:
    write(tmp_path / ".codex" / "code_map_ignore", "")
    write(tmp_path / "src" / "smhelper" / "__init__.py")

    module = load_update_code_map_module()
    first_changed = module.write_code_map(tmp_path)
    first = (tmp_path / "CODE_MAP.md").read_text(encoding="utf-8")
    second_changed = module.write_code_map(tmp_path)
    second = (tmp_path / "CODE_MAP.md").read_text(encoding="utf-8")

    assert first_changed is True
    assert second_changed is False
    assert second == first
