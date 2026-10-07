"""Local source/query registration, with no video access or automatic declarations."""

import base64
import hashlib
import html
from importlib.resources import files

from gamingcreator.application.benchmark_plan_draft import validate_draft
from gamingcreator.application.benchmark_preparation import canonical_json
from gamingcreator.ui.benchmark_review import STYLE


def render_plan_editor(draft: dict[str, object]) -> str:
    encoded = base64.b64encode(canonical_json(validate_draft(draft))).decode("ascii")
    script = (
        "const initialDraft=JSON.parse(new TextDecoder().decode(Uint8Array.from(atob('"
        + encoded
        + "'),c=>c.charCodeAt(0))));\n"
        + files("gamingcreator.ui").joinpath("static/benchmark-plan.js").read_text(encoding="utf-8")
    )
    digest = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode("ascii")
    policy = f"default-src 'none'; style-src 'unsafe-inline'; script-src 'sha256-{digest}'; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'"
    body = """<header><h1>登记录像和事前查询</h1>
<p>先确定用哪些原录像、分别想找什么，再看模型结果。这里不读取录像、分析项目或模型描述。</p>
<p class="notice">草稿可以留空保存。完整计划仍待原录像核对、原片人工标注和冻结；文件数量及填写声明不证明独立验收通过。</p>
<label>这次计划名称<input id="dataset-id" type="text" autocomplete="off" placeholder="例如：首次玩法检索验收"></label>
<label>继续登记草稿<input id="load-draft" type="file" accept=".json,application/json"></label>
<button id="save-draft" type="button">保存登记草稿</button>
<button id="export-plan" type="button">导出待核对计划</button>
<p id="status" role="status" aria-live="polite">还没有修改登记资料。</p></header>
<section><h2>原录像</h2><p>同一次录制的PV、剪辑或不同版本保持相同录制组；不知道时先留空。用途和是否看过模型结果请明确选择。</p>
<button id="add-source" type="button">增加一段录像</button><div id="source-list"></div></section>
<section><h2>事前查询</h2><p>填写实际想找的玩法。同一需求及其改写使用相同归组；主查询至少需要十个独立可用参考，少例和负例单独评估。</p>
<button id="add-query" type="button">增加一个查询</button><div id="query-list"></div></section>
<section><h2>保存后怎么做</h2><p>登记没完成时保存草稿，关闭前下载，下次在本页载入继续。填齐后导出待核对计划，交给原片标注入口；有人工参考的计划用原片标注页继续，不在这里改来源或查询。</p>
<p>这里不自动填写人工参考、评分、确认或冻结，不调用模型或上传文件。导出成功只说明登记格式有效，录像是否可读及实际来源由后续入口核对。</p></section>"""
    return (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        + '<meta http-equiv="Content-Security-Policy" content="'
        + html.escape(policy, quote=True)
        + '"><title>登记录像和事前查询</title><style>'
        + STYLE
        + "</style></head><body><main>"
        + body
        + "</main><script>"
        + script
        + "</script></body></html>"
    )
