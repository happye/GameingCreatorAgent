"""Enterprise basics: roles, brand glossary, separation of duties, review-gated publishing."""

# ruff: noqa: F811
import json
import threading
import urllib.error
import urllib.request
from uuid import uuid4

import pytest
from test_creation_publication import ROOT, finish, payload, rendered, service  # noqa: F401

from gamingcreator.application.enterprise import apply_review, check_brand, validate_team
from gamingcreator.ui import package_jobs

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


def make_package(jobs, render, monkeypatch, title):
    pub_req = payload(jobs, render)
    pub_req["title"] = title
    pub_id = jobs.submit("publication", pub_req)["jobId"]
    assert finish(jobs, pub_id)["status"] == "completed"
    snap = jobs.publication(pub_id)
    profile = package_jobs.profiles()["profiles"][0]
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
            post("/api/enterprise/team", {"team": TEAM, "actor": "小编"})
        post("/api/enterprise/team", {"team": TEAM, "actor": "老板"})
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
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
