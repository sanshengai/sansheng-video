#!/usr/bin/env python3
"""Deterministic STEM formula anchors, geometry/physics SVG primitives, and fact gates.

Designed for HyperFrames + GSAP offline rendering:
- No external LaTeX/CDN dependency; formulas compile to deterministic HTML/SVG with
  individually addressable ``data-term`` anchors.
- World-to-SVG ``Plane2D`` preserves aspect ratio for geometry and enforces portrait /
  landscape safe areas by default.
- ``verify_stem_spec`` checks algebraic step equivalence, geometric orthogonality /
  area conservation, numeric bindings, and viewport safe-area bounds using exact
  rational arithmetic where applicable.
- ``stem_runtime_js`` drives pure-time state updates via a child tween so GSAP
  ``tl.seek(t)`` (whose default ``suppressEvents=true`` skips root timeline callbacks)
  remains strictly deterministic across forward, reverse, and cold seeks.
"""
from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from fractions import Fraction
from html import escape
import json
import math
from pathlib import Path
import re
import sys
from typing import Callable, Iterable, Sequence

PORTRAIT_CANVAS = (1080, 1920)
LANDSCAPE_CANVAS = (1920, 1080)
# Matches references/craft-defaults.md safe-area defaults.
PORTRAIT_SAFE_BOX = (120.0, 250.0, 940.0, 1500.0)
LANDSCAPE_SAFE_MARGIN = 96.0

TERM_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,31}$")
ROLE_RE = re.compile(r"^[a-z][a-z0-9_-]{0,23}$")
CMD_RE = re.compile(r"\\[A-Za-z]+")

SYMBOLS: dict[str, str] = {
    r"\times": "×",
    r"\div": "÷",
    r"\pm": "±",
    r"\cdot": "·",
    r"\le": "≤",
    r"\ge": "≥",
    r"\ne": "≠",
    r"\approx": "≈",
    r"\to": "→",
    r"\Rightarrow": "⇒",
    r"\Delta": "Δ",
    r"\pi": "π",
    r"\theta": "θ",
    r"\alpha": "α",
    r"\beta": "β",
    r"\gamma": "γ",
    r"\lambda": "λ",
    r"\mu": "μ",
    r"\Omega": "Ω",
    r"\degree": "°",
    r"\checkmark": "✓",
    r"\perp": "⊥",
    r"\parallel": "∥",
    r"\angle": "∠",
    r"\triangle": "△",
}


# ---------------------------------------------------------------------------
# 1. Deterministic offline formula compiler with term anchors
# ---------------------------------------------------------------------------

