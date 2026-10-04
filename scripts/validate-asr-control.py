"""Cancel and time out a real local ASR inference after the readiness handshake.

The source bundle is reloaded from the completed four-video run through TimelineStore.
No paid API. Transcript text is not graded. A passing report is not F003 acceptance.
"""

import asyncio
import ctypes
import json
import os
import time
import uuid
from importlib.metadata import version
from pathlib import Path

from gamingcreator.application.asr import LocalAsrSettings, ModelFile
from gamingcreator.application.providers import AsrRequest, CancellationContext, ProviderStatus
from gamingcreator.domain.media import MediaPreprocessingResult
from gamingcreator.domain.models import EvidenceReference
from gamingcreator.infrastructure.local_asr import WORKER_SCHEMA, LocalAsrProvider
from gamingcreator.infrastructure.sqlite_store import SqliteTimelineStore

SOURCE_PROJECT = Path("artifacts/asr-F003/6133e370bc014955aa0585ac3db0528a")
SOURCE_RUN = "asr-002"
SOURCE_SHA256 = "dd4cc33653bd7c8b6a4c2040e22fc6dd1354ed7f910555b644e01739f8366e2d"
PRIOR_FULL_ELAPSED_MS = 21428


def load_settings(repository: Path) -> LocalAsrSettings:
    pin = json.loads((repository / "docs/references/asr-models.json").read_text(encoding="utf-8"))
    native = json.loads(
        (repository / "docs/references/asr-native-toolchain.json").read_text(encoding="utf-8")
    )
    native_directory = repository / ".tools/native/msvc" / native["version"]
    return LocalAsrSettings(
        repository / ".cache/models/faster-whisper/tiny" / pin["revision"],
        pin["model"],
        pin["revision"],
        tuple(ModelFile(**file) for file in pin["files"]),
        native_directory,
        native_library_files=tuple(
            ModelFile(name, (native_directory / name).stat().st_size, sha)
            for name, sha in native["files"].items()
        ),
    )


def write_report(report: Path, payload: dict[str, object]) -> None:
    temporary = report.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as output:
        output.write(json.dumps(payload, ensure_ascii=False, indent=2))
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(report)


def snapshot_requests(repository: Path) -> set[Path]:
    root = repository / ".cache" / "asr-requests"
    if not root.exists():
        return set()
    return {path for path in root.iterdir() if path.is_dir()}


class ProcessWatch:
    def __init__(self, pid: int) -> None:
        self.pid = pid
        self._kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self._kernel.OpenProcess.restype = ctypes.c_void_p
        self._kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        self._kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        self._kernel.WaitForSingleObject.restype = ctypes.c_uint32
        self._kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        self._handle: int | None = None
        handle = self._kernel.OpenProcess(0x100000, False, pid)
        if not isinstance(handle, int) or handle == 0:
            raise OSError(ctypes.get_last_error(), f"OpenProcess failed for pid {pid}")
        self._handle = handle

    def wait_ms(self, timeout_ms: int) -> int:
        if self._handle is None:
            raise RuntimeError("Process handle is closed.")
        return int(self._kernel.WaitForSingleObject(self._handle, timeout_ms))

    def close(self) -> None:
        if self._handle is not None:
            self._kernel.CloseHandle(self._handle)
            self._handle = None


def request_for(run_id: str, bundle: MediaPreprocessingResult) -> AsrRequest:
    audio = bundle.audio
    if audio is None:
        raise RuntimeError("Stored speech bundle has no audio.")
    mapped = audio.map_interval(0, audio.sample_count, bundle.asset)
    reference = EvidenceReference(
        audio.evidence_id,
        bundle.asset.media_id,
        "audio",
        mapped.source_range,
        audio.path,
        audio.sha256,
        bundle.transform_version,
    )
    return AsrRequest(
        run_id,
        reference,
        "transcript-v1",
        "auto",
        media_asset=bundle.asset,
        audio_clock=audio,
    )


