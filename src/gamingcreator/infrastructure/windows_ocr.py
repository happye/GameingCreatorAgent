"""Windows' built-in OCR engine (Windows.Media.Ocr) through one PowerShell 5.1 process.

Nothing is installed or downloaded: only recognizer languages Windows already has are used,
and a missing language is reported as unavailable. Images never leave the machine.
"""

import base64
import json
import os
import platform
import sys
from collections.abc import Sequence
from pathlib import Path
from uuid import uuid4

from gamingcreator.application.ocr_frames import OcrBatch, OcrEngineIdentity
from gamingcreator.application.providers import CancellationContext
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.domain.ocr_frames import OcrReading, parse_reading
from gamingcreator.infrastructure.media_process import run_media_process

ENGINE = "windows-media-ocr-v1"
_REQUEST_TOKEN = "__GC_OCR_REQUEST__"
# Reads the request file, recognizes each image with each available requested language and
# prints one JSON object per line: each text line, then its frame summary. Failures are
# reported per image, never as text. The request path arrives base64-encoded so no path
# character can end a PowerShell string literal.
_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
$requestPath = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('__GC_OCR_REQUEST__'))
$request = [IO.File]::ReadAllText($requestPath, [Text.Encoding]::UTF8) | ConvertFrom-Json
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
        $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
        $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
    })[0]
function Await($operation, [type]$type) {
    $task = $asTask.MakeGenericMethod($type).Invoke($null, @($operation))
    $null = $task.Wait(-1)
    $task.Result
}
$available = @([Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages | ForEach-Object { $_.LanguageTag })
$engines = [ordered]@{}
foreach ($tag in $request.languages) {
    if ($available -contains $tag) {
        $engines[$tag] = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new($tag))
    }
}
[Console]::Out.WriteLine((@{ kind = 'engine'; available = $available; maxImageDimension = [int][Windows.Media.Ocr.OcrEngine]::MaxImageDimension } | ConvertTo-Json -Compress))
$index = 0
foreach ($path in $request.paths) {
    try {
        $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($path)) ([Windows.Storage.StorageFile])
        $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
        try {
            $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
            $bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
            foreach ($tag in $engines.Keys) {
                $result = Await ($engines[$tag].RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
                $count = 0
                foreach ($line in $result.Lines) {
                    $words = @(foreach ($word in $line.Words) {
                            $box = $word.BoundingRect
                            @{ text = $word.Text; x = [int]$box.X; y = [int]$box.Y; width = [int]$box.Width; height = [int]$box.Height }
                        })
                    [Console]::Out.WriteLine((@{ kind = 'line'; index = $index; language = $tag; text = $line.Text; words = $words } | ConvertTo-Json -Compress -Depth 5))
                    $count += 1
                }
                [Console]::Out.WriteLine((@{ kind = 'frame'; index = $index; language = $tag; width = [int]$bitmap.PixelWidth; height = [int]$bitmap.PixelHeight; lineCount = $count } | ConvertTo-Json -Compress))
            }
        } finally { $stream.Dispose() }
    } catch {
        [Console]::Out.WriteLine((@{ kind = 'failed'; index = $index; error = $_.Exception.GetType().Name } | ConvertTo-Json -Compress))
    }
    $index += 1
}
[Console]::Out.WriteLine('{"kind":"done"}')
"""


def powershell_executable() -> Path:
    """System Windows PowerShell 5.1, never one found through PATH."""
    root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    return root / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"


class OcrOutputParser:
    """Collects the engine's JSON lines; anything malformed stops the whole batch."""

    def __init__(self, count: int) -> None:
        self.count = count
        self.available: tuple[str, ...] | None = None
        self.readings: list[OcrReading] = []
        self.failed: set[int] = set()
        self.done = False
        self._lines: dict[tuple[int, str], list[object]] = {}

    def consume(self, line: str) -> bool:
        text = line.strip().lstrip("\ufeff")
        if not text.startswith("{"):
            return False
        try:
            record = json.loads(text)
            if not isinstance(record, dict):
                raise ValueError
            kind = record.get("kind")
            if kind == "engine":
                available = record.get("available")
                if not isinstance(available, list) or not all(
                    type(item) is str for item in available
                ):
                    raise ValueError
                self.available = tuple(available)
            elif kind == "line":
                index, language = record.get("index"), record.get("language")
                if (
                    type(index) is not int
                    or not 0 <= index < self.count
                    or type(language) is not str
                ):
                    raise ValueError
                self._lines.setdefault((index, language), []).append(
                    {"text": record.get("text"), "words": record.get("words")}
                )
            elif kind == "frame":
                index, language = record.get("index"), record.get("language")
                if type(index) is not int or type(language) is not str:
                    raise ValueError
                lines = self._lines.pop((index, language), [])
                if record.get("lineCount") != len(lines):
                    raise ValueError
                reading = parse_reading({**record, "lines": lines})
                if reading.index >= self.count:
                    raise ValueError
                self.readings.append(reading)
            elif kind == "failed":
                index = record.get("index")
                if type(index) is not int or not 0 <= index < self.count:
                    raise ValueError
                self.failed.add(index)
                for key in [key for key in self._lines if key[0] == index]:
                    del self._lines[key]
            elif kind == "done":
                if self._lines:
                    raise ValueError
                self.done = True
            else:
                raise ValueError
        except ValueError:
            raise AppError("ocr.output", "文字识别结果格式无效。", ExitCode.ENVIRONMENT) from None
        return True


