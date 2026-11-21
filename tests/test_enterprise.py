"""Enterprise basics: roles, brand glossary, separation of duties, review-gated publishing."""

# ruff: noqa: F811
import asyncio
import json
import threading
import urllib.error
import urllib.request
from uuid import uuid4

import pytest
from test_creation_publication import ROOT, finish, payload, rendered, service  # noqa: F401
from test_overlay_assets import png

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
from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure.overlay_assets import OverlayAssetLibrary
from gamingcreator.ui import brand_templates, package_jobs

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
    other_project = jobs.repository / "artifacts" / "other-team"
    other_project.mkdir()
    (other_project / "timeline.sqlite3").touch()
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
            f"{base}/api/enterprise/review?packageJobId={good}&projectId={PROJECT}"
        ) as response:
            context = json.loads(response.read())
            assert context["review"]["state"] == "approved"
            assert context["team"]["reviewRequired"]
            assert context["brandIssues"] == context["blockers"] == []
        with pytest.raises(urllib.error.HTTPError) as wrong_project:
            urllib.request.urlopen(
                f"{base}/api/enterprise/review?packageJobId={good}&projectId=artifacts/other-team"
            )
        assert wrong_project.value.code == 404
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
        with urllib.request.urlopen(
            f"{base}/api/enterprise/review?packageJobId={good}&projectId={PROJECT}"
        ) as response:
            context = json.loads(response.read())
            assert context["review"]["state"] == "approved"
            assert any("新版本" in issue for issue in context["brandIssues"])
            assert context["blockers"]
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


def test_brand_copy_template_is_project_scoped_and_owner_updated(service):
    other = "artifacts/other"
    (service.repository / other).mkdir(parents=True)
    (service.repository / other / "timeline.sqlite3").touch()
    service.set_team(PROJECT, TEAM, "老板")
    copy = {"title": "  代号Atom · 团队栏目 ", "description": "", "tags": ["实况"]}
    request = {
        "projectId": PROJECT,
        "actor": "老板",
        "expectedTemplateSha256": None,
        "template": copy,
    }
    with pytest.raises(AppError, match="负责人"):
        brand_templates.save_template(service, {**request, "actor": "小编"})
    saved = brand_templates.save_template(service, request)
    assert saved["template"]["title"] == copy["title"].strip()
    assert brand_templates.get_template(service, PROJECT) == saved
    assert brand_templates.get_template(service, other) == {
        "template": None,
        "revisionSha256": None,
    }
    assert brand_templates.save_template(service, request) == saved

    changed = {**request, "template": {**copy, "title": "代号Atom · 新栏目"}}
    with pytest.raises(AppError, match="已更新"):
        brand_templates.save_template(service, changed)
    with pytest.raises(ValueError, match="标签"):
        brand_templates.save_template(
            service, {**request, "template": {**copy, "tags": ["甲，乙"]}}
        )
    current = brand_templates.save_template(
        service, {**changed, "expectedTemplateSha256": saved["revisionSha256"]}
    )
    assert current["template"]["title"] == changed["template"]["title"]
    assert current["revisionSha256"] != saved["revisionSha256"]
    restored = brand_templates.save_template(
        service, {**request, "expectedTemplateSha256": current["revisionSha256"]}
    )
    assert restored["revisionSha256"] != saved["revisionSha256"]
    with pytest.raises(AppError, match="已更新"):
        brand_templates.save_template(
            service, {**changed, "expectedTemplateSha256": saved["revisionSha256"]}
        )

    cleared = brand_templates.save_template(
        service,
        {
            **request,
            "expectedTemplateSha256": restored["revisionSha256"],
            "template": {"title": "", "description": "", "tags": []},
        },
    )
    assert cleared["template"] is None and cleared["revisionSha256"]
    assert brand_templates.get_template(service, PROJECT) == cleared
    with pytest.raises(AppError, match="已更新"):
        brand_templates.save_template(service, request)


def test_brand_copy_template_rejects_damaged_snapshot(service):
    service.set_team(PROJECT, TEAM, "老板")
    brand_templates.save_template(
        service,
        {
            "projectId": PROJECT,
            "actor": "老板",
            "expectedTemplateSha256": None,
            "template": {"title": "", "description": "团队栏目", "tags": []},
        },
    )
    (path,) = (service.root / "enterprise" / "brand-copy").glob("*.json")
    stored = service.read(path)
    stored["template"]["description"] = "损坏的数据"
    service.save(path, stored)
    with pytest.raises(AppError, match="已损坏"):
        brand_templates.get_template(service, PROJECT)


def test_brand_copy_template_cannot_write_against_a_damaged_team(service):
    service.set_team(PROJECT, TEAM, "老板")
    (path,) = (service.root / "enterprise" / "teams").glob("*.json")
    service.save(path, {"members": [{}]})
    with pytest.raises(AppError, match="团队设置已损坏"):
        brand_templates.save_template(
            service,
            {
                "projectId": PROJECT,
                "actor": "老板",
                "expectedTemplateSha256": None,
                "template": {"title": "", "description": "栏目", "tags": []},
            },
        )
    assert brand_templates.get_template(service, PROJECT)["revisionSha256"] is None


def test_visual_brand_template_verifies_asset_history_and_can_clear_damaged_assets(
    service, monkeypatch
):
    tool = ROOT / ".tools/ffmpeg/bin/ffmpeg.exe"
    if not tool.is_file():
        pytest.skip("Pinned FFmpeg is unavailable")
    service.set_team(PROJECT, TEAM, "老板")
    library = OverlayAssetLibrary(service.repository)
    monkeypatch.setattr(library, "_tool", lambda: str(tool))
    asset = asyncio.run(library.register_png(png(), "brand.png"))
    row = {
        "overlayId": "b" * 32,
        "kind": "image",
        "startFrame": 30,
        "endFrame": 60,
        "x": 100,
        "y": 200,
        "width": 600,
        "fadeInFrames": 2,
        "fadeOutFrames": 3,
        "assetId": asset.asset_id,
        "assetReceiptSha256": asset.receipt_sha256,
    }
    template = {
        "timelineFrames": 60,
        "overlays": {"schemaVersion": "creation-overlays-v1", "items": [row]},
    }
    request = {
        "projectId": PROJECT,
        "actor": "老板",
        "expectedTemplateSha256": None,
        "template": template,
    }
    with pytest.raises(ValueError, match="duration"):
        brand_templates.save_template(
            service, {**request, "template": {**template, "timelineFrames": 40}}, "visual"
        )
    result = brand_templates.save_template(service, request, "visual")
    assert result["template"]["assets"][0]["assetReceiptSha256"] == asset.receipt_sha256
    assert result["template"]["overlays"] == template["overlays"]
    assert brand_templates.get_template(service, PROJECT, "visual") == result
    assert brand_templates.get_template(service, PROJECT)["template"] is None
    with pytest.raises(AppError, match="已更新"):
        brand_templates.save_template(service, {**request, "template": None}, "visual")

    asset.path.write_bytes(png(3, 2))
    damaged = brand_templates.get_template(service, PROJECT, "visual")
    assert damaged["template"]["assets"] == [] and damaged["template"]["assetIssue"]
    assert damaged["revisionSha256"] == result["revisionSha256"]
    with pytest.raises(ValueError, match="changed"):
        brand_templates.save_template(service, request, "visual")
    cleared = brand_templates.save_template(
        service,
        {
            **request,
            "template": None,
            "expectedTemplateSha256": damaged["revisionSha256"],
        },
        "visual",
    )
    assert cleared["template"] is None and cleared["revisionSha256"] != damaged["revisionSha256"]
