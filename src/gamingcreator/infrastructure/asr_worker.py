"""One offline inference invocation. Never import native model packages in the parent process."""
# ruff: noqa: I001

import sys
from pathlib import Path

# Isolated worker starts with -I, so PYTHONPATH is ignored. When this file lives in a
# source checkout, put that checkout first so the worker matches the calling tree.
_SRC = Path(__file__).resolve().parents[2]
if _SRC.name == "src":
    sys.path.insert(0, str(_SRC))

import ctypes  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import time  # noqa: E402
from contextlib import ExitStack, redirect_stdout  # noqa: E402
from typing import cast  # noqa: E402

from gamingcreator.application.asr import ModelFile  # noqa: E402
from gamingcreator.infrastructure.asr_runtime import loaded_runtime_libraries, verify_native  # noqa: E402

WORKER_SCHEMA = "local-asr-worker-v1"
MAX_SEGMENTS = 10000


def _read_request(path: Path) -> dict[str, object]:
    if path.stat().st_size > 1024 * 1024:
        raise ValueError("Request limit.")
    value = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "schema",
        "audioPath",
        "modelDirectory",
        "model",
        "revision",
        "nativeDirectory",
        "nativeFiles",
        "repository",
        "computeType",
        "cpuThreads",
        "beamSize",
        "vadFilter",
        "language",
        "gameTerms",
    }
    if (
        not isinstance(value, dict)
        or not required <= set(value)
        or set(value) - required - {"wordTimestamps"}
    ):
        raise ValueError("Request schema.")
    request = cast(dict[str, object], value)
    if request.get("wordTimestamps") not in (None, True, False):
        raise ValueError("Request values.")
    if (
        request["schema"] != WORKER_SCHEMA
        or any(
            not isinstance(request[key], str) or not request[key]
            for key in (
                "audioPath",
                "modelDirectory",
                "model",
                "revision",
                "language",
                "repository",
            )
        )
        or request["computeType"] != "int8"
        or type(request["cpuThreads"]) is not int
        or request["cpuThreads"] <= 0
        or type(request["beamSize"]) is not int
        or not 0 < request["beamSize"] <= 100
        or type(request["vadFilter"]) is not bool
        or not isinstance(request["gameTerms"], list)
        or not isinstance(request["nativeFiles"], list)
        or any(
            not isinstance(item, dict) or set(item) != {"name", "size", "sha256"}
            for item in request["nativeFiles"]
        )
        or any(not isinstance(term, str) for term in cast(list[object], request["gameTerms"]))
        or (
            request["nativeDirectory"] is not None
            and not isinstance(request["nativeDirectory"], str)
        )
    ):
        raise ValueError("Request values.")
    return request


def _infer(  # noqa: C901
    request: dict[str, object], readiness_path: Path | None = None
) -> dict[str, object]:
    started = time.monotonic()
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["DO_NOT_TRACK"] = "1"
    native = request["nativeDirectory"]
    with ExitStack() as stack, redirect_stdout(sys.stderr):
        try:
            if sys.platform == "win32" and isinstance(native, str):
                files: list[ModelFile] = []
                for item in cast(list[dict[str, object]], request["nativeFiles"]):
                    name, size, digest = item["name"], item["size"], item["sha256"]
                    if (
                        not isinstance(name, str)
                        or type(size) is not int
                        or not isinstance(digest, str)
                    ):
                        raise ValueError("Native file record.")
                    files.append(ModelFile(name, size, digest))
                verify_native(Path(native), tuple(files), Path(str(request["repository"])))
                stack.enter_context(os.add_dll_directory(native))
                # Load before any C++ package; keep both objects alive until iteration completes.
                native_runtime = ctypes.WinDLL(str(Path(native) / "msvcp140.dll"))
                stack.callback(lambda: native_runtime)
            elif sys.platform == "win32":
                raise OSError("Project-local CRT directory required")
            from faster_whisper import WhisperModel  # type: ignore[import-untyped]

            libraries = loaded_runtime_libraries(Path(str(request["repository"])))
        except (ImportError, OSError, ValueError):
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
            word_mode = request.get("wordTimestamps") is True
            if word_mode:
                segments, information = model.transcribe(
                    str(request["audioPath"]),
                    language=None if request["language"] == "auto" else str(request["language"]),
                    beam_size=cast(int, request["beamSize"]),
                    vad_filter=cast(bool, request["vadFilter"]),
                    hotwords=", ".join(cast(list[str], request["gameTerms"])) or None,
                    word_timestamps=True,
                )
            else:
                segments, information = model.transcribe(
                    str(request["audioPath"]),
                    language=None if request["language"] == "auto" else str(request["language"]),
                    beam_size=cast(int, request["beamSize"]),
                    vad_filter=cast(bool, request["vadFilter"]),
                    hotwords=", ".join(cast(list[str], request["gameTerms"])) or None,
                )
            rows: list[dict[str, object]] = []
            words: list[dict[str, object]] = []
            for segment in segments:
                if len(rows) >= MAX_SEGMENTS:
                    raise ValueError("Segment limit.")
                rows.append(
                    {"start": str(segment.start), "end": str(segment.end), "text": segment.text}
                )
                if word_mode:
                    for word in getattr(segment, "words", None) or ():
                        text = getattr(word, "word", None)
                        if text is None:
                            text = getattr(word, "text", None)
                        start = getattr(word, "start", None)
                        end = getattr(word, "end", None)
                        if text is None or start is None or end is None:
                            continue
                        words.append({"start": str(start), "end": str(end), "text": text})
                if len(rows) == 1 and readiness_path is not None:
                    temporary = readiness_path.with_suffix(".tmp")
                    temporary.write_text(
                        json.dumps(
                            {
                                "schema": WORKER_SCHEMA,
                                "pid": os.getpid(),
                                "stage": "inference_started",
                                "completedSegments": 1,
                            }
                        ),
                        encoding="utf-8",
                    )
                    temporary.replace(readiness_path)
            language = information.language
            libraries = loaded_runtime_libraries(Path(str(request["repository"])))
        except Exception:
            return {"schema": WORKER_SCHEMA, "status": "failed", "code": "asr.inference"}
    result = {
        "schema": WORKER_SCHEMA,
        "status": "completed",
        "model": request["model"],
        "revision": request["revision"],
        "language": language,
        "elapsedMs": max(0, int((time.monotonic() - started) * 1000)),
        "segments": rows,
        "nativeLibraries": libraries,
    }
    if request.get("wordTimestamps") is True:
        result["words"] = words
    return result


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
