"""Explicitly resumed, persistent serial queues over existing package jobs."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from gamingcreator.domain.errors import AppError
from gamingcreator.domain.platform_profile import profile_digest, validate_profile
from gamingcreator.infrastructure.local_files import read_bounded, write_exclusive_text
from gamingcreator.infrastructure.writer_lock import ProjectWriterLock
from gamingcreator.ui import package_jobs

SCHEMA = "package-batch-v1"
TERMINAL = {"completed", "failed", "cancelled"}


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def identity(value: Any) -> str:
    from gamingcreator.ui.creation_jobs import identity as validate

    return validate(value)


@contextmanager
def locked(directory: Path) -> Iterator[None]:
    lock = ProjectWriterLock(directory)
    for attempt in range(500):
        try:
            lock.acquire()
            break
        except AppError as error:
            if error.code != "storage.writer_busy" or attempt == 499:
                raise
            time.sleep(0.01)
    try:
        yield
    finally:
        lock.close()


class PackageBatches:
    def __init__(self, jobs: Any) -> None:
        self.jobs = jobs
        self.root = jobs.safe(jobs.root / "batches")
        self.root.mkdir(exist_ok=True)
        self.registration = jobs.safe(self.root / "registration")
        self.registration.mkdir(exist_ok=True)

    def directory(self, batch_id: str) -> Path:
        path = self.jobs.safe(self.root / identity(batch_id))
        if not path.is_dir():
            raise ValueError("Unknown package batch")
        return cast(Path, path)

    def request(self, directory: Path) -> dict[str, Any]:
        stored = json.loads(read_bounded(self.jobs.safe(directory / "request.json")))
        if stored["schemaVersion"] != SCHEMA or digest(stored["request"]) != stored["sha256"]:
            raise ValueError("Package batch request changed")
        return dict(stored["request"])

    def read(self, directory: Path) -> dict[str, Any]:
        request = self.request(directory)
        stored = self.jobs.read(directory / "state.json")
        if (
            stored["schemaVersion"] != "package-batch-state-v1"
            or digest(stored["state"]) != stored["sha256"]
        ):
            raise ValueError("Package batch state changed")
        state = stored["state"]
        if state["schemaVersion"] != SCHEMA or state["requestSha256"] != digest(request):
            raise ValueError("Package batch state identity changed")
        if state["batchId"] != directory.name:
            raise ValueError("Package batch identity changed")
        return cast(dict[str, Any], state)

    def save(self, directory: Path, state: dict[str, Any]) -> None:
        state["updatedAt"] = time.time()
        self.jobs.save(
            directory / "state.json",
            {"schemaVersion": "package-batch-state-v1", "state": state, "sha256": digest(state)},
        )

    def validate(self, value: dict[str, Any]) -> None:
        expected = {
            "requestId",
            "projectId",
            "publicationJobId",
            "expectedPublicationReceiptSha256",
            "profiles",
        }
        if not isinstance(value, dict) or set(value) != expected:
            raise ValueError("Expected complete package batch fields")
        identity(value["requestId"])
        identity(value["publicationJobId"])
        self.jobs.project(value["projectId"])
        profiles = value["profiles"]
        if not isinstance(profiles, list) or not 1 <= len(profiles) <= 4:
            raise ValueError("Select one to four profiles")
        for profile in profiles:
            validate_profile(profile)
        if len({p["Platform"] for p in profiles}) != len(profiles):
            raise ValueError("Duplicate platform")
        parent, _, _ = package_jobs.parent(self.jobs, value)
        if parent["projectId"] != value["projectId"]:
            raise ValueError("Publication belongs to another project")

    def submit(self, value: dict[str, Any]) -> dict[str, Any]:
        self.validate(value)
        batch_id = identity(value["requestId"])
        directory = self.jobs.safe(self.root / batch_id)
        created = False
        with locked(self.registration):
            if directory.exists():
                if self.request(directory) != value:
                    raise ValueError("Batch request ID already has different content")
            else:
                target = directory
                directory = self.jobs.safe(self.root / ("pending-" + uuid4().hex))
                directory.mkdir()
                for name in ("owner", "state-lock"):
                    (directory / name).mkdir()
                write_exclusive_text(
                    directory / "request.json",
                    json.dumps(
                        {"schemaVersion": SCHEMA, "request": value, "sha256": digest(value)},
                        ensure_ascii=False,
                    ),
                )
                state = {
                    "schemaVersion": SCHEMA,
                    "requestSha256": digest(value),
                    "batchId": batch_id,
                    **{
                        k: value[k]
                        for k in (
                            "projectId",
                            "publicationJobId",
                            "expectedPublicationReceiptSha256",
                        )
                    },
                    "status": "pending",
                    "cancelRequested": False,
                    "items": [
                        {
                            "profile": p,
                            "profileSha256": profile_digest(p),
                            "jobId": None,
                            "status": "pending",
                            "error": None,
                            "attempt": 1,
                            "childRequestId": uuid4().hex,
                            "history": [],
                        }
                        for p in value["profiles"]
                    ],
                }
                self.save(directory, state)
                directory.rename(target)
                directory = target
                created = True
        if created:
            self.start(directory)
        return self.get(batch_id, value["projectId"])

    def get(self, batch_id: str, project_id: str) -> dict[str, Any]:
        self.jobs.project(project_id)
        directory = self.directory(batch_id)
        with locked(directory / "state-lock"):
            state = self.read(directory)
            if state["projectId"] != project_id:
                raise ValueError("Batch belongs to another project")
            if state["status"] not in TERMINAL:
                owner = ProjectWriterLock(directory / "owner")
                try:
                    owner.acquire()
                except AppError as error:
                    if error.code != "storage.writer_busy":
                        raise
                else:
                    owner.close()
                    state["status"] = "interrupted"
            return state

    def catalog(self, project_id: str, publication_id: str) -> dict[str, Any]:
        self.jobs.project(project_id)
        identity(publication_id)
        rows = []
        errors = []
        for directory in sorted(self.root.iterdir()):
            if len(directory.name) != 32 or not directory.is_dir():
                continue
            try:
                state = (
                    self.get(directory.name, project_id)
                    if self.read(directory)["projectId"] == project_id
                    else None
                )
                if state and state["publicationJobId"] == publication_id:
                    rows.append(state)
            except (ValueError, OSError, KeyError, TypeError, AppError) as error:
                errors.append({"batchId": directory.name, "message": str(error)})
        return {"batches": rows, "errors": errors}

    def cancel(self, batch_id: str, project_id: str) -> dict[str, Any]:
        self.get(batch_id, project_id)
        directory = self.directory(batch_id)
        with locked(directory / "state-lock"):
            state = self.read(directory)
            if state["status"] not in TERMINAL:
                state.update(cancelRequested=True, status="cancelled")
                self.save(directory, state)
        return self.get(batch_id, project_id)

    def resume(self, batch_id: str, project_id: str) -> dict[str, Any]:
        snapshot = self.get(batch_id, project_id)
        if snapshot["status"] not in {"interrupted", "cancelled"}:
            return snapshot
        directory = self.directory(batch_id)
        self.validate(self.request(directory))
        self.start(directory, resume=True)
        return self.get(batch_id, project_id)

    def start(self, directory: Path, resume: bool = False) -> None:
        owner = ProjectWriterLock(directory / "owner")
        try:
            owner.acquire()
        except AppError as error:
            if error.code == "storage.writer_busy":
                return
            raise
        try:
            with locked(directory / "state-lock"):
                state = self.read(directory)
                if resume:
                    state["cancelRequested"] = False
                state["status"] = "running"
                self.save(directory, state)
            thread = threading.Thread(target=self.run, args=(directory, owner), daemon=True)
            self.jobs.threads.append(thread)
            thread.start()
        except BaseException:
            owner.close()
            raise

    def child_request(self, state: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
        return {
            "requestId": item["childRequestId"],
            "profile": item["profile"],
            "publicationJobId": state["publicationJobId"],
            "expectedPublicationReceiptSha256": state["expectedPublicationReceiptSha256"],
        }

    def reusable(self, state: dict[str, Any], item: dict[str, Any]) -> str | None:
        for directory in sorted(self.jobs.jobs.iterdir()):
            if not directory.is_dir() or not (directory / "request.json").exists():
                continue
            stored = self.jobs.read(directory / "request.json")
            request = stored.get("request", {})
            if (
                request.get("publicationJobId") != state["publicationJobId"]
                or request.get("expectedPublicationReceiptSha256")
                != state["expectedPublicationReceiptSha256"]
                or request.get("profile") != item["profile"]
            ):
                continue
            child = self.jobs.get(directory.name)
            if (
                child["kind"] == "package"
                and child["projectId"] == state["projectId"]
                and child["status"] in {"completed", "pending", "running"}
            ):
                return str(directory.name)
        return None

    def bind(self, directory: Path, index: int) -> str | None:
        publication = self.request(directory)["publicationJobId"]
        gate = self.jobs.safe(self.root / ("publication-" + identity(publication)))
        gate.mkdir(exist_ok=True)
        with locked(gate), locked(directory / "state-lock"):
            state = self.read(directory)
            if state["cancelRequested"]:
                return None
            item = state["items"][index]
            if not item["jobId"]:
                registration = self.jobs.safe(self.jobs.root / (item["childRequestId"] + ".json"))
                if registration.exists():
                    item["jobId"] = self.jobs.read(registration)["jobId"]
                    self.save(directory, state)
            if item["jobId"]:
                child = self.jobs.get(item["jobId"])
                if child["status"] == "interrupted":
                    item["history"].append(
                        {
                            k: item[k]
                            for k in ("jobId", "childRequestId", "attempt", "status", "error")
                        }
                    )
                    item.update(
                        jobId=None,
                        childRequestId=uuid4().hex,
                        attempt=item["attempt"] + 1,
                        status="pending",
                        error=None,
                    )
                    self.save(directory, state)
                else:
                    return str(item["jobId"])
            job_id = self.reusable(state, item)
            if job_id is None:
                # Persist intent before submit; a crash reuses precisely this request ID.
                self.save(directory, state)
                job_id = self.jobs.submit("package", self.child_request(state, item))["jobId"]
            item.update(jobId=job_id, status="running")
            self.save(directory, state)
            return str(job_id)

    def wait_child(self, directory: Path, index: int, job_id: str) -> None:
        while True:
            child = self.jobs.get(job_id)
            with locked(directory / "state-lock"):
                state = self.read(directory)
                item = state["items"][index]
                item.update(status=child["status"], error=child.get("error"))
                self.save(directory, state)
            if child["status"] not in {"pending", "running"}:
                return
            time.sleep(0.25)

    def run(self, directory: Path, owner: ProjectWriterLock) -> None:
        try:
            count = len(self.request(directory)["profiles"])
            for index in range(count):
                with locked(directory / "state-lock"):
                    state = self.read(directory)
                    if state["cancelRequested"]:
                        return
                    item = state["items"][index]
                    if item["status"] == "failed":
                        continue
                job_id = self.bind(directory, index)
                if job_id is None:
                    return
                self.wait_child(directory, index, job_id)
            with locked(directory / "state-lock"):
                state = self.read(directory)
                if not state["cancelRequested"]:
                    statuses = {item["status"] for item in state["items"]}
                    state["status"] = (
                        "completed"
                        if statuses == {"completed"}
                        else "interrupted"
                        if "interrupted" in statuses
                        else "failed"
                    )
                self.save(directory, state)
        except Exception as error:
            with locked(directory / "state-lock"):
                state = self.read(directory)
                if not state["cancelRequested"]:
                    state.update(status="interrupted", error={"message": str(error)})
                self.save(directory, state)
        finally:
            owner.close()
