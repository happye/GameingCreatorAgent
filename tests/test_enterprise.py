"""Enterprise basics: roles, brand glossary, separation of duties, review-gated publishing."""

# ruff: noqa: F811
import json
import threading
import urllib.error
import urllib.request
from uuid import uuid4

import pytest
from test_creation_publication import ROOT, finish, payload, rendered, service  # noqa: F401

from gamingcreator.application.enterprise import (
    apply_review,
    audit_as_csv,
    audit_as_json,
    check_brand,
    merge_audit_rows,
    publish_blockers,
    review_events_as_audit,
    validate_team,
)
from gamingcreator.ui import package_jobs

PROJECT = "artifacts/project"

TEAM = {
    "members": [
        {"name": "老板", "role": "owner"},
        {"name": "小编", "role": "editor"},
        {"name": "审核员", "role": "reviewer"},
        {"name": "访客", "role": "viewer"},
    ],
    "brandTerms": {"required": ["代号Atom"], "forbidden": ["外挂"]},
    "reviewRequired": True,
}


def test_team_validation_and_brand_checks():
    team = validate_team(TEAM)
    for bad in (
        {**TEAM, "members": [{"name": "小编", "role": "editor"}]},
        {
            **TEAM,
            "members": [{"name": "老板", "role": "owner"}, {"name": "老板", "role": "editor"}],
        },
        {**TEAM, "members": [{"name": "老板", "role": "god"}]},
        {**TEAM, "extra": 1},
    ):
        with pytest.raises(ValueError):
            validate_team(bad)
    assert check_brand(team, {"标题": "代号Atom新版本", "简介": "", "标签": ""}) == []
    assert check_brand(team, {"标题": "新版本外挂", "简介": "", "标签": ""}) == [
        "缺少必须出现的品牌词“代号Atom”",
        "标题含禁用词“外挂”",
    ]


def test_review_roles_and_separation_of_duties():
    team = validate_team(TEAM)
    with pytest.raises(PermissionError):
        apply_review(team, None, "访客", "submit", "", [], "t0")
    record = apply_review(team, None, "小编", "submit", "请审", [], "t1")
    with pytest.raises(PermissionError):
        apply_review(team, record, "小编", "approve", "", [], "t2")
    with pytest.raises(ValueError):
        apply_review(team, record, "审核员", "approve", "", ["标题含禁用词“外挂”"], "t2")
    with pytest.raises(ValueError):
        apply_review(team, record, "审核员", "reject", "  ", [], "t2")
    rejected = apply_review(team, record, "审核员", "reject", "标题太长", [], "t3")
    resubmitted = apply_review(team, rejected, "小编", "submit", "已改", [], "t4")
    approved = apply_review(team, resubmitted, "老板", "approve", "可以", [], "t5")
    assert approved["state"] == "approved"
    assert [e["action"] for e in approved["events"]] == ["submit", "reject", "submit", "approve"]


def test_approval_is_rechecked_against_the_current_team():
    team = validate_team(TEAM)
    record = {"state": "pending", "submittedBy": "小编", "events": []}
    approved = apply_review(team, record, "审核员", "approve", "", [], "t")
    assert publish_blockers(team, approved, []) == []
    assert publish_blockers(team, record, []) and publish_blockers(team, None, [])
    demoted = validate_team(
        {**TEAM, "members": [m for m in TEAM["members"] if m["name"] != "审核员"]}
    )
    assert "不再是审核员" in publish_blockers(demoted, approved, [])[0]
    assert "品牌词" in publish_blockers(team, approved, ["标题含禁用词“新版本”"])[0]
    assert publish_blockers(None, None, []) == []


def make_package(jobs, render, monkeypatch, title, index=0):
    pub_req = payload(jobs, render)
    pub_req["title"] = title
    pub_id = jobs.submit("publication", pub_req)["jobId"]
    assert finish(jobs, pub_id)["status"] == "completed"
    snap = jobs.publication(pub_id)
    profile = package_jobs.profiles()["profiles"][index]
    for kind in ("video", "cover"):
        profile["Fields"][kind]["width"] //= 10
        profile["Fields"][kind]["height"] //= 10
        for key in ("width", "height"):
            profile["Fields"][kind][key] += profile["Fields"][kind][key] % 2
    original = package_jobs.encode

    async def encode(repository, *args):
        return await original(ROOT, *args)

    monkeypatch.setattr(package_jobs, "encode", encode)
    job = jobs.submit(
        "package",
        dict(
            requestId=uuid4().hex,
            publicationJobId=pub_id,
            expectedPublicationReceiptSha256=snap["publicationReceiptSha256"],
            profile=profile,
        ),
    )["jobId"]
    assert finish(jobs, job)["status"] == "completed"
    return job