def _read_braced(src: str, pos: int) -> tuple[str, int]:
    if pos >= len(src) or src[pos] != "{":
        raise ValueError(f"公式语法错误：位置 {pos} 缺少 '{{'")
    depth = 0
    start = pos + 1
    i = pos
    while i < len(src):
        ch = src[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return src[start:i], i + 1
        i += 1
    raise ValueError("公式语法错误：花括号未闭合")


def _read_script_arg(src: str, pos: int) -> tuple[str, int]:
    if pos >= len(src):
        raise ValueError("公式语法错误：上标或下标缺少内容")
    if src[pos] == "{":
        return _read_braced(src, pos)
    if src[pos] == "\\":
        m = CMD_RE.match(src, pos)
        if not m:
            raise ValueError(f"公式语法错误：位置 {pos} 非法转义")
        return m.group(0), m.end()
    return src[pos], pos + 1


def render_formula(expr: str, *, formula_id: str | None = None) -> str:
    """Compile a concise math expression into deterministic HTML with term anchors.

    Term anchor syntax:
      ``{term_id:body}`` or ``{term_id#role:body}``
    Supported math constructs:
      ``\\frac{num}{den}``, ``\\sqrt{body}``, ``^sup``, ``_sub``, and known ``SYMBOLS``.
    """
    if not isinstance(expr, str) or not expr.strip():
        raise ValueError("公式内容不能为空")
    if formula_id is not None and not TERM_ID_RE.match(formula_id):
        raise ValueError(f"非法 formula_id：{formula_id!r}")

    seen_terms: set[str] = set()

    def compile_span(text: str) -> str:
        out: list[str] = []
        i = 0
        n = len(text)
        while i < n:
            ch = text[i]
            if ch.isspace():
                out.append('<span class="stem-sp"> </span>')
                while i < n and text[i].isspace():
                    i += 1
                continue
            if ch == "}":
                raise ValueError(f"公式语法错误：多余的 '}}'（位置 {i}）")
            if ch == "{":
                inner, nxt = _read_braced(text, i)
                colon = _find_top_level_colon(inner)
                if colon != -1:
                    header = inner[:colon].strip()
                    body = inner[colon + 1 :]
                    if not body.strip():
                        raise ValueError(f"公式锚点 {header!r} 内容为空")
                    if "#" in header:
                        term_id, role = header.split("#", 1)
                        if not ROLE_RE.match(role):
                            raise ValueError(f"非法公式语义色角色：{role!r}")
                    else:
                        term_id, role = header, ""
                    if not TERM_ID_RE.match(term_id):
                        raise ValueError(f"非法公式锚点 ID：{term_id!r}")
                    if term_id in seen_terms:
                        raise ValueError(f"同一公式内存在重复锚点 ID：{term_id!r}")
                    seen_terms.add(term_id)
                    role_attr = f' data-role="{escape(role, quote=True)}"' if role else ""
                    out.append(
                        f'<span class="stem-term" data-term="{escape(term_id, quote=True)}"{role_attr}>'
                        f"{compile_span(body)}</span>"
                    )
                else:
                    out.append(f'<span class="stem-group">{compile_span(inner)}</span>')
                i = nxt
                continue
            if ch == "\\":
                m = CMD_RE.match(text, i)
                if not m:
                    raise ValueError(f"公式语法错误：位置 {i} 存在未识别转义")
                cmd = m.group(0)
                i = m.end()
                if cmd == r"\frac":
                    while i < n and text[i].isspace():
                        i += 1
                    num_raw, i = _read_braced(text, i)
                    while i < n and text[i].isspace():
                        i += 1
                    den_raw, i = _read_braced(text, i)
                    if not num_raw.strip() or not den_raw.strip():
                        raise ValueError(r"\frac 分子和分母均不能为空")
                    out.append(
                        '<span class="stem-frac">'
                        f'<span class="stem-num">{compile_span(num_raw)}</span>'
                        '<span class="stem-bar" aria-hidden="true"></span>'
                        f'<span class="stem-den">{compile_span(den_raw)}</span>'
                        "</span>"
                    )
                elif cmd == r"\sqrt":
                    while i < n and text[i].isspace():
                        i += 1
                    rad_raw, i = _read_braced(text, i)
                    if not rad_raw.strip():
                        raise ValueError(r"\sqrt 被开方数不能为空")
                    out.append(
                        '<span class="stem-sqrt">'
                        '<svg class="stem-sqrt-sign" viewBox="0 0 18 32" preserveAspectRatio="none" aria-hidden="true">'
                        '<path d="M1 19 L5.5 19 L9.5 29 L17 2" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round"/>'
                        "</svg>"
                        f'<span class="stem-radicand">{compile_span(rad_raw)}</span>'
                        "</span>"
                    )
                elif cmd in SYMBOLS:
                    sym = SYMBOLS[cmd]
                    cls = "stem-op" if cmd not in (r"\pi", r"\theta", r"\alpha", r"\beta", r"\gamma", r"\lambda", r"\mu", r"\Omega", r"\Delta") else "stem-var"
                    out.append(f'<span class="{cls}">{escape(sym)}</span>')
                else:
                    raise ValueError(f"未受支持的数学命令：{cmd}")
                continue
            if ch in ("^", "_"):
                arg_raw, i = _read_script_arg(text, i + 1)
                if not arg_raw.strip():
                    raise ValueError("上标或下标内容不能为空")
                tag = "sup" if ch == "^" else "sub"
                cls = "stem-sup" if ch == "^" else "stem-sub"
                out.append(f'<{tag} class="{cls}">{compile_span(arg_raw)}</{tag}>')
                continue
            if ch in ("+", "-", "=", "<", ">"):
                glyph = "−" if ch == "-" else ch
                out.append(f'<span class="stem-op">{escape(glyph)}</span>')
                i += 1
                continue
            if ch.isdigit() or ch == ".":
                j = i + 1
                while j < n and (text[j].isdigit() or text[j] == "."):
                    j += 1
                out.append(f'<span class="stem-num-lit">{escape(text[i:j])}</span>')
                i = j
                continue
            if ch.isalpha() and ch.isascii():
                out.append(f'<span class="stem-var">{escape(ch)}</span>')
                i += 1
                continue
            out.append(f'<span class="stem-sym">{escape(ch)}</span>')
            i += 1
        return "".join(out)

    id_attr = f' id="{escape(formula_id, quote=True)}"' if formula_id else ""
    return f'<span class="stem-math"{id_attr}>{compile_span(expr)}</span>'


def _find_top_level_colon(inner: str) -> int:
    depth = 0
    for idx, ch in enumerate(inner):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif ch == ":" and depth == 0:
            return idx
    return -1


def stem_math_css() -> str:
    """Minimal, self-contained deterministic CSS for ``render_formula``."""
    return """/* Deterministic STEM math layout (generated by stem_kit.py) */
.stem-math {
  display: inline-flex;
  align-items: center;
  flex-wrap: nowrap;
  gap: 0.08em;
  font-family: "STIX Two Math", "Cambria Math", "Times New Roman", "PingFang SC", serif;
  font-variant-numeric: lining-nums tabular-nums;
  line-height: 1.2;
  white-space: nowrap;
}
.stem-sp { display: inline-block; width: 0.22em; }
.stem-term, .stem-group {
  display: inline-flex;
  align-items: center;
  position: relative;
  border-radius: 0.22em;
  padding: 0.04em 0.10em;
}
.stem-var { font-style: italic; }
.stem-num-lit, .stem-sym { font-style: normal; }
.stem-op {
  display: inline-block;
  padding: 0 0.14em;
  font-style: normal;
}
.stem-sup, .stem-sub {
  font-size: 0.62em;
  line-height: 1;
  position: relative;
}
.stem-sup { top: -0.52em; margin-left: 0.03em; }
.stem-sub { bottom: -0.26em; margin-left: 0.03em; }
.stem-frac {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  vertical-align: middle;
  margin: 0 0.12em;
  font-size: 0.86em;
}
.stem-frac > .stem-num { padding: 0 0.2em 0.06em; line-height: 1.05; }
.stem-frac > .stem-bar {
  width: 100%;
  min-width: 1.1em;
  height: 2.5px;
  background: currentColor;
  border-radius: 1px;
}
.stem-frac > .stem-den { padding: 0.08em 0.2em 0; line-height: 1.05; }
.stem-sqrt {
  display: inline-flex;
  align-items: stretch;
  margin: 0 0.08em;
}
.stem-sqrt-sign {
  width: 0.58em;
  height: auto;
  flex: 0 0 auto;
  margin-right: -1px;
}
.stem-radicand {
  border-top: 2.3px solid currentColor;
  padding: 0.05em 0.14em 0 0.08em;
  display: inline-flex;
  align-items: center;
}
.stem-term[data-role="a"] { color: #0F766E; }
.stem-term[data-role="b"] { color: #B45309; }
.stem-term[data-role="c"] { color: #1D4ED8; }
.stem-term[data-role="accent"] { color: #0F766E; font-weight: 600; }
"""


# ---------------------------------------------------------------------------
# 2. World-to-SVG Plane2D & STEM Geometry / Physics Primitives
# ---------------------------------------------------------------------------

def default_safe_box(canvas: Sequence[int | float]) -> tuple[float, float, float, float]:
    if len(canvas) != 2:
        raise ValueError("canvas 必须为 [width, height]")
    w, h = float(canvas[0]), float(canvas[1])
    if w <= 0 or h <= 0 or not (math.isfinite(w) and math.isfinite(h)):
        raise ValueError("canvas 宽高必须为有限正数")
    if (int(round(w)), int(round(h))) == PORTRAIT_CANVAS:
        return PORTRAIT_SAFE_BOX
    if w >= h:
        mx = LANDSCAPE_SAFE_MARGIN * (w / 1920.0)
        my = LANDSCAPE_SAFE_MARGIN * (h / 1080.0)
        return (mx, my, w - mx, h - my)
    # Generic portrait fallback proportional to 1080x1920 craft defaults.
    return (
        120.0 * (w / 1080.0),
        250.0 * (h / 1920.0),
        940.0 * (w / 1080.0),
        1500.0 * (h / 1920.0),
    )


def _fmt(v: float) -> str:
    if abs(v) < 1e-9:
        v = 0.0
    return f"{v:.2f}".rstrip("0").rstrip(".")


@dataclass(frozen=True)
class Plane2D:
    """Maps mathematical Cartesian (x, y) (+y up) to SVG pixel coordinates (+y down)."""

    domain_x: tuple[float, float]
    domain_y: tuple[float, float]
    viewport: tuple[float, float, float, float]  # (x, y, width, height) in SVG px
    equal_aspect: bool = True
    scale_x: float = 1.0
    scale_y: float = 1.0
    origin_px: tuple[float, float] = (0.0, 0.0)
    active_box: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)

    @classmethod
    def create(
        cls,
        domain_x: Sequence[float],
        domain_y: Sequence[float],
        viewport: Sequence[float],
        *,
        canvas: Sequence[int | float] | None = None,
        equal_aspect: bool = True,
        safe_override_reason: str | None = None,
    ) -> "Plane2D":
        if len(domain_x) != 2 or len(domain_y) != 2 or len(viewport) != 4:
            raise ValueError("domain_x/domain_y 须为 2 元组，viewport 须为 [x, y, w, h]")
        x0, x1 = float(domain_x[0]), float(domain_x[1])
        y0, y1 = float(domain_y[0]), float(domain_y[1])
        vx, vy, vw, vh = (float(v) for v in viewport)
        vals = (x0, x1, y0, y1, vx, vy, vw, vh)
        if not all(math.isfinite(v) for v in vals):
            raise ValueError("坐标系参数包含非有限数值")
        if x1 <= x0 or y1 <= y0:
            raise ValueError("domain 必须满足 min < max")
        if vw <= 0 or vh <= 0:
            raise ValueError("viewport 宽高必须为正数")

        if canvas is not None:
            sx0, sy0, sx1, sy1 = default_safe_box(canvas)
            eps = 1e-6
            outside = (vx < sx0 - eps or vy < sy0 - eps or vx + vw > sx1 + eps or vy + vh > sy1 + eps)
            if outside and not (isinstance(safe_override_reason, str) and safe_override_reason.strip()):
                raise ValueError(
                    f"viewport [{vx}, {vy}, {vx + vw}, {vy + vh}] 超出安全区 "
                    f"[{sx0}, {sy0}, {sx1}, {sy1}]；请收进安全区或显式提供 safe_override_reason"
                )

        dx = x1 - x0
        dy = y1 - y0
        if equal_aspect:
            s = min(vw / dx, vh / dy)
            sx = sy = s
            used_w = dx * s
            used_h = dy * s
            ax = vx + (vw - used_w) / 2.0
            ay = vy + (vh - used_h) / 2.0
        else:
            sx = vw / dx
            sy = vh / dy
            used_w, used_h = vw, vh
            ax, ay = vx, vy

        ox = ax - x0 * sx
        oy = ay + y1 * sy
        return cls(
            domain_x=(x0, x1),
            domain_y=(y0, y1),
            viewport=(vx, vy, vw, vh),
            equal_aspect=equal_aspect,
            scale_x=sx,
            scale_y=sy,
            origin_px=(ox, oy),
            active_box=(ax, ay, ax + used_w, ay + used_h),
        )

    def to_px(self, x: float, y: float) -> tuple[float, float]:
        if not (math.isfinite(x) and math.isfinite(y)):
            raise ValueError("坐标点必须为有限实数")
        return (self.origin_px[0] + x * self.scale_x, self.origin_px[1] - y * self.scale_y)

    def vec_to_px(self, dx: float, dy: float) -> tuple[float, float]:
        return (dx * self.scale_x, -dy * self.scale_y)


