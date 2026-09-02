"""Service status card (PNG) for Cloudy VPS Bot (1.4 Beta · dev).

`!status` answers with a real picture instead of a wall of text: one row per
service with a colored pill.

    green   normal
    yellow  under load
    red     outage

The image is drawn with Pillow (see requirements.txt). The module never
imports discord and never talks to Docker - the caller passes ready rows, so
the same renderer can be reused for any dashboard.
"""

from __future__ import annotations

import io
import os

try:
    from PIL import Image, ImageDraw, ImageFont

    HAS_PILLOW = True
except Exception:  # pragma: no cover - Pillow missing
    Image = ImageDraw = ImageFont = None  # type: ignore[assignment]
    HAS_PILLOW = False


class StatusCardError(RuntimeError):
    """Raised when the picture cannot be rendered."""


OK = "ok"
LOAD = "load"
DOWN = "down"

STATUS_RGB = {
    OK: (87, 242, 135),
    LOAD: (254, 231, 92),
    DOWN: (237, 66, 69),
}
STATUS_WORD_EN = {OK: "Operational", LOAD: "Under load", DOWN: "Outage"}

BG = (15, 17, 21)
CARD = (28, 31, 37)
ROW = (34, 38, 45)
BORDER = (48, 53, 62)
TEXT = (237, 240, 245)
MUTED = (150, 158, 170)

