from __future__ import annotations

import tomllib
from pathlib import Path


def test_default_dependencies_do_not_require_vnstock() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text())

    default_dependencies = pyproject["project"]["dependencies"]
    optional_dependencies = pyproject["project"]["optional-dependencies"]

    assert not any(dependency.startswith("vnstock") for dependency in default_dependencies)
    assert "vnstock" not in optional_dependencies
    all_dependencies = default_dependencies + [dep for group in optional_dependencies.values() for dep in group]
    assert not any(dep.lower().startswith(("vnstock", "vnai")) for dep in all_dependencies)
