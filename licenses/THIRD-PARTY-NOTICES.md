# Third-Party Notices

This folder lists license texts that were **already present on disk** when the portable app was assembled. Nothing here was downloaded by the collector.

First-party code (`gamingcreator`) and developer-only packages (pytest/mypy/ruff/…) are omitted.

| Component | Version | License (as found) | Source file | Copied to | Status |
| --- | --- | --- | --- | --- | --- |
| CPython | cpython-3.13.16-windows-x86_64-none | PSF / historical (see LICENSE.txt) | .tools/python/cpython-3.13.16-windows-x86_64-none/LICENSE.txt | sources/cpython/LICENSE.txt | ok |
| FFmpeg | N-123317-gc1be2107c9-20260310 | GPL (enabled in build flags); production LICENSE.txt missing on disk | docs/references/media-toolchain.json | sources/ffmpeg/BUILD-AND-PROVENANCE.txt | noted_without_file |
| Microsoft.Web.WebView2 | 1.0.4314.35 | Microsoft WebView2 SDK license (LICENSE.txt in the package); redistribution terms must be reviewed before shipping an installer. | .tools/webview2/1.0.4314.35/files/LICENSE.txt | sources/webview2/LICENSE.txt | ok |
| Microsoft Visual C++ Redistributable (local pin) | 14.51.36247 | Microsoft redistributable terms (file missing locally) | .tools/native/msvc/14.51.36247/receipt.json | sources/msvc-native/README.txt | noted_without_file |
| Xenova/multilingual-e5-small | 761b726dd34fb83930e26aab4e9ac3899aa1fa78 | MIT (base model); exported artifact licensing requires release review | docs/references/embedding-model.json | sources/models/multilingual-e5-small/embedding-model.json | noted_without_file |
| Systran/faster-whisper-tiny | d90ca5fe260221311c53c58e660288d3deb8d356 | UNKNOWN (no LICENSE file next to model weights) | docs/references/asr-models.json | sources/models/faster-whisper-tiny/asr-models.json | missing_license_file |
| anyio | 4.15.1 | MIT | .venv/Lib/site-packages/anyio-4.15.1.dist-info/licenses/LICENSE | sources/python/anyio-4.15.1/licenses/LICENSE | ok |
| ast_serialize | 0.12.1 | MIT | .venv/Lib/site-packages/ast_serialize-0.12.1.dist-info/licenses/crates/LICENSE | sources/python/ast_serialize-0.12.1/licenses/crates/LICENSE | ok |
| av | 16.1.0 | BSD-3-Clause | .venv/Lib/site-packages/av-16.1.0.dist-info/licenses/LICENSE.txt | sources/python/av-16.1.0/licenses/LICENSE.txt | ok |
| certifi | 2026.7.22 | MPL-2.0 | .venv/Lib/site-packages/certifi-2026.7.22.dist-info/licenses/LICENSE | sources/python/certifi-2026.7.22/licenses/LICENSE | ok |
| click | 8.5.0 | BSD-3-Clause | .venv/Lib/site-packages/click-8.5.0.dist-info/licenses/LICENSE.txt | sources/python/click-8.5.0/licenses/LICENSE.txt | ok |
| colorama | 0.4.6 | OSI Approved :: BSD License | .venv/Lib/site-packages/colorama-0.4.6.dist-info/licenses/LICENSE.txt | sources/python/colorama-0.4.6/licenses/LICENSE.txt | ok |
| ctranslate2 | 4.8.2 | MIT | .venv/Lib/site-packages/ctranslate2-4.8.2.dist-info/METADATA | sources/python/ctranslate2-4.8.2/METADATA | missing_license_file |
| faster-whisper | 1.2.1 | MIT | .venv/Lib/site-packages/faster_whisper-1.2.1.dist-info/LICENSE | sources/python/faster-whisper-1.2.1/LICENSE | ok |
| filelock | 4.0.9 | MIT | .venv/Lib/site-packages/filelock-4.0.9.dist-info/licenses/LICENSE | sources/python/filelock-4.0.9/licenses/LICENSE | ok |
| flatbuffers | 25.12.19 | Apache 2.0 | .venv/Lib/site-packages/flatbuffers-25.12.19.dist-info/METADATA | sources/python/flatbuffers-25.12.19/METADATA | missing_license_file |
| fsspec | 2026.9.0 | BSD-3-Clause | .venv/Lib/site-packages/fsspec-2026.9.0.dist-info/licenses/LICENSE | sources/python/fsspec-2026.9.0/licenses/LICENSE | ok |
| greenlet | 3.5.6 | MIT AND PSF-2.0 | .venv/Lib/site-packages/greenlet-3.5.6.dist-info/licenses/LICENSE | sources/python/greenlet-3.5.6/licenses/LICENSE | ok |
| h11 | 0.16.0 | MIT | .venv/Lib/site-packages/h11-0.16.0.dist-info/licenses/LICENSE.txt | sources/python/h11-0.16.0/licenses/LICENSE.txt | ok |
| hf-xet | 1.6.0 | Apache-2.0 | .venv/Lib/site-packages/hf_xet-1.6.0.dist-info/licenses/LICENSE | sources/python/hf-xet-1.6.0/licenses/LICENSE | ok |
| httpcore | 1.0.9 | BSD-3-Clause | .venv/Lib/site-packages/httpcore-1.0.9.dist-info/licenses/LICENSE.md | sources/python/httpcore-1.0.9/licenses/LICENSE.md | ok |
| httpx | 0.28.1 | BSD-3-Clause | .venv/Lib/site-packages/httpx-0.28.1.dist-info/licenses/LICENSE.md | sources/python/httpx-0.28.1/licenses/LICENSE.md | ok |
| huggingface_hub | 1.33.0 | Apache-2.0 | .venv/Lib/site-packages/huggingface_hub-1.33.0.dist-info/licenses/LICENSE | sources/python/huggingface_hub-1.33.0/licenses/LICENSE | ok |
| idna | 3.20 | BSD-3-Clause | .venv/Lib/site-packages/idna-3.20.dist-info/licenses/LICENSE.md | sources/python/idna-3.20/licenses/LICENSE.md | ok |
| librt | 0.16.0 | MIT | .venv/Lib/site-packages/librt-0.16.0.dist-info/licenses/LICENSE | sources/python/librt-0.16.0/licenses/LICENSE | ok |
| mypy_extensions | 1.1.0 | MIT | .venv/Lib/site-packages/mypy_extensions-1.1.0.dist-info/licenses/LICENSE | sources/python/mypy_extensions-1.1.0/licenses/LICENSE | ok |
| numpy | 2.5.3 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | .venv/Lib/site-packages/numpy-2.5.3.dist-info/licenses/LICENSE.txt | sources/python/numpy-2.5.3/licenses/LICENSE.txt | ok |
| onnxruntime | 1.30.0 | MIT License | .venv/Lib/site-packages/onnxruntime-1.30.0.dist-info/METADATA | sources/python/onnxruntime-1.30.0/METADATA | missing_license_file |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause | .venv/Lib/site-packages/packaging-26.3.dist-info/licenses/LICENSE | sources/python/packaging-26.3/licenses/LICENSE | ok |
| playwright | 1.63.0 | Apache-2.0 | .venv/Lib/site-packages/playwright-1.63.0.dist-info/licenses/LICENSE | sources/python/playwright-1.63.0/licenses/LICENSE | ok |
| protobuf | 7.36.2 | 3-Clause BSD License | .venv/Lib/site-packages/protobuf-7.36.2.dist-info/LICENSE | sources/python/protobuf-7.36.2/LICENSE | ok |
| pyee | 13.0.1 | MIT | .venv/Lib/site-packages/pyee-13.0.1.dist-info/licenses/LICENSE | sources/python/pyee-13.0.1/licenses/LICENSE | ok |
| Pygments | 2.21.0 | BSD-2-Clause | .venv/Lib/site-packages/pygments-2.21.0.dist-info/licenses/LICENSE | sources/python/Pygments-2.21.0/licenses/LICENSE | ok |
| PyYAML | 6.0.3 | MIT | .venv/Lib/site-packages/pyyaml-6.0.3.dist-info/licenses/LICENSE | sources/python/PyYAML-6.0.3/licenses/LICENSE | ok |
| tokenizers | 0.23.2 | OSI Approved :: Apache Software License | .venv/Lib/site-packages/tokenizers-0.23.2.dist-info/METADATA | sources/python/tokenizers-0.23.2/METADATA | missing_license_file |
| tomlkit | 0.15.1 | MIT | .venv/Lib/site-packages/tomlkit-0.15.1.dist-info/licenses/LICENSE | sources/python/tomlkit-0.15.1/licenses/LICENSE | ok |
| tqdm | 4.70.1 | MPL-2.0 AND MIT | .venv/Lib/site-packages/tqdm-4.70.1.dist-info/licenses/LICENCE | sources/python/tqdm-4.70.1/licenses/LICENCE | ok |
| typing_extensions | 4.16.0 | PSF-2.0 | .venv/Lib/site-packages/typing_extensions-4.16.0.dist-info/licenses/LICENSE | sources/python/typing_extensions-4.16.0/licenses/LICENSE | ok |

