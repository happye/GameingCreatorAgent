"""Local page for choosing a run, typing a query, and reading store-backed results."""

import json
from collections.abc import Sequence
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from gamingcreator.application.retrieval import RetrievalMode
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.ui.service import inspect_run, list_project_runs

PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>时间线检查</title>
<style>
  body { font-family: "Segoe UI", sans-serif; margin: 24px; color: #1c1c1c; }
  form { display: grid; grid-template-columns: 8em 1fr; gap: 8px 12px; max-width: 52em; }
  label { align-self: center; }
  input, select, button { font: inherit; padding: 6px 8px; }
  button { width: fit-content; }
  section { margin-top: 24px; }
  table { border-collapse: collapse; width: 100%; }
  th, td { border-bottom: 1px solid #ccc; text-align: left; vertical-align: top; padding: 6px; }
  .note { color: #444; }
  .empty { color: #666; }
</style>
</head>
<body>
<h1>时间线检查</h1>
<p class="note">这是本地检查页，不是成片编辑器，也不是人工质量验收。检索排名按分数，不是按时间轴。</p>
<form id="inspect">
  <label for="project">项目目录</label>
  <input id="project" name="project" value="artifacts/demo-phase0">
  <label for="run">运行</label>
  <span>
    <select id="run" name="run"></select>
    <button type="button" id="load-runs">读取运行</button>
  </span>
  <label for="query">查询</label>
  <input id="query" name="query" value="寻找角色打斗和攻击的片段">
  <label for="mode">模式</label>
  <select id="mode" name="mode">
    <option value="hybrid" selected>hybrid</option>
    <option value="lexical">lexical</option>
    <option value="semantic">semantic</option>
  </select>
  <label for="top">条数</label>
  <input id="top" name="top" type="number" min="1" max="100" value="3">
  <span></span>
  <button type="submit">查看</button>
</form>
<p id="status" class="note"></p>
<p id="artifact"></p>
<section>
  <h2>时间轴（源时间）</h2>
  <div id="timeline"></div>
</section>
<section>
  <h2>检索排名（分数，然后时间）</h2>
  <div id="ranked"></div>
</section>
<script>
const status = document.querySelector("#status");
const timeline = document.querySelector("#timeline");
const ranked = document.querySelector("#ranked");
function params() {
  return new URLSearchParams({
    project: document.querySelector("#project").value,
    run: document.querySelector("#run").value,
    query: document.querySelector("#query").value,
    mode: document.querySelector("#mode").value,
    top: document.querySelector("#top").value
  });
}
function table(rows, rankedRows) {
  if (!rows.length) return "<p class=\\"empty\\">没有记录。</p>";
  const head = rankedRows
    ? "<tr><th>名次</th><th>开始</th><th>结束</th><th>可观察事实</th><th>证据</th></tr>"
    : "<tr><th>开始</th><th>结束</th><th>可观察事实</th><th>证据</th></tr>";
  const body = rows.map(row => {
    const facts = (row.observableFacts || []).join("；");
    const evidence = (row.evidenceIds || []).join(", ");
    const times = `<td>${row.startTimecode}</td><td>${row.endTimecode}</td><td>${facts}</td><td>${evidence}</td>`;
    return rankedRows ? `<tr><td>${row.rank}</td>${times}</tr>` : `<tr>${times}</tr>`;
  }).join("");
  return `<table>${head}${body}</table>`;
}
async function loadRuns() {
  const project = document.querySelector("#project").value;
  const response = await fetch("/api/runs?" + new URLSearchParams({project}));
  const payload = await response.json();
  const select = document.querySelector("#run");
  select.innerHTML = "";
  for (const run of payload.runs || []) {
    const option = document.createElement("option");
    option.value = run.id;
    option.textContent = run.id + " (" + run.status + ")";
    select.appendChild(option);
  }
  if (!select.options.length) status.textContent = payload.message || "这个项目里没有运行。";
}
async function inspect() {
  status.textContent = "正在读取数据库…";
  const response = await fetch("/api/inspect?" + params());
  const payload = await response.json();
  if (!response.ok) {
    status.textContent = payload.message || "读取失败。";
    return;
  }
  document.querySelector("#artifact").textContent = "读取自 " + payload.artifact;
  timeline.innerHTML = table(payload.timeline || [], false);
  ranked.innerHTML = table(payload.candidates || [], true);
  const reason = payload.abstentionReason ? " 检索说明：" + payload.abstentionReason : "";
  status.textContent = "运行 " + payload.runId + " 状态 " + payload.runStatus + "。" + reason
    + " 再次点击「查看」会重新读取数据库，不必重启本页。";
}
document.querySelector("#load-runs").addEventListener("click", () => loadRuns().catch(error => {
  status.textContent = String(error);
}));
document.querySelector("#inspect").addEventListener("submit", event => {
  event.preventDefault();
  inspect().catch(error => { status.textContent = String(error); });
});
loadRuns().catch(() => { status.textContent = "填写项目目录后点击「读取运行」。"; });
</script>
</body>
</html>
"""


def _query(path: str) -> dict[str, str]:
    parsed = urlparse(path)
    values = parse_qs(parsed.query, keep_blank_values=True)
    return {key: items[0] for key, items in values.items() if items}


class InspectionHandler(BaseHTTPRequestHandler):
    repository = Path.cwd()

    def log_message(self, format: str, *args: object) -> None:
        return

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: dict[str, object]) -> None:
        self._send(
            status,
            json.dumps(payload, ensure_ascii=False).encode(),
            "application/json; charset=utf-8",
        )

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler name
        import asyncio

        path = urlparse(self.path).path
        if path == "/":
            self._send(200, PAGE.encode(), "text/html; charset=utf-8")
            return
        query = _query(self.path)
        try:
            if path == "/api/runs":
                project = Path(query.get("project", "")).expanduser()
                runs = asyncio.run(list_project_runs(project.resolve()))
                self._json(
                    200,
                    {"runs": [{"id": run_id, "status": status} for run_id, status in runs]},
                )
                return
            if path == "/api/inspect":
                modes: dict[str, RetrievalMode] = {
                    "lexical": "lexical",
                    "semantic": "semantic",
                    "hybrid": "hybrid",
                }
                requested = query.get("mode", "hybrid")
                if requested not in modes:
                    raise AppError(
                        "retrieval.configuration", "检索模式无效。", ExitCode.ENVIRONMENT
                    )
                mode = modes[requested]
                payload = asyncio.run(
                    inspect_run(
                        Path(query.get("project", "")).expanduser().resolve(),
                        query.get("run", ""),
                        query.get("query", ""),
                        self.repository,
                        mode=mode,
                        top_k=int(query.get("top", "10")),
                    )
                )
                self._json(200, payload)
                return
        except AppError as error:
            self._json(
                error.exit_code,
                {"code": error.code, "runId": error.run_id, "message": error.message},
            )
            return
        except (OSError, ValueError) as error:
            self._json(400, {"code": "input.project", "message": str(error)})
            return
        self._json(404, {"code": "input.route", "message": "没有这个页面。"})


def serve(host: str, port: int, repository: Path) -> None:
    InspectionHandler.repository = repository.resolve()
    server = ThreadingHTTPServer((host, port), InspectionHandler)
    print(f"Inspection UI: http://{host}:{port}/", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="打开本地时间线检查页")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    args = parser.parse_args(list(argv) if argv is not None else None)
    serve(args.host, args.port, args.repository)
    return 0