def svg_axes(
    plane: Plane2D,
    *,
    x_step: float = 1.0,
    y_step: float = 1.0,
    grid: bool = True,
    show_numbers: bool = True,
    x_label: str = "x",
    y_label: str = "y",
    axis_color: str = "#334155",
    grid_color: str = "#E2E8F0",
) -> str:
    if x_step <= 0 or y_step <= 0:
        raise ValueError("坐标轴步长必须为正数")
    x0, x1 = plane.domain_x
    y0, y1 = plane.domain_y
    parts: list[str] = ['<g class="stem-axes">']

    ix = math.ceil(x0 / x_step) * x_step
    xs: list[float] = []
    while ix <= x1 + 1e-9:
        xs.append(round(ix, 8))
        ix += x_step
    iy = math.ceil(y0 / y_step) * y_step
    ys: list[float] = []
    while iy <= y1 + 1e-9:
        ys.append(round(iy, 8))
        iy += y_step

    if grid:
        parts.append(f'<g class="stem-grid" stroke="{escape(grid_color, quote=True)}" stroke-width="1.2">')
        for xv in xs:
            px0, py0 = plane.to_px(xv, y0)
            px1, py1 = plane.to_px(xv, y1)
            parts.append(f'<line x1="{_fmt(px0)}" y1="{_fmt(py0)}" x2="{_fmt(px1)}" y2="{_fmt(py1)}"/>')
        for yv in ys:
            px0, py0 = plane.to_px(x0, yv)
            px1, py1 = plane.to_px(x1, yv)
            parts.append(f'<line x1="{_fmt(px0)}" y1="{_fmt(py0)}" x2="{_fmt(px1)}" y2="{_fmt(py1)}"/>')
        parts.append("</g>")

    y_axis_val = 0.0 if y0 <= 0.0 <= y1 else y0
    x_axis_val = 0.0 if x0 <= 0.0 <= x1 else x0
    ax0, ay0 = plane.to_px(x0, y_axis_val)
    ax1, ay1 = plane.to_px(x1, y_axis_val)
    bx0, by0 = plane.to_px(x_axis_val, y0)
    bx1, by1 = plane.to_px(x_axis_val, y1)

    parts.append(f'<g stroke="{escape(axis_color, quote=True)}" stroke-width="2.4" stroke-linecap="round">')
    parts.append(f'<line x1="{_fmt(ax0)}" y1="{_fmt(ay0)}" x2="{_fmt(ax1)}" y2="{_fmt(ay1)}"/>')
    parts.append(f'<path d="M{_fmt(ax1 - 10)} {_fmt(ay1 - 5)} L{_fmt(ax1)} {_fmt(ay1)} L{_fmt(ax1 - 10)} {_fmt(ay1 + 5)}" fill="none"/>')
    parts.append(f'<line x1="{_fmt(bx0)}" y1="{_fmt(by0)}" x2="{_fmt(bx1)}" y2="{_fmt(by1)}"/>')
    parts.append(f'<path d="M{_fmt(bx1 - 5)} {_fmt(by1 + 10)} L{_fmt(bx1)} {_fmt(by1)} L{_fmt(bx1 + 5)} {_fmt(by1 + 10)}" fill="none"/>')
    parts.append("</g>")

    if show_numbers:
        parts.append(f'<g fill="{escape(axis_color, quote=True)}" font-size="22" font-family="STIX Two Math, PingFang SC, sans-serif">')
        for xv in xs:
            if abs(xv - x_axis_val) < 1e-7:
                continue
            px, py = plane.to_px(xv, y_axis_val)
            txt = _fmt(xv).replace("-", "−")
            parts.append(f'<text x="{_fmt(px)}" y="{_fmt(py + 26)}" text-anchor="middle">{escape(txt)}</text>')
        for yv in ys:
            if abs(yv - y_axis_val) < 1e-7:
                continue
            px, py = plane.to_px(x_axis_val, yv)
            txt = _fmt(yv).replace("-", "−")
            parts.append(f'<text x="{_fmt(px - 12)}" y="{_fmt(py + 7)}" text-anchor="end">{escape(txt)}</text>')
        if x_label:
            parts.append(f'<text x="{_fmt(ax1 - 4)}" y="{_fmt(ay1 - 14)}" text-anchor="end" font-style="italic">{escape(x_label)}</text>')
        if y_label:
            parts.append(f'<text x="{_fmt(bx1 + 14)}" y="{_fmt(by1 + 16)}" font-style="italic">{escape(y_label)}</text>')
        parts.append("</g>")

    parts.append("</g>")
    return "".join(parts)