## Gaps (need user confirmation before relying on redistribution)

- **FFmpeg**: Production .tools/ffmpeg/bin has no LICENSE/COPYING; media-toolchain.json says GPL obligations must be resolved before packaging. Do not treat a different candidate build's LICENSE.txt as this pin without user review.
- **Microsoft.Web.WebView2**: LICENSE.txt is bundled from the NuGet package; redistribution terms must still be reviewed before shipping an installer (see docs/references/webview2-sdk.json).
- **MSVC native (.tools/native)**: DLL pin present but no Microsoft license text file alongside it.
- **multilingual-e5-small model weights**: No LICENSE/model card file under .cache/models/multilingual-e5-small; embedding-model.json notes MIT (base model) and exported artifact needs release review.
- **faster-whisper-tiny model weights**: No LICENSE/model card under .cache/models/faster-whisper; only weight files + receipt. Need user confirmation of redistribution terms before shipping.
- **ctranslate2 4.8.2**: No LICENSE/COPYING/NOTICE under ctranslate2-4.8.2.dist-info; METADATA license field is MIT.
- **flatbuffers 25.12.19**: No LICENSE/COPYING/NOTICE under flatbuffers-25.12.19.dist-info; METADATA license field is Apache 2.0.
- **onnxruntime 1.30.0**: No LICENSE/COPYING/NOTICE under onnxruntime-1.30.0.dist-info; METADATA license field is MIT License.
- **tokenizers 0.23.2**: No LICENSE/COPYING/NOTICE under tokenizers-0.23.2.dist-info; METADATA license field is OSI Approved :: Apache Software License.
