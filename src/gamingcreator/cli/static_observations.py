"""Production CLI assembly for explicit local static declaration import and search."""

import asyncio
from pathlib import Path

from gamingcreator.application.detail_query import loads_constraint
from gamingcreator.application.retrieval import load_searchable_timeline
from gamingcreator.application.static_observations import (
    PublishStatus,
    StaticCollectionArtifact,
    StoredStaticCollection,
    build_static_collection_artifact,
    build_static_import_result,
    build_static_search_report,
)
from gamingcreator.application.storage import StoredTimeline
from gamingcreator.domain.actor_details import QUERY_SCHEMA_VERSION
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.domain.static_observations import (
    MAX_STATIC_PACKAGE_BYTES,
    STATIC_QUERY_SCHEMA_VERSION,
    StaticObservationPackage,
    StaticQuery,
    UnsupportedStaticSchema,
)
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore
from gamingcreator.infrastructure.static_observation_codec import (
    loads_static_package,
    loads_static_query,
    query_schema_version,
)
from gamingcreator.infrastructure.static_observation_store import (
    SqliteStaticObservationStore,
)


def _input_error(message: str) -> AppError:
    return AppError("input.static_observation", message, ExitCode.INPUT)


def _read_bounded(path: Path, label: str) -> bytes:
    try:
        if not path.is_file():
            raise _input_error(f"找不到静态{label}文件。")
        with path.open("rb") as stream:
            data = stream.read(MAX_STATIC_PACKAGE_BYTES + 1)
    except OSError as error:
        raise _input_error(f"无法读取静态{label}文件。") from error
    if len(data) > MAX_STATIC_PACKAGE_BYTES:
        raise _input_error(f"静态{label}超过1MiB。")
    return data


def _scope_error() -> AppError:
    return AppError(
        "static.scope",
        "命令行显式 run／collection 与声明包或查询不一致。",
        ExitCode.INPUT,
    )


def _load_package(path: Path, run_id: str, collection_id: str) -> StaticObservationPackage:
    data = _read_bounded(path, "声明")
    try:
        package = loads_static_package(data)
    except UnsupportedStaticSchema:
        raise AppError(
            "static.schema_unsupported",
            "不支持的静态声明版本。",
            ExitCode.INPUT,
        ) from None
    except ValueError:
        raise _input_error("静态声明格式或词表无效。") from None
    if package.run_id != run_id or package.collection_id != collection_id:
        raise _scope_error()
    return package


def _load_query(path: Path, run_id: str, collection_id: str) -> StaticQuery:
    data = _read_bounded(path, "查询")
    try:
        schema = query_schema_version(data)
    except UnsupportedStaticSchema:
        raise AppError(
            "static.schema_unsupported",
            "不支持的静态查询版本。",
            ExitCode.INPUT,
        ) from None
    except ValueError:
        raise _input_error("静态查询格式或词表无效。") from None
    try:
        if schema == STATIC_QUERY_SCHEMA_VERSION:
            query = loads_static_query(
                data,
                run_id=run_id,
                collection_id=collection_id,
            )
        elif schema == QUERY_SCHEMA_VERSION:
            # Reuse the frozen typed constraint manifest; the CLI supplies explicit scope.
            query = StaticQuery(run_id, collection_id, loads_constraint(data.decode("utf-8")))
        else:
            raise UnsupportedStaticSchema("Unsupported static observation query version.")
    except UnsupportedStaticSchema:
        raise AppError(
            "static.schema_unsupported",
            "不支持的静态查询版本。",
            ExitCode.INPUT,
        ) from None
    except ValueError:
        raise _input_error("静态查询格式或词表无效。") from None
    if query.run_id != run_id or query.collection_id != collection_id:
        raise _scope_error()
    return query


def _require_project(project: Path) -> None:
    if not (project / "timeline.sqlite3").is_file():
        raise AppError("input.project", "找不到已分析的项目数据库。", ExitCode.INPUT)


async def _completed_timeline(project: Path, run_id: str) -> StoredTimeline:
    _require_project(project)
    store = await SqliteTimelineStore.open(project, read_only=True)
    try:
        return await load_searchable_timeline(store, run_id)
    finally:
        await store.close()


def _publish(project: Path, artifact: StaticCollectionArtifact) -> PublishStatus:
    store = SqliteStaticObservationStore.open(project, read_only=False)
    try:
        return store.publish(artifact)
    finally:
        store.close()


def _load(project: Path, run_id: str, collection_id: str) -> StoredStaticCollection:
    store = SqliteStaticObservationStore.open(project, read_only=True)
    try:
        return store.load_collection(run_id, collection_id)
    finally:
        store.close()


async def execute_import_static_observations(
    project: Path,
    run_id: str,
    collection_id: str,
    input_path: Path,
) -> dict[str, object]:
    """Import one immutable declared collection after full current-timeline revalidation."""
    project = project.resolve()
    if not run_id.strip() or not collection_id.strip():
        raise AppError("static.scope", "必须显式提供 run 与 collection。", ExitCode.INPUT)
    package = _load_package(input_path, run_id, collection_id)
    timeline = await _completed_timeline(project, run_id)
    artifact = build_static_collection_artifact(package, timeline)
    status = await asyncio.to_thread(_publish, project, artifact)
    return build_static_import_result(artifact, status)


async def execute_search_static_observations(
    project: Path,
    run_id: str,
    collection_id: str,
    input_path: Path,
) -> dict[str, object]:
    """Search one explicit collection with a typed AND query in a fresh process."""
    project = project.resolve()
    if not run_id.strip() or not collection_id.strip():
        raise AppError("static.scope", "必须显式提供 run 与 collection。", ExitCode.INPUT)
    query = _load_query(input_path, run_id, collection_id)
    timeline = await _completed_timeline(project, run_id)
    stored = await asyncio.to_thread(_load, project, run_id, collection_id)
    return build_static_search_report(stored, query, timeline)