def svg_curve(
    plane: Plane2D,
    fn: Callable[[float], float],
    x_min: float,
    x_max: float,
    *,
    samples: int = 120,
    stroke: str = "#0F766E",
    stroke_width: float = 4.0,
    elem_id: str | None = None,
    traced: bool = False,
    dashed: bool = False,
) -> str:
    if samples < 2 or x_max <= x_min:
        raise ValueError("函数曲线采样要求 samples >= 2 且 x_max > x_min")
    cmds: list[str] = []
    for i in range(samples + 1):
        xv = x_min + (x_max - x_min) * (i / samples)
        yv = float(fn(xv))
        if not math.isfinite(yv):
            raise ValueError(f"函数在 x={xv} 处取值非有限：{yv}")
        px, py = plane.to_px(xv, yv)
        cmds.append(("M" if i == 0 else "L") + f"{_fmt(px)} {_fmt(py)}")
    attrs = [
        f'd="{" ".join(cmds)}"',
        'fill="none"',
        f'stroke="{escape(stroke, quote=True)}"',
        f'stroke-width="{_fmt(stroke_width)}"',
        'stroke-linecap="round"',
        'stroke-linejoin="round"',
    ]
    if elem_id:
        attrs.insert(0, f'id="{escape(elem_id, quote=True)}"')
    if traced:
        attrs.append('pathLength="1000"')
    if dashed:
        attrs.append('stroke-dasharray="10 8"')
    return f'<path {" ".join(attrs)}/>'


