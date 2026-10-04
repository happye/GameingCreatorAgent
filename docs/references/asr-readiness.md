# F003 本地 ASR 准备记录

2026-10-03 只读研究，供后续 owner 接续；**没有安装 ASR 包、下载权重或运行推理，F003 仍 false**。Windows 标准 x64/GIL CPython 3.13 已有官方 wheel 候选，不能把元数据兼容当成 native import 成功。

2026-10-04 更新：下表保留首轮研究候选；现在 ASR wheels、项目内 CRT 和 tiny 四文件已安装/下载并校验，native/CPU int8/Silero探针通过。PyAV19.0.1 实际转录失败，因为19版移除了 faster-whisper1.2.1仍调用的 `av.open(metadata_errors=...)`。该候选不得视为可用推理组合。root 已把运行时固定为 `av==16.1.0`，并以该组合完成 synthetic 与四段本地运行时复验；当前固定版本以 pyproject/uv.lock 为准。实际失败报告、四段结果和后续证据见 `docs/exec-plans/sprint-F003.md`。不改写昨日只读研究为昨日已验证。readiness 握手后的真实取消/超时已有本机报告，见 sprint-F003 中的 `34e9c47a2fff470a8e665f7a9ce537e5`。该报告和四段 `validationPassed` 都不是 F003 验收。

## 固定候选

| 包 | 版本 / wheel | SHA256 |
| --- | --- | --- |
| faster-whisper | 1.2.1 / py3-none-any | `79a66ad50688c0b794dd501dc340a736992a6342f7f95e5811be60b5224a26a7` |
| CTranslate2 | 4.8.2 / cp313-win_amd64 | `399c20a7336b6358f69ce3c615e090eabc08f29735a079fd1ac1e464119e0861` |
| PyAV | 19.0.1 / cp312-abi3-win_amd64 | `906fc3db09288319a75ea23ffefb59961c7dbe0d1c074601507a89de7d8593d8` |
| onnxruntime CPU | 1.30.0 / cp313-win_amd64 | `4b63041bd623a9a9ac5e353948436c6fa7f43edd12d6b4a4ebc340bca959ba93` |

依据官方 PyPI JSON：[faster-whisper](https://pypi.org/pypi/faster-whisper/1.2.1/json)、[CTranslate2](https://pypi.org/pypi/ctranslate2/4.8.2/json)、[PyAV](https://pypi.org/pypi/av/19.0.1/json)、[onnxruntime](https://pypi.org/pypi/onnxruntime/1.30.0/json)。传递依赖由 root owner 审查并更新 uv.lock；限定 wheel，不临时编译工具链。

项目 Python 已包含 vcruntime140/140_1，但项目目录没有 msvcp140。先用可终止 worker 验证四包 import、CPU int8、Silero CPU session，以及加载 DLL 的位置。CTranslate2 需 SSE4.1，CTranslate2/onnxruntime 官方要求 VC runtime；缺失则准备合法来源的 app-local DLL，**不得运行系统 VC++/CUDA/驱动安装器**。CPU 路线无需 torch/CUDA，PyAV wheel 自带其 FFmpeg 库。来源：[CTranslate2](https://opennmt.net/CTranslate2/installation.html)、[硬件](https://opennmt.net/CTranslate2/hardware_support.html)、[onnxruntime](https://onnxruntime.ai/docs/install/)、[Microsoft app-local](https://learn.microsoft.com/en-us/cpp/windows/deployment-in-visual-cpp?view=msvc-170)。

## 首轮模型快照

`Systran/faster-whisper-tiny`，固定 commit `d90ca5fe260221311c53c58e660288d3deb8d356`。只下载四个真实文件到 `.cache/models/faster-whisper/tiny/<commit>`，逐个核对尺寸/hash，临时与 HF/Xet 缓存仍在 `.cache`。

| 文件 | bytes | SHA256 |
| --- | ---: | --- |
| model.bin | 75538270 | `dcb76c6586fc06cbdac6dd21f14cfd129cc4cdd9dce19bf4ffa62e59cbe6e6d1` |
| config.json | 2249 | `a73a28cdfe1c43ccc7202fa333d1f89c202477271407ae9a7f19afa52039cac8` |
| tokenizer.json | 2203239 | `fb7b63191e9bb045082c79fd742a3106a12c99513ab30df4a0d47fa6cb6fd0ab` |
| vocabulary.txt | 459861 | `34ce3fe1c5041027b3f8d42912270993f986dbc4bb34cf27f951e34a1e453913` |

[官方模型元数据](https://huggingface.co/api/models/Systran/faster-whisper-tiny?blobs=true)提供权重尺寸/hash；小文件已由只读 agent 在内存校验固定 commit 的 Git blob 并计算 SHA。small 对照可后置：commit `536b0662742c02347bc0e980a01041f333bce120`，model.bin 483546902 bytes、SHA `3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671`，其 config 的 SHA 为 `b55496ac7940a7ae47d2c01eab40edfd8701feec1229d9cce3b40014383fb828`（2370 bytes），tokenizer/vocabulary 与 tiny 相同。

## 实现前须验证

- 完整本地目录预检；`local_files_only=True`，worker 设置 HF_HUB_OFFLINE/TRANSFORMERS_OFFLINE。缺 tokenizer 时 v1.2.1 仍可能尝试联网，必须预检失败。[初始化源码](https://github.com/SYSTRAN/faster-whisper/blob/v1.2.1/faster_whisper/transcribe.py)
- Silero VAD v6 ONNX 随 wheel，核对实装资产 hash，使用 CPUExecutionProvider。内置 VAD 已返回输入 WAV 秒轴；随后经 F002 piecewise mapping 变为源轴，不能二次恢复 VAD。[VAD 源码](https://github.com/SYSTRAN/faster-whisper/blob/v1.2.1/faster_whisper/vad.py)
- 人工确认并冻结各一段清晰中文/英文参考；未确认现有 PV 有两种语言。分别测试无音轨 no_audio、真静音 no_speech、坏 WAV/缺权重 failed。
- readiness 握手后实际推理取消/超时并终止整个 Windows Job；segments 是惰性生成器，加载和完整迭代均在 worker，不能只取消 await。[运行语义](https://github.com/SYSTRAN/faster-whisper)
- native import/推理、模型质量、视觉 schema/预算/重试分别记录；这些都不能替代 F006 人工检索 gate。
