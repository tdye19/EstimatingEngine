"""Regression guard for the 'missing import in models/__init__.py' class of bug.

The Project model carries relationships that reference child models by
string name (e.g. `relationship("SubBidPackage", ...)`). SQLAlchemy
resolves those strings against its class registry at mapper-configure
time. If a child class is never imported before configure_mappers()
runs, resolution fails with InvalidRequestError — which is exactly how
DELETE-cascade commit broke main's alembic / script boot path.

These tests would have caught that bug at test-collection time:

  * `configure_mappers()` is forced to run against only the imports
    that `apex.backend.models` provides — no FastAPI router chain, no
    side-effect wiring. If any Project.* relationship target isn't
    reachable through the package __init__.py, this raises.

  * Every child model referenced by a `Project.*` relationship that
    uses `back_populates="project"` is confirmed importable from
    `apex.backend.models` by attribute lookup.
"""

from __future__ import annotations

import importlib

from sqlalchemy.orm import configure_mappers


def test_project_relationships_configure_cleanly():
    """Force full mapper configuration using only the package's declared
    public surface. Fails fast if any relationship target string doesn't
    resolve because its class was never imported."""
    # Reload to ensure we test the module state the package itself declares,
    # not leftover side-effects from a prior FastAPI import in the same process.
    models_pkg = importlib.import_module("apex.backend.models")
    importlib.reload(models_pkg)
    # configure_mappers raises InvalidRequestError if any string-named
    # relationship target is unresolved.
    configure_mappers()


def test_every_project_relationship_target_is_exported():
    """Enumerate every class named by `Project.*` relationships and assert
    it is importable via `apex.backend.models`. This guards against a
    future relationship being added with a target class that isn't wired
    into __init__.py — which is the exact shape of the SubBidPackage
    bug this file exists to prevent."""
    from apex.backend.models import Project

    models_pkg = importlib.import_module("apex.backend.models")
    pkg_symbols = set(dir(models_pkg))

    missing: list[str] = []
    for rel in Project.__mapper__.relationships:
        target_cls = rel.mapper.class_
        name = target_cls.__name__
        if name not in pkg_symbols:
            missing.append(f"{rel.key} → {name}")

    assert not missing, (
        "Project relationship target(s) not importable from "
        "apex.backend.models — add to models/__init__.py so SQLAlchemy "
        f"can resolve them at mapper-configure time: {missing}"
    )


def test_sub_bid_package_specifically_importable():
    """Regression pin for the exact bug that prompted this file."""
    from apex.backend.models import SubBidPackage  # must not raise

    assert SubBidPackage.__name__ == "SubBidPackage"
    assert SubBidPackage.__tablename__ == "sub_bid_packages"
