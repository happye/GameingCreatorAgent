"""Activity rule extraction: cited fields, unknowns stay empty; a web page only when named."""

import asyncio
import base64
import hashlib
import http.server
import json
import subprocess
import sys
import threading
import urllib.error
import urllib.request

import pytest

from gamingcreator.application.activity_rules import extract_activity_rules
from gamingcreator.application.providers import CancellationContext
from gamingcreator.domain.errors import AppError
from gamingcreator.infrastructure.rule_sources import (
    MAX_BYTES,
    fetch_rule_page,
    html_text,
    join_ocr_line,
    read_rule_source,
)

RULES = """《代号Atom》新版本创作活动
活动名称：《星际奔跑》创作季
活动时间：2026年11月1日 10:00 - 2026-11-30 23:59
参与平台：抖音、B站
1. 视频时长不少于30秒，不超过3分钟，建议竖屏9:16
2. 投稿需带上话题 #代号Atom新版本# 和 #星际奔跑
3. 禁止使用未授权音乐
4. 不得搬运他人作品
"""


PAGES = {
    "/rules.html": (
        "text/html; charset=gb2312",
        (
            "<html><script>x()</script><body><p>" + "</p><p>".join(RULES.splitlines()) + "</p>"
        ).encode("gb2312"),
    ),
    "/rules.txt": ("text/plain", RULES.encode("utf-8")),
    "/data.json": ("application/json", b"{}"),
    "/huge.txt": ("text/plain", b"a" * (MAX_BYTES + 1)),
}


@pytest.fixture
def site():
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            kind, body = PAGES.get(self.path, ("text/plain", b""))
            self.send_response(200 if self.path in PAGES else 404)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()
    thread.join()


def test_web_page_fetch_keeps_provenance_and_rejects_non_text(site):
    page = fetch_rule_page(site + "/rules.html")
    assert page["sourceKind"] == "web" and page["url"] == site + "/rules.html"
    assert page["sha256"] == hashlib.sha256(PAGES["/rules.html"][1]).hexdigest()
    assert "x()" not in page["text"]
    assert extract_activity_rules(page["text"])["knownFields"] == 8
    assert fetch_rule_page(site + "/rules.txt")["text"] == RULES
    for address, code in (
        (site + "/data.json", "rules.type"),
        (site + "/huge.txt", "rules.size"),
        (site + "/missing", "rules.fetch"),
        ("file:///C:/Windows/win.ini", "rules.url"),
        ("ftp://example.com/a", "rules.url"),
        ("http://127.0.0.1:9/closed", "rules.fetch"),
    ):
        with pytest.raises(AppError) as refused:
            fetch_rule_page(address)
        assert refused.value.code == code, address


def values(result, field):
    value = result["fields"][field]
    return [item["value"] for item in value] if isinstance(value, list) else value["value"]


def test_fields_are_extracted_with_source_lines():
    result = extract_activity_rules(RULES)
    assert result["status"] == "extracted-human-check-required"
    assert values(result, "name") == "《星际奔跑》创作季"
    assert values(result, "period") == {"start": "2026-11-01 10:00", "end": "2026-11-30 23:59"}
    assert result["fields"]["period"]["line"] == 3
    assert values(result, "platforms") == ["douyin", "bilibili"]
    assert values(result, "minDurationSeconds") == 30
    assert values(result, "maxDurationSeconds") == 180
    assert values(result, "orientation") == "vertical"
    assert values(result, "requiredTopics") == ["代号Atom新版本", "星际奔跑"]
    assert values(result, "forbidden") == ["禁止使用未授权音乐", "不得搬运他人作品"]
    assert result["knownFields"] == 8
    for field in result["fields"].values():
        for item in field if isinstance(field, list) else [field]:
            assert (
                item["text"] in RULES
                and RULES.splitlines()[item["line"] - 1].strip() == item["text"]
            )


