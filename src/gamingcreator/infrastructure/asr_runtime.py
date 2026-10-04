"""Verify pinned local CRT files and audit loaded runtime origins without native imports."""

import ctypes
import hashlib
import re
import sys
from ctypes import wintypes
from pathlib import Path

from gamingcreator.application.asr import ModelFile

NATIVE_FILES = frozenset(
    {
        "msvcp140.dll",
        "msvcp140_1.dll",
        "msvcp140_2.dll",
        "msvcp140_atomic_wait.dll",
        "msvcp140_codecvt_ids.dll",
        "vcruntime140.dll",
        "vcruntime140_1.dll",
        "vcruntime140_threads.dll",
        "concrt140.dll",
    }
)
_CRT_PREFIXES = ("msvcp140", "vcruntime140", "concrt140")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def verify_native(directory: Path, files: tuple[ModelFile, ...], repository: Path) -> None:
    """Reject incomplete, modified or externally resolved project CRT bundles."""
    root = repository.resolve()
    native = directory.resolve()
    if (
        not native.is_relative_to(root)
        or not native.is_dir()
        or len(files) != len(NATIVE_FILES)
        or {item.name for item in files} != NATIVE_FILES
    ):
        raise ValueError("ASR runtime configuration is invalid.")
    for item in files:
        if (
            type(item.size) is not int
            or item.size <= 0
            or not re.fullmatch(r"[a-f0-9]{64}", item.sha256)
        ):
            raise ValueError("ASR runtime configuration is invalid.")
        path = (native / item.name).resolve()
        if (
            not path.is_relative_to(native)
            or not path.is_relative_to(root)
            or not path.is_file()
            or path.stat().st_size != item.size
            or _sha256(path) != item.sha256
        ):
            raise ValueError("ASR runtime integrity verification failed.")


def _api_error(operation: str) -> OSError:
    return OSError(ctypes.get_last_error(), f"Windows {operation} failed")


def _runtime_module_paths() -> list[Path]:
    if sys.platform != "win32":
        return []
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.argtypes = []
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.K32EnumProcessModules.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.HMODULE),
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel.K32EnumProcessModules.restype = wintypes.BOOL
    kernel.K32GetModuleFileNameExW.argtypes = [
        wintypes.HANDLE,
        wintypes.HMODULE,
        wintypes.LPWSTR,
        wintypes.DWORD,
    ]
    kernel.K32GetModuleFileNameExW.restype = wintypes.DWORD
    process = kernel.GetCurrentProcess()
    if not process:
        raise _api_error("GetCurrentProcess")
    capacity = 256
    width = ctypes.sizeof(wintypes.HMODULE)
    for _ in range(8):
        modules = (wintypes.HMODULE * capacity)()
        needed = wintypes.DWORD()
        if not kernel.K32EnumProcessModules(
            process, modules, ctypes.sizeof(modules), ctypes.byref(needed)
        ):
            raise _api_error("K32EnumProcessModules")
        if needed.value % width:
            raise OSError("Windows module enumeration size is invalid.")
        if needed.value <= ctypes.sizeof(modules):
            break
        capacity = needed.value // width + 16
        if capacity > 65536:
            raise OSError("Windows module enumeration limit exceeded.")
    else:
        raise OSError("Windows module enumeration did not stabilize.")
    paths = []
    for module in modules[: needed.value // width]:
        path_capacity = 260
        while True:
            buffer = ctypes.create_unicode_buffer(path_capacity)
            length = kernel.K32GetModuleFileNameExW(process, module, buffer, path_capacity)
            if not length:
                raise _api_error("K32GetModuleFileNameExW")
            if length < path_capacity - 1:
                paths.append(Path(buffer.value))
                break
            if path_capacity == 32768:
                raise OSError("Windows module path limit exceeded.")
            path_capacity = min(path_capacity * 2, 32768)
    return paths


def loaded_runtime_libraries(repository: Path) -> list[dict[str, str]]:
    """Return loaded CRT identities, failing if a related module resides outside the project."""
    root = repository.resolve()
    libraries = []
    seen = set()
    for candidate in _runtime_module_paths():
        name = candidate.name.lower()
        if not name.endswith(".dll") or not name.startswith(_CRT_PREFIXES):
            continue
        path = candidate.resolve()
        if not path.is_relative_to(root):
            raise ValueError("ASR runtime loaded a library outside the repository.")
        if path not in seen:
            seen.add(path)
            libraries.append({"name": path.name, "path": str(path), "sha256": _sha256(path)})
    return sorted(libraries, key=lambda item: item["path"].casefold())
