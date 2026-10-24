"""Cross-process at-most-once generation, crash recovery, and new-process typed query."""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path
from typing import cast

import pytest
from fake_vision_transport import FakeVisionTransport
from test_static_observation_generation import (
    ACTORS_CONTENT,
    dispatch,
    prepare,
    static_reply,
    write_authorization,
)
from test_static_observations import create_project, query_document, sha, write_json

from gamingcreator.application.pricing import DEEPSEEK_FLASH_20261004
from gamingcreator.application.providers import CancellationContext
from gamingcreator.application.retrieval import load_searchable_timeline
from gamingcreator.application.static_observation_generation import (
    execute_static_observation_generation,
    loads_static_generation_authorization,
    loads_static_generation_proposal,
)
from gamingcreator.application.static_observations import (
    PublishStatus,
    StaticCollectionArtifact,
)
from gamingcreator.application.storage import StoredTimeline
from gamingcreator.infrastructure.deepseek_static_observations import (
    DeepSeekStaticObservationProvider,
)
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore
from gamingcreator.infrastructure.static_observation_attempts import (
    LEDGER_SQLITE_NAME,
    SqliteStaticGenerationLedger,
)
from gamingcreator.infrastructure.static_observation_store import (
    SqliteStaticObservationStore,
)

RUN_ID = "run-1"
COLLECTION = "look-1"


def repository() -> Path:
    return Path(__file__).resolve().parents[1]


