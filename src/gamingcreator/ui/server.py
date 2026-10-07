"""Loopback workspace backed by registered timelines, media and local search."""

import asyncio
import html
import json
import os
import socket
from collections.abc import Sequence
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from gamingcreator.application.detail_query_draft import draft_detail_query
from gamingcreator.application.retrieval import RetrievalMode
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.ui.benchmark_workflow import BenchmarkWorkflows
from gamingcreator.ui.media import MediaResource, VerifiedMediaCache, byte_range
from gamingcreator.ui.media_preparation import MediaPreparationJobs
from gamingcreator.ui.service import (
    detail_costs,
    inspect_run,
    match_details,
    project_runs_payload,
    project_search_payload,
    project_tasks_payload,
    registered_media,
)

STATIC = Path(__file__).with_name("static")
ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/assets/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/assets/style.css": ("style.css", "text/css; charset=utf-8"),
    "/acceptance": ("benchmark-workflow.html", "text/html; charset=utf-8"),
    "/assets/benchmark-workflow.js": ("benchmark-workflow.js", "text/javascript; charset=utf-8"),
    "/assets/benchmark-workflow.css": ("benchmark-workflow.css", "text/css; charset=utf-8"),
}


def _query(path: str) -> dict[str, str]:
    values = parse_qs(urlparse(path).query, keep_blank_values=True, max_num_fields=16)
    if any(len(items) != 1 for items in values.values()):
        raise ValueError("Duplicate parameter")
    return {key: items[0] for key, items in values.items()}


def resolve_project(repository: Path, value: str) -> Path:
    project = Path(value)
    if not project.is_absolute():
        project = repository / project
    project = project.resolve()
    if not project.is_relative_to(repository.resolve()):
        raise AppError("input.project", "项目必须位于当前仓库内。", ExitCode.INPUT)
    database = project / "timeline.sqlite3"
    if not database.resolve().is_relative_to(repository.resolve()):
        raise AppError("input.project", "项目数据库必须位于当前仓库内。", ExitCode.INPUT)
    if not database.is_file():
        raise AppError("input.project", "这个目录没有已分析的项目数据库。", ExitCode.INPUT)
    return project


def discover_projects(repository: Path) -> list[dict[str, str]]:
    artifacts = repository / "artifacts"
    if not artifacts.is_dir():
        return []
    projects = []
    for database in sorted(artifacts.glob("*/timeline.sqlite3")):
        directory = database.parent.resolve()
        if directory.is_relative_to(repository.resolve()) and database.resolve().is_relative_to(
            repository.resolve()
        ):
            projects.append(
                {"path": directory.relative_to(repository).as_posix(), "name": directory.name}
            )
    return projects


def error_status(error: AppError) -> int:
    if error.code in {
        "input.evidence",
        "storage.run_missing",
        "storage.run_not_found",
        "input.preparation_job",
    }:
        return 404
    return {
        ExitCode.INPUT: 400,
        ExitCode.ENVIRONMENT: 503,
        ExitCode.PROVIDER: 502,
        ExitCode.STORAGE: 409,
        ExitCode.BENCHMARK: 422,
        ExitCode.BUDGET: 402,
        ExitCode.CANCELLED: 409,
    }.get(error.exit_code, 500)