class WindowsOcrEngine:
    def __init__(self, scratch: Path) -> None:
        self.scratch = scratch

    def identity(self) -> OcrEngineIdentity:
        return OcrEngineIdentity(ENGINE, f"Windows {platform.version()}")

    async def recognize(
        self, images: Sequence[Path], languages: Sequence[str], context: CancellationContext
    ) -> OcrBatch:
        if sys.platform != "win32":
            raise AppError(
                "environment.ocr_unavailable",
                "本机文字识别只在Windows上可用。",
                ExitCode.ENVIRONMENT,
            )
        self.scratch.mkdir(parents=True, exist_ok=True)
        request = self.scratch / f"ocr-request-{uuid4().hex}.json"
        parser = OcrOutputParser(len(images))
        try:
            request.write_text(
                json.dumps(
                    {
                        "paths": [str(item.resolve()) for item in images],
                        "languages": list(languages),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            location = base64.b64encode(str(request.resolve()).encode("utf-8")).decode("ascii")
            script = _SCRIPT.replace(_REQUEST_TOKEN, location)
            encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
            await run_media_process(
                [
                    str(powershell_executable()),
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-EncodedCommand",
                    encoded,
                ],
                context,
                stdout_line_consumer=parser.consume,
            )
        except OSError:
            raise AppError(
                "environment.ocr_unavailable", "无法启动本机文字识别。", ExitCode.ENVIRONMENT
            ) from None
        except AppError as error:
            # The shared process runner names media failures; say what actually failed.
            if error.code in {"environment.media_tool", "input.media_decode"}:
                raise AppError(
                    "environment.ocr_unavailable",
                    "本机文字识别没有正常运行（Windows OCR组件不可用或被系统阻止）。",
                    ExitCode.ENVIRONMENT,
                ) from None
            if error.code == "media.timeout":
                raise AppError("ocr.timeout", "文字识别超时。", ExitCode.ENVIRONMENT) from None
            if error.code == "media.output_limit":
                raise AppError(
                    "ocr.output", "某一行识别结果过长，已停止识别。", ExitCode.ENVIRONMENT
                ) from None
            raise
        finally:
            request.unlink(missing_ok=True)
        if not parser.done or parser.available is None:
            raise AppError("ocr.output", "文字识别没有完整结束。", ExitCode.ENVIRONMENT)
        return OcrBatch(parser.available, tuple(parser.readings), frozenset(parser.failed))
