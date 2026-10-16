"""Validate and inject authored SVG paths into the whiteboard strokes slot.

This module handles only geometry stroke data. The project lifecycle must lock
the normalized result before calling ``inject_strokes`` on a derived HTML copy.
"""
from __future__ import annotations

from html import escape
import math
import re


MAX_STROKES = 24
MAX_PATH_CHARS = 2048
MAX_TOTAL_CHARS = 16384
VIEWBOX_WIDTH = 1000
VIEWBOX_HEIGHT = 560
SLOT = '<g class="wbi-sketch" data-slot="strokes" data-sketch="custom" hidden></g>'
TOKEN = re.compile(r"[MmLlHhVvCcQqZz]|[+-]?(?:(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)")
ARITY = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "Q": 4, "Z": 0}


def _path_tokens(value: str) -> list[str]:
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_PATH_CHARS:
        raise ValueError("笔画路径为空或过长")
    tokens: list[str] = []
    cursor = 0
    for match in TOKEN.finditer(value):
        if value[cursor:match.start()].strip(" \t\r\n,"):
            raise ValueError("笔画路径包含不允许的字符或命令")
        tokens.append(match.group())
        cursor = match.end()
    if value[cursor:].strip(" \t\r\n,") or not tokens or tokens[0] != "M":
        raise ValueError("笔画路径必须由绝对 M 坐标开始")

    normalized: list[str] = []
    command = ""
    numbers: list[str] = []
    drawn = False

    def finish() -> None:
        nonlocal drawn
        count = len(numbers)
        size = ARITY[command]
        if (size == 0 and count) or (size > 0 and (count < size or count % size)):
            raise ValueError("笔画路径命令的坐标数量无效")
        for i, number in enumerate(map(float, numbers)):
            limit = VIEWBOX_HEIGHT if command == "V" or (command not in {"H", "V"} and i % 2) else VIEWBOX_WIDTH
            if number < 0 or number > limit:
                raise ValueError("笔画坐标超出白板 SVG 的 1000×560 画布")
        if command == "M" and count > 2:
            drawn = True
        if command in {"L", "H", "V", "C", "Q"}:
            drawn = True
        normalized.extend([command, *numbers])

    for token in tokens:
        if len(token) == 1 and token.isalpha():
            if token not in ARITY:
                raise ValueError("笔画只接受绝对 M/L/H/V/C/Q/Z 命令")
            if command:
                finish()
            command = token
            numbers = []
            continue
        if not command or command == "Z":
            raise ValueError("笔画路径缺少绘图命令")
        number = float(token)
        if not math.isfinite(number):
            raise ValueError("笔画坐标不是有限范围内的数")
        numbers.append(format(number, ".12g"))
    finish()
    if not drawn:
        raise ValueError("笔画路径没有可绘制的线段")
    return normalized


def normalize_strokes(value: object) -> list[dict[str, object]]:
    """Return a bounded, deterministic representation suitable for a project lock."""
    if not isinstance(value, list) or not 1 <= len(value) <= MAX_STROKES:
        raise ValueError("笔画须为 1—24 条的列表")
    result: list[dict[str, object]] = []
    total = 0
    for stroke in value:
        if not isinstance(stroke, dict) or set(stroke) - {"d", "accent", "width"}:
            raise ValueError("笔画只允许 d/accent/width 字段")
        if "d" not in stroke:
            raise ValueError("笔画缺少 d 路径")
        tokens = _path_tokens(stroke["d"])
        path = " ".join(tokens)
        total += len(path)
        if total > MAX_TOTAL_CHARS:
            raise ValueError("笔画路径总长度过长")
        accent = stroke.get("accent", False)
        if not isinstance(accent, bool):
            raise ValueError("accent 须为布尔值")
        width = stroke.get("width", 6)
        if isinstance(width, bool) or not isinstance(width, (int, float)) or not math.isfinite(width) or not 1 <= width <= 20:
            raise ValueError("笔画宽度须为 1—20 的有限数")
        result.append({"d": path, "accent": accent, "width": float(width)})
    return result


def inject_strokes(source: str, strokes: object) -> str:
    """Replace the one known empty slot in a derived whiteboard HTML copy."""
    if not isinstance(source, str) or source.count(SLOT) != 1:
        raise ValueError("白板组件缺少唯一的空笔画槽位")
    rows = []
    for stroke in normalize_strokes(strokes):
        accent = ' data-ink="accent"' if stroke["accent"] else ""
        rows.append(
            f'<path d="{escape(stroke["d"], quote=True)}"{accent} '
            f'stroke-width="{format(stroke["width"], ".12g")}"/>'
        )
    return source.replace(SLOT, SLOT[:-4] + "\n" + "\n".join(rows) + "\n</g>")
