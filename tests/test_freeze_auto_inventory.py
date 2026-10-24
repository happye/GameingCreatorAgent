"""freeze-benchmark --auto-inventory: the freeze itself inventories the planned recordings."""

import json
import os
from pathlib import Path

import pytest
from test_benchmark_preparation import plan_fixture
from test_source_inventory import FFMPEG, ROOT, make_derived, make_video

from gamingcreator.application.benchmark_preparation import canonical_json
from gamingcreator.cli import main as cli
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.infrastructure.benchmark_preparation_files import read_freeze
from gamingcreator.infrastructure.ffmpeg_signatures import FfmpegSignatureExtractor

DIFFERENT_GROUPS = "shared_footage_has_different_recording_groups"
DERIVED = "派生 片.mp4"


@pytest.fixture(scope="module")
def media(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if not FFMPEG.is_file():
        pytest.skip("Project-local FFmpeg not prepared")
    directory = tmp_path_factory.mktemp("自动 盘点")
    make_video(directory / "原片.mp4", "mandelbrot=size=160x96:rate=10", 24)
    make_derived(directory / "原片.mp4", directory / DERIVED, 3, 16)
    return directory


@pytest.fixture(autouse=True)
def repository_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(ROOT)  # the CLI looks for .tools/ffmpeg under the working directory


def make_plan(tmp_path: Path, media: Path, *, same_group: bool = False) -> Path:
    """Two sources: the original (absolute path) and its derived cut (path relative to the plan)."""
    raw, _ = plan_fixture(tmp_path, count=2)
    plan_directory = tmp_path / "计划"
    plan_directory.mkdir()
    raw["sources"][0]["path"] = str(media / "原片.mp4")
    raw["sources"][1]["path"] = os.path.relpath(media / DERIVED, plan_directory)
    if same_group:
        raw["sources"][1]["recordingGroup"] = raw["sources"][0]["recordingGroup"]
    plan = plan_directory / "plan.json"
    plan.write_bytes(canonical_json(raw))
    return plan


def freeze(
    tmp_path: Path, plan: Path, capsys: pytest.CaptureFixture[str], *extra: str
) -> tuple[int, Path, str]:
    output = tmp_path / "冻结"
    code = cli.main(["freeze-benchmark", "--input", str(plan), "--output", str(output), *extra])
    return code, output, capsys.readouterr().out


def standalone_report(media: Path, destination: Path) -> bytes:
    code = cli.main(
        [
            "inventory-sources",
            "--input",
            str(media / "原片.mp4"),
            str(media / DERIVED),
            "--output",
            str(destination),
        ]
    )
    assert code == 0
    return destination.read_bytes()


def test_auto_inventory_blocks_shared_footage_in_different_groups_with_standalone_bytes(
    tmp_path: Path, media: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    before = sorted(path.name for path in media.iterdir())
    code, output, printed = freeze(tmp_path, make_plan(tmp_path, media), capsys, "--auto-inventory")
    assert code == 0, printed
    result = json.loads(printed)
    assert result["sourceInventory"]["generated"] == "auto"
    assert result["sourceInventory"]["provided"] is True
    assert result["paidRequestsSent"] == 0 and result["qualityGate"] is None
    assert "source-inventory.json" in result["files"]
    frozen, _ = read_freeze(output)
    assert frozen["schemaVersion"] == "benchmark-freeze-v2"
    blockers = frozen["preparation"]["blockers"]
    assert DIFFERENT_GROUPS in blockers and "source_inventory_missing" not in blockers
    assert frozen["preparation"]["readyForIndependentEvaluation"] is False
    assert [row["status"] for row in frozen["sourceInventory"]["sources"]] == ["compared"] * 2
    assert frozen["sourceInventory"]["sharedFootage"]
    # Byte-identical to what the standalone command writes for the same files in the same order.
    standalone = standalone_report(media, tmp_path / "standalone.json")
    capsys.readouterr()
    assert (output / "source-inventory.json").read_bytes() == standalone
    # Nothing was written into the footage directory and no scratch copy is left in the bundle.
    assert sorted(path.name for path in media.iterdir()) == before
    assert not list(output.glob("*.tmp"))


def test_auto_inventory_same_recording_group_has_no_group_blocker(
    tmp_path: Path, media: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    plan = make_plan(tmp_path, media, same_group=True)
    code, output, printed = freeze(tmp_path, plan, capsys, "--auto-inventory")
    assert code == 0, printed
    blockers = read_freeze(output)[0]["preparation"]["blockers"]
    assert DIFFERENT_GROUPS not in blockers
    assert not {"source_inventory_missing", "source_inventory_incomplete"} & set(blockers)


def test_auto_inventory_bundle_is_readable_and_tampering_is_rejected(
    tmp_path: Path, media: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, output, _ = freeze(tmp_path, make_plan(tmp_path, media), capsys, "--auto-inventory")
    assert code == 0
    frozen, digest = read_freeze(output)
    assert frozen["sourceInventory"]["reportSha256"]
    report = output / "source-inventory.json"
    original = report.read_bytes()
    report.write_bytes(original + b" ")
    with pytest.raises(ValueError):
        read_freeze(output)
    report.write_bytes(original)
    assert read_freeze(output)[1] == digest


def test_auto_inventory_and_uploaded_report_are_mutually_exclusive(
    tmp_path: Path, media: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report = tmp_path / "report.json"
    report.write_text("{}", encoding="utf-8")
    code, output, _ = freeze(
        tmp_path,
        make_plan(tmp_path, media),
        capsys,
        "--auto-inventory",
        "--inventory",
        str(report),
    )
    assert code == int(ExitCode.INPUT)
    assert not output.exists()


def test_provided_and_absent_inventory_report_their_origin(
    tmp_path: Path, media: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    plan = make_plan(tmp_path, media)
    code, _, printed = freeze(tmp_path, plan, capsys)
    assert code == 0
    summary = json.loads(printed)["sourceInventory"]
    assert summary["provided"] is False and summary["generated"] is None
    inventory = tmp_path / "盘点.json"
    uploaded = standalone_report(media, inventory)
    capsys.readouterr()
    output = tmp_path / "冻结-上传"
    arguments = ["--input", str(plan), "--output", str(output), "--inventory", str(inventory)]
    assert cli.main(["freeze-benchmark", *arguments]) == 0
    summary = json.loads(capsys.readouterr().out)["sourceInventory"]
    assert summary["provided"] is True and summary["generated"] == "provided"
    assert (output / "source-inventory.json").read_bytes() == uploaded


def test_failed_source_in_auto_inventory_still_freezes_with_incomplete_blocker(
    tmp_path: Path,
    media: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailsOnDerived(FfmpegSignatureExtractor):
        async def signature(self, source, duration_us, context):  # type: ignore[no-untyped-def]
            if source.name == DERIVED:
                raise AppError("input.video", "无法读取源文件。", ExitCode.INPUT)
            return await super().signature(source, duration_us, context)

    monkeypatch.setattr(cli, "FfmpegSignatureExtractor", FailsOnDerived)
    code, output, printed = freeze(tmp_path, make_plan(tmp_path, media), capsys, "--auto-inventory")
    assert code == 0, printed
    frozen, _ = read_freeze(output)
    assert "source_inventory_incomplete" in frozen["preparation"]["blockers"]
    assert [row["status"] for row in frozen["sourceInventory"]["sources"]] == ["compared", "failed"]
    report = json.loads((output / "source-inventory.json").read_text(encoding="utf-8"))
    assert [item["code"] for item in report["failedSources"]] == ["input.video"]
