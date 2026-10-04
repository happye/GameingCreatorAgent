"""Offline CPU inference; executed as an isolated script so worktree tests use owned code."""

import ctypes
import hashlib
import json
import os
import sys
from contextlib import ExitStack, redirect_stdout
from pathlib import Path
from typing import Any

# -I removes cwd and PYTHONPATH. Explicitly load this reviewed source tree only.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from gamingcreator.application.asr import ModelFile  # noqa: E402
from gamingcreator.infrastructure.asr_runtime import (  # noqa: E402
    loaded_runtime_libraries,
    verify_native,
)

SCHEMA = "local-e5-onnx-v2"


def _infer(request: dict[str, Any]) -> dict[str, object]:
    root = Path(request["repository"]).resolve()
    model = Path(request["modelDirectory"]).resolve()
    if request["schema"] != SCHEMA or not model.is_relative_to(root):
        raise ValueError("Invalid worker identity")
    for item in request["modelFiles"]:
        path = (model / item["name"]).resolve()
        if not path.is_relative_to(model) or path.stat().st_size != item["size"]:
            raise ValueError("Invalid model path")
        digest = hashlib.sha256()
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
        if digest.hexdigest() != item["sha256"]:
            raise ValueError("Model integrity failed")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    with ExitStack() as stack, redirect_stdout(sys.stderr):
        if sys.platform == "win32":
            native = Path(request["nativeDirectory"]).resolve()
            files = tuple(
                ModelFile(item["name"], item["size"], item["sha256"])
                for item in request["nativeFiles"]
            )
            verify_native(native, files, root)
            stack.enter_context(os.add_dll_directory(str(native)))
            runtime_handle = ctypes.WinDLL(str(native / "msvcp140.dll"))
        import numpy as np
        import onnxruntime as ort  # type: ignore[import-untyped]
        from tokenizers import Tokenizer

        tokenizer = Tokenizer.from_file(str(model / "tokenizer.json"))
        pad_id = tokenizer.token_to_id("<pad>")
        if pad_id is None:
            raise ValueError("Tokenizer pad identity missing")
        tokenizer.enable_truncation(max_length=512)
        tokenizer.enable_padding(pad_id=pad_id, pad_token="<pad>")
        options = ort.SessionOptions()
        options.intra_op_num_threads = request["cpuThreads"]
        options.inter_op_num_threads = 1
        session = ort.InferenceSession(
            str(model / "onnx/model_quantized.onnx"),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
        input_names = {item.name for item in session.get_inputs()}
        if not {"input_ids", "attention_mask"} <= input_names or input_names - {
            "input_ids",
            "attention_mask",
            "token_type_ids",
        }:
            raise ValueError("Unsupported ONNX input schema")
        vectors = []
        # Dynamic quantization depends on batch activations. A fixed single-text batch
        # makes textHash cache reuse independent of unrelated request texts and padding.
        for text in request["texts"]:
            encoded = tokenizer.encode_batch([text])
            ids = np.asarray([item.ids for item in encoded], dtype=np.int64)
            mask = np.asarray([item.attention_mask for item in encoded], dtype=np.int64)
            inputs = {"input_ids": ids, "attention_mask": mask}
            if "token_type_ids" in input_names:
                inputs["token_type_ids"] = np.asarray(
                    [item.type_ids for item in encoded], dtype=np.int64
                )
            hidden = np.asarray(session.run(None, inputs)[0], dtype=np.float32)
            if hidden.ndim != 3 or hidden.shape[:2] != ids.shape or hidden.shape[2] != 384:
                raise ValueError("Unsupported ONNX output schema")
            denominator = mask.sum(axis=1, keepdims=True)
            if np.any(denominator == 0):
                raise ValueError("Empty tokenizer output")
            pooled = (hidden * mask[:, :, None]).sum(axis=1) / denominator
            norms = np.linalg.norm(pooled, axis=1, keepdims=True)
            if np.any(norms == 0) or not np.all(np.isfinite(pooled)):
                raise ValueError("Invalid embedding output")
            vectors.extend((pooled / norms).tolist())
        libraries = loaded_runtime_libraries(root)
        if sys.platform == "win32":
            # Keep the explicit handle and DLL-directory registration alive through all batches.
            assert runtime_handle is not None
    return {"schema": SCHEMA, "vectors": vectors, "nativeLibraries": libraries}


def main() -> int:
    try:
        path = Path(sys.argv[1])
        if path.stat().st_size > 16 * 1024 * 1024:
            raise ValueError("Request exceeds limit")
        request = json.loads(path.read_text(encoding="utf-8"))
        response = _infer(request)
        print(json.dumps(response, ensure_ascii=True, allow_nan=False, separators=(",", ":")))
        return 0
    except Exception:
        print("embedding.worker_failed: offline inference did not complete", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