def test_real_package_review_gates_sandbox_publish(rendered, monkeypatch):
    jobs, render = rendered
    good = make_package(jobs, render, monkeypatch, "代号Atom 新版本")
    from gamingcreator.ui.server import create_server

    server = create_server("127.0.0.1", 0, jobs.repository)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"

    def post(path, body):
        req = urllib.request.Request(
            base + path, json.dumps(body).encode(), {"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read())

    try:
        with pytest.raises(urllib.error.HTTPError):
            post("/api/enterprise/team", {"projectId": PROJECT, "team": TEAM, "actor": "小编"})
        post("/api/enterprise/team", {"projectId": PROJECT, "team": TEAM, "actor": "老板"})
        with pytest.raises(urllib.error.HTTPError) as gated:
            post("/api/creation/publish", {"packageJobId": good, "target": "sandbox"})
        assert "审核" in json.loads(gated.value.read())["message"]
        post(
            "/api/enterprise/review",
            {"packageJobId": good, "actor": "小编", "action": "submit", "comment": ""},
        )
        approved = post(
            "/api/enterprise/review",
            {"packageJobId": good, "actor": "审核员", "action": "approve", "comment": "ok"},
        )
        assert approved["state"] == "approved"
        assert (
            post("/api/creation/publish", {"packageJobId": good, "target": "sandbox"})["state"]
            == "submitted"
        )
        with urllib.request.urlopen(
            f"{base}/api/enterprise/review?packageJobId={good}"
        ) as response:
            assert json.loads(response.read())["review"]["state"] == "approved"
        with urllib.request.urlopen(
            f"{base}/api/enterprise/audit?projectId={PROJECT}&format=json"
        ) as response:
            audit = json.loads(response.read())
            assert audit["schemaVersion"] == "enterprise-audit-v1"
            assert any(row.get("kind") == "review" for row in audit["rows"])
            assert all(row.get("actorSelfReported") for row in audit["rows"] if row.get("actor"))
        # A glossary change after approval makes the old approval insufficient.
        stricter = {**TEAM, "brandTerms": {"required": ["代号Atom"], "forbidden": ["新版本"]}}
        post("/api/enterprise/team", {"projectId": PROJECT, "team": stricter, "actor": "老板"})
        with pytest.raises(urllib.error.HTTPError) as stale:
            post("/api/creation/publish", {"packageJobId": good, "target": "sandbox"})
        assert "品牌词" in json.loads(stale.value.read())["message"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_audit_helpers_mark_self_reported_names():
    record = {
        "state": "approved",
        "events": [
            {
                "actor": "小编",
                "role": "editor",
                "action": "submit",
                "comment": "",
                "brandIssues": [],
                "at": "t1",
            },
            {
                "actor": "审核员",
                "role": "reviewer",
                "action": "approve",
                "comment": "ok",
                "brandIssues": [],
                "at": "t2",
            },
        ],
    }
    rows = review_events_as_audit("proj", "p" * 32, record)
    assert rows[-1]["state"] == "approved" and rows[0]["state"] is None
    assert all(row["actorSelfReported"] is True for row in rows)
    assert "不是登录账号" in audit_as_json(rows)
    csv_text = audit_as_csv(rows)
    assert "actorSelfReported" in csv_text.splitlines()[0]
    assert "true" in csv_text
    merged = merge_audit_rows(rows, rows)
    assert len(merged) == len(rows)


def test_per_project_teams_and_audit_export(service):
    other = "artifacts/other"
    (service.repository / other).mkdir(parents=True)
    (service.repository / other / "timeline.sqlite3").touch()
    a = service.set_team(PROJECT, TEAM, "老板")
    b_team = {
        **TEAM,
        "members": [
            {"name": "甲", "role": "owner"},
            {"name": "乙", "role": "editor"},
        ],
        "brandTerms": {"required": ["别的游戏"], "forbidden": []},
        "reviewRequired": False,
    }
    b = service.set_team(other, b_team, "甲")
    assert service.team(PROJECT)["brandTerms"]["required"] == ["代号Atom"]
    assert service.team(other)["brandTerms"]["required"] == ["别的游戏"]
    assert a["reviewRequired"] and not b["reviewRequired"]
    # Legacy global file is still readable when the project file is absent.
    legacy_project = "artifacts/legacy"
    (service.repository / legacy_project).mkdir(parents=True)
    (service.repository / legacy_project / "timeline.sqlite3").touch()
    service.save(service.root / "enterprise-team.json", validate_team(TEAM))
    assert service.team(legacy_project)["members"][0]["name"] == "老板"
    rows = service.audit_rows(PROJECT)
    assert any(row["kind"] == "team_change" and row["actorSelfReported"] for row in rows)
    body, name, mime = service.export_audit(PROJECT, "json")
    assert name.endswith(".json") and "enterprise-audit-v1" in body and "不是登录账号" in body
    csv_body, csv_name, csv_mime = service.export_audit(PROJECT, "csv")
    assert csv_name.endswith(".csv") and "actorSelfReported" in csv_body
