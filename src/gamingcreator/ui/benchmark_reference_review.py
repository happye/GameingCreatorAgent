"""Standalone raw-footage reference editor; no model output or network access."""

import base64
import hashlib
import html
import json
from importlib.resources import files
from pathlib import Path
from typing import cast

from gamingcreator.ui.benchmark_review import STYLE


def render_reference_review(
    context: dict[str, object],
    template: dict[str, object],
    *,
    media_urls: dict[str, str] | None = None,
) -> str:
    media = [
        {
            **row,
            "videoUrl": media_urls[cast(str, row["id"])]
            if media_urls is not None
            else Path(cast(str, row["path"])).as_uri(),
        }
        for row in cast(list[dict[str, object]], context["media"])
    ]
    encoded = base64.b64encode(
        json.dumps(
            {"context": {**context, "media": media}, "template": template},
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
    ).decode("ascii")
    script = (
        "const source=JSON.parse(new TextDecoder().decode(Uint8Array.from(atob('"
        + encoded
        + "'),c=>c.charCodeAt(0))));\n"
        + files("gamingcreator.ui")
        .joinpath("static/benchmark-references.js")
        .read_text(encoding="utf-8")
    )
    digest = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode("ascii")
    media_policy = "'self'" if media_urls is not None else "file: blob:"
    policy = f"default-src 'none'; media-src {media_policy}; style-src 'unsafe-inline'; script-src 'sha256-{digest}'; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'"
    body = """<header><h1>原片 · 人工参考标注</h1>
<p>先看原录像，记录事前查询对应的真实动作和可用区间。这里没有模型描述，也不执行分析或检索。</p>
<p class="notice">这是待冻结的参考草稿。下载、填写区间或人工声明均不自动通过独立验收；主查询需要至少十个独立可用参考事件。</p>
<div class="fields"><label>人工参考版本<input id="label-version" type="text" autocomplete="off"></label><label>填写人（每行一人）<textarea id="annotators"></textarea></label></div>
<label><input id="confirmed" type="checkbox"> 人工参考已实际确认</label>
<label><input id="reviewed" type="checkbox"> 人工参考已由人复核</label>
<label>继续已有标注<input id="load-record" type="file" accept=".json,application/json"></label>
<button id="download-record" type="button">保存当前标注记录</button>
<p id="status" role="status" aria-live="polite">尚未新增人工参考。</p></header>
<section><label>选择事前查询<select id="query-select"></select></label><p id="query-info"></p>
<video id="source-video" controls preload="metadata"></video><p id="clock-state"></p>
<div class="fields"><label>可用起点（源时间秒）<input id="start-seconds" type="text" inputmode="decimal" placeholder="0.000000"><button id="capture-start" type="button">用当前位置标记起点</button></label>
<label>可用终点（源时间秒）<input id="end-seconds" type="text" inputmode="decimal" placeholder="1.000000"><button id="capture-end" type="button">用当前位置标记终点</button></label></div>
<div class="fields"><label>真实事件名称<input id="event-id" type="text" placeholder="例如：第一次闪避"></label><label>独立动作归组<input id="event-group" type="text" placeholder="同一动作的不同区间填相同名称"></label></div>
<label>为什么这个区间可用<textarea id="reason"></textarea></label>
<button id="add-reference" type="button">登记这个可用区间</button><p id="reference-summary"></p><div id="reference-list"></div></section>
<section><h2>保存后怎么做</h2><p>下载并保留标注记录。导入工具会重新核对原录像和事前查询，生成可交给已有冻结入口的计划；没有自动冻结、分析或人工评分。</p>
<p>同一真实事件可以登记多个不同可用区间；名字相同会归到同一参考。同一个动作即使起多个名字，也应保持相同独立动作归组。</p></section>"""
    return (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        + '<meta http-equiv="Content-Security-Policy" content="'
        + html.escape(policy, quote=True)
        + '"><title>原片 · 人工参考标注</title><style>'
        + STYLE
        + "</style></head><body><main>"
        + body
        + "</main><script>"
        + script
        + "</script></body></html>"
    )