def test_unstated_fields_stay_unknown():
    result = extract_activity_rules("欢迎大家踊跃参加，奖品丰厚。")
    assert result["knownFields"] == 0
    assert all(value is None for value in result["fields"].values())
    for bad in ("", "   ", None, "字" * 200_001):
        with pytest.raises(ValueError):
            extract_activity_rules(bad)


def test_duration_range_and_horizontal():
    result = extract_activity_rules("视频时长15-60秒，横屏16:9投稿")
    assert values(result, "minDurationSeconds") == 15
    assert values(result, "maxDurationSeconds") == 60
    assert values(result, "orientation") == "horizontal"


def test_html_strips_scripts_and_keeps_blocks():
    page = "<html><head><style>p{}</style><script>alert('x')</script></head><body><h1>活动规则</h1><p>活动时间：2026年11月1日-2026年11月2日</p><p>禁止搬运&amp;抄袭</p></body></html>"
    text = html_text(page)
    assert text.splitlines() == [
        "活动规则",
        "活动时间：2026年11月1日-2026年11月2日",
        "禁止搬运&抄袭",
    ]
    assert values(extract_activity_rules(text), "forbidden") == ["禁止搬运&抄袭"]


def test_ocr_line_joining():
    assert join_ocr_line("2026 年 1 1 月 , # 代号 Ato m #", "zh-Hans-CN") == "2026年11月,#代号Atom#"
    assert join_ocr_line("Summer Event 活 动", "en-US") == "Summer Event 活动"


def test_text_and_html_sources_and_rejections(tmp_path):
    context = CancellationContext("rules", 30)
    text = asyncio.run(read_rule_source("规则.txt", RULES.encode("gb18030"), tmp_path, context))
    assert text["sourceKind"] == "text" and "活动时间" in text["text"]
    page = asyncio.run(read_rule_source("a.html", "<p>竖屏</p>".encode(), tmp_path, context))
    assert page == {"text": "竖屏", "sourceKind": "html"}
    from gamingcreator.domain.errors import AppError

    for name, data in (("a.exe", b"MZ"), ("a.txt", b""), ("a.txt", b"x" * (10 * 1024 * 1024 + 1))):
        with pytest.raises(AppError):
            asyncio.run(read_rule_source(name, data, tmp_path, context))
    assert list(tmp_path.iterdir()) == []


