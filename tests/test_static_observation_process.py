"""Real SQLite Completed run, production CLI, and a separate-process static search."""

import json
import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

from test_static_observations import (
    create_project,
    package_document,
    query_document,
    sha,
    write_json,
)

from gamingcreator.domain.static_observations import (
    observation_id,
    package_sha256,
)
from gamingcreator.infrastructure.static_observation_codec import loads_static_package


def run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    repository = Path(__file__).resolve().parents[1]
    environment = os.environ | {
        "PYTHONUTF8": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": os.pathsep.join(
            [str(repository / "src"), os.environ.get("PYTHONPATH", "")]
        ).strip(os.pathsep),
    }
    return subprocess.run(
        [sys.executable, "-m", "gamingcreator", *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=120,
        env=environment,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )


def test_completed_every_frame_import_is_visible_to_a_new_process(
    tmp_path: Path,
) -> None:
    project, bundle = create_project(tmp_path)
    package_path = tmp_path / "package.json"
    write_json(package_path, package_document(project, bundle))
    query_path = tmp_path / "query.json"
    write_json(query_path, query_document())
    timeline_hash = sha(project / "timeline.sqlite3")

    imported = run_cli(
        "import-static-observations",
        "--project",
        str(project),
        "--run",
        "run-1",
        "--collection",
        "look-1",
        "--input",
        str(package_path),
    )
    assert imported.returncode == 0, imported.stderr
    import_document = json.loads(imported.stdout)
    package = loads_static_package(package_path.read_bytes())
    expected_id = observation_id(package, package.observations[0])
    assert import_document["status"] == "created"
    assert import_document["collectionSha256"] == package_sha256(package)
    assert (project / "static-observations.sqlite3").is_file()
    assert sha(project / "timeline.sqlite3") == timeline_hash

    searched = run_cli(
        "search-static-observations",
        "--project",
        str(project),
        "--run",
        "run-1",
        "--collection",
        "look-1",
        "--input",
        str(query_path),
    )
    assert searched.returncode == 0, searched.stderr
    search_document = json.loads(searched.stdout)
    assert search_document["collectionSha256"] == import_document["collectionSha256"]
    assert search_document["matchCount"] == 1
    match = search_document["matches"][0]
    assert match["kind"] == "static_appearance"
    assert match["observationId"] == expected_id
    assert match["evidenceId"] == bundle.images[0].evidence_id
    assert match["sourceTimeUs"] == 100_000
    assert match["sourceRange"] == {
        "startUs": 100_000,
        "endUs": 100_001,
        "durationUs": 2_000_000,
    }
    assert match["imageSha256"] == bundle.images[0].sha256
    assert match["artifactPath"] == str(bundle.images[0].path.resolve())
    assert match["sourcePath"] == str(bundle.asset.source_path)
    assert {item["kind"] for item in match["supportedAttributes"]} == {
        "hair_color",
        "clothing_color",
        "clothing_shape",
        "held_shape",
        "held_class",
    }
    assert search_document["provenance"] == package_document(project, bundle)["provenance"]
    assert search_document["localPaidRequestsSent"] == 0
    assert search_document["visualVerified"] is None
    assert search_document["humanLabels"] is None
    assert search_document["qualityGate"] is None

    repeated = run_cli(
        "import-static-observations",
        "--project",
        str(project),
        "--run",
        "run-1",
        "--collection",
        "look-1",
        "--input",
        str(package_path),
    )
    assert repeated.returncode == 0, repeated.stderr
    assert json.loads(repeated.stdout)["status"] == "unchanged"
    assert sha(project / "timeline.sqlite3") == timeline_hash
    with closing(sqlite3.connect(project / "timeline.sqlite3")) as connection:
        assert connection.execute("SELECT count(*) FROM semantic_events").fetchone()[0] == 0
        assert (
            connection.execute(
                "SELECT count(*) FROM provider_invocations WHERE status='running'"
            ).fetchone()[0]
            == 0
        )
