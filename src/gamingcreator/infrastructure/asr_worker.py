"""One offline inference invocation. Never import native model packages in the parent process."""

import ctypes
import json
import os
import sys
import time
from contextlib import ExitStack, redirect_stdout
from pathlib import Path
from typing import cast

WORKER_SCHEMA = "local-asr-worker-v1"
MAX_SEGMENTS = 10000


def _read_request(path: Path) -> dict[str, object]:
    if path.stat().st_size > 1024 * 1024:
        raise ValueError("Request limit.")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or set(value) != {
        "schema",
        "audioPath",
        "modelDirectory",
        "model",
        "revision",
        "nativeDirectory",
        "computeType",
        "cpuThreads",
        "beamSize",
        "vadFilter",
        "language",
        "gameTerms",
    }:
        raise ValueError("Request schema.")
    request = cast(dict[str, object], value)
    if (
        request["schema"] != WORKER_SCHEMA
        or any(
            not isinstance(request[key], str) or not request[key]
            for key in ("audioPath", "modelDirectory", "model", "revision", "language")
        )
        or request["computeType"] != "int8"
        or type(request["cpuThreads"]) is not int
        or request["cpuThreads"] <= 0
        or type(request["beamSize"]) is not int
        or not 0 < request["beamSize"] <= 100
        or type(request["vadFilter"]) is not bool
        or not isinstance(request["gameTerms"], list)
        or any(not isinstance(term, str) for term in cast(list[object], request["gameTerms"]))
        or (
            request["nativeDirectory"] is not None
            and not isinstance(request["nativeDirectory"], str)
        )
    ):
        raise ValueError("Request values.")
    return request


def _infer(request: dict[str, object], readiness_path: Path | None = None) -> dict[str, object]:
    started = time.monotonic()
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["DO_NOT_TRACK"] = "1"
    native = request["nativeDirectory"]
    with ExitStack() as stack, redirect_stdout(sys.stderr):
        try:
            if sys.platform == "win32" and isinstance(native, str):
                stack.enter_context(os.add_dll_directory(native))
                # Load before any C++ package; keep both objects alive until iteration completes.
                native_runtime = ctypes.WinDLL(str(Path(native) / "msvcp140.dll"))
                stack.callback(lambda: native_runtime)
            elif sys.platform == "win32":
                raise OSError("Project-local CRT directory required")
            from faster_whisper import WhisperModel  # type: ignore[import-untyped]
        except (ImportError, OSError):
            return {"schema": WORKER_SCHEMA, "status": "failed", "code": "asr.runtime_unavailable"}
        try:
            model = WhisperModel(
                str(request["modelDirectory"]),
                device="cpu",
                compute_type="int8",
                cpu_threads=cast(int, request["cpuThreads"]),
                num_workers=1,
                local_files_only=True,
            )
        except Exception:
            return {"schema": WORKER_SCHEMA, "status": "failed", "code": "asr.model_load"}
        try:
            if readiness_path is not None:
                temporary = readiness_path.with_suffix(".tmp")
                temporary.write_text(
                    json.dumps(
                        {"schema": WORKER_SCHEMA, "pid": os.getpid(), "stage": "inference_started"}
                    ),
                    encoding="utf-8",
                )
                temporary.replace(readiness_path)
            segments, information = model.transcribe(
                str(request["audioPath"]),
                language=None if request["language"] == "auto" else str(request["language"]),
                beam_size=cast(int, request["beamSize"]),
                vad_filter=cast(bool, request["vadFilter"]),
                hotwords=", ".join(cast(list[str], request["gameTerms"])) or None,
            )
            rows: list[dict[str, object]] = []
            for segment in segments:
                if len(rows) >= MAX_SEGMENTS:
                    raise ValueError("Segment limit.")
                rows.append(
                    {"start": str(segment.start), "end": str(segment.end), "text": segment.text}
                )
            language = information.language
        except Exception:
            return {"schema": WORKER_SCHEMA, "status": "failed", "code": "asr.inference"}
    return {
        "schema": WORKER_SCHEMA,
        "status": "completed",
        "model": request["model"],
        "revision": request["revision"],
        "language": language,
        "elapsedMs": max(0, int((time.monotonic() - started) * 1000)),
        "segments": rows,
    }


def main() -> None:
    try:
        if len(sys.argv) != 2:
            raise ValueError("Request argument.")
        request_path = Path(sys.argv[1])
        result = _infer(_read_request(request_path), request_path.with_name("ready.json"))
    except Exception:
        result = {"schema": WORKER_SCHEMA, "status": "failed", "code": "asr.worker_input"}
    # ASCII JSON is independent of the Windows pipe code page; text escapes decode losslessly.
    sys.stdout.write(json.dumps(result, ensure_ascii=True, allow_nan=False))
    sys.stdout.flush()


if __name__ == "__main__":
    main()