FONT_DIRS = (
    "/usr/share/fonts/truetype/dejavu",
    "/usr/share/fonts/truetype/liberation",
    "/usr/share/fonts/truetype/noto",
    "/usr/share/fonts/TTF",
    "/Library/Fonts",
    "C:/Windows/Fonts",
)
FONT_REGULAR = ("DejaVuSans.ttf", "LiberationSans-Regular.ttf", "NotoSans-Regular.ttf", "Arial.ttf")
FONT_BOLD = ("DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "NotoSans-Bold.ttf", "Arialbd.ttf")


def _font_path(bold: bool) -> str:
    names = FONT_BOLD if bold else FONT_REGULAR
    for directory in FONT_DIRS:
        for name in names:
            candidate = os.path.join(directory, name)
            if os.path.exists(candidate):
                return candidate
    return ""


def has_unicode_font() -> bool:
    """True when a TrueType font is available (needed for Cyrillic labels)."""
    return bool(_font_path(False))


def _font(size: int, bold: bool = False):
    if not HAS_PILLOW:  # pragma: no cover
        raise StatusCardError("Pillow is not installed")
    path = _font_path(bold)
    if path:
        try:
            return ImageFont.truetype(path, size)
        except OSError:  # pragma: no cover
            pass
    return ImageFont.load_default()


def _blend(color, base, alpha: float):
    return tuple(
        int(round(component * alpha + base[index] * (1.0 - alpha)))
        for index, component in enumerate(color)
    )


def _text_width(draw, text: str, font) -> float:
    try:
        return draw.textlength(text, font=font)
    except AttributeError:  # pragma: no cover - very old Pillow
        return font.getsize(text)[0]


def overall_status(rows) -> str:
    """Worst status of every real row."""
    order = {OK: 0, LOAD: 1, DOWN: 2}
    worst = OK
    for row in rows or []:
        status = str(row.get("status") or "")
        if status in order and order[status] > order[worst]:
            worst = status
    return worst


def render_status_card(
    title: str,
    subtitle: str = "",
    rows: list[dict] | None = None,
    legend: list[tuple[str, str]] | None = None,
    footer: str = "",
    accent: str = OK,
    width: int = 1120,
) -> bytes:
    """Draw the status card and return the PNG bytes.

    `rows` items are either a section header (`{"section": "Core"}`) or a
    service row:

        {"label": "Deploy", "status": "ok", "detail": "4/5 slots",
         "text": "Normal"}

    `legend` is a list of `(status, word)` pairs shown at the bottom.
    """
    if not HAS_PILLOW:
        raise StatusCardError(
            "Pillow is not installed - run `pip install -r requirements.txt`"
        )

    rows = list(rows or [])
    legend = list(legend or [(OK, STATUS_WORD_EN[OK]), (LOAD, STATUS_WORD_EN[LOAD]), (DOWN, STATUS_WORD_EN[DOWN])])

    pad = 36
    header_h = 132
    row_h = 62
    section_h = 52
    legend_h = 86
    body_h = sum(section_h if row.get("section") else row_h for row in rows)
    height = pad * 2 + header_h + body_h + legend_h

    image = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(image)

    card = (pad, pad, width - pad, height - pad)
    draw.rounded_rectangle(card, radius=28, fill=CARD, outline=BORDER, width=2)

    accent_rgb = STATUS_RGB.get(accent, STATUS_RGB[OK])
    draw.rounded_rectangle(
        (pad + 2, pad + 2, width - pad - 2, pad + 10), radius=6, fill=accent_rgb
    )

    font_title = _font(40, bold=True)
    font_sub = _font(22)
    font_label = _font(27, bold=True)
    font_detail = _font(22)
    font_pill = _font(21, bold=True)
    font_section = _font(20, bold=True)
    font_footer = _font(19)

    left = pad + 36
    right = width - pad - 36

    draw.text((left, pad + 34), title, font=font_title, fill=TEXT)
    if subtitle:
        draw.text((left, pad + 84), subtitle, font=font_sub, fill=MUTED)

    y = pad + header_h
    for row in rows:
        section = row.get("section")
        if section:
            draw.text((left, y + 18), str(section).upper(), font=font_section, fill=MUTED)
            draw.line((left, y + 46, right, y + 46), fill=BORDER, width=1)
            y += section_h
            continue

        status = str(row.get("status") or OK)
        color = STATUS_RGB.get(status, STATUS_RGB[OK])
        word = str(row.get("text") or STATUS_WORD_EN.get(status, status))
        label = str(row.get("label") or "")
        detail = str(row.get("detail") or "")

        draw.rounded_rectangle((left, y + 4, right, y + row_h - 8), radius=14, fill=ROW)

        dot_x, dot_y = left + 30, y + (row_h - 4) // 2
        draw.ellipse(
            (dot_x - 15, dot_y - 15, dot_x + 15, dot_y + 15),
            fill=_blend(color, ROW, 0.22),
        )
        draw.ellipse((dot_x - 8, dot_y - 8, dot_x + 8, dot_y + 8), fill=color)

        draw.text((left + 62, dot_y - 15), label, font=font_label, fill=TEXT)

        pill_w, pill_h = 178, 38
        pill_x1 = right - 22
        pill_x0 = pill_x1 - pill_w
        pill_y0 = dot_y - pill_h // 2
        draw.rounded_rectangle(
            (pill_x0, pill_y0, pill_x1, pill_y0 + pill_h),
            radius=pill_h // 2,
            fill=_blend(color, ROW, 0.18),
            outline=color,
            width=2,
        )
        word_w = _text_width(draw, word, font_pill)
        draw.text(
            (pill_x0 + (pill_w - word_w) / 2, pill_y0 + 8), word, font=font_pill, fill=color
        )

        if detail:
            detail_w = _text_width(draw, detail, font_detail)
            draw.text(
                (pill_x0 - 24 - detail_w, dot_y - 12), detail, font=font_detail, fill=MUTED
            )

        y += row_h

    legend_y = height - pad - legend_h + 22
    draw.line((left, legend_y - 14, right, legend_y - 14), fill=BORDER, width=1)
    x = left
    for status, word in legend:
        color = STATUS_RGB.get(status, STATUS_RGB[OK])
        draw.ellipse((x, legend_y + 6, x + 16, legend_y + 22), fill=color)
        draw.text((x + 26, legend_y + 2), str(word), font=font_detail, fill=MUTED)
        x += 26 + int(_text_width(draw, str(word), font_detail)) + 42

    if footer:
        footer_w = _text_width(draw, footer, font_footer)
        draw.text((right - footer_w, legend_y + 4), footer, font=font_footer, fill=MUTED)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