async def wait_ready(
    repository: Path,
    baseline: set[Path],
    task: asyncio.Task[object],
    timeout_s: float,
) -> tuple[dict[str, object], Path, ProcessWatch]:
    root = repository / ".cache" / "asr-requests"
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if task.done():
            raise RuntimeError("Worker finished before the readiness handshake.")
        if root.exists():
            for directory in root.iterdir():
                if directory in baseline or not directory.is_dir():
                    continue
                ready_path = directory / "ready.json"
                if not ready_path.is_file():
                    continue
                try:
                    payload = json.loads(ready_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    continue
                if not isinstance(payload, dict):
                    continue
                ready = {str(key): value for key, value in payload.items()}
                pid = ready.get("pid")
                if (
                    set(ready) != {"schema", "pid", "stage", "completedSegments"}
                    or ready.get("schema") != WORKER_SCHEMA
                    or ready.get("stage") != "inference_started"
                    or ready.get("completedSegments") != 1
                    or type(pid) is not int
                    or pid <= 0
                ):
                    raise RuntimeError("Readiness payload did not match the worker contract.")
                return ready, directory, ProcessWatch(pid)
        await asyncio.sleep(0.05)
    raise RuntimeError("Readiness handshake was not observed before the deadline.")


def outcome(result: object) -> dict[str, object]:
    status = getattr(result, "status", None)
    error = getattr(result, "error", None)
    output = getattr(result, "output", None)
    return {
        "status": None if status is None else status.value,
        "error": None if error is None else error.code,
        "outputPublished": output is not None,
        "segmentCount": 0 if output is None else len(output),
    }


def passed_control(summary: dict[str, object], *, error_code: str, status: str) -> bool:
    return (
        summary.get("status") == status
        and summary.get("error") == error_code
        and summary.get("outputPublished") is False
        and summary.get("segmentCount") == 0
        and summary.get("readyContract") is True
        and summary.get("processExited") is True
        and summary.get("requestDirectoryRemoved") is True
    )


async def drive(
    repository: Path,
    provider: LocalAsrProvider,
    bundle: MediaPreprocessingResult,
    *,
    run_id: str,
    timeout_seconds: float,
    cancel_on_ready: bool,
) -> dict[str, object]:
    request = request_for(run_id, bundle)
    context = CancellationContext(run_id, timeout_seconds)
    baseline = snapshot_requests(repository)
    started = time.monotonic()
    task: asyncio.Task[object] = asyncio.create_task(provider.transcribe(request, context))
    watch: ProcessWatch | None = None
    ready_directory: Path | None = None
    summary: dict[str, object] = {
        "runId": run_id,
        "timeoutSeconds": timeout_seconds,
        "cancelOnReady": cancel_on_ready,
        "readyContract": False,
    }
    try:
        ready, ready_directory, watch = await wait_ready(repository, baseline, task, 120)
        summary["ready"] = ready
        summary["readyElapsedMs"] = max(0, int((time.monotonic() - started) * 1000))
        summary["readyContract"] = True
        if cancel_on_ready:
            context.cancelled.set()
        result = await task
        summary.update(outcome(result))
        summary["elapsedMs"] = max(0, int((time.monotonic() - started) * 1000))
        wait_result = watch.wait_ms(5000)
        summary["processWait"] = wait_result
        summary["processExited"] = wait_result == 0
        summary["requestDirectoryRemoved"] = not ready_directory.exists()
        return summary
    except Exception as error:
        if not task.done():
            context.cancelled.set()
        result = await task
        summary.update(outcome(result))
        summary["elapsedMs"] = max(0, int((time.monotonic() - started) * 1000))
        summary["driverError"] = f"{type(error).__name__}: {error}"
        if watch is not None:
            wait_result = watch.wait_ms(5000)
            summary["processWait"] = wait_result
            summary["processExited"] = wait_result == 0
        if ready_directory is not None:
            summary["requestDirectoryRemoved"] = not ready_directory.exists()
        return summary
    finally:
        if watch is not None:
            watch.close()


def timeout_seconds_for(ready_ms: int) -> float:
    ready_s = ready_ms / 1000
    prior_s = PRIOR_FULL_ELAPSED_MS / 1000
    candidate = ready_s + 4.0
    if candidate > prior_s - 3:
        candidate = ready_s + max(1.0, (prior_s - ready_s) / 2)
    if candidate <= ready_s + 0.4:
        raise RuntimeError("No timeout window remains after the readiness handshake.")
    return candidate


def retry_timeout(attempt: dict[str, object], first_ready_ms: int) -> float | None:
    observed = attempt.get("readyElapsedMs")
    elapsed = attempt.get("elapsedMs")
    if (
        attempt.get("status") == ProviderStatus.COMPLETED.value
        and type(observed) is int
        and type(elapsed) is int
        and elapsed > observed + 800
    ):
        return observed / 1000 + max(0.8, (elapsed - observed) / 2000)
    if attempt.get("readyContract") is not True and attempt.get("error") == "asr.timeout":
        later = min(PRIOR_FULL_ELAPSED_MS / 1000 - 2, first_ready_ms / 1000 + 8)
        if later > first_ready_ms / 1000 + 0.4:
            return later
    return None


async def validate(repository: Path) -> Path:
    project = repository / "artifacts" / "asr-F003" / uuid.uuid4().hex
    project.mkdir(parents=True)
    report = project / "validation.json"
    provider = LocalAsrProvider(repository, load_settings(repository))
    store = await SqliteTimelineStore.open(repository / SOURCE_PROJECT, read_only=True)
    try:
        bundle = await store.load_media_bundle(SOURCE_RUN)
    finally:
        await store.close()
    if bundle.asset.sha256 != SOURCE_SHA256 or bundle.audio is None:
        raise RuntimeError("Stored media bundle is not the previously completed speech recording.")
    payload: dict[str, object] = {
        "feature": "F003-ASR-control",
        "scope": "real inference cancel and timeout after readiness; ungraded; no network API",
        "state": "running",
        "validationPassed": None,
        "sourceRun": SOURCE_RUN,
        "sourceProject": SOURCE_PROJECT.as_posix(),
        "sourceSha256": bundle.asset.sha256,
        "audioSha256": bundle.audio.sha256,
        "priorFullElapsedMs": PRIOR_FULL_ELAPSED_MS,
        "packageVersions": {
            package: version(package)
            for package in ("faster-whisper", "ctranslate2", "av", "onnxruntime")
        },
    }
    write_report(report, payload)
    print(json.dumps({"phase": "cancel", "report": str(report)}), flush=True)
    cancel = await drive(
        repository,
        provider,
        bundle,
        run_id="asr-cancel",
        timeout_seconds=180,
        cancel_on_ready=True,
    )
    payload["cancel"] = cancel
    write_report(report, payload)
    print(
        json.dumps(
            {
                "phase": "cancel-finished",
                "status": cancel.get("status"),
                "error": cancel.get("error"),
                "readyElapsedMs": cancel.get("readyElapsedMs"),
                "processExited": cancel.get("processExited"),
                "driverError": cancel.get("driverError"),
            }
        ),
        flush=True,
    )
    attempts: list[dict[str, object]] = []
    ready_ms = cancel.get("readyElapsedMs")
    if cancel.get("readyContract") is True and type(ready_ms) is int:
        timeout_seconds = timeout_seconds_for(ready_ms)
        print(json.dumps({"phase": "timeout", "timeoutSeconds": timeout_seconds}), flush=True)
        attempt = await drive(
            repository,
            provider,
            bundle,
            run_id="asr-timeout",
            timeout_seconds=timeout_seconds,
            cancel_on_ready=False,
        )
        attempts.append(attempt)
        write_report(report, {**payload, "timeoutAttempts": attempts})
        print(
            json.dumps(
                {
                    "phase": "timeout-finished",
                    "status": attempt.get("status"),
                    "error": attempt.get("error"),
                    "readyContract": attempt.get("readyContract"),
                    "processExited": attempt.get("processExited"),
                }
            ),
            flush=True,
        )
        if not passed_control(
            attempt, error_code="asr.timeout", status=ProviderStatus.FAILED.value
        ):
            retry_seconds = retry_timeout(attempt, ready_ms)
            if retry_seconds is not None:
                print(
                    json.dumps({"phase": "timeout-retry", "timeoutSeconds": retry_seconds}),
                    flush=True,
                )
                retry = await drive(
                    repository,
                    provider,
                    bundle,
                    run_id="asr-timeout-retry",
                    timeout_seconds=retry_seconds,
                    cancel_on_ready=False,
                )
                retry["retriedBecause"] = "first deadline missed the post-readiness window"
                attempts.append(retry)
    payload["timeoutAttempts"] = attempts
    payload["timeout"] = None if not attempts else attempts[-1]
    timeout = None if not attempts else attempts[-1]
    cancel_ok = passed_control(
        cancel, error_code="asr.cancelled", status=ProviderStatus.CANCELLED.value
    )
    timeout_ok = timeout is not None and passed_control(
        timeout, error_code="asr.timeout", status=ProviderStatus.FAILED.value
    )
    payload["state"] = "completed"
    payload["validationPassed"] = cancel_ok and timeout_ok
    write_report(report, payload)
    print(
        json.dumps({"report": str(report), "validationPassed": payload["validationPassed"]}),
        flush=True,
    )
    return report


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    report = asyncio.run(validate(repository))
    passed = json.loads(report.read_text(encoding="utf-8"))["validationPassed"]
    return 0 if passed is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
