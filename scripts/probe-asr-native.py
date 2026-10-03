"""Explicit local-only native probe; no model download or network inference."""

import ctypes
import hashlib
import json
import os
import sys
from pathlib import Path


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    pin = json.loads((repository / "docs/references/asr-native-toolchain.json").read_text())
    native = repository / ".tools/native/msvc" / pin["version"]
    for name, expected in pin["files"].items():
        if hashlib.sha256((native / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Native library hash mismatch")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    with os.add_dll_directory(str(native)):
        # Resolve MSVCP from the pinned app-local directory before any C++ package.
        library = ctypes.WinDLL(str(native / "msvcp140.dll"))
        import av
        import ctranslate2
        import faster_whisper
        import numpy as np
        import onnxruntime
        from faster_whisper.vad import get_vad_model

        vad = get_vad_model()
        prediction = vad(np.zeros(512 * 32, dtype=np.float32))
        supported = sorted(ctranslate2.get_supported_compute_types("cpu"))
        if "int8" not in supported or vad.session.get_providers() != ["CPUExecutionProvider"]:
            raise ValueError("CPU ASR/VAD prerequisites unavailable")
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        kernel.K32EnumProcessModules.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.c_void_p,
        ]
        kernel.K32GetModuleFileNameExW.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_wchar_p,
            ctypes.c_uint32,
        ]
        modules = (ctypes.c_void_p * 2048)()
        needed = ctypes.c_uint32()
        process = kernel.GetCurrentProcess()
        if not kernel.K32EnumProcessModules(
            process, modules, ctypes.sizeof(modules), ctypes.byref(needed)
        ):
            raise OSError("Native module enumeration failed")
        loaded = []
        for index in range(needed.value // ctypes.sizeof(ctypes.c_void_p)):
            path = ctypes.create_unicode_buffer(32768)
            if not kernel.K32GetModuleFileNameExW(process, modules[index], path, len(path)):
                raise OSError("Native module path unavailable")
            location = Path(path.value)
            if location.name.lower().startswith(("msvcp140", "vcruntime140", "concrt140")):
                if not location.resolve().is_relative_to(repository):
                    raise ValueError("Third-party CRT resolved outside the project")
                loaded.append(
                    {
                        "name": location.name,
                        "path": str(location.relative_to(repository)),
                        "sha256": hashlib.sha256(location.read_bytes()).hexdigest(),
                    }
                )
        model = Path(faster_whisper.__file__).parent / "assets/silero_vad_v6.onnx"
        output = {
            "status": "completed",
            "cpuInt8": True,
            "vadProviders": vad.session.get_providers(),
            "vadOutputShape": list(prediction.shape),
            "nativeLibraries": loaded,
            "packageVersions": {
                "faster-whisper": faster_whisper.__version__,
                "ctranslate2": ctranslate2.__version__,
                "av": av.__version__,
                "onnxruntime": onnxruntime.__version__,
            },
            "vadSha256": hashlib.sha256(model.read_bytes()).hexdigest(),
            "msvcpHandleLoaded": bool(library._handle),
        }
        print(json.dumps(output))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, ImportError):
        print(
            "Local native ASR probe failed; no installer or network fallback was run.",
            file=sys.stderr,
        )
        raise SystemExit(3) from None