def svg_polygon(
    plane: Plane2D,
    points: Sequence[Sequence[float]],
    *,
    fill: str = "none",
    fill_opacity: float | None = None,
    stroke: str = "#1E293B",
    stroke_width: float = 3.5,
    elem_id: str | None = None,
    class_name: str | None = None,
) -> str:
    if len(points) < 3:
        raise ValueError("多边形至少需要 3 个顶点")
    pts = [plane.to_px(float(p[0]), float(p[1])) for p in points]
    pts_attr = " ".join(f"{_fmt(px)},{_fmt(py)}" for px, py in pts)
    attrs: list[str] = []
    if elem_id:
        attrs.append(f'id="{escape(elem_id, quote=True)}"')
    if class_name:
        attrs.append(f'class="{escape(class_name, quote=True)}"')
    attrs.extend([
        f'points="{pts_attr}"',
        f'fill="{escape(fill, quote=True)}"',
        f'stroke="{escape(stroke, quote=True)}"',
        f'stroke-width="{_fmt(stroke_width)}"',
        'stroke-linejoin="round"',
    ])
    if fill_opacity is not None:
        attrs.append(f'fill-opacity="{_fmt(fill_opacity)}"')
    return f'<polygon {" ".join(attrs)}/>'


def svg_right_angle(
    plane: Plane2D,
    vertex: Sequence[float],
    p1: Sequence[float],
    p2: Sequence[float],
    *,
    size_px: float = 18.0,
    stroke: str = "#334155",
    stroke_width: float = 2.5,
    elem_id: str | None = None,
) -> str:
    if not plane.equal_aspect:
        raise ValueError("直角标记要求 Plane2D 开启 equal_aspect=True，防止非等比缩放把直角压歪")
    vx, vy = float(vertex[0]), float(vertex[1])
    u1x, u1y = float(p1[0]) - vx, float(p1[1]) - vy
    u2x, u2y = float(p2[0]) - vx, float(p2[1]) - vy
    n1 = math.hypot(u1x, u1y)
    n2 = math.hypot(u2x, u2y)
    if n1 < 1e-9 or n2 < 1e-9:
        raise ValueError("直角标记边长为零")
    cos_theta = (u1x * u2x + u1y * u2y) / (n1 * n2)
    if abs(cos_theta) > 1e-3:
        raise ValueError(f"顶点并非直角（cos={cos_theta:.6f}），拒绝绘制直角符号")

    v_px = plane.to_px(vx, vy)
    d1 = plane.vec_to_px(u1x / n1, u1y / n1)
    d2 = plane.vec_to_px(u2x / n2, u2y / n2)
    l1 = math.hypot(*d1)
    l2 = math.hypot(*d2)
    e1 = (d1[0] / l1 * size_px, d1[1] / l1 * size_px)
    e2 = (d2[0] / l2 * size_px, d2[1] / l2 * size_px)
    a = (v_px[0] + e1[0], v_px[1] + e1[1])
    b = (v_px[0] + e1[0] + e2[0], v_px[1] + e1[1] + e2[1])
    c = (v_px[0] + e2[0], v_px[1] + e2[1])
    id_attr = f' id="{escape(elem_id, quote=True)}"' if elem_id else ""
    return (
        f'<path{id_attr} class="stem-right-angle" '
        f'd="M{_fmt(a[0])} {_fmt(a[1])} L{_fmt(b[0])} {_fmt(b[1])} L{_fmt(c[0])} {_fmt(c[1])}" '
        f'fill="none" stroke="{escape(stroke, quote=True)}" stroke-width="{_fmt(stroke_width)}" '
        'stroke-linecap="square" stroke-linejoin="miter"/>'
    )


def svg_dimension_segment(
    plane: Plane2D,
    p1: Sequence[float],
    p2: Sequence[float],
    *,
    offset_px: float = 26.0,
    label: str = "",
    color: str = "#334155",
    elem_id: str | None = None,
) -> str:
    q1 = plane.to_px(float(p1[0]), float(p1[1]))
    q2 = plane.to_px(float(p2[0]), float(p2[1]))
    dx, dy = q2[0] - q1[0], q2[1] - q1[1]
    length = math.hypot(dx, dy)
    if length < 1e-6:
        raise ValueError("度量标注线段长度为零")
    nx, ny = -dy / length, dx / length
    s1 = (q1[0] + nx * offset_px, q1[1] + ny * offset_px)
    s2 = (q2[0] + nx * offset_px, q2[1] + ny * offset_px)
    mid = ((s1[0] + s2[0]) / 2.0 + nx * 18.0, (s1[1] + s2[1]) / 2.0 + ny * 18.0)
    tick = 6.0
    id_attr = f' id="{escape(elem_id, quote=True)}"' if elem_id else ""
    parts = [
        f'<g{id_attr} class="stem-dim" stroke="{escape(color, quote=True)}" fill="{escape(color, quote=True)}">',
        f'<line x1="{_fmt(s1[0])}" y1="{_fmt(s1[1])}" x2="{_fmt(s2[0])}" y2="{_fmt(s2[1])}" stroke-width="2.2"/>',
        f'<line x1="{_fmt(s1[0] - nx * tick)}" y1="{_fmt(s1[1] - ny * tick)}" x2="{_fmt(s1[0] + nx * tick)}" y2="{_fmt(s1[1] + ny * tick)}" stroke-width="2.2"/>',
        f'<line x1="{_fmt(s2[0] - nx * tick)}" y1="{_fmt(s2[1] - ny * tick)}" x2="{_fmt(s2[0] + nx * tick)}" y2="{_fmt(s2[1] + ny * tick)}" stroke-width="2.2"/>',
    ]
    if label:
        parts.append(
            f'<text x="{_fmt(mid[0])}" y="{_fmt(mid[1] + 8)}" stroke="none" font-size="26" '
            f'font-family="STIX Two Math, PingFang SC, serif" text-anchor="middle">{escape(label)}</text>'
        )
    parts.append("</g>")
    return "".join(parts)


