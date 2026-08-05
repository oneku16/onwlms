"""Mechanical checks for modular-monolith dependency direction."""

import ast
from pathlib import Path

SOURCE_ROOT = Path(__file__).parents[2] / "src"
LAYERS = {"domain", "application", "infrastructure", "presentation"}
FRAMEWORK_MODULES = {
    "alembic",
    "asyncpg",
    "fastapi",
    "httpx",
    "jwt",
    "mcp",
    "sqlalchemy",
    "starlette",
}


def _imports(path: Path) -> list[str]:
    """Return absolute import roots and module paths from one Python file."""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    values: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            values.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            values.append(node.module)
    return values


def _feature_and_layer(path: Path) -> tuple[str, str] | None:
    """Return a feature/layer pair for files following the module convention."""

    relative = path.relative_to(SOURCE_ROOT)
    if len(relative.parts) < 3 or relative.parts[1] not in LAYERS:
        return None
    return relative.parts[0], relative.parts[1]


def test_domain_and_application_layers_do_not_depend_on_adapters() -> None:
    violations: list[str] = []
    for path in SOURCE_ROOT.rglob("*.py"):
        location = _feature_and_layer(path)
        if location is None:
            continue
        _, layer = location
        for imported in _imports(path):
            parts = imported.split(".")
            if layer in {"domain", "application"} and any(
                part in {"infrastructure", "presentation"} for part in parts
            ):
                violations.append(f"{path}: inward layer imports {imported}")
            if layer == "domain" and parts[0] in FRAMEWORK_MODULES:
                violations.append(f"{path}: domain imports framework {imported}")
    assert violations == []


def test_cross_module_imports_never_reach_private_adapters() -> None:
    violations: list[str] = []
    features = {
        path.name
        for path in SOURCE_ROOT.iterdir()
        if path.is_dir() and any((path / layer).exists() for layer in LAYERS)
    }
    for path in SOURCE_ROOT.rglob("*.py"):
        location = _feature_and_layer(path)
        if location is None:
            continue
        feature, _ = location
        for imported in _imports(path):
            parts = imported.split(".")
            if not parts or parts[0] not in features or parts[0] == feature:
                continue
            if any(part in {"infrastructure", "presentation"} for part in parts):
                violations.append(f"{path}: cross-module private import {imported}")
    assert violations == []
