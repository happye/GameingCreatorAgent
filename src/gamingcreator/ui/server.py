"""Loopback workspace backed by registered timelines, media and local search."""

import asyncio
import json
import os
import socket
from collections.abc import Sequence
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from gamingcreator.application.retrieval import RetrievalMode
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.ui.media import VerifiedMediaCache, byte_range
from gamingcreator.ui.service import inspect_run, project_runs_payload, registered_media

STATIC = Path(__file__).with_name("static")
ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/assets/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/assets/style.css": ("style.css", "text/css; charset=utf-8"),
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
    if error.code in {"input.evidence", "storage.run_missing", "storage.run_not_found"}:
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

    def log_message(self, format: str, *args: object) -> None:
        return

    def _headers(self, status: int, length: int, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
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
            if path not in {"/api/runs", "/api/inspect", "/api/media", "/api/evidence"}:
                self._json(404, {"code": "input.route", "message": "没有这个页面。"})
                return
            project = resolve_project(self.repository, query.get("project", ""))
            if path == "/api/runs":
                self._json(200, asyncio.run(project_runs_payload(project)))
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
    handler = type(
        "WorkspaceHandler",
        (InspectionHandler,),
        {
            "repository": repository.resolve(),
            "media_cache": VerifiedMediaCache(),
        },
    )
    return WorkspaceServer((host, port), handler)


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
