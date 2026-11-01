"""Real-style activity-rule samples for TD020 phrasing coverage (T5).

Each row is one line (or short block) with the field under test and the expected
extracted value. ``None`` means 未识别 — the extractor must leave the field empty
rather than guess. Corpus covers multi-stage times, 截止到 / 自…起, full-width
digits, 不少于/至少/≥/≧, 禁止/不得/请勿, and OCR 秒→杪 confusions.
"""

from __future__ import annotations

# (text, field, expected_value)
CORPUS: list[tuple[str, str, object]] = [
    # --- multi-stage / ambiguous periods → 未识别 ---
    (
        "活动时间：第一阶段2026年11月1日-11月15日，第二阶段11月16日-11月30日",
        "period",
        None,
    ),
    (
        "活动周期分两阶段：第一阶段2026年10月1日至10月15日；第二阶段10月16日至10月31日",
        "period",
        None,
    ),
    (
        "投稿时间：第一阶段2026年11月1日-11月7日，第二阶段11月8日-11月14日，第三阶段11月15日-11月21日",
        "period",
        None,
    ),
    ("活动时间：2026年11月1日-11月30日（延期至12月15日）", "period", None),
    ("活动时间：2026年11月1日-11月30日，具体以另行通知为准", "period", None),
    ("活动时间：2026年12月20日至1月5日", "period", None),
    # --- 截止到 alone (end only) → 未识别, never invent start ---
    ("投稿截止到2026年11月30日", "period", None),
    ("截止到2026年11月30日23:59前投稿", "period", None),
    ("作品提交截止到２０２６年１２月１日", "period", None),
    ("请于截止到本月底前完成投稿", "period", None),
    # --- 自…起…至/到… (both ends) ---
    (
        "自2026年11月1日10:00起至2026年11月30日23:59止",
        "period",
        {"start": "2026-11-01 10:00", "end": "2026-11-30 23:59"},
    ),
    (
        "活动时间：自2026年11月1日起至2026年11月30日止",
        "period",
        {"start": "2026-11-01", "end": "2026-11-30"},
    ),
    (
        "活动时间自2026年11月1日起至11月30日",
        "period",
        {"start": "2026-11-01", "end": "2026-11-30"},
    ),
    (
        "投稿时间自2026-11-01起至2026-11-15",
        "period",
        {"start": "2026-11-01", "end": "2026-11-15"},
    ),
    (
        "征集时间：自2026年10月20日起到2026年11月10日结束",
        "period",
        {"start": "2026-10-20", "end": "2026-11-10"},
    ),
    (
        "报名时间：2026年11月1日起至2026年11月7日",
        "period",
        {"start": "2026-11-01", "end": "2026-11-07"},
    ),
    (
        "截止时间：2026年11月1日-11月30日",
        "period",
        {"start": "2026-11-01", "end": "2026-11-30"},
    ),
    (
        "活动时间：2026年11月1日起至2026年11月30日",
        "period",
        {"start": "2026-11-01", "end": "2026-11-30"},
    ),
    (
        "自２０２６年１１月１日起至２０２６年１１月１５日止",
        "period",
        {"start": "2026-11-01", "end": "2026-11-15"},
    ),
    # --- classic labeled ranges (regression anchors) ---
    (
        "活动时间：2026年11月1日-11月30日",
        "period",
        {"start": "2026-11-01", "end": "2026-11-30"},
    ),
    (
        "活动时间：２０２６年１１月１日-２０２６年１１月３０日",
        "period",
        {"start": "2026-11-01", "end": "2026-11-30"},
    ),
    (
        "投稿时间：2026年11月1日 00:00 - 2026年11月10日 23:59",
        "period",
        {"start": "2026-11-01 00:00", "end": "2026-11-10 23:59"},
    ),
    # --- full-width digits on durations ---
    ("视频时长不少于３０秒", "minDurationSeconds", 30.0),
    ("视频时长不超过３分钟", "maxDurationSeconds", 180.0),
    ("作品时长不得少于１５秒", "minDurationSeconds", 15.0),
    ("成片长度≥２分钟", "minDurationSeconds", 120.0),
    ("视频时长１５-６０秒", "minDurationSeconds", 15.0),
    ("视频时长１５-６０秒", "maxDurationSeconds", 60.0),
    ("视频时长不超过１分钟３０秒", "maxDurationSeconds", 90.0),
    # --- 不少于 / 至少 / ≥ / ≧ ---
    ("视频时长不少于30秒", "minDurationSeconds", 30.0),
    ("作品时长至少1分钟", "minDurationSeconds", 60.0),
    ("成片长度≥60秒", "minDurationSeconds", 60.0),
    ("视频时长≧90秒", "minDurationSeconds", 90.0),
    ("视频时长≧１分钟", "minDurationSeconds", 60.0),
    ("视频时长不低于45秒", "minDurationSeconds", 45.0),
    ("视频时长不得少于20秒", "minDurationSeconds", 20.0),
    ("视频时长不能少于10秒", "minDurationSeconds", 10.0),
    ("成片时长最短30秒", "minDurationSeconds", 30.0),
    ("视频时长大于等于2分钟", "minDurationSeconds", 120.0),
    ("视频时长>=90秒", "minDurationSeconds", 90.0),
    # --- max verbs / 以内 ---
    ("视频时长不超过3分钟", "maxDurationSeconds", 180.0),
    ("作品时长不得超过120秒", "maxDurationSeconds", 120.0),
    ("成片长度≤90秒", "maxDurationSeconds", 90.0),
    ("视频时长≦2分钟", "maxDurationSeconds", 120.0),
    ("视频时长60秒以内", "maxDurationSeconds", 60.0),
    ("视频时长最长5分钟", "maxDurationSeconds", 300.0),
    # --- OCR 秒→杪 ---
    ("视频时长不少于30杪", "minDurationSeconds", 30.0),
    ("视频时长不少于３０杪", "minDurationSeconds", 30.0),
    ("视频时长30杪-90杪", "minDurationSeconds", 30.0),
    ("视频时长30杪-90杪", "maxDurationSeconds", 90.0),
    ("成片时长３０杪到９０杪", "minDurationSeconds", 30.0),
    ("成片时长３０杪到９０杪", "maxDurationSeconds", 90.0),
    ("作品时长不超过１２０杪", "maxDurationSeconds", 120.0),
    ("视频时长至少４５杪", "minDurationSeconds", 45.0),
    # --- 禁止 / 不得 / 请勿 / 严禁 ---
    ("禁止使用未授权音乐", "forbidden", ["禁止使用未授权音乐"]),
    ("不得搬运他人作品", "forbidden", ["不得搬运他人作品"]),
    ("请勿使用未授权BGM", "forbidden", ["请勿使用未授权BGM"]),
    ("请勿抄袭、搬运", "forbidden", ["请勿抄袭、搬运"]),
    ("严禁使用AI生成画面", "forbidden", ["严禁使用AI生成画面"]),
    ("不允许出现竞品对比画面", "forbidden", ["不允许出现竞品对比画面"]),
    ("不可使用商业曲库付费曲目", "forbidden", ["不可使用商业曲库付费曲目"]),
    # --- must NOT guess (wrong subject / optional / conflict) ---
    ("直播时长不少于60分钟", "minDurationSeconds", None),
    ("累计观看时长不少于30分钟", "minDurationSeconds", None),
    ("游戏时长不少于10分钟", "minDurationSeconds", None),
    ("视频评分不低于4分", "minDurationSeconds", None),
    ("示例视频时长不超过30秒", "maxDurationSeconds", None),
    ("素材原视频时长不少于10分钟", "minDurationSeconds", None),
    ("推荐带上话题 #星际奔跑 增加曝光", "requiredTopics", None),
    ("可选话题 #代号Atom", "requiredTopics", None),
    ("请勿使用竖屏", "orientation", None),
    ("支持竖屏或横屏", "orientation", None),
    ("本游戏为竖屏手游，请录制精彩画面", "orientation", None),
    ("每日 9:16 发布", "orientation", None),
    ("视频时长不少于60秒，不超过30秒", "minDurationSeconds", None),
    ("视频时长不少于60秒，不超过30秒", "maxDurationSeconds", None),
]

assert len({row[0] for row in CORPUS}) >= 60, len({row[0] for row in CORPUS})
