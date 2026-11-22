"""Local editable publication metadata, without platform or AI claims."""

import unicodedata
from typing import Any


def _text_problem(item: object, minimum: int, maximum: int, multiline: bool = False) -> str:
    if not isinstance(item, str):
        return "格式无效"
    if len(item) > maximum:
        return f"不能超过 {maximum} 字"
    if minimum and (len(item) < minimum or not item.strip()):
        return "不能为空"
    if any(
        unicodedata.category(char) == "Cc" and not (multiline and char in "\r\n\t") for char in item
    ):
        return "包含无效字符"
    return ""


def validate_copy(value: dict[str, Any], *, title_optional: bool = False) -> None:
    problem = _text_problem(value.get("title"), 0 if title_optional else 1, 200)
    if problem:
        raise ValueError(f"标题{problem}。")
    problem = _text_problem(value.get("description"), 0, 5000, multiline=True)
    if problem:
        raise ValueError(f"简介{problem}。")
    tags = value.get("tags")
    if not isinstance(tags, list):
        raise ValueError("标签格式无效。")
    if len(tags) > 20:
        raise ValueError("标签不能超过 20 个。")
    for tag in tags:
        problem = _text_problem(tag, 1, 50)
        if problem:
            raise ValueError(
                "单个标签不能超过 50 字。" if problem == "不能超过 50 字" else f"标签{problem}。"
            )
    if len(tags) != len(set(tags)):
        raise ValueError("标签不能重复。")


def validate_metadata(value: dict[str, Any], frames: int) -> None:
    validate_copy(value)
    if type(value.get("coverFrame")) is not int or not 0 <= value["coverFrame"] < frames:
        raise ValueError("封面帧超出成片范围。")
    validate_cover_title(value.get("coverTitle", ""))


def validate_cover_title(title: str) -> None:
    problem = _text_problem(title, 0, 18)
    if problem:
        raise ValueError(f"封面标题{problem}。")
    if any(unicodedata.category(char) in {"Cf", "Cs", "Zl", "Zp"} for char in title):
        raise ValueError("封面标题包含无效字符。")
    if any(char in "{}\\" for char in title):
        raise ValueError("封面标题不能包含半角花括号或反斜杠。")


def user_input_message(error: BaseException) -> str:
    text = str(error).strip()
    if text.startswith(("标题", "简介", "标签", "封面帧", "封面标题")):
        return text
    return "无法保存发布信息。"
