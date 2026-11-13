# ruff: noqa: F811 -- pytest fixtures are imported for discovery, then injected by name.

from pathlib import Path

import pytest
from test_creation_jobs import service  # noqa: F401

from gamingcreator.domain.errors import AppError
from gamingcreator.ui.creation_jobs import CreationJobs
from gamingcreator.ui.creation_works_http import works_get, works_post

PROJECT = "artifacts/project"
WORK_ID = "a" * 32


def _other_project(jobs: CreationJobs) -> str:
    project = "artifacts/other"
    directory = jobs.repository / project
    directory.mkdir(parents=True)
    (directory / "timeline.sqlite3").touch()
    return project


def test_get_does_not_create_work_storage(service: CreationJobs) -> None:
    assert works_get(service, PROJECT) == {"works": []}
    with pytest.raises(ValueError):
        works_get(service, PROJECT, WORK_ID)
    assert not (service.root / "works").exists()


def test_post_is_idempotent_and_get_reads_same_record(service: CreationJobs) -> None:
    request = {"projectId": PROJECT, "requestId": WORK_ID}
    response = works_post(service, request)
    path = service.root / "works" / f"{WORK_ID}.json"
    original = path.read_bytes()
    assert works_post(service, request) == response
    assert works_get(service, PROJECT, WORK_ID) == response
    assert path.read_bytes() == original
    assert works_get(service, PROJECT) == {"works": [response["work"]]}


def test_cross_project_read_and_recreate_are_refused(service: CreationJobs) -> None:
    works_post(service, {"projectId": PROJECT, "requestId": WORK_ID})
    other = _other_project(service)
    with pytest.raises(ValueError):
        works_get(service, other, WORK_ID)
    with pytest.raises(ValueError):
        works_post(service, {"projectId": other, "requestId": WORK_ID})


@pytest.mark.parametrize(
    "value",
    [
        None,
        {},
        {"projectId": PROJECT},
        {"projectId": PROJECT, "requestId": WORK_ID, "workId": WORK_ID},
        {"projectId": PROJECT, "workId": WORK_ID},
        {"projectId": PROJECT, "requestId": ""},
        {"projectId": PROJECT, "requestId": " "},
        {"projectId": PROJECT, "requestId": 123},
        {"projectId": "", "requestId": WORK_ID},
    ],
)
def test_post_refuses_unknown_or_invalid_fields(service: CreationJobs, value: object) -> None:
    with pytest.raises(ValueError):
        works_post(service, value)
    assert not (service.root / "works").exists()


@pytest.mark.parametrize("project", ["unknown", "../outside", None, 123])
def test_get_requires_discovered_project(service: CreationJobs, project: object) -> None:
    with pytest.raises(AppError):
        works_get(service, project)
    assert not (service.root / "works").exists()


def test_post_requires_discovered_project_even_if_directory_exists(service: CreationJobs) -> None:
    directory = service.repository / "artifacts/undiscovered"
    directory.mkdir(parents=True)
    with pytest.raises(AppError):
        works_post(service, {"projectId": "artifacts/undiscovered", "requestId": WORK_ID})
    assert not (service.root / "works").exists()


def test_catalog_filters_projects_but_refuses_any_corruption(service: CreationJobs) -> None:
    first = works_post(service, {"projectId": PROJECT, "requestId": WORK_ID})
    other = _other_project(service)
    other_id = "b" * 32
    works_post(service, {"projectId": other, "requestId": other_id})
    assert works_get(service, PROJECT) == {"works": [first["work"]]}
    path: Path = service.root / "works" / f"{other_id}.json"
    path.write_bytes(b"{")
    with pytest.raises(ValueError):
        works_get(service, PROJECT)
