"""Acceptance workflow page links readiness read-only and never claims pass."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src" / "gamingcreator" / "ui" / "static"


def test_benchmark_workflow_static_links_readiness_without_pass_claims() -> None:
    js = (ROOT / "benchmark-workflow.js").read_text(encoding="utf-8")
    html = (ROOT / "benchmark-workflow.html").read_text(encoding="utf-8")
    css = (ROOT / "benchmark-workflow.css").read_text(encoding="utf-8")
    assert "/api/acceptance-readiness" in js
    assert "acceptance-readiness-v1" in js
    assert "function assertReadinessInert" in js
    assert "function fillBindReadiness" in js
    assert 'readiness.id="bind-readiness"' in js or "bind-readiness" in js
    assert "formalAcceptancePassed !== false" in js
    assert 'formalAcceptanceStatus === "passed"' in js
    assert "不等于已验收或 F006 通过" in js
    assert "不宣称通过" in js or "不宣称验收通过" in html
    assert "验收就绪" in html
    assert "不等于已验收／F006／人评通过" in html or "不等于已验收" in html
    assert ".bind-readiness" in css
    # Must not instruct UI to celebrate pass as success state for readiness.
    assert "formalAcceptancePassed===true" not in js.replace(" ", "")
    assert "humanEvalPassed===true" not in js.replace(" ", "")