def run_cli(*arguments: str, timeout: float = 180) -> subprocess.CompletedProcess[str]:
    root = repository()
    environment = os.environ | {
        "PYTHONUTF8": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": os.pathsep.join((str(root / "src"), str(root / "tests"))),
    }
    return subprocess.run(
        [sys.executable, "-B", "-m", "gamingcreator", *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=timeout,
        env=environment,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )


def document_out(process: subprocess.CompletedProcess[str]) -> dict[str, object]:
    return cast(dict[str, object], json.loads(process.stdout))


def bootstrap_script(tmp_path: Path) -> Path:
    root = repository()
    script = tmp_path / "dispatch_child.py"
    script.write_text(
        f'''
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(r"{root}")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from fake_vision_transport import FakeVisionTransport
from gamingcreator.infrastructure.http_transport import HttpResponse

LOG = Path(os.environ["STATIC_SEND_LOG"])
CONTENT = os.environ["STATIC_CONTENT"]


class LoggingTransport:
    async def post(self, payload, timeout_seconds):
        del payload, timeout_seconds
        with open(LOG, "a", encoding="utf-8") as stream:
            stream.write("send\\n")
        time.sleep(0.25)
        body = {{
            "id": "chatcmpl-concurrent",
            "model": "deepseek-flash",
            "usage": {{
                "prompt_tokens": 120,
                "completion_tokens": 20,
                "prompt_cache_hit_tokens": 0,
                "prompt_cache_miss_tokens": 120,
                "total_tokens": 140,
            }},
            "choices": [
                {{
                    "finish_reason": "stop",
                    "message": {{"role": "assistant", "content": CONTENT}},
                }}
            ],
        }}
        return HttpResponse(200, json.dumps(body).encode("utf-8"))


import gamingcreator.cli.static_observation_generation as generation

generation.build_vision_transport = lambda: LoggingTransport()
from gamingcreator.cli.main import main

sys.exit(main(sys.argv[1:]))
''',
        encoding="utf-8",
    )
    return script


def child_environment(tmp_path: Path, log: Path) -> dict[str, str]:
    return os.environ | {
        "STATIC_SEND_LOG": str(log),
        "STATIC_CONTENT": ACTORS_CONTENT,
        "PYTHONUTF8": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def dispatch_arguments(project: Path, proposal: Path, authorization: Path) -> list[str]:
    return [
        "dispatch-static-observation-generation",
        "--project",
        str(project),
        "--proposal",
        str(proposal),
        "--authorization",
        str(authorization),
    ]


def protected_hashes() -> dict[str, str]:
    root = repository()
    return {
        str(path): sha(path)
        for path in (
            root / "feature_list.json",
            root / "原片标注记录.json",
            root / "src" / "gamingcreator" / "infrastructure" / "deepseek_vision.py",
            root / "src" / "gamingcreator" / "application" / "static_observations.py",
        )
    }


def test_two_processes_share_one_request_and_never_send_twice(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project, bundle = create_project(tmp_path)
    proposal = tmp_path / "proposal.json"
    prepare(capsys, project, proposal, bundle.images[0].evidence_id)
    authorization = write_authorization(tmp_path / "authorization.json", proposal)
    timeline_hash = sha(project / "timeline.sqlite3")
    before = protected_hashes()
    log = tmp_path / "sends.log"
    script = bootstrap_script(tmp_path)
    environment = child_environment(tmp_path, log)
    command = [
        sys.executable,
        "-B",
        str(script),
        *dispatch_arguments(project, proposal, authorization),
    ]

    first = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env=environment,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    second = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env=environment,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    first_output = first.communicate(timeout=180)
    second_output = second.communicate(timeout=180)
    assert log.read_text(encoding="utf-8").splitlines() == ["send"]
    outcomes = [
        (first.returncode, first_output[0], first_output[1]),
        (second.returncode, second_output[0], second_output[1]),
    ]
    assert all(code in (0, 7) for code, _, _ in outcomes), outcomes
    assert any(code == 0 for code, _, _ in outcomes)
    reports = [json.loads(stdout) for code, stdout, _ in outcomes if code == 0]
    sent_reports = [item for item in reports if item["providerRequestsSent"] == 1]
    assert len(sent_reports) == 1
    assert sent_reports[0]["status"] == "published"
    assert sent_reports[0]["attemptStatus"] == "recorded"
    assert sent_reports[0]["publishStatus"] == "created"
    for item in reports:
        if item is not sent_reports[0]:
            assert item["providerRequestsSent"] == 0
            assert item["status"] == "published"
            assert item["publishStatus"] == "unchanged"
    blocked = [json.loads(stderr) for code, _, stderr in outcomes if code == 7]
    assert all(item["code"] == "static_generation.request_busy" for item in blocked)

    repeated = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=180,
        env=environment,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    assert repeated.returncode == 0, repeated.stderr
    assert document_out(repeated)["providerRequestsSent"] == 0
    assert document_out(repeated)["publishStatus"] == "unchanged"
    assert log.read_text(encoding="utf-8").splitlines() == ["send"]

    query_path = tmp_path / "query.json"
    write_json(query_path, query_document())
    searched = run_cli(
        "search-static-observations",
        "--project",
        str(project),
        "--run",
        RUN_ID,
        "--collection",
        COLLECTION,
        "--input",
        str(query_path),
    )
    assert searched.returncode == 0, searched.stderr
    search = document_out(searched)
    assert search["matchCount"] == 1
    assert search["matches"][0]["evidenceId"] == bundle.images[0].evidence_id
    assert search["matches"][0]["sourceTimeUs"] == 100_000
    assert {support["partId"] for support in search["matches"][0]["supportedAttributes"]} == {
        "hair-1",
        "clothing-1",
        "held-1",
    }
    assert search["visualVerified"] is None
    assert search["humanLabels"] is None
    assert search["qualityGate"] is None
    assert search["f006Passed"] is False
    assert search["f009Passed"] is False
    assert search["f010Passed"] is False

    assert sha(project / "timeline.sqlite3") == timeline_hash
    assert protected_hashes() == before
    attempts = tuple(
        (project / ".static-observation-generation" / "ledger" / "attempts").glob("*.json")
    )
    assert len(attempts) == 1


def publish_with_real_store(project: Path, artifact: StaticCollectionArtifact) -> PublishStatus:
    store = SqliteStaticObservationStore.open(project, read_only=False)
    try:
        return store.publish(artifact)
    finally:
        store.close()


def stored_timeline(project: Path) -> StoredTimeline:
    async def load() -> StoredTimeline:
        store = await SqliteTimelineStore.open(project, read_only=True)
        try:
            return await load_searchable_timeline(store, RUN_ID)
        finally:
            await store.close()

    return asyncio.run(load())


def run_application(
    project: Path,
    proposal_path: Path,
    authorization_path: Path,
    *,
    transport: FakeVisionTransport,
    ledger_hook: object = None,
    publisher_failure: bool = False,
) -> None:
    proposal = loads_static_generation_proposal(proposal_path.read_bytes())
    authorization = loads_static_generation_authorization(authorization_path.read_bytes())
    timeline = stored_timeline(project)
    ledger = SqliteStaticGenerationLedger(project)
    provider = DeepSeekStaticObservationProvider(transport, price_snapshot=DEEPSEEK_FLASH_20261004)
    context = CancellationContext(RUN_ID, 30.0)
    if ledger_hook is not None:
        ledger_hook(ledger)  # type: ignore[operator]

    def publisher(artifact: StaticCollectionArtifact) -> PublishStatus:
        if publisher_failure:
            raise RuntimeError("simulated crash after settlement before publish")
        return publish_with_real_store(project, artifact)

    try:
        asyncio.run(
            execute_static_observation_generation(
                proposal=proposal,
                authorization=authorization,
                timeline=timeline,
                ledger=ledger,
                publisher=publisher,
                provider=provider,
                context=context,
                operation="dispatch",
            )
        )
    finally:
        ledger.close()


def prepare_case(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> tuple[Path, Path, Path, Path]:
    project, bundle = create_project(tmp_path)
    proposal = tmp_path / "proposal.json"
    prepare(capsys, project, proposal, bundle.images[0].evidence_id)
    authorization = write_authorization(tmp_path / "authorization.json", proposal)
    return project, bundle.images[0].path, proposal, authorization


def resume_or_die(
    project: Path, proposal: Path, authorization: Path, *, expected_code: int = 0
) -> dict[str, object]:
    resumed = run_cli(
        "resume-static-observation-generation",
        "--project",
        str(project),
        "--proposal",
        str(proposal),
        "--authorization",
        str(authorization),
    )
    assert resumed.returncode == expected_code, (resumed.returncode, resumed.stderr)
    return document_out(resumed)


def test_crash_before_result_persistence_keeps_planned_unknown_and_never_resends(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project, _, proposal, authorization = prepare_case(tmp_path, capsys)
    transport = FakeVisionTransport([static_reply(ACTORS_CONTENT)])
    log = tmp_path / "sends.log"

    def crash_record(ledger: SqliteStaticGenerationLedger) -> None:
        def boom(*args: object, **kwargs: object) -> None:
            del args, kwargs
            raise RuntimeError("simulated crash after response before result persistence")

        ledger.record_result = boom  # type: ignore[method-assign]

    with pytest.raises(RuntimeError):
        run_application(
            project,
            proposal,
            authorization,
            transport=transport,
            ledger_hook=crash_record,
        )
    assert len(transport.payloads) == 1
    resumed = resume_or_die(project, proposal, authorization, expected_code=7)
    assert resumed["status"] == "unknown"
    assert resumed["providerRequestsSent"] == 0
    assert resumed["chargeStatus"] == "unknown"
    assert resumed["reservationCny"] == "0.416"
    assert not (project / "static-observations.sqlite3").exists()

    script = bootstrap_script(tmp_path)
    environment = child_environment(tmp_path, log)
    blocked = subprocess.run(
        [sys.executable, "-B", str(script), *dispatch_arguments(project, proposal, authorization)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=180,
        env=environment,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    assert blocked.returncode == 7, blocked.stderr
    assert document_out(blocked)["status"] == "unknown"
    assert document_out(blocked)["providerRequestsSent"] == 0
    assert not log.exists() or log.read_text(encoding="utf-8").splitlines() == []


def test_crash_after_result_file_but_before_ledger_settlement_recovers_publish(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project, _, proposal, authorization = prepare_case(tmp_path, capsys)
    transport = FakeVisionTransport([static_reply(ACTORS_CONTENT)])

    def crash_settle(ledger: SqliteStaticGenerationLedger) -> None:
        def boom(*args: object, **kwargs: object) -> None:
            del args, kwargs
            raise RuntimeError("simulated crash between attempt file and ledger row")

        ledger._settle_recorded_row = boom  # type: ignore[method-assign]

    with pytest.raises(RuntimeError):
        run_application(
            project,
            proposal,
            authorization,
            transport=transport,
            ledger_hook=crash_settle,
        )
    assert len(transport.payloads) == 1
    resumed = resume_or_die(project, proposal, authorization)
    assert resumed["status"] == "published"
    assert resumed["providerRequestsSent"] == 0
    assert resumed["publishStatus"] == "created"
    assert resumed["chargeStatus"] == "known"
    store = SqliteStaticObservationStore.open(project, read_only=True)
    try:
        stored = store.load_collection(RUN_ID, COLLECTION)
    finally:
        store.close()
    assert len(stored.package.observations) == 1


def test_crash_after_settlement_before_publish_only_publishes_locally(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project, _image, proposal, authorization = prepare_case(tmp_path, capsys)
    transport = FakeVisionTransport([static_reply(ACTORS_CONTENT)])
    with pytest.raises(RuntimeError):
        run_application(
            project,
            proposal,
            authorization,
            transport=transport,
            publisher_failure=True,
        )
    assert len(transport.payloads) == 1
    assert not (project / "static-observations.sqlite3").exists()
    resumed = resume_or_die(project, proposal, authorization)
    assert resumed["status"] == "published"
    assert resumed["providerRequestsSent"] == 0
    assert resumed["publishStatus"] == "created"
    assert resumed["collectionSha256"] is not None
    assert str(resumed["evidenceId"]).endswith(":image:000000")


def test_crash_after_publish_before_marking_republishes_idempotently(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project, _, proposal, authorization = prepare_case(tmp_path, capsys)
    transport = FakeVisionTransport([static_reply(ACTORS_CONTENT)])

    def crash_mark(ledger: SqliteStaticGenerationLedger) -> None:
        def boom(*args: object, **kwargs: object) -> None:
            del args, kwargs
            raise RuntimeError("simulated crash after publish before ledger mark")

        ledger.mark_published = boom  # type: ignore[method-assign]

    with pytest.raises(RuntimeError):
        run_application(
            project,
            proposal,
            authorization,
            transport=transport,
            ledger_hook=crash_mark,
        )
    assert len(transport.payloads) == 1
    store = SqliteStaticObservationStore.open(project, read_only=True)
    try:
        published = store.load_collection(RUN_ID, COLLECTION)
    finally:
        store.close()
    resumed = resume_or_die(project, proposal, authorization)
    assert resumed["status"] == "published"
    assert resumed["providerRequestsSent"] == 0
    assert resumed["publishStatus"] == "unchanged"
    assert resumed["collectionSha256"] == published.package_sha256


def test_resume_without_any_attempt_never_creates_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project, _, proposal, authorization = prepare_case(tmp_path, capsys)
    resumed = run_cli(
        "resume-static-observation-generation",
        "--project",
        str(project),
        "--proposal",
        str(proposal),
        "--authorization",
        str(authorization),
    )
    assert resumed.returncode == 0, resumed.stderr
    report = document_out(resumed)
    assert report["status"] == "nothing_to_resume"
    assert report["providerRequestsSent"] == 0
    attempts = project / ".static-observation-generation" / "ledger" / "attempts"
    assert not attempts.exists() or not tuple(attempts.glob("*.json"))


def test_dispatch_without_authorization_file_fails_closed_without_sending(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project, bundle = create_project(tmp_path)
    proposal = tmp_path / "proposal.json"
    prepare(capsys, project, proposal, bundle.images[0].evidence_id)
    missing = tmp_path / "missing-authorization.json"
    code, report, stderr = dispatch(capsys, project, proposal, missing)
    assert code == 2
    assert report is None
    assert json.loads(stderr)["code"] == "input.static_generation"
    attempts = project / ".static-observation-generation" / "ledger" / "attempts"
    assert not attempts.exists() or not tuple(attempts.glob("*.json"))
    assert not (project / "static-observations.sqlite3").exists()


def test_authorization_is_required_to_be_immutable_across_a_restart(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project, bundle = create_project(tmp_path)
    proposal = tmp_path / "proposal.json"
    prepare(capsys, project, proposal, bundle.images[0].evidence_id)
    authorization = write_authorization(tmp_path / "authorization.json", proposal)
    document = json.loads(authorization.read_text(encoding="utf-8"))
    document["maxCostCny"] = "0.45"
    authorization.write_text(json.dumps(document), encoding="utf-8")
    resumed = run_cli(
        "resume-static-observation-generation",
        "--project",
        str(project),
        "--proposal",
        str(proposal),
        "--authorization",
        str(authorization),
    )
    assert resumed.returncode != 0
    failure = json.loads(resumed.stderr)
    assert failure["code"] == "static_generation.authorization_hash"


def test_a_tampered_attempt_file_is_not_an_empty_result(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project, _bundle, proposal, authorization = prepare_case(tmp_path, capsys)
    transport = FakeVisionTransport([static_reply(ACTORS_CONTENT)])
    run_application(project, proposal, authorization, transport=transport)
    attempt = next(
        (project / ".static-observation-generation" / "ledger" / "attempts").glob("*.json")
    )
    document = json.loads(attempt.read_text(encoding="utf-8"))
    document["plannedAt"] = "2026-10-24T00:00:00+00:00"
    attempt.write_text(json.dumps(document), encoding="utf-8")
    resumed = run_cli(
        "resume-static-observation-generation",
        "--project",
        str(project),
        "--proposal",
        str(proposal),
        "--authorization",
        str(authorization),
    )
    assert resumed.returncode == 5
    failure = json.loads(resumed.stderr)
    assert failure["code"] == "static_generation.ledger_inconsistent"
    assert attempt.exists()


def test_protected_inputs_and_old_timeline_stay_unchanged(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    before = protected_hashes()
    project, _bundle, proposal, authorization = prepare_case(tmp_path, capsys)
    timeline_hash = sha(project / "timeline.sqlite3")
    transport = FakeVisionTransport([static_reply(ACTORS_CONTENT)])
    run_application(project, proposal, authorization, transport=transport)
    assert sha(project / "timeline.sqlite3") == timeline_hash
    assert protected_hashes() == before


def hard_exit_script(tmp_path: Path) -> Path:
    root = repository()
    script = tmp_path / "hard_exit_child.py"
    script.write_text(
        f'''
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(r"{root}")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from gamingcreator.application.pricing import DEEPSEEK_FLASH_20261004
from gamingcreator.application.providers import CancellationContext
from gamingcreator.application.retrieval import load_searchable_timeline
from gamingcreator.application.static_observation_generation import (
    execute_static_observation_generation,
    loads_static_generation_authorization,
    loads_static_generation_proposal,
)
from gamingcreator.infrastructure.deepseek_static_observations import (
    DeepSeekStaticObservationProvider,
)
from gamingcreator.infrastructure.http_transport import HttpResponse
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore
from gamingcreator.infrastructure.static_observation_attempts import (
    SqliteStaticGenerationLedger,
)
from gamingcreator.infrastructure.static_observation_store import (
    SqliteStaticObservationStore,
)

PROJECT = Path(os.environ["STATIC_PROJECT"])
PROPOSAL = Path(os.environ["STATIC_PROPOSAL"])
AUTHORIZATION = Path(os.environ["STATIC_AUTHORIZATION"])
LOG = Path(os.environ["STATIC_SEND_LOG"])
CONTENT = os.environ["STATIC_CONTENT"]
MODE = os.environ["STATIC_EXIT_MODE"]


class Transport:
    async def post(self, payload, timeout_seconds):
        del payload, timeout_seconds
        with open(LOG, "a", encoding="utf-8") as stream:
            stream.write("send\\n")
        if MODE == "http_exit":
            os._exit(91)
        body = {{
            "id": "chatcmpl-hard-exit",
            "model": "deepseek-flash",
            "usage": {{
                "prompt_tokens": 120,
                "completion_tokens": 20,
                "prompt_cache_hit_tokens": 0,
                "prompt_cache_miss_tokens": 120,
                "total_tokens": 140,
            }},
            "choices": [
                {{
                    "finish_reason": "stop",
                    "message": {{"role": "assistant", "content": CONTENT}},
                }}
            ],
        }}
        return HttpResponse(200, json.dumps(body).encode("utf-8"))


class ExitProvider:
    async def observe(self, request, context):
        del request, context
        os._exit(90)


async def run():
    proposal = loads_static_generation_proposal(PROPOSAL.read_bytes())
    authorization = loads_static_generation_authorization(AUTHORIZATION.read_bytes())
    timeline_store = await SqliteTimelineStore.open(PROJECT, read_only=True)
    try:
        timeline = await load_searchable_timeline(timeline_store, "run-1")
    finally:
        await timeline_store.close()
    ledger = SqliteStaticGenerationLedger(PROJECT)
    if MODE == "settle_exit":
        ledger._settle_recorded_row = lambda *args, **kwargs: os._exit(92)
    if MODE == "mark_exit":
        ledger.mark_published = lambda *args, **kwargs: os._exit(93)

    def publisher(artifact):
        store = SqliteStaticObservationStore.open(PROJECT, read_only=False)
        try:
            return store.publish(artifact)
        finally:
            store.close()

    if MODE == "planned_exit":
        provider = ExitProvider()
    else:
        provider = DeepSeekStaticObservationProvider(
            Transport(), price_snapshot=DEEPSEEK_FLASH_20261004
        )
    await execute_static_observation_generation(
        proposal=proposal,
        authorization=authorization,
        timeline=timeline,
        ledger=ledger,
        publisher=publisher,
        provider=provider,
        context=CancellationContext("run-1", 30.0),
        operation="dispatch",
    )
    ledger.close()
    os._exit(70)


asyncio.run(run())
''',
        encoding="utf-8",
    )
    return script


def ledger_database(project: Path) -> Path:
    return project / ".static-observation-generation" / "ledger" / LEDGER_SQLITE_NAME


def ledger_row(project: Path) -> tuple[object, ...]:
    with closing(sqlite3.connect(ledger_database(project))) as connection:
        row = connection.execute(
            "SELECT status, revision, published, authorization_id FROM generation_attempts"
        ).fetchone()
    assert row is not None
    return tuple(row)


def run_hard_exit(
    project: Path,
    proposal: Path,
    authorization: Path,
    tmp_path: Path,
    mode: str,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ | {
        "STATIC_PROJECT": str(project),
        "STATIC_PROPOSAL": str(proposal),
        "STATIC_AUTHORIZATION": str(authorization),
        "STATIC_SEND_LOG": str(tmp_path / "hard-exit-sends.log"),
        "STATIC_CONTENT": ACTORS_CONTENT,
        "STATIC_EXIT_MODE": mode,
        "PYTHONUTF8": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    return subprocess.run(
        [sys.executable, "-B", str(hard_exit_script(tmp_path))],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=180,
        env=environment,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )


@pytest.mark.parametrize(
    ("mode", "expected_exit"),
    [
        ("planned_exit", 90),
        ("http_exit", 91),
        ("settle_exit", 92),
        ("mark_exit", 93),
    ],
)
def test_hard_process_exit_recovers_in_another_process_without_resend(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    mode: str,
    expected_exit: int,
) -> None:
    project, _bundle, proposal, authorization = prepare_case(tmp_path, capsys)
    result = run_hard_exit(project, proposal, authorization, tmp_path, mode)
    assert result.returncode == expected_exit, (result.returncode, result.stderr)
    send_log = tmp_path / "hard-exit-sends.log"
    expected_sends = [] if mode == "planned_exit" else ["send"]
    assert (
        [] if not send_log.exists() else send_log.read_text(encoding="utf-8").splitlines()
    ) == expected_sends
    attempts = tuple((ledger_database(project).parent / "attempts").glob("*.json"))
    assert len(attempts) == 1
    file_document = json.loads(attempts[0].read_text(encoding="utf-8"))
    row = ledger_row(project)
    assert row[3] == "auth-static-1"
    store_file = project / "static-observations.sqlite3"

    if mode in ("planned_exit", "http_exit"):
        assert file_document["status"] == "planned"
        assert tuple(row[:3]) == ("planned", 1, 0)
        assert not store_file.exists()
        resumed = resume_or_die(project, proposal, authorization, expected_code=7)
        assert resumed["status"] == "unknown"
        assert resumed["providerRequestsSent"] == 0
        assert resumed["chargeStatus"] == "unknown"
        assert resumed["reservationCny"] == "0.416"
        assert not store_file.exists()
        assert ledger_row(project)[:3] == ("planned", 1, 0)
    elif mode == "settle_exit":
        assert file_document["status"] == "recorded"
        assert tuple(row[:3]) == ("planned", 1, 0)
        assert not store_file.exists()
        resumed = resume_or_die(project, proposal, authorization)
        assert resumed["status"] == "published"
        assert resumed["providerRequestsSent"] == 0
        assert resumed["publishStatus"] == "created"
        assert resumed["chargeStatus"] == "known"
        assert store_file.is_file()
        assert ledger_row(project)[:3] == ("recorded", 2, 1)
    else:
        assert file_document["status"] == "recorded"
        assert tuple(row[:3]) == ("recorded", 2, 0)
        assert store_file.is_file()
        store = SqliteStaticObservationStore.open(project, read_only=True)
        try:
            published_sha = store.load_collection(RUN_ID, COLLECTION).package_sha256
        finally:
            store.close()
        resumed = resume_or_die(project, proposal, authorization)
        assert resumed["status"] == "published"
        assert resumed["providerRequestsSent"] == 0
        assert resumed["publishStatus"] == "unchanged"
        assert resumed["collectionSha256"] == published_sha
        assert ledger_row(project)[:3] == ("recorded", 2, 1)
    assert (
        [] if not send_log.exists() else send_log.read_text(encoding="utf-8").splitlines()
    ) == expected_sends