def svg_vector_arrow(
    plane: Plane2D,
    origin: Sequence[float],
    delta: Sequence[float],
    *,
    color: str = "#0F766E",
    stroke_width: float = 4.0,
    head_px: float = 14.0,
    label: str = "",
    elem_id: str | None = None,
) -> str:
    ox, oy = float(origin[0]), float(origin[1])
    dx, dy = float(delta[0]), float(delta[1])
    if math.hypot(dx, dy) < 1e-9:
        raise ValueError("物理或几何矢量长度不能为零")
    p0 = plane.to_px(ox, oy)
    p1 = plane.to_px(ox + dx, oy + dy)
    vx, vy = p1[0] - p0[0], p1[1] - p0[1]
    plen = math.hypot(vx, vy)
    ux, uy = vx / plen, vy / plen
    nx, ny = -uy, ux
    wing = head_px * 0.48
    h1 = (p1[0] - ux * head_px + nx * wing, p1[1] - uy * head_px + ny * wing)
    h2 = (p1[0] - ux * head_px - nx * wing, p1[1] - uy * head_px - ny * wing)
    id_attr = f' id="{escape(elem_id, quote=True)}"' if elem_id else ""
    parts = [
        f'<g{id_attr} class="stem-vec">',
        f'<line x1="{_fmt(p0[0])}" y1="{_fmt(p0[1])}" x2="{_fmt(p1[0] - ux * head_px * 0.65)}" y2="{_fmt(p1[1] - uy * head_px * 0.65)}" '
        f'stroke="{escape(color, quote=True)}" stroke-width="{_fmt(stroke_width)}" stroke-linecap="round"/>',
        f'<polygon points="{_fmt(p1[0])},{_fmt(p1[1])} {_fmt(h1[0])},{_fmt(h1[1])} {_fmt(h2[0])},{_fmt(h2[1])}" fill="{escape(color, quote=True)}"/>',
    ]
    if label:
        lx = (p0[0] + p1[0]) / 2.0 + nx * 22.0
        ly = (p0[1] + p1[1]) / 2.0 + ny * 22.0
        parts.append(
            f'<text x="{_fmt(lx)}" y="{_fmt(ly + 8)}" fill="{escape(color, quote=True)}" font-size="26" '
            f'font-family="STIX Two Math, PingFang SC, serif" text-anchor="middle">{escape(label)}</text>'
        )
    parts.append("</g>")
    return "".join(parts)


# ---------------------------------------------------------------------------
# 3. Programmatic STEM Fact & Safe-Area Verifier (Exact Rational Engine)
# ---------------------------------------------------------------------------

def _to_fraction(val: int | float | str) -> Fraction:
    if isinstance(val, bool):
        raise ValueError("布尔值不能作为数学量")
    if isinstance(val, int):
        return Fraction(val)
    if isinstance(val, float):
        if not math.isfinite(val):
            raise ValueError("数学量必须有限")
        return Fraction(str(val))
    if isinstance(val, str) and val.strip():
        return Fraction(val.strip())
    raise ValueError(f"无法解析为精确有理数：{val!r}")


