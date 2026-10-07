"""Standalone local candidate review form with file playback and no connections."""

import base64
import hashlib
import html
import json
from importlib.resources import files
from pathlib import Path
from typing import cast

STYLE = """body{margin:0;background:#f3f6fb;color:#203047;font:16px/1.55 system-ui,sans-serif}
main{max-width:1100px;margin:auto;padding:24px}header,section{background:#fff;border:1px solid #dce3ee;border-radius:12px;padding:20px;margin:0 0 20px}
h1{font-size:27px}h2{font-size:22px}h3{font-size:18px}.notice{background:#fff4d5;padding:12px;border-radius:8px}p,li,pre{overflow-wrap:anywhere}
.slot{border-top:1px solid #dce3ee;margin-top:16px;padding-top:16px}.empty{color:#66758a}label{display:block;margin:10px 0}
input[type=text],input[type=date],textarea,select{box-sizing:border-box;width:100%;padding:10px;font:inherit}textarea{min-height:72px}
button{padding:10px 16px;font:inherit;cursor:pointer}button:disabled{cursor:default}input[type=file]{max-width:100%}
.fields{display:grid;grid-template-columns:1fr 1fr;gap:16px}.player{position:sticky;top:0;z-index:1;background:#fff;border-bottom:1px solid #dce3ee;padding:12px}
video{display:block;max-width:100%;width:640px;max-height:320px;background:#151b24}#play-state,#status{overflow-wrap:anywhere}a{color:#1758a8}
@media(max-width:700px){main{padding:12px}header,section{padding:14px}.fields{grid-template-columns:1fr}.player{position:static}h1{font-size:23px}}
"""


def render_benchmark_review(
    context: dict[str, object],
    template: dict[str, object],
    *,
    media_urls: dict[str, str] | None = None,
) -> str:
    media = [
        {
            **row,
            "videoUrl": media_urls[cast(str, row["runId"])]
            if media_urls is not None
            else Path(cast(str, row["path"])).as_uri(),
        }
        for row in cast(list[dict[str, object]], context["media"])
    ]
    config = {"context": {**context, "media": media}, "template": template}
    encoded = base64.b64encode(
        json.dumps(config, ensure_ascii=False, allow_nan=False).encode()
    ).decode("ascii")
    asset = (
        files("gamingcreator.ui").joinpath("static/benchmark-review.js").read_text(encoding="utf-8")
    )
    script = (
        "const source=JSON.parse(new TextDecoder().decode(Uint8Array.from(atob('"
        + encoded
        + "'),c=>c.charCodeAt(0))));\n"
        + asset
    )
    digest = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode("ascii")
    media_policy = "'self'" if media_urls is not None else "file: blob:"
    policy = f"default-src 'none'; media-src {media_policy}; style-src 'unsafe-inline'; script-src 'sha256-{digest}'; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'"
    body = """<header><h1>检索候选 · 人工判分</h1>
<p>按原排名核对十个固定位置。缺位和已知重复保留，不能用后面的结果补位；相同真实动作可映射到同一独立事件。</p>
<p class="notice">所有评分先留空。模型描述只供对照，请回看原片；下载或选择评分不会自动通过检索验收。没有事前人工参考时，可记录0/1或暂不判分，2/3需要对应的冻结独立事件。</p>
<p>页面只读取本机原片和你选择的记录，不联网。修改后下载保存；导入工具会重新核对原录像、固定结果和冻结依据，再生成评测文件。</p>
<div class="fields"><label>日期<input id="recordedOn" type="date"></label><label>填写人<input id="reviewer" type="text" autocomplete="off"></label></div>
<label><input id="reviewed" type="checkbox"> 本次候选记录已由人复核</label>
<label>继续填写已有记录<input id="load-record" type="file" accept=".json,application/json"></label>
<button id="download-record" type="button">下载当前记录</button><p id="status" role="status" aria-live="polite">尚未填写评分。</p></header>
<div class="player"><video id="source-video" controls preload="none"></video><p id="play-state">选择“播放此区间”回看原片。</p><a id="open-source" hidden>打开本机原片</a></div>
<div id="queries"></div>"""
    return (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        + '<meta http-equiv="Content-Security-Policy" content="'
        + html.escape(policy, quote=True)
        + '"><title>检索候选 · 人工判分</title><style>'
        + STYLE
        + "</style></head><body><main>"
        + body
        + "</main><script>"
        + script
        + "</script></body></html>"
    )