class WorkspaceServer(ThreadingHTTPServer):
    preparation_jobs: MediaPreparationJobs
    benchmark_workflows: BenchmarkWorkflows

    def server_close(self) -> None:
        jobs = getattr(self, "preparation_jobs", None)
        if jobs is not None:
            jobs.close()
        workflows = getattr(self, "benchmark_workflows", None)
        if workflows is not None:
            workflows.close()
        super().server_close()

    def server_bind(self) -> None:
        # Windows SO_REUSEADDR permits two live listeners on the same endpoint.
        # Use exclusive ownership so a stale preview cannot serve the new URL.
        if os.name == "nt":
            self.allow_reuse_address = False
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class InspectionHandler(BaseHTTPRequestHandler):
    repository = Path.cwd()
    media_cache = VerifiedMediaCache()
    preparation_jobs: MediaPreparationJobs
    benchmark_workflows: BenchmarkWorkflows

    def log_message(self, format: str, *args: object) -> None:
        return

    def _headers(
        self, status: int, length: int, content_type: str, policy: str | None = None
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            policy
            or "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; media-src 'self'; object-src 'none'; "
            "frame-ancestors 'none'; base-uri 'none'",
        )

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self._headers(status, len(body), content_type)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, payload: dict[str, object]) -> None:
        self._send(
            status,
            json.dumps(payload, ensure_ascii=False, allow_nan=False).encode(),
            "application/json; charset=utf-8",
        )

    def _local_request(self) -> bool:
        host = self.headers.get("Host", "")
        hostname = urlparse("http://" + host).hostname
        origin = self.headers.get("Origin")
        return (
            hostname in {"127.0.0.1", "localhost"}
            and self.headers.get("Sec-Fetch-Site") != "cross-site"
            and (origin is None or origin == "http://" + host)
        )

    def _media(self, project: Path, run_id: str, evidence_id: str | None = None) -> None:
        resource = asyncio.run(registered_media(project, run_id, evidence_id))
        self._serve_media(resource)

    def _serve_media(self, resource: MediaResource) -> None:
        with self.media_cache.open(resource) as source:
            size = os.fstat(source.fileno()).st_size
            try:
                offset, length, partial = byte_range(self.headers.get("Range"), size)
            except ValueError:
                self._headers(416, 0, resource.content_type)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
            self._headers(206 if partial else 200, length, resource.content_type)
            self.send_header("Accept-Ranges", "bytes")
            if partial:
                self.send_header("Content-Range", f"bytes {offset}-{offset + length - 1}/{size}")
            self.end_headers()
            if self.command == "HEAD":
                return
            source.seek(offset)
            remaining = length
            while remaining:
                chunk = source.read(min(256 * 1024, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def do_HEAD(self) -> None:  # noqa: N802 - stdlib handler name
        self.do_GET()

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler name
        try:
            if (
                self.headers.get_content_type() != "application/json"
                or self.headers.get("Transfer-Encoding") is not None
                or len(self.headers.get_all("Content-Length", [])) != 1
            ):
                raise ValueError("Expected a bounded JSON body.")
            length = int(self.headers["Content-Length"])
            path = urlparse(self.path).path
            body_limit = 8_388_608 if path == "/api/benchmark-step" else 65536
            if not 0 < length <= body_limit:
                raise ValueError("Request is too large.")
            # Socket read timeout prevents a partial body from retaining a handler indefinitely.
            self.connection.settimeout(10)
            body = self.rfile.read(length)
            if len(body) != length:
                raise ValueError("Incomplete JSON body.")
            # Drain the bounded body before rejection: closing a Windows socket with
            # unread request bytes can reset the connection before the 403 arrives.
            if not self._local_request():
                self._json(403, {"code": "input.origin", "message": "请从本机工作台访问。"})
                return
            path = urlparse(self.path).path
            if path not in {
                "/api/match-details",
                "/api/draft-detail-query",
                "/api/search-project",
                "/api/prepare-media-batch",
                "/api/cancel-media-preparation",
                "/api/benchmark-workflows",
                "/api/benchmark-step",
            }:
                self._json(404, {"code": "input.route", "message": "没有这个操作。"})
                return

            def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
                result: dict[str, object] = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError("Duplicate request field.")
                    result[key] = value
                return result

            value = json.loads(body, object_pairs_hook=unique)
            if path in {"/api/benchmark-workflows", "/api/benchmark-step"}:
                if type(value) is not dict:
                    raise ValueError("Expected workflow fields.")
                payload = (
                    self.benchmark_workflows.create(value)
                    if path == "/api/benchmark-workflows"
                    else self.benchmark_workflows.submit(value)
                )
                self._json(201 if path == "/api/benchmark-workflows" else 202, payload)
                return
            if path == "/api/prepare-media-batch":
                if type(value) is not dict:
                    raise ValueError("Expected preparation fields.")
                self._json(202, self.preparation_jobs.submit(value))
                return
            if path == "/api/cancel-media-preparation":
                if (
                    type(value) is not dict
                    or set(value) != {"project", "job"}
                    or any(type(item) is not str for item in value.values())
                ):
                    raise ValueError("Expected exact cancellation identity.")
                self._json(200, self.preparation_jobs.cancel(value["project"], value["job"]))
                return
            if path == "/api/search-project":
                if (
                    type(value) is not dict
                    or set(value) != {"project", "runs", "query", "mode", "top"}
                    or any(type(value[key]) is not str for key in ("project", "query", "mode"))
                    or type(value["runs"]) is not list
                    or not 1 <= len(value["runs"]) <= 100
                    or any(type(item) is not str for item in value["runs"])
                    or type(value["top"]) is not int
                    or not 1 <= value["top"] <= 100
                    or value["mode"] not in ("lexical", "semantic", "hybrid")
                ):
                    raise ValueError("Invalid project search fields.")
                project = resolve_project(self.repository, value["project"])
                self._json(
                    200,
                    asyncio.run(
                        project_search_payload(
                            project,
                            value["runs"],
                            value["query"],
                            self.repository,
                            mode=value["mode"],
                            top_k=value["top"],
                            project_reference=value["project"],
                        )
                    ),
                )
                return
            if path == "/api/draft-detail-query":
                if type(value) is not dict or set(value) != {"text"}:
                    raise ValueError("Invalid draft request fields.")
                self._json(200, draft_detail_query(value["text"]))
                return
            if (
                type(value) is not dict
                or set(value) != {"project", "run", "event", "profile", "constraint"}
                or any(
                    type(value[key]) is not str for key in ("project", "run", "event", "profile")
                )
                or type(value["constraint"]) is not dict
            ):
                raise ValueError("Invalid match request fields.")
            project = resolve_project(self.repository, value["project"])
            payload = asyncio.run(
                match_details(
                    project,
                    value["run"],
                    value["event"],
                    json.dumps(value["constraint"], ensure_ascii=False, allow_nan=False),
                    profile=value["profile"],
                )
            )
            self._json(200, payload)
        except AppError as error:
            self._json(
                error_status(error),
                {
                    "code": error.code,
                    "message": error.message,
                    "runId": error.run_id,
                    "exitCode": int(error.exit_code),
                },
            )
        except ConnectionError:
            return
        except (OSError, ValueError, RecursionError):
            self._json(
                400, {"code": "input.request", "message": "复合条件请求无效。", "exitCode": 2}
            )

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler name
        try:
            if not self._local_request():
                self._json(403, {"code": "input.origin", "message": "请从本机工作台访问。"})
                return
            path = urlparse(self.path).path
            if path in ASSETS:
                name, mime = ASSETS[path]
                self._send(200, (STATIC / name).read_bytes(), mime)
                return
            if path == "/api/health":
                self._json(
                    200,
                    {
                        "application": "gamingcreator-workspace",
                        "apiVersion": 1,
                        "capabilities": [
                            "media-preparation-v1",
                            "benchmark-workflow-v1",
                            "benchmark-bind-options-v1",
                        ],
                        "repository": str(self.repository.resolve()),
                        "pid": os.getpid(),
                        "parentPid": os.getppid(),
                    },
                )
                return
            if path == "/api/projects":
                self._json(200, {"projects": discover_projects(self.repository)})
                return
            query = _query(self.path)
            if path == "/api/benchmark-workflows":
                if query:
                    raise ValueError("Unexpected workflow catalog fields.")
                self._json(200, self.benchmark_workflows.catalog())
                return
            if path == "/api/benchmark-workflow":
                if set(query) != {"workflow"}:
                    raise ValueError("Expected workflow identity.")
                self._json(200, self.benchmark_workflows.get(query["workflow"]))
                return
            if path == "/api/benchmark-bind-options":
                if set(query) != {"workflow", "project", "partition"}:
                    raise ValueError("Expected exact binding selection identity.")
                self._json(
                    200,
                    asyncio.run(
                        self.benchmark_workflows.binding_options(
                            query["workflow"], query["project"], query["partition"]
                        )
                    ),
                )
                return
            if path == "/api/benchmark-source":
                if set(query) != {"workflow", "attempt", "source"}:
                    raise ValueError("Expected registered source identity.")
                self._serve_media(
                    self.benchmark_workflows.media(
                        query["workflow"], query["attempt"], query["source"]
                    )
                )
                return
            if path == "/api/benchmark-file":
                if set(query) != {"workflow", "attempt", "file"}:
                    raise ValueError("Expected registered workflow file.")
                identifier, attempt, name = query["workflow"], query["attempt"], query["file"]
                if name.endswith(".html"):
                    data = self.benchmark_workflows.page(identifier, attempt, name)
                    # Renderer supplies a hash-only inline policy. Apply the same policy in the response.
                    policy = html.unescape(
                        data.decode()
                        .split('http-equiv="Content-Security-Policy" content="', 1)[1]
                        .split('"', 1)[0]
                    )
                    self._headers(
                        200,
                        len(data),
                        "text/html; charset=utf-8",
                        policy + "; frame-ancestors 'none'",
                    )
                    self.end_headers()
                    if self.command != "HEAD":
                        self.wfile.write(data)
                else:
                    self._send(
                        200,
                        self.benchmark_workflows.file(identifier, attempt, name),
                        "application/json; charset=utf-8",
                    )
                return
            if path == "/api/media-preparation":
                if set(query) != {"project", "job"}:
                    raise ValueError("Expected preparation identity.")
                self._json(200, self.preparation_jobs.get(query["project"], query["job"]))
                return
            if path == "/api/media-batches":
                if set(query) - {"project", "limit", "offset"} or "project" not in query:
                    raise ValueError("Expected batch catalog fields.")
                self._json(
                    200,
                    self.preparation_jobs.catalog(
                        query["project"],
                        limit=int(query.get("limit", "20")),
                        offset=int(query.get("offset", "0")),
                    ),
                )
                return
            if path not in {
                "/api/runs",
                "/api/tasks",
                "/api/inspect",
                "/api/media",
                "/api/evidence",
                "/api/detail-cost-history",
            }:
                self._json(404, {"code": "input.route", "message": "没有这个页面。"})
                return
            project = resolve_project(self.repository, query.get("project", ""))
            if path == "/api/runs":
                self._json(200, asyncio.run(project_runs_payload(project)))
            elif path == "/api/tasks":
                self._json(
                    200,
                    asyncio.run(
                        project_tasks_payload(
                            project,
                            limit=int(query.get("limit", "100")),
                            offset=int(query.get("offset", "0")),
                            run_id=query.get("run"),
                            project_reference=query.get("project"),
                        )
                    ),
                )
            elif path == "/api/detail-cost-history":
                self._json(200, asyncio.run(detail_costs(project, query.get("run", ""))))
            elif path in {"/api/media", "/api/evidence"}:
                evidence_id = query.get("id", "") if path == "/api/evidence" else None
                self._media(project, query.get("run", ""), evidence_id)
            else:
                modes: dict[str, RetrievalMode] = {
                    "lexical": "lexical",
                    "semantic": "semantic",
                    "hybrid": "hybrid",
                }
                mode, top = query.get("mode", "hybrid"), int(query.get("top", "10"))
                if mode not in modes or not 1 <= top <= 100:
                    raise AppError(
                        "retrieval.configuration", "检索模式或条数无效。", ExitCode.INPUT
                    )
                payload = asyncio.run(
                    inspect_run(
                        project,
                        query.get("run", ""),
                        query.get("query", ""),
                        self.repository,
                        mode=modes[mode],
                        top_k=top,
                        project_reference=query.get("project"),
                        detail_profile=query.get("detailProfile", "v1"),
                    )
                )
                self._json(200, payload)
        except AppError as error:
            self._json(
                error_status(error),
                {
                    "code": error.code,
                    "runId": error.run_id,
                    "message": error.message,
                    "exitCode": int(error.exit_code),
                },
            )
        except ConnectionError:
            return
        except (OSError, ValueError):
            self._json(
                400,
                {
                    "code": "input.request",
                    "message": "读取失败，请检查项目、运行和本地文件。",
                    "exitCode": 2,
                },
            )


def create_server(host: str, port: int, repository: Path) -> ThreadingHTTPServer:
    if host != "127.0.0.1":
        raise ValueError("The inspection workspace only binds to 127.0.0.1")
    jobs = MediaPreparationJobs(repository)
    workflows = BenchmarkWorkflows(repository)
    handler = type(
        "WorkspaceHandler",
        (InspectionHandler,),
        {
            "repository": repository.resolve(),
            "media_cache": VerifiedMediaCache(),
            "preparation_jobs": jobs,
            "benchmark_workflows": workflows,
        },
    )
    server = WorkspaceServer((host, port), handler)
    server.preparation_jobs = jobs
    server.benchmark_workflows = workflows
    return server


def serve(host: str, port: int, repository: Path) -> None:
    server = create_server(host, port, repository)
    print(f"Inspection UI: http://{host}:{server.server_port}/", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="打开本地素材检查工作台")
    parser.add_argument("--host", choices=("127.0.0.1",), default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    args = parser.parse_args(list(argv) if argv is not None else None)
    serve(args.host, args.port, args.repository)
    return 0