def test_http_pasted_text_file_and_refusal(tmp_path, site):
    from gamingcreator.ui.server import create_server

    server = create_server("127.0.0.1", 0, tmp_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def post(body):
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/api/creation/activity-rules",
            json.dumps(body).encode(),
            {"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request) as response:
            return json.loads(response.read())

    try:
        pasted = post({"text": RULES})
        assert pasted["source"] == {"sourceKind": "pasted", "characters": len(RULES)}
        assert pasted["knownFields"] == 8
        upload = post(
            {"fileName": "rules.md", "dataBase64": base64.b64encode(RULES.encode()).decode()}
        )
        assert upload["source"]["sourceKind"] == "text"
        assert upload["fields"]["period"] == pasted["fields"]["period"]
        web = post({"url": site + "/rules.html"})
        assert web["source"]["sourceKind"] == "web" and web["source"]["url"].endswith("/rules.html")
        assert web["fields"]["period"] == pasted["fields"]["period"]
        for body in (
            {"text": ""},
            {"fileName": "a.txt", "dataBase64": "%%%"},
            {"other": 1},
            {"url": "file:///C:/Windows/win.ini"},
        ):
            with pytest.raises(urllib.error.HTTPError) as refused:
                post(body)
            assert refused.value.code == 400
            assert json.loads(refused.value.read())["message"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows OCR and PDF rendering")
def test_real_screenshot_and_pdf_through_windows(tmp_path):
    png = tmp_path / "rules.png"
    draw = (
        "Add-Type -AssemblyName System.Drawing;"
        "$b=New-Object Drawing.Bitmap 1400,320;$g=[Drawing.Graphics]::FromImage($b);"
        "$g.Clear([Drawing.Color]::White);$f=New-Object Drawing.Font('Microsoft YaHei',36);"
        "$g.DrawString('活动时间：2026年11月1日至2026年11月30日',$f,[Drawing.Brushes]::Black,20,20);"
        "$g.DrawString('视频时长不少于30秒，竖屏9:16',$f,[Drawing.Brushes]::Black,20,150);"
        f"$b.Save('{png}');$g.Dispose();$b.Dispose()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", draw], check=True, capture_output=True)
    work = tmp_path / "work"
    image = asyncio.run(
        read_rule_source("rules.png", png.read_bytes(), work, CancellationContext("rules", 120))
    )
    fields = extract_activity_rules(image["text"])["fields"]
    assert fields["period"]["value"] == {"start": "2026-11-01", "end": "2026-11-30"}
    assert fields["minDurationSeconds"]["value"] == 30
    assert fields["orientation"]["value"] == "vertical"
    content = "BT /F1 28 Tf 50 700 Td (Summer Event Rules) Tj 0 -40 Td (#AtomSummer#) Tj ET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        "/Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(content)} >>\nstream\n{content}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    pdf, offsets = "%PDF-1.4\n", []
    for number, body in enumerate(objects, 1):
        offsets.append(len(pdf))
        pdf += f"{number} 0 obj\n{body}\nendobj\n"
    start = len(pdf)
    pdf += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n"
    pdf += "".join(f"{offset:010d} 00000 n \n" for offset in offsets)
    pdf += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n"
    document = asyncio.run(
        read_rule_source("rules.pdf", pdf.encode("latin-1"), work, CancellationContext("pdf", 120))
    )
    assert document["sourceKind"] == "pdf" and document["pagesRead"] == document["pages"] == 1
    assert "Summer Event Rules" in document["text"]
    assert (
        extract_activity_rules(document["text"])["fields"]["requiredTopics"][0]["value"]
        == "AtomSummer"
    )
    assert not work.exists() or list(work.iterdir()) == []


@pytest.mark.parametrize(
    ("text", "field", "expected"),
    [
        ("截止时间：2026年11月30日 19:16 前投稿", "orientation", None),
        ("请勿使用竖屏", "orientation", None),
        ("支持竖屏或横屏", "orientation", None),
        ("画面比例16:9", "orientation", "horizontal"),
        ("视频时长30秒-1分钟", "minDurationSeconds", 30),
        ("视频时长30秒-1分钟", "maxDurationSeconds", 60),
        ("视频评分不低于4分", "minDurationSeconds", None),
        ("视频需包含不少于3秒的游戏画面", "minDurationSeconds", None),
        ("作品时长不得少于20秒", "minDurationSeconds", 20),
        ("视频时长不少于60秒，不超过30秒", "minDurationSeconds", None),
        (
            "活动时间：2026年11月1日-11月30日",
            "period",
            {"start": "2026-11-01", "end": "2026-11-30"},
        ),
        (
            "活动时间：2026年12月20日至1月5日",
            "period",
            None,
        ),
        ("直播时长不少于60分钟", "minDurationSeconds", None),
        ("累计观看时长不少于30分钟", "minDurationSeconds", None),
        ("游戏时长不少于10分钟", "minDurationSeconds", None),
        ("不接受竖屏作品", "orientation", None),
        ("不支持竖屏", "orientation", None),
        ("非竖屏作品无效", "orientation", None),
        ("视频时长不超过60秒（至少10秒游戏画面）", "minDurationSeconds", None),
        ("视频时长不超过60秒（至少10秒游戏画面）", "maxDurationSeconds", 60),
        (
            "活动时间：第一阶段2026年11月1日-11月15日，第二阶段11月16日-11月30日",
            "period",
            None,
        ),
        ("活动名称：Atom Run 创作季", "name", "Atom Run 创作季"),
        ("活动名称：新手奖励计划", "name", "新手奖励计划"),
        ("每日 9:16 发布", "orientation", None),
        ("视频时长不超过60秒\n决赛作品时长不超过5分钟", "maxDurationSeconds", None),
        (
            "投稿时间：2026年11月1日-11月10日\n活动时间：2026年11月1日-11月30日",
            "period",
            {"start": "2026-11-01", "end": "2026-11-30"},
        ),
        (
            "活动时间：2026年11月1日-11月30日，获奖公示2026年12月5日",
            "period",
            {"start": "2026-11-01", "end": "2026-11-30"},
        ),
        ("活动时间：2026年13月45日-2026年14月1日", "period", None),
        ("活动名称：代号Atom征集 活动时间：2026年11月1日-11月2日", "name", "代号Atom征集"),
    ],
)
def test_review_cases_do_not_produce_cited_wrong_values(text, field, expected):
    value = extract_activity_rules(text)["fields"][field]
    assert (None if value is None else value["value"]) == expected


def test_platforms_topics_and_forbidden_stay_in_context():
    result = extract_activity_rules(
        "\n".join(
            [
                "禁止转载到抖音；快手账号不可参与",
                "发布平台：小红书，请勿发布到抖音",
                "#1 报名 a#section （#话题！） #代号Atom#",
                "时长不得少于30秒",
                "不得抄袭",
            ]
        )
    )
    assert values(result, "platforms") == ["xiaohongshu"]
    assert values(result, "requiredTopics") == ["话题", "代号Atom"]
    assert values(result, "forbidden") == [
        "禁止转载到抖音；快手账号不可参与",
        "发布平台：小红书，请勿发布到抖音",
        "不得抄袭",
    ]


def test_second_review_contexts():
    platforms = extract_activity_rules("参与平台：抖音、B站，不含快手")
    assert values(platforms, "platforms") == ["douyin", "bilibili"]
    assert values(extract_activity_rules("参与平台：抖音（不含B站）"), "platforms") == ["douyin"]
    topics = extract_activity_rules("禁止使用 #原神# 话题")
    assert topics["fields"]["requiredTopics"] is None
    assert extract_activity_rules("推荐 #A12")["fields"]["requiredTopics"] is None
    assert extract_activity_rules("###规则 话题")["fields"]["requiredTopics"] is None
    assert extract_activity_rules("【禁止事项】")["fields"]["forbidden"] is None


@pytest.mark.parametrize(
    ("text", "field", "expected"),
    [
        ("视频时长不超过1分钟30秒", "maxDurationSeconds", 90),
        ("视频时长不少于2分钟30秒", "minDurationSeconds", 150),
        ("视频时长3分钟30秒以内", "maxDurationSeconds", 210),
        ("视频时长：1分30秒-3分钟", "minDurationSeconds", 90),
        ("视频时长：1分30秒-3分钟", "maxDurationSeconds", 180),
        ("视频评分不低于4分", "minDurationSeconds", None),
        ("活动名称：星际奔跑创作季 参与对象：全体玩家", "name", "星际奔跑创作季"),
        ("活动名称：代号Atom：觉醒", "name", "代号Atom：觉醒"),
        ("示例视频时长不超过30秒", "maxDurationSeconds", None),
        ("素材原视频时长不少于10分钟", "minDurationSeconds", None),
        ("本游戏为竖屏手游，请录制精彩画面", "orientation", None),
        ("活动时间：2026年11月1日-11月30日（延期至12月15日）", "period", None),
        (
            "投稿时间：2026年11月1日-11月10日（活动时间另行通知）",
            "period",
            None,
        ),
        (
            "报名及投稿时间：2026年11月1日-11月10日",
            "period",
            {"start": "2026-11-01", "end": "2026-11-10"},
        ),
    ],
)
def test_third_review_cases(text, field, expected):
    value = extract_activity_rules(text)["fields"][field]
    assert (None if value is None else value["value"]) == expected


def test_third_review_contexts():
    assert extract_activity_rules("参与平台：除抖音、快手以外的平台")["fields"]["platforms"] is None
    for text in ("可选话题 #星际奔跑", "推荐带上话题 #星际奔跑 增加曝光"):
        assert extract_activity_rules(text)["fields"]["requiredTopics"] is None
    assert extract_activity_rules("参赛作品禁止出现以下内容：")["fields"]["forbidden"] is None
