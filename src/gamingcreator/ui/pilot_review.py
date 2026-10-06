"""Standalone local pilot review editor and readable review summary."""

import base64
import hashlib
import html
import json
from importlib.resources import files
from typing import cast

from gamingcreator.application.detail_pilot_review import DIMENSIONS, PilotReview
from gamingcreator.application.detail_query import loads_constraint, query_options

LABELS = {
    "objectMistakenForActor": ("物品是否仍被误认成人物", "仍有误认", "未发现误认"),
    "shotBoundariesAreReal": ("新版标出的切镜是否真实", "切镜真实", "切镜有误"),
    "positiveDescriptionsRetained": ("原来正确的描述是否保留", "已保留", "有遗漏或错误"),
    "queriedClipUsable": ("同一查询找到的片段是否可用", "可用", "不可用"),
}
_STYLE = """body{margin:0;background:#f4f7fb;color:#203047;font:16px/1.65 system-ui,sans-serif}
main{max-width:1100px;margin:auto;padding:24px}header,section{background:white;border:1px solid #dce3ee;border-radius:14px;padding:24px;margin-bottom:24px}
h1{font-size:27px}.frames{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}figure{margin:0}img{width:100%;height:auto;border-radius:8px}
fieldset{border:1px solid #dce3ee;margin-top:18px;padding:16px;min-width:0}label{display:block;margin:12px 0}input[type=text],input[type=date],textarea,select{box-sizing:border-box;width:100%;max-width:100%;padding:10px;font:inherit}
button{padding:12px 18px;font:inherit;cursor:pointer}textarea{min-height:100px}pre{white-space:pre-wrap;overflow-wrap:anywhere}li{overflow-wrap:anywhere}.notice{background:#fff5d8;padding:12px;border-radius:8px}
#status{overflow-wrap:anywhere}input[type=file]{max-width:100%}a{color:#1758a8}table{width:100%;border-collapse:collapse}th,td{text-align:left;border-bottom:1px solid #dce3ee;padding:8px;overflow-wrap:anywhere}
@media(max-width:700px){main{padding:12px}header,section{padding:16px}.frames{grid-template-columns:1fr}h1{font-size:23px}}
"""


def _page(title: str, body: str, script: str = "") -> str:
    script_policy = "'none'"
    if script:
        digest = base64.b64encode(hashlib.sha256(script.encode("utf-8")).digest()).decode("ascii")
        script_policy = f"'sha256-{digest}'"
    policy = (
        "default-src 'none'; img-src data:; style-src 'unsafe-inline'; "
        f"script-src {script_policy}; connect-src 'none'; object-src 'none'; "
        "base-uri 'none'; form-action 'none'"
    )
    return (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<meta http-equiv="Content-Security-Policy" content="{html.escape(policy, quote=True)}">'
        f"<title>{html.escape(title)}</title><style>{_STYLE}</style></head>"
        f"<body><main>{body}</main>"
        + (f"<script>{script}</script>" if script else "")
        + "</body></html>"
    )


def _frames(case: dict[str, object]) -> str:
    result = []
    for frame in cast(list[dict[str, object]], case["frames"]):
        seconds = cast(int, frame["sourceUs"]) / 1_000_000
        result.append(
            f'<figure><img src="{html.escape(cast(str, frame["imageDataUrl"]), quote=True)}" '
            f'alt="源视频 {seconds:g} 秒原画面"><figcaption>{seconds:g} 秒</figcaption></figure>'
        )
    return '<div class="frames">' + "".join(result) + "</div>"


def _query_label(case: dict[str, object]) -> str:
    legacy = cast(dict[str, object], case["legacy"])
    matching = cast(dict[str, object], legacy["match"])
    constraint = loads_constraint(cast(str, matching["constraintJson"]))
    labels = {}
    for kind in cast(list[dict[str, object]], query_options()["kinds"]):
        for value in cast(list[dict[str, object]], kind["values"]):
            labels[(kind["kind"], value["value"])] = f"{kind['label']}：{value['label']}"
    return " + ".join(
        labels[(condition.kind.value, condition.value)]
        for condition in (*constraint.actor_all, *constraint.environment_all)
    )


def render_review_editor(comparison: dict[str, object], template: dict[str, object]) -> str:
    config = {
        "comparison": comparison,
        "template": template,
        "labels": LABELS,
        "queryLabels": {
            cast(str, case["caseId"]): _query_label(case)
            for case in cast(list[dict[str, object]], comparison["cases"])
        },
    }
    encoded = base64.b64encode(
        json.dumps(config, ensure_ascii=False, allow_nan=False).encode("utf-8")
    ).decode("ascii")
    asset = files("gamingcreator.ui").joinpath("static/pilot-review.js").read_text(encoding="utf-8")
    script = (
        "const context=JSON.parse(new TextDecoder().decode(Uint8Array.from(atob('"
        + encoded
        + "'),c=>c.charCodeAt(0))));\n"
        + asset
    )
    body = """<header><h1>同画面对照 · 人工记录</h1>
<p>分别记录物品误认、切镜、正确描述保留、片段可用性。没有新版真实结果时，这组判断保持未核对；旧版意见不会自动成为新版结论。</p>
<p>页面只处理你选择的本地文件，不发送画面或记录。修改后请下载保存；可再次载入继续填写。此记录不代表检索质量已验收。</p>
<label>日期<input id="recordedOn" type="date"></label>
<label>填写人<input id="reviewer" type="text" autocomplete="off"></label>
<label>载入已有记录<input id="load-record" type="file" accept=".json,application/json"></label>
<button id="download-record" type="button">下载当前记录</button>
<p id="status" role="status" aria-live="polite">尚未填写判断；未核对项目保持空白。</p>
</header><div id="cases"></div>"""
    return _page("同画面对照 · 人工记录", body, script)


def render_review_summary(comparison: dict[str, object], review: PilotReview) -> str:
    payload = json.loads(review.payload_json)
    rows = {row["caseId"]: row for row in payload["cases"]}
    metadata = f"日期：{review.recorded_on or '未填写'}；填写人：{review.reviewer or '未填写'}"
    body = (
        "<header><h1>同画面对照 · 已保存人工记录</h1><p>"
        + html.escape(metadata)
        + "</p><p>各维度分别保留判断；未核对不计为通过。没有合并评分，也不代表独立检索质量通过。保存过程没有模型请求或费用变化。</p></header>"
    )
    for case in cast(list[dict[str, object]], comparison["cases"]):
        row = rows[case["caseId"]]
        interval = cast(dict[str, int], case["sourceRange"])
        start, end = interval["startUs"] / 1_000_000, (interval["endUs"] - 1) / 1_000_000
        table = []
        for key in DIMENSIONS:
            question, yes, no = LABELS[key]
            answer = "未核对" if row[key] is None else yes if row[key] else no
            table.append(f"<tr><th>{question}</th><td>{answer}</td></tr>")
        targets = "、".join(row["reviewedTemporalEntityIds"] or []) or "未指定"
        body += (
            f"<section><h2>{start:g}–{end:g} 秒</h2>"
            f"<p>本组查询：{html.escape(_query_label(case))}</p>{_frames(case)}"
            f"<table>{''.join(table)}</table>"
            f"<p>核对实体：{html.escape(targets)}</p>"
            f"<p>说明：{html.escape(row['statement'] or '未填写')}</p>"
            "<details><summary>本记录对应的结果来源</summary><pre>"
            + html.escape(
                json.dumps(
                    {key: row[key] for key in row if key not in DIMENSIONS},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            + "</pre></details></section>"
        )
    return _page("同画面对照 · 已保存人工记录", body)