def _eval_linear_poly(node: ast.AST, var_name: str, env: dict[str, Fraction]) -> tuple[Fraction, Fraction]:
    """Evaluate AST into linear polynomial ``(a, b)`` representing ``a * var + b``."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return (Fraction(0), _to_fraction(node.value))
    if isinstance(node, ast.Name):
        if node.id == var_name:
            return (Fraction(1), Fraction(0))
        if node.id in env:
            return (Fraction(0), env[node.id])
        raise ValueError(f"表达式引用了未定义变量：{node.id!r}")
    if isinstance(node, ast.UnaryOp):
        a, b = _eval_linear_poly(node.operand, var_name, env)
        if isinstance(node.op, ast.UAdd):
            return (a, b)
        if isinstance(node.op, ast.USub):
            return (-a, -b)
        raise ValueError("不支持的一元运算")
    if isinstance(node, ast.BinOp):
        la, lb = _eval_linear_poly(node.left, var_name, env)
        ra, rb = _eval_linear_poly(node.right, var_name, env)
        if isinstance(node.op, ast.Add):
            return (la + ra, lb + rb)
        if isinstance(node.op, ast.Sub):
            return (la - ra, lb - rb)
        if isinstance(node.op, ast.Mult):
            if la != 0 and ra != 0:
                raise ValueError("一元一次方程链中出现高次乘积项")
            return (la * rb + ra * lb, lb * rb)
        if isinstance(node.op, ast.Div):
            if ra != 0:
                raise ValueError("分母含未知数，不属于整式线性步骤")
            if rb == 0:
                raise ValueError("数学验算错误：除以零")
            return (la / rb, lb / rb)
        if isinstance(node.op, ast.Pow):
            if la != 0 or ra != 0:
                raise ValueError("未知数幂运算请放入 identities 数值恒等检查")
            if rb.denominator != 1 or rb.numerator < 0 or rb.numerator > 12:
                raise ValueError(f"指数超出有理精确检验范围：{rb}")
            return (Fraction(0), lb ** rb.numerator)
    raise ValueError(f"不支持的表达式语法：{ast.dump(node)}")


def _eval_exact_expr(expr: str, env: dict[str, Fraction]) -> Fraction:
    if not isinstance(expr, str) or not expr.strip():
        raise ValueError("算式不能为空")
    tree = ast.parse(expr.strip(), mode="eval")
    a, b = _eval_linear_poly(tree.body, "__none__", env)
    assert a == 0
    return b


def verify_stem_spec(spec: dict) -> dict:
    """Validate mathematical facts, algebraic step chains, geometry, and safe-area bounds."""
    if not isinstance(spec, dict) or not spec:
        raise ValueError("STEM 验算输入不能为空对象")

    chains = spec.get("equation_chains", [])
    triangles = spec.get("right_triangles", [])
    identities = spec.get("identities", [])
    viewports = spec.get("viewport_checks", [])

    for name, seq in (
        ("equation_chains", chains),
        ("right_triangles", triangles),
        ("identities", identities),
        ("viewport_checks", viewports),
    ):
        if not isinstance(seq, list):
            raise ValueError(f"{name} 必须为数组")

    total_items = len(chains) + len(triangles) + len(identities) + len(viewports)
    if total_items == 0:
        raise ValueError("STEM 验算规范未包含任何检查项（空输入拒绝通过）")

    checked = {"equation_chains": 0, "right_triangles": 0, "identities": 0, "viewport_checks": 0}

    for item in chains:
        if not isinstance(item, dict):
            raise ValueError("equation_chains 条目必须为对象")
        var = item.get("variable", "x")
        if not isinstance(var, str) or not var.isidentifier():
            raise ValueError(f"非法未知数名：{var!r}")
        steps = item.get("steps")
        if not isinstance(steps, list) or len(steps) < 2:
            raise ValueError("equation_chains 至少需要 2 步方程变形")
        expected_sol = _to_fraction(item["solution"])
        env = {k: _to_fraction(v) for k, v in (item.get("constants") or {}).items()}

        first_root: Fraction | None = None
        for idx, step in enumerate(steps):
            if not isinstance(step, str) or step.count("=") != 1:
                raise ValueError(f"第 {idx + 1} 步不是合法等式：{step!r}")
            lhs_s, rhs_s = step.split("=", 1)
            la, lb = _eval_linear_poly(ast.parse(lhs_s.strip(), mode="eval").body, var, env)
            ra, rb = _eval_linear_poly(ast.parse(rhs_s.strip(), mode="eval").body, var, env)
            coef = la - ra
            const = lb - rb
            if coef == 0:
                raise ValueError(f"第 {idx + 1} 步未知数系数退化为 0：{step!r}")
            root = -const / coef
            if first_root is None:
                first_root = root
            elif root != first_root:
                raise ValueError(
                    f"第 {idx + 1} 步 {step!r} 解为 {root}，与原方程解 {first_root} 不等价（疑似移项漏变号或系数计算错误）"
                )
        if first_root != expected_sol:
            raise ValueError(f"声明答案 {expected_sol} 与方程真实解 {first_root} 不一致")
        checked["equation_chains"] += 1

    for tri in triangles:
        if not isinstance(tri, dict):
            raise ValueError("right_triangles 条目必须为对象")
        verts = tri.get("vertices")
        rv = tri.get("right_vertex")
        if not isinstance(verts, dict) or len(verts) != 3 or rv not in verts:
            raise ValueError("right_triangles 需提供 3 个命名顶点并指明 right_vertex")
        other = [k for k in verts if k != rv]
        vx, vy = (_to_fraction(verts[rv][0]), _to_fraction(verts[rv][1]))
        p1x, p1y = (_to_fraction(verts[other[0]][0]), _to_fraction(verts[other[0]][1]))
        p2x, p2y = (_to_fraction(verts[other[1]][0]), _to_fraction(verts[other[1]][1]))
        u1x, u1y = p1x - vx, p1y - vy
        u2x, u2y = p2x - vx, p2y - vy
        a_sq = u1x * u1x + u1y * u1y
        b_sq = u2x * u2x + u2y * u2y
        c_sq = (p1x - p2x) ** 2 + (p1y - p2y) ** 2
        if a_sq == 0 or b_sq == 0:
            raise ValueError("退化三角形：直角边长度为 0")
        dot = u1x * u2x + u1y * u2y
        if dot != 0:
            raise ValueError(f"顶点 {rv} 处两直角边内积为 {dot} != 0，不是直角三角形")
        if a_sq + b_sq != c_sq:
            raise ValueError(f"勾股平方和校验失败：{a_sq} + {b_sq} != {c_sq}")
        if "claimed_squares" in tri:
            cs = tri["claimed_squares"]
            got = sorted([a_sq, b_sq, c_sq])
            exp = sorted([_to_fraction(cs["a2"]), _to_fraction(cs["b2"]), _to_fraction(cs["c2"])])
            if got != exp or _to_fraction(cs["a2"]) + _to_fraction(cs["b2"]) != _to_fraction(cs["c2"]):
                raise ValueError(f"画面声明面积与真实顶点几何不一致：{cs}")
        checked["right_triangles"] += 1

    for ident in identities:
        if not isinstance(ident, dict):
            raise ValueError("identities 条目必须为对象")
        eq = ident.get("equation")
        if not isinstance(eq, str) or eq.count("=") != 1:
            raise ValueError(f"恒等式格式错误：{eq!r}")
        lhs_s, rhs_s = eq.split("=", 1)
        cases = ident.get("cases") or [ident.get("bindings") or {}]
        if not isinstance(cases, list) or not cases:
            raise ValueError("identities.cases 不能为空")
        for case in cases:
            if not isinstance(case, dict):
                raise ValueError("identities.cases 元素必须为键值映射")
            env = {k: _to_fraction(v) for k, v in case.items()}
            lv = _eval_exact_expr(lhs_s, env)
            rv = _eval_exact_expr(rhs_s, env)
            if lv != rv:
                raise ValueError(f"恒等式 {eq!r} 在参数 {case} 下不成立：{lv} != {rv}")
        checked["identities"] += 1

    for vp in viewports:
        if not isinstance(vp, dict):
            raise ValueError("viewport_checks 条目必须为对象")
        canvas = vp.get("canvas")
        box = vp.get("viewport")
        domain_x = vp.get("domain_x", [0.0, 1.0])
        domain_y = vp.get("domain_y", [0.0, 1.0])
        equal_aspect = vp.get("equal_aspect", True)
        if not isinstance(equal_aspect, bool):
            raise ValueError("equal_aspect 必须为布尔值")
        plane = Plane2D.create(
            domain_x,
            domain_y,
            box,
            canvas=canvas,
            equal_aspect=equal_aspect,
            safe_override_reason=vp.get("safe_override_reason"),
        )
        if vp.get("require_equal_aspect", False) and abs(plane.scale_x - plane.scale_y) > 1e-6:
            raise ValueError("几何舞台要求等比例缩放（require_equal_aspect），实际 x/y 比例不一致")
        sx0, sy0, sx1, sy1 = default_safe_box(canvas)
        for pt in vp.get("world_points") or []:
            px, py = plane.to_px(float(pt[0]), float(pt[1]))
            if not vp.get("safe_override_reason"):
                if px < sx0 - 1e-6 or px > sx1 + 1e-6 or py < sy0 - 1e-6 or py > sy1 + 1e-6:
                    raise ValueError(f"世界坐标点 {pt} 投影像素 ({px:.2f}, {py:.2f}) 越出安全区")
        checked["viewport_checks"] += 1

    return {"status": "verified", "checked": checked, "total": total_items}


# ---------------------------------------------------------------------------
# 4. Browser Runtime Micro-Helper for Seek-Deterministic STEM Scenes
# ---------------------------------------------------------------------------

def stem_runtime_js() -> str:
    """Pure-time GSAP driver ensuring HyperFrames ``tl.seek(t)`` updates dynamic state."""
    return """/* Seek-deterministic STEM clock & pure math helpers (generated by stem_kit.py) */
