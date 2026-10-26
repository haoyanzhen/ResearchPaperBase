import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location(
    "architecture", ROOT / "scripts/check_architecture.py"
)
assert spec and spec.loader
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


@pytest.mark.parametrize(
    ("path", "source"),
    [
        ("rpb/modules/project/domain/model.py", "from sqlalchemy import Table"),
        ("rpb/modules/project/domain/model.py", "from ..application import commands"),
        ("rpb/modules/project/application/use_case.py", "from rpb.adapters import database"),
        (
            "rpb/modules/project/application/use_case.py",
            "from rpb.modules.review.domain import model",
        ),
        ("rpb/knowledge/read.py", "from rpb.agents import generate"),
        ("rpb/api/routes.py", "from rpb.modules.project.domain import model"),
        ("rpb/api/routes.py", "import archive.maybe_useful"),
        ("rpb/modules/project/domain/model.py", "__import__('sqlalchemy')"),
    ],
)
def test_forbidden_dependencies(path, source):
    assert checker.violations(path, source)


@pytest.mark.parametrize(
    ("path", "source"),
    [
        ("rpb/modules/project/domain/model.py", "from dataclasses import dataclass"),
        ("rpb/modules/project/application/use_case.py", "from ..domain import model"),
        ("rpb/bootstrap/api.py", "from rpb.adapters import database"),
        ("rpb/agents/service.py", "from rpb.knowledge import ports"),
    ],
)
def test_allowed_dependencies(path, source):
    assert not checker.violations(path, source)


def test_actual_import_graph():
    checker.main()


@pytest.mark.parametrize("target", ["rpb.adapters", "rpb.bootstrap"])
@pytest.mark.parametrize(
    "form", ["import {target}", "from {parent} import {leaf}", "from {target} import service"]
)
def test_application_rejects_package_and_member_imports(target, form):
    parent, leaf = target.rsplit(".", 1)
    source = form.format(target=target, parent=parent, leaf=leaf)
    assert checker.violations("rpb/modules/project/application/use_case.py", source)


@pytest.mark.parametrize("target", ["rpb.agents", "rpb.modules", "rpb.api"])
@pytest.mark.parametrize(
    "form", ["import {target}", "from {parent} import {leaf}", "from {target} import service"]
)
def test_knowledge_rejects_reverse_package_imports(target, form):
    parent, leaf = target.rsplit(".", 1)
    assert checker.violations(
        "rpb/knowledge/read.py", form.format(target=target, parent=parent, leaf=leaf)
    )


@pytest.mark.parametrize(
    "source",
    [
        "import rpb.modules.review.application.ports",
        "from rpb.modules.review.application import ports",
        "from rpb.modules.review.application.ports import ReadReview",
    ],
)
def test_public_port_package_and_members_allowed(source):
    assert not checker.violations("rpb/modules/project/application/use_case.py", source)


@pytest.mark.parametrize(
    "source",
    [
        "from rpb.modules.review.application import ports_private",
        "import rpb.modules.review.application.ports_private",
    ],
)
def test_similarly_named_private_packages_still_rejected(source):
    assert checker.violations("rpb/modules/project/application/use_case.py", source)


@pytest.mark.parametrize("dependency", ["fastapi", "sqlalchemy", "psycopg", "uvicorn"])
@pytest.mark.parametrize("form", ["import {dependency}", "from {dependency} import Client"])
def test_application_rejects_http_and_storage_libraries(dependency, form):
    assert checker.violations(
        "rpb/modules/project/application/use_case.py", form.format(dependency=dependency)
    )
