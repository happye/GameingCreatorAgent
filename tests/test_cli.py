import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from gamingcreator.cli.main import main
from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure.local_files import LocalInputReader


@pytest.fixture
def inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    video = tmp_path / "中文 空格.mp4"
    video.write_bytes(b"readable file; container decoding belongs to F002")
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "vision": {"provider": "deepseek", "model": "deepseek-flash"},
                "limits": {"maxRequests": 2, "maxInputFrames": 5},
            }
        ),
        encoding="utf-8",
    )
    return video, config, tmp_path / "not-created"


def analyze_args(video: Path, config: Path, project: Path, budget: str = "1.00") -> list[str]:
    return [
        "analyze",
        str(video),
        "--project",
        str(project),
        "--config",
        str(config),
        f"--max-cost-cny={budget}",
    ]


def test_module_cli_rejects_undecodable_video_without_creating_project(
    inputs: tuple[Path, Path, Path],
) -> None:
    video, config, project = inputs
    result = subprocess.run(
        [sys.executable, "-m", "gamingcreator", *analyze_args(video, config, project)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        env=os.environ | {"PYTHONUTF8": "1"},
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert json.loads(result.stderr)["code"] == "input.media_decode"
    assert not project.exists()


@pytest.mark.parametrize("source_kind", ["missing", "directory", "empty"])
def test_invalid_video_has_no_project_side_effects(
    inputs: tuple[Path, Path, Path],
    source_kind: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    video, config, project = inputs
    if source_kind == "missing":
        video.unlink()
    elif source_kind == "directory":
        video.unlink()
        video.mkdir()
    else:
        video.write_bytes(b"")
    assert main(analyze_args(video, config, project)) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert json.loads(captured.err) == {
        "code": "input.video",
        "runId": None,
        "retryable": False,
        "message": "视频必须是可读取的非空本地文件。",
    }
    assert not project.exists()


def test_unreadable_video_is_sanitized(
    inputs: tuple[Path, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    video, config, project = inputs
    original_open = Path.open

    def deny_source(path: Path, *args: object, **kwargs: object) -> object:
        if path == video:
            raise PermissionError("private credential in low-level error")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", deny_source)
    assert main(analyze_args(video, config, project)) == 2
    assert "private credential" not in capsys.readouterr().err
    assert not project.exists()


@pytest.mark.parametrize("budget", ["0", "-1", "NaN", "Infinity", "-Infinity", "not-a-number"])
def test_invalid_budget_does_not_create_project(
    inputs: tuple[Path, Path, Path],
    budget: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(analyze_args(*inputs, budget=budget)) == 2
    assert json.loads(capsys.readouterr().err)["code"] == "input.budget"
    assert not inputs[2].exists()


@pytest.mark.parametrize(
    "content",
    ["", "{", "[]", '{"schemaVersion":true}', '{"apiKey":"secret-value"}'],
)
def test_invalid_config_is_rejected_without_echoing_contents(
    inputs: tuple[Path, Path, Path],
    content: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    video, config, project = inputs
    config.write_text(content, encoding="utf-8")
    assert main(analyze_args(video, config, project)) == 3
    captured = capsys.readouterr()
    assert json.loads(captured.err)["code"] == "configuration.invalid"
    assert "secret-value" not in captured.err
    assert captured.out == ""
    assert not project.exists()


def test_config_accepts_only_versioned_nonsecret_fields(inputs: tuple[Path, Path, Path]) -> None:
    _, config, _ = inputs
    parsed = LocalInputReader().load_config(config)
    assert parsed.provider == "deepseek" and parsed.max_requests == 2
    raw = json.loads(config.read_text(encoding="utf-8"))
    raw["vision"]["apiKey"] = "secret-value"
    config.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(AppError, match="配置文件无效"):
        LocalInputReader().load_config(config)


def test_resume_does_not_allow_configuration_override(
    inputs: tuple[Path, Path, Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main([*analyze_args(*inputs), "--resume", "old-run"]) == 2
    assert json.loads(capsys.readouterr().err)["code"] == "input.resume"
    assert not inputs[2].exists()


@pytest.mark.parametrize("resume", ["old-run", "   "])
def test_resume_only_obeys_contract_without_creating_project(
    inputs: tuple[Path, Path, Path],
    resume: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    video, _, project = inputs
    result = main(["analyze", str(video), "--project", str(project), "--resume", resume])
    assert result == 2
    assert json.loads(capsys.readouterr().err)["code"] == "input.resume"
    assert not project.exists()


def test_resume_forbids_budget_override(inputs: tuple[Path, Path, Path]) -> None:
    video, _, project = inputs
    assert (
        main(
            [
                "analyze",
                str(video),
                "--project",
                str(project),
                "--resume",
                "old-run",
                "--max-cost-cny=1",
            ]
        )
        == 2
    )
    assert not project.exists()


def test_new_analysis_requires_config_and_budget(inputs: tuple[Path, Path, Path]) -> None:
    video, _, project = inputs
    assert main(["analyze", str(video), "--project", str(project)]) == 2
    assert not project.exists()


def test_argument_error_is_json_and_never_echoes_unknown_values(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["--unexpected-secret-value"]) == 2
    captured = capsys.readouterr()
    assert json.loads(captured.err)["code"] == "input.arguments"
    assert "unexpected-secret-value" not in captured.err and captured.out == ""


def test_search_and_benchmark_remain_unimplemented(
    inputs: tuple[Path, Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    _, _, project = inputs
    assert main(["search", "机制", "--project", str(project), "--run", "run-1"]) == 3
    assert json.loads(capsys.readouterr().err)["code"] == "feature.not_implemented"
    assert (
        main(
            [
                "benchmark",
                "--input",
                "labels.json",
                "--project",
                str(project),
                "--output",
                "out.json",
            ]
        )
        == 3
    )
    assert not project.exists()


def test_help_and_version_are_successful(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--help"]) == 0
    assert "analyze" in capsys.readouterr().out
    assert main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == "gamingcreator 0.1.0"