(function (global) {
  "use strict";
  function clamp01(x) {
    return x <= 0 ? 0 : x >= 1 ? 1 : x;
  }
  function smoothstep(edge0, edge1, x) {
    if (edge1 <= edge0) return x >= edge1 ? 1 : 0;
    var u = clamp01((x - edge0) / (edge1 - edge0));
    return u * u * (3 - 2 * u);
  }
  function lerp(a, b, u) {
    return a + (b - a) * u;
  }
  function formatNumber(value, decimals) {
    var d = typeof decimals === "number" ? decimals : 1;
    var n = Math.abs(value) < 1e-9 ? 0 : value;
    var s = Math.abs(n).toFixed(d);
    return (n < 0 ? "\u2212" : "") + s;
  }
  function bindClock(tl, duration, renderAtTime) {
    if (!tl || typeof tl.fromTo !== "function") {
      throw new Error("StemRuntime.bindClock requires a GSAP timeline");
    }
    if (!(duration > 0) || typeof renderAtTime !== "function") {
      throw new Error("StemRuntime.bindClock requires positive duration and renderAtTime(t)");
    }
    var driver = { t: 0 };
    renderAtTime(0);
    // HyperFrames steps timelines with 1-arg tl.seek(ts) where suppressEvents=true
    // skips root timeline callbacks, while child tween onUpdate always runs.
    tl.fromTo(
      driver,
      { t: 0 },
      {
        t: duration,
        duration: duration,
        ease: "none",
        immediateRender: true,
        onUpdate: function () {
          renderAtTime(driver.t);
        }
      },
      0
    );
    return driver;
  }
  global.StemRuntime = {
    clamp01: clamp01,
    smoothstep: smoothstep,
    lerp: lerp,
    formatNumber: formatNumber,
    bindClock: bindClock
  };
})(typeof window !== "undefined" ? window : globalThis);
"""


def emit_assets(out_dir: Path) -> dict[str, str]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    css_path = out_dir / "stem-math.css"
    js_path = out_dir / "stem-runtime.js"
    css_path.write_text(stem_math_css(), encoding="utf-8")
    js_path.write_text(stem_runtime_js(), encoding="utf-8")
    return {"css": str(css_path), "js": str(js_path)}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)

    p_verify = subs.add_parser("verify", help="verify a stem-spec.json file")
    p_verify.add_argument("spec", type=Path)

    p_formula = subs.add_parser("formula", help="compile a formula expression to HTML")
    p_formula.add_argument("expr")
    p_formula.add_argument("--id", dest="formula_id")

    p_emit = subs.add_parser("emit-assets", help="write stem-math.css and stem-runtime.js")
    p_emit.add_argument("out_dir", type=Path)

    args = parser.parse_args(argv)
    try:
        if args.command == "verify":
            raw = args.spec.read_text(encoding="utf-8")
            if not raw.strip():
                raise ValueError("STEM 验算文件为空")
            report = verify_stem_spec(json.loads(raw))
            print(json.dumps(report, ensure_ascii=False))
            return 0
        if args.command == "formula":
            print(render_formula(args.expr, formula_id=args.formula_id))
            return 0
        if args.command == "emit-assets":
            print(json.dumps(emit_assets(args.out_dir), ensure_ascii=False))
            return 0
    except (ValueError, OSError, json.JSONDecodeError, SyntaxError, KeyError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
