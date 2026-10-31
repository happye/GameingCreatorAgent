"""Read activity rules from local text, HTML, screenshots or PDFs (no network, no downloads).

Screenshots use Windows' built-in OCR; PDFs are rendered page by page with Windows.Data.Pdf
and then recognized the same way. Everything stays in this job's own scratch directory.
"""

import base64
import json
import re
import shutil
from html.parser import HTMLParser
from pathlib import Path
from uuid import uuid4

from gamingcreator.application.ocr_frames import DEFAULT_LANGUAGES
from gamingcreator.application.providers import CancellationContext
from gamingcreator.domain.errors import AppError, ExitCode
from gamingcreator.domain.ocr_frames import OcrReading
from gamingcreator.infrastructure.media_process import run_media_process
from gamingcreator.infrastructure.windows_ocr import WindowsOcrEngine, powershell_executable

MAX_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 10
TEXT_SUFFIXES = {".txt", ".md"}
HTML_SUFFIXES = {".html", ".htm"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp"}
_CJK = r"[　-〿㐀-鿿＀-￯]"
_PDF_TOKEN = "__GC_PDF_REQUEST__"
_PDF_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
$requestPath = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('__GC_PDF_REQUEST__'))
$request = [IO.File]::ReadAllText($requestPath, [Text.Encoding]::UTF8) | ConvertFrom-Json
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Data.Pdf.PdfDocument, Windows.Data.Pdf, ContentType = WindowsRuntime]
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Storage.StorageFolder, Windows.Storage, ContentType = WindowsRuntime]
$methods = [System.WindowsRuntimeSystemExtensions].GetMethods()
$asTask = ($methods | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
$asAction = ($methods | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncAction' })[0]
function Await($operation, [type]$type) { $task = $asTask.MakeGenericMethod($type).Invoke($null, @($operation)); $null = $task.Wait(-1); $task.Result }
function AwaitAction($action) { $task = $asAction.Invoke($null, @($action)); $null = $task.Wait(-1) }
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($request.pdf)) ([Windows.Storage.StorageFile])
$document = Await ([Windows.Data.Pdf.PdfDocument]::LoadFromFileAsync($file)) ([Windows.Data.Pdf.PdfDocument])
$folder = Await ([Windows.Storage.StorageFolder]::GetFolderFromPathAsync($request.folder)) ([Windows.Storage.StorageFolder])
$count = [Math]::Min([int]$document.PageCount, [int]$request.maxPages)
[Console]::Out.WriteLine((@{ kind = 'document'; pages = [int]$document.PageCount } | ConvertTo-Json -Compress))
for ($i = 0; $i -lt $count; $i++) {
    $page = $document.GetPage($i)
    try {
        $target = Await ($folder.CreateFileAsync(('page-{0:D3}.png' -f $i), [Windows.Storage.CreationCollisionOption]::FailIfExists)) ([Windows.Storage.StorageFile])
        $stream = Await ($target.OpenAsync([Windows.Storage.FileAccessMode]::ReadWrite)) ([Windows.Storage.Streams.IRandomAccessStream])
        try {
            $options = New-Object Windows.Data.Pdf.PdfPageRenderOptions
            # Bound both sides so an extreme page shape cannot balloon memory.
            $width = [Math]::Min(2000, [Math]::Max(1000, $page.Size.Width * 2))
            $height = $width * $page.Size.Height / [Math]::Max(1, $page.Size.Width)
            if ($height -gt 4000) { $width = $width * 4000 / $height; $height = 4000 }
            $options.DestinationWidth = [uint32][Math]::Max(1, $width)
            $options.DestinationHeight = [uint32][Math]::Max(1, $height)
            AwaitAction ($page.RenderToStreamAsync($stream, $options))
        } finally { $stream.Dispose() }
        [Console]::Out.WriteLine((@{ kind = 'page'; index = $i; path = $target.Path } | ConvertTo-Json -Compress))
    } finally { $page.Dispose() }
}
[Console]::Out.WriteLine('{"kind":"done"}')
"""


class _Text(HTMLParser):
    BLOCKS = {
        "p",
        "div",
        "br",
        "li",
        "tr",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "section",
        "article",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style", "noscript"):
            self.skip += 1
        elif tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript") and self.skip:
            self.skip -= 1
        elif tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.parts.append(data)


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise AppError("rules.encoding", "无法识别文件编码（请另存为UTF-8）。", ExitCode.INPUT)


def html_text(markup: str) -> str:
    parser = _Text()
    parser.feed(markup)
    parser.close()
    text = "".join(parser.parts)
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def join_ocr_line(text: str, language: str) -> str:
    """Windows' Chinese recognizer puts spaces between almost every token ("2026 年 1 1 月").

    Rule text needs no spaces in Chinese readings, so they are all removed there; other
    languages only lose spaces between CJK characters.
    """
    if language.startswith("zh"):
        return re.sub(r"\s+", "", text)
    return re.sub(rf"(?<={_CJK})\s+(?={_CJK})", "", text).strip()


async def _ocr(images: list[Path], scratch: Path, context: CancellationContext) -> str:
    batch = await WindowsOcrEngine(scratch).recognize(images, DEFAULT_LANGUAGES, context)
    pages: list[str] = []
    for index in range(len(images)):
        readings = [r for r in batch.readings if r.index == index]

        # Chinese recognizer when the page has Chinese text; otherwise the reading with most lines
        # (an English page read by the Chinese recognizer would lose its word spaces).
        def chinese(reading: OcrReading) -> bool:
            return reading.language.startswith("zh") and any(
                re.search(_CJK, line.text) for line in reading.lines
            )

        readings.sort(key=lambda r: (not chinese(r), r.language.startswith("zh"), -len(r.lines)))
        if readings and readings[0].lines:
            reading = readings[0]
            pages.append(
                "\n".join(join_ocr_line(line.text, reading.language) for line in reading.lines)
            )
    if not pages:
        raise AppError("rules.ocr_empty", "图片中没有识别到文字。", ExitCode.INPUT)
    return "\n".join(pages)


async def _pdf_pages(
    pdf: Path, folder: Path, context: CancellationContext
) -> tuple[list[Path], int]:
    request = folder / f"pdf-request-{uuid4().hex}.json"
    request.write_text(
        json.dumps(
            {"pdf": str(pdf.resolve()), "folder": str(folder.resolve()), "maxPages": MAX_PDF_PAGES}
        ),
        encoding="utf-8",
    )
    location = base64.b64encode(str(request.resolve()).encode("utf-8")).decode("ascii")
    script = _PDF_SCRIPT.replace(_PDF_TOKEN, location)
    pages: list[Path] = []
    total = 0
    done = False

    def consume(line: str) -> bool:
        nonlocal total, done
        text = line.strip().lstrip("﻿")
        if not text.startswith("{"):
            return False
        record = json.loads(text)
        if record.get("kind") == "document":
            total = int(record["pages"])
        elif record.get("kind") == "page":
            path = Path(record["path"]).resolve()
            if path.parent != folder.resolve():
                raise AppError("rules.pdf", "PDF页面输出位置异常。", ExitCode.ENVIRONMENT)
            pages.append(path)
        elif record.get("kind") == "done":
            done = True
        return True

    try:
        await run_media_process(
            [
                str(powershell_executable()),
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-EncodedCommand",
                base64.b64encode(script.encode("utf-16-le")).decode("ascii"),
            ],
            context,
            stdout_line_consumer=consume,
        )
    except AppError as error:
        if error.code in {"environment.media_tool", "input.media_decode"}:
            raise AppError(
                "rules.pdf", "无法读取这个PDF（可能已加密或损坏）。", ExitCode.INPUT
            ) from None
        raise
    finally:
        request.unlink(missing_ok=True)
    if not done or not pages:
        raise AppError("rules.pdf", "PDF没有可识别的页面。", ExitCode.INPUT)
    return pages, total


async def read_rule_source(
    name: str, data: bytes, scratch: Path, context: CancellationContext
) -> dict[str, object]:
    """Text of one uploaded rule file; the scratch directory is created and removed here."""
    if not data or len(data) > MAX_BYTES:
        raise AppError("rules.size", "文件为空或超过10MB。", ExitCode.INPUT)
    suffix = Path(name).suffix.casefold()
    if suffix in TEXT_SUFFIXES:
        return {"text": _decode(data), "sourceKind": "text"}
    if suffix in HTML_SUFFIXES:
        return {"text": html_text(_decode(data)), "sourceKind": "html"}
    if suffix not in IMAGE_SUFFIXES and suffix != ".pdf":
        raise AppError("rules.type", "只支持 txt/md/html/png/jpg/bmp/pdf 文件。", ExitCode.INPUT)
    folder = scratch / uuid4().hex
    folder.mkdir(parents=True)
    try:
        source = folder / ("source" + suffix)
        source.write_bytes(data)
        if suffix == ".pdf":
            pages, total = await _pdf_pages(source, folder, context)
            return {
                "text": await _ocr(pages, folder, context),
                "sourceKind": "pdf",
                "pages": total,
                "pagesRead": len(pages),
            }
        return {"text": await _ocr([source], folder, context), "sourceKind": "image"}
    finally:
        shutil.rmtree(folder, ignore_errors=True)
