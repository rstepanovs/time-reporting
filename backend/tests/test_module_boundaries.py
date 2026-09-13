"""Feature modules may reach each other only through their public contracts."""

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

import time_reporting.modules

MODULES_ROOT = Path(time_reporting.modules.__path__[0])
# Files directly in modules/ (e.g. the registry composition root) are exempt.
MODULE_FILES = sorted(MODULES_ROOT.glob("*/**/*.py"))
# Public submodules besides ``contracts``: (module, submodule).
EXTRA_PUBLIC = {("auth", "dependencies")}


def _imported_names(tree: ast.Module) -> Iterator[str]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                yield f"<relative import at line {node.lineno}>"
            else:
                yield from (f"{node.module}.{alias.name}" for alias in node.names)


def find_violations(path: Path) -> list[str]:
    own_module = path.relative_to(MODULES_ROOT).parts[0]
    violations = []
    for name in _imported_names(ast.parse(path.read_text(encoding="utf-8"))):
        if name.startswith("<relative"):
            violations.append(name)
            continue
        parts = name.split(".")
        if parts[:2] != ["time_reporting", "modules"] or len(parts) < 3:
            continue
        module = parts[2]
        submodule = parts[3] if len(parts) > 3 else None
        if module == own_module or submodule == "contracts" or (module, submodule) in EXTRA_PUBLIC:
            continue
        violations.append(name)
    return violations


def test_module_files_are_discovered() -> None:
    assert MODULE_FILES


@pytest.mark.parametrize("path", MODULE_FILES, ids=lambda p: str(p.relative_to(MODULES_ROOT)))
def test_module_imports_only_public_contracts(path: Path) -> None:
    assert find_violations(path) == []


def test_violations_are_detected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "auth" / "service.py"
    source.parent.mkdir()
    source.write_text(
        "from time_reporting.modules.users.contracts import UserDTO\n"
        "from time_reporting.modules.users import models\n"
        "import time_reporting.modules.users.repository\n"
        "from .jwt import create_access_token\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(__name__ + ".MODULES_ROOT", tmp_path)

    assert find_violations(source) == [
        "time_reporting.modules.users.models",
        "time_reporting.modules.users.repository",
        "<relative import at line 4>",
    ]
