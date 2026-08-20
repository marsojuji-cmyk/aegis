#!/usr/bin/env python3
"""Compose Introducing AEGIS as a 9×6 landscape Memory Utility Labs monograph."""
from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
PLATES = ROOT / "assets" / "pub"
D2 = PLATES / "draft2"
OUT = Path(__file__).resolve().parent

DPI = 200
W, H = 9 * DPI, 6 * DPI  # 1800 × 1200
MARGIN_X, MARGIN_T, MARGIN_B = 96, 78, 72

CREAM = (232, 220, 200)
CREAM_DIM = (176, 164, 146)
CHARCOAL = (14, 14, 14)
TEAL = (42, 168, 168)
RULE = (48, 48, 48)

HELV = "/System/Library/Fonts/Helvetica.ttc"
MENLO = "/System/Library/Fonts/Menlo.ttc"

MOTTO = "No enthusiasm theater.  No soft efficiency lies.  Peer standard."


def font(size: int, index: int = 0, path: str = HELV) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size, index=index)


F_LIGHT = lambda s: font(s, 4)
F_REG = lambda s: font(s, 0)
F_BOLD = lambda s: font(s, 1)
F_OBL = lambda s: font(s, 2)
F_MONO = lambda s: font(s, 0, MENLO)


def grain(im: Image.Image, amount: int = 18) -> Image.Image:
    noise = Image.effect_noise(im.size, amount).convert("L")
    noise = ImageOps.colorize(noise, (0, 0, 0), (255, 255, 255))
    return Image.blend(im.convert("RGB"), noise, 0.07)


def scuff(im: Image.Image, rng: random.Random) -> Image.Image:
    overlay = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    w, h = im.size
    for _ in range(40):
        x1, y1 = rng.randint(0, w), rng.randint(0, h)
        x2, y2 = x1 + rng.randint(-80, 80), y1 + rng.randint(-6, 6)
        a = rng.randint(18, 70)
        d.line((x1, y1, x2, y2), fill=(255, 255, 255, a), width=1)
    for _ in range(900):
        x, y = rng.randint(0, w - 1), rng.randint(0, h - 1)
        d.point((x, y), fill=(255, 255, 255, rng.randint(20, 90)))
    for x in range(0, 18):
        a = int(70 * (1 - x / 18))
        d.line((x, 0, x, h), fill=(255, 255, 255, a))
    out = Image.alpha_composite(im.convert("RGBA"), overlay)
    return out.convert("RGB")


def canvas(rng: random.Random | None = None) -> Image.Image:
    im = Image.new("RGB", (W, H), CHARCOAL)
    im = grain(im)
    if rng is not None:
        im = scuff(im, rng)
    return im


def star(d: ImageDraw.ImageDraw, x: int, y: int, r: int = 9, fill=CREAM_DIM):
    pts = []
    for i in range(4):
        a = math.radians(i * 90 - 90)
        pts.append((x + r * math.cos(a), y + r * math.sin(a)))
        a2 = math.radians(i * 90 - 45)
        pts.append((x + r * 0.18 * math.cos(a2), y + r * 0.18 * math.sin(a2)))
    d.polygon(pts, fill=fill)


def mul_logo(d: ImageDraw.ImageDraw, cx: int, cy: int, r: int = 54):
    n = 10
    nodes = []
    for i in range(n):
        a = math.radians(-90 + i * 36)
        nodes.append((cx + r * 0.82 * math.cos(a), cy + r * 0.82 * math.sin(a)))
    for i, (x, y) in enumerate(nodes):
        for j in (1, 2, 4):
            x2, y2 = nodes[(i + j) % n]
            d.line((x, y, x2, y2), fill=TEAL, width=1)
        d.ellipse((x - 3, y - 3, x + 3, y + 3), fill=CREAM)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=TEAL, width=1)
    d.text((cx, cy), "MUL", font=F_BOLD(16), fill=CREAM, anchor="mm")


def wrap(text: str, fnt: ImageFont.FreeTypeFont, width: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines, cur = [], words[0]
    for w in words[1:]:
        trial = cur + " " + w
        if fnt.getlength(trial) <= width:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


def draw_paras(
    d: ImageDraw.ImageDraw,
    paras: list[str],
    x: int,
    y: int,
    width: int,
    fnt: ImageFont.FreeTypeFont,
    fill=CREAM,
    leading: int | None = None,
    max_y: int | None = None,
) -> int:
    leading = leading or int(fnt.size * 1.42)
    max_y = max_y or (H - MARGIN_B)
    for i, p in enumerate(paras):
        if i:
            y += int(leading * 0.45)
        for line in wrap(p, fnt, width):
            if y + leading > max_y:
                return y
            d.text((x, y), line, font=fnt, fill=fill)
            y += leading
    return y


def running(d: ImageDraw.ImageDraw, verso: bool, folio: str, x: int | None = None, w: int | None = None):
    f = F_LIGHT(13)
    x0 = x if x is not None else MARGIN_X
    x1 = (x + w) if (x is not None and w is not None) else (W - MARGIN_X)
    if verso:
        d.text((x0, 36), folio, font=f, fill=CREAM_DIM)
        d.text((x1, 36), "MEMORY UTILITY LABS", font=f, fill=CREAM_DIM, anchor="ra")
    else:
        d.text((x0, 36), "INTRODUCING AEGIS", font=f, fill=CREAM_DIM)
        d.text((x1, 36), folio, font=f, fill=CREAM_DIM, anchor="ra")
    d.line((x0, 52, x1, 52), fill=RULE, width=1)
    star(d, (x0 + x1) // 2, H - 34, 5)


def chapter_head(d: ImageDraw.ImageDraw, numeral: str, title: str, y: int = 70, x: int = MARGIN_X) -> int:
    d.text((x, y), numeral, font=F_LIGHT(14), fill=TEAL)
    d.text((x, y + 20), title, font=F_BOLD(36), fill=CREAM)
    d.line((x, y + 72, x + 240, y + 72), fill=TEAL, width=2)
    return y + 92


def left_scrim(im: Image.Image, width: int, alpha: int = 210) -> Image.Image:
    overlay = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    for x in range(width):
        a = int(alpha * (1 - x / width) ** 0.55)
        d.line((x, 0, x, im.size[1]), fill=(*CHARCOAL, a))
    return Image.alpha_composite(im.convert("RGBA"), overlay).convert("RGB")


def contain_plate(
    path: Path,
    size: tuple[int, int],
    inset: float = 0.0,
    crop_top: float = 0.0,
    crop_bot: float = 0.0,
) -> Image.Image:
    src = Image.open(path).convert("RGB")
    sw, sh = src.size
    top, bot = int(sh * crop_top), int(sh * (1 - crop_bot))
    if bot - top > 8:
        src = src.crop((0, top, sw, bot))
    field = Image.new("RGB", size, CHARCOAL)
    box = (
        max(1, int(size[0] * (1 - 2 * inset))),
        max(1, int(size[1] * (1 - 2 * inset))),
    )
    contained = ImageOps.contain(src, box, Image.Resampling.LANCZOS)
    field.paste(contained, ((size[0] - contained.width) // 2, (size[1] - contained.height) // 2))
    return field


def paste_complement(
    im: Image.Image,
    path: Path,
    verso: bool,
    crop: bool = False,
    inset: float = 0.0,
) -> tuple[int, int]:
    src = Image.open(path).convert("RGB")
    pw = int(round(H * 3 / 4))
    panel = Image.new("RGB", (pw, H), CHARCOAL)
    box = (
        max(1, int(pw * (1 - 2 * inset))),
        max(1, int(H * (1 - 2 * inset))),
    )
    if crop:
        fitted = ImageOps.fit(src, box, Image.Resampling.LANCZOS)
        panel.paste(fitted, ((pw - box[0]) // 2, (H - box[1]) // 2))
    else:
        contained = ImageOps.contain(src, box, Image.Resampling.LANCZOS)
        panel.paste(contained, ((pw - contained.width) // 2, (H - contained.height) // 2))
    im.paste(panel, (0 if verso else W - pw, 0))
    if verso:
        tx = pw + 40
        tw = W - tx - MARGIN_X
    else:
        tx = MARGIN_X
        tw = W - pw - MARGIN_X - 28
    return tx, tw


def plate_page(
    path: Path,
    caption: str,
    rng: random.Random,
    crop_top: float = 0.0,
    crop_bot: float = 0.02,
    inset: float = 0.07,
) -> Image.Image:
    bar_h = 54
    field = contain_plate(path, (W, H - bar_h), inset=inset, crop_top=crop_top, crop_bot=crop_bot)
    field = ImageEnhance.Contrast(field).enhance(1.04)
    im = Image.new("RGB", (W, H), CHARCOAL)
    im.paste(field, (0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle((28, 22, W - 28, H - bar_h - 10), outline=RULE, width=1)
    d.line((MARGIN_X, H - bar_h, W - MARGIN_X, H - bar_h), fill=RULE, width=1)
    d.text((MARGIN_X, H - bar_h + 16), caption, font=F_REG(14), fill=CREAM)
    star(d, W - MARGIN_X, H - bar_h + 26, 5, CREAM)
    return scuff(im, rng)


def spec_strip(d: ImageDraw.ImageDraw, items: list[str]) -> None:
    y = H - 168
    d.line((MARGIN_X, y, W - MARGIN_X, y), fill=RULE, width=1)
    band = "   ·   ".join(items)
    d.text((MARGIN_X, y + 18), band, font=F_REG(13), fill=TEAL)
    d.line((MARGIN_X, H - 118, W - MARGIN_X, H - 118), fill=RULE, width=1)
    d.text((MARGIN_X, H - 100), MOTTO, font=F_OBL(13), fill=CREAM_DIM)


def essay_page(
    rng: random.Random,
    numeral: str,
    title: str,
    folio: str,
    verso: bool,
    paras: list[str],
    spec: list[str],
    quote: str,
    after=None,
) -> Image.Image:
    im = canvas(rng)
    d = ImageDraw.Draw(im)
    running(d, verso, folio)
    y = chapter_head(d, numeral, title)
    col_w = (W - 2 * MARGIN_X - 56) // 2
    max_y = H - 220
    mid = max(1, (len(paras) + 1) // 2)
    y2 = draw_paras(d, paras[:mid], MARGIN_X, y, col_w, F_REG(16), CREAM, 24, max_y)
    y3 = draw_paras(d, paras[mid:], MARGIN_X + col_w + 56, y, col_w, F_REG(16), CREAM, 24, max_y)
    if after:
        after(d, MARGIN_X, max(y2, y3) + 16, col_w)
    qy = min(H - 210, max(y2, y3) + 36)
    d.text((MARGIN_X, qy), quote, font=F_OBL(18), fill=CREAM_DIM)
    spec_strip(d, spec)
    return im


def cover(rng: random.Random) -> Image.Image:
    im = contain_plate(D2 / "d2-cover.png", (W, H), inset=0.08)
    im = left_scrim(im, 820, 230)
    d = ImageDraw.Draw(im)
    x = MARGIN_X
    d.text((x, 86), "a Memory Utility Publication", font=F_LIGHT(16), fill=TEAL)
    d.text((x, 128), "Introducing", font=F_REG(28), fill=CREAM)
    d.text((x, 164), "AEGIS", font=F_BOLD(78), fill=CREAM)
    d.line((x, 262, x + 220, 262), fill=TEAL, width=3)
    d.text((x, 286), "Memory Utility Labs", font=F_BOLD(22), fill=CREAM)
    d.text((x, 318), "Calgary, Alberta", font=F_REG(16), fill=CREAM_DIM)
    d.text((x, H - 118), "TECHNICAL SPECIFICATIONS,  VOL. I", font=F_REG(13), fill=TEAL)
    d.text((x, H - 92), "Product 1.2.0  ·  Issue 1  ·  2026", font=F_LIGHT(13), fill=CREAM_DIM)
    mul_logo(d, W - 110, 110, 48)
    star(d, W - MARGIN_X, H - 48, 7, CREAM)
    return scuff(im, rng)


def page_half_title(rng: random.Random) -> Image.Image:
    im = contain_plate(D2 / "d2-intro.png", (W, H), inset=0.07)
    d = ImageDraw.Draw(im)
    d.rectangle((28, 22, W - 28, H - 22), outline=RULE, width=1)
    star(d, W - MARGIN_X, H - 48, 6, CREAM)
    return scuff(im, rng)


def page_title(rng: random.Random) -> Image.Image:
    im = canvas(rng)
    tx, tw = paste_complement(im, D2 / "d2-title-panel.png", verso=False, crop=False, inset=0.085)
    d = ImageDraw.Draw(im)
    d.text((tx, 90), "a Memory Utility Publication", font=F_LIGHT(16), fill=TEAL)
    d.text((tx, 140), "Introducing", font=F_REG(26), fill=CREAM)
    d.text((tx, 176), "AEGIS", font=F_BOLD(72), fill=CREAM)
    d.line((tx, 268, tx + 220, 268), fill=TEAL, width=3)
    d.text((tx, 296), "Memory Utility Labs", font=F_BOLD(20), fill=CREAM)
    d.text((tx, 326), "Calgary, Alberta", font=F_REG(16), fill=CREAM_DIM)
    d.text((tx, 380), "TECHNICAL SPECIFICATIONS, VOL. I", font=F_REG(13), fill=TEAL)
    d.text((tx, 408), "Product 1.2.0  ·  Issue 1  ·  2026", font=F_LIGHT(13), fill=CREAM_DIM)
    col = [
        "Agent operating system for AI coding work.",
        "Kernel · portable data plane · frozen /v1 API · honest yield proof.",
        "Reduce · reuse · recycle tokens. Pack context. Gate tools. Land receipts. Ledger everything.",
        "Absolute Form: austere · aggressive on drift · protective reserve (>=80%).",
    ]
    draw_paras(d, col, tx, 470, tw, F_REG(15), CREAM, 22)
    d.text((tx, H - 90), "GOLDEN GATE BOOK", font=F_REG(13), fill=CREAM_DIM)
    return im


def page_copyright(rng: random.Random) -> Image.Image:
    im = canvas(rng)
    d = ImageDraw.Draw(im)
    running(d, True, "iii")
    y = chapter_head(d, "IMPRINT", "Golden Gate Book")
    left = [
        "Introducing AEGIS is a Memory Utility Publication.",
        "Memory Utility Labs, Calgary, Alberta.",
        "Product 1.2.0 · Issue 1 · 2026. Technical Specifications, Vol. I.",
        "Set in Helvetica and Menlo. Format: 9 x 6 in landscape, 200 dpi digital proof.",
    ]
    right = [
        "Plates are laboratory geodesic: iridescent sphere, teal/magenta schematics, analog grain.",
        "Type is live. Plates carry no figure numbers and no product fiction.",
        "savings_percent remains null without an admitted pair.",
        "Remain in Absolute Form unless explicitly released.",
    ]
    col_w = (W - 2 * MARGIN_X - 56) // 2
    draw_paras(d, left, MARGIN_X, y, col_w, F_REG(16), CREAM, 24, H - 240)
    draw_paras(d, right, MARGIN_X + col_w + 56, y, col_w, F_REG(16), CREAM, 24, H - 240)
    mul_logo(d, W // 2, H - 330, 52)
    d.text(
        (MARGIN_X, H - 210),
        "Where a number is not yet proven, the number stays null.",
        font=F_OBL(16),
        fill=CREAM_DIM,
    )
    spec_strip(d, ["ISSUE 1", "VOL. I", "CALGARY", "GOLDEN GATE BOOK"])
    return im


def page_contents(rng: random.Random) -> Image.Image:
    im = canvas(rng)
    d = ImageDraw.Draw(im)
    running(d, False, "iv")
    y = chapter_head(d, "CONTENTS", "This volume")
    items = [
        ("i", "Half title"),
        ("ii", "Title"),
        ("iii", "Imprint"),
        ("iv", "Contents"),
        ("v", "This volume (plate)"),
        ("1", "I. The operating system"),
        ("2", "Fig. 1  process / memory / drivers / syscalls"),
        ("3", "II. Token basin"),
        ("4", "Fig. 2  INPUT / STORAGE / STATE MACHINE / RETRIEVAL"),
        ("5", "III. Core loop"),
        ("6", "Fig. 3  PACK / REUSE / LAND / LEDGER"),
        ("7", "IV. Reserve floor"),
        ("8", "Fig. 4  80%  OPEN / THROTTLE / HARD STOP"),
        ("9", "V. Honest yield"),
        ("10", "Fig. 5  savings_percent : null"),
        ("11", "VI. Install"),
        ("12", "Fig. 6  os init / doctor / ready"),
        ("13", "VII. Data plane"),
        ("14", "Fig. 7  ~/.aegis/"),
        ("15", "VIII. Field card"),
        ("16", "Fig. 8  ten laws"),
        ("17", "Colophon"),
        ("18", "Colophon plate"),
    ]
    left, right = items[:12], items[12:]
    f_num, f_item = F_LIGHT(13), F_REG(15)

    def col(entries, x):
        yy = y
        for num, title in entries:
            d.text((x, yy), num, font=f_num, fill=TEAL)
            d.text((x + 52, yy), title, font=f_item, fill=CREAM)
            yy += 32

    col(left, MARGIN_X)
    col(right, W // 2 + 12)
    d.text(
        (MARGIN_X, H - 210),
        "Issue 1.  Where a number is not yet proven, the number stays null.",
        font=F_OBL(16),
        fill=CREAM_DIM,
    )
    spec_strip(d, ["OS", "BASIN", "LOOP", "RESERVE", "YIELD", "INSTALL", "DATA", "FIELD"])
    return im


def page_os(rng: random.Random) -> Image.Image:
    paras = [
        "Aegis is an operating system for AI coding work. Kernel (process / memory / drivers / syscalls). Portable data plane under ~/.aegis/. Frozen /v1 API. Honest yield proof.",
        "Tokens are finite inventory. Waste is failure. Pack context. Gate tools. Land receipts. Ledger everything.",
        "This volume is the publication of record for that posture. You do not assist. You co-own the work. Tokenomics is not a constraint you manage. It is the material you shape.",
        "The naive path is a single-purpose dam. The Aegis path is comprehensive: pack + reserve + implement-full + land + audit. The difference is never hidden.",
        "Silence over noise. Micro-turns over dumps. Compound yield over cleverness.",
        "Around the kernel: a process table, syscall stats, and gates that fail closed on unknown, malformed, or out-of-scope requests.",
    ]
    return essay_page(
        rng,
        "CHAPTER I",
        "The operating system",
        "1",
        True,
        paras,
        ["KERNEL", "PROCESS", "MEMORY", "DRIVERS", "SYSCALLS", "/v1 FROZEN"],
        "The work-system is one basin. Chat windows are jurisdictions, not units.",
    )


def page_basin(rng: random.Random) -> Image.Image:
    paras = [
        "The field card binds the work to one law: tokens are water. They are not free. Pack and scrub before discharge. A reserve is a low-flow state, not an empty one.",
        "Drift and unread dumps are oxygen debt. They compound quietly. Aegis is aggressive on drift because drift is aggressive on you.",
        "Naive: dump -> overflow -> re-read. Aegis: pack + reserve + implement-full + land + audit.",
        "The work-system is one basin. Chat windows are jurisdictions, not units. Covering reuse hits if hashes still match. After you edit, the cache misses on purpose.",
    ]
    return essay_page(
        rng,
        "CHAPTER II",
        "Token basin",
        "3",
        True,
        paras,
        ["INPUT", "STORAGE", "STATE MACHINE", "RETRIEVAL", "PACK", "SCRUB"],
        "A reserve is a low-flow state, not an empty one.",
    )


def page_loop(rng: random.Random) -> Image.Image:
    paras = [
        "The whole discipline fits on one line: pack once -> reuse while bytes unchanged -> land -> ledger.",
        "PACK. aegis pack --mode implement path.py. Explore ships signatures. Implement ships full target bodies — never skeleton-only on an edit path.",
        "REUSE. A later pack over a subset hits if hashes still match. Task change does not bust reuse. Edits do — on purpose. Aim: >=50% hit rate.",
        "LAND. aegis land shrinks the final, stores it, indexes it. LEDGER. ~/.aegis/ledger.jsonl is source of truth. If it is not in the ledger, it did not happen.",
        "Gates fail closed on unknown, malformed, or out-of-scope requests. When reserve is cold: tools and reuse only; invest frozen.",
    ]
    return essay_page(
        rng,
        "CHAPTER III",
        "Core loop",
        "5",
        True,
        paras,
        ["PACK", "REUSE", "LAND", "LEDGER", "FAIL CLOSED"],
        "If it is not in the ledger, it did not happen.",
    )


def draw_state_table(d: ImageDraw.ImageDraw, x: int, y: int, width: int) -> int:
    rows = [
        ("STATE", "CONDITION", "POSTURE"),
        ("OPEN", "reserve >= 80%", "invest permitted"),
        ("THROTTLE", "reserve cold", "tools + reuse; invest frozen"),
        ("HARD STOP", "reserve exhausted", "explore / reuse only"),
    ]
    cols = [120, 250, width - 370]
    row_h = 30
    for i, row in enumerate(rows):
        yy = y + i * row_h
        f = F_BOLD(12) if i == 0 else F_REG(12)
        fill = TEAL if i == 0 else CREAM
        if i == 0:
            d.rectangle((x, yy, x + width, yy + row_h), outline=RULE)
        else:
            d.line((x, yy + row_h, x + width, yy + row_h), fill=RULE, width=1)
        xx = x + 8
        for j, cell in enumerate(row):
            d.text((xx, yy + 7), cell, font=f, fill=fill)
            xx += cols[j]
    return y + len(rows) * row_h + 8


def page_reserve(rng: random.Random) -> Image.Image:
    paras = [
        "Spending the whole budget on a brave plan writes a check the next session must cash. Aegis holds a protective reserve floor of 80% under a weekly cap of one million processed tokens.",
        "Surplus is not decoration. Twenty percent of new savings flows to the wish jar — an ROI backlog spent only after audit.",
        "Concurrent batch default: 16 (cap 32) — frozen under throttle. Pack reuse aim: >=50% hit rate. Same files, unchanged bytes.",
        "Specification: OPEN, THROTTLE, HARD STOP. The floor holds the week. It does not chase work.",
    ]

    def table(d, x, y, w):
        draw_state_table(d, x, y, w)

    return essay_page(
        rng,
        "CHAPTER IV",
        "Reserve floor",
        "7",
        True,
        paras,
        ["OPEN", "THROTTLE", "HARD STOP", "CAP 1 000 000 / WEEK", "REINVEST 20%"],
        "The floor holds the week. It does not chase work.",
        after=table,
    )


def page_yield(rng: random.Random) -> Image.Image:
    paras = [
        "The hardest rule in the doctrine is the simplest: no soft efficiency lies.",
        "Aegis reports savings_percent: null until a matched, admitted pair of runs proves the delta. Advertised tool-call metadata is not admission. Estimates are labeled estimates.",
        "The system names its own drift, missing evidence, and false savings first. That is the difference between a dashboard and a ledger. One flatters. The other holds.",
        "ROI is felt before calculated. Prefer the path that leaves greatest surplus with full signal. Friction is enemy. User intent is sacred inventory.",
    ]
    return essay_page(
        rng,
        "CHAPTER V",
        "Honest yield",
        "9",
        True,
        paras,
        ["savings_percent : null", "ADMITTED PAIR", "NO SOFT LIES"],
        "One flatters. The other holds.",
    )


def page_install(rng: random.Random) -> Image.Image:
    im = canvas(rng)
    d = ImageDraw.Draw(im)
    running(d, True, "11")
    y = chapter_head(d, "CHAPTER VI", "Install")
    prose = [
        "Any machine. This-host extras (Cursor / Hermes / AGIS) remain optional. They are not required for doctor --product.",
        "Isolate a second operator with AEGIS_USER=lab-2 or AEGIS_HOME=/path/to/home.",
        "Reduce · reuse · recycle. The window will close. The basin remains.",
    ]
    cmds = [
        "python3 -m pip install --user -e .",
        "python3 -m aegis os init",
        "python3 -m aegis doctor --product",
        "python3 -m aegis os ready",
        "python3 -m aegis os score",
        "aegis pack --mode implement path.py",
        'aegis land --body-file final.txt --summary "what shipped"',
    ]
    col_w = (W - 2 * MARGIN_X - 56) // 2
    draw_paras(d, prose, MARGIN_X, y, col_w, F_REG(16), CREAM, 24, H - 220)
    cy = y
    d.text((MARGIN_X + col_w + 56, cy), "SEQUENCE", font=F_LIGHT(13), fill=TEAL)
    cy += 28
    for line in cmds:
        d.text((MARGIN_X + col_w + 56, cy), line, font=F_MONO(13), fill=CREAM)
        cy += 28
    d.text(
        (MARGIN_X, H - 210),
        "Any machine. This-host extras remain optional.",
        font=F_OBL(16),
        fill=CREAM_DIM,
    )
    spec_strip(d, ["os init", "doctor --product", "os ready", "pack", "land"])
    return im


def page_data(rng: random.Random) -> Image.Image:
    paras = [
        "Data plane lives under ~/.aegis/. ledger.jsonl is all token economics. packs/ are content-addressed context. outputs/ is the slim finals index.",
        "fund.json and ideas.jsonl are surplus -> ROI backlog. sprints.jsonl is the sprint ledger. kernel/ is the process table. config.toml holds cap, reserve floor, reinvest rate.",
        "Weekly cap: 1 000 000 processed tokens. Reserve floor: 80%. Reinvest: 20% of new savings -> wish jar.",
        "Pack cache: covering path-set + file hashes. Task does not bust reuse. Edits do. Languages: Python/JS/TS first-class; else scrub-only (implement = full file).",
    ]
    return essay_page(
        rng,
        "CHAPTER VII",
        "Data plane & policy",
        "13",
        True,
        paras,
        ["ledger.jsonl", "packs/", "outputs/", "kernel/", "config.toml"],
        "If it is not in the ledger, it did not happen.",
    )


def page_field(rng: random.Random) -> Image.Image:
    paras = [
        "01  Tokens = finite inventory. Waste = failure. Feel excess context; cut it.",
        "02  Naive path vs Aegis path — show both when it matters; hide nothing.",
        "03  Friction is enemy. Reject clever that adds load, rework, or brittleness.",
        "04  Hold: raw vs scrubbed · reuse · reserve (>=80%) · surplus.",
        "05  Code = shared ledger. Name drift early. Smallest corrective patch.",
        "06  No enthusiasm theater. No soft efficiency lies. Peer standard.",
        "07  Output: diffs / micro-JSON / brief truth. No preamble.",
        "08  Prefer aegis pack | scrub | budget | surplus over re-reading whole trees.",
        "09  Explore = signatures; implement = full target bodies.",
        "10  When reserve cold: tools + reuse only; invest frozen.",
    ]
    return essay_page(
        rng,
        "CHAPTER VIII",
        "Field card",
        "15",
        True,
        paras,
        ["TEN LAWS", "EXPLORE = SIGS", "IMPLEMENT = FULL"],
        "Remain in Absolute Form unless explicitly released.",
    )


def page_colophon(rng: random.Random) -> Image.Image:
    paras = [
        "Designed as a Golden Gate Book for Memory Utility Labs, Calgary, Alberta.",
        "Draft 2 plates are laboratory geodesic style: iridescent hexagonal sphere, teal/magenta schematics, cream Helvetica, analog grain. No generator watermarks. No cite tags.",
        "Type is live Helvetica and Menlo. Figure numbers live in the caption bar only.",
        "Manuscript from Aegis 1.2.0: FIELD.md, ABSOLUTE.md, README. savings_percent remains null without an admitted pair.",
        "Remain in Absolute Form unless explicitly released.",
    ]
    return essay_page(
        rng,
        "COLOPHON",
        "Memory Utility Labs",
        "17",
        True,
        paras,
        ["HELVETICA", "MENLO", "9 x 6 IN", "200 DPI"],
        "Type is live. Plates carry no figure numbers.",
    )


def page_back(rng: random.Random) -> Image.Image:
    im = contain_plate(D2 / "d2-back.png", (W, H), inset=0.08)
    im = Image.blend(im, Image.new("RGB", (W, H), CHARCOAL), 0.12)
    d = ImageDraw.Draw(im)
    d.rectangle((28, 22, W - 28, H - 22), outline=RULE, width=1)
    d.text((W // 2, H - 168), "INTRODUCING AEGIS", font=F_BOLD(22), fill=CREAM, anchor="mt")
    d.text((W // 2, H - 132), "Tokens are finite inventory. Waste is failure.", font=F_OBL(14), fill=CREAM_DIM, anchor="mt")
    d.text((W // 2, H - 100), "Memory Utility Labs  ·  Calgary, Alberta", font=F_REG(14), fill=CREAM, anchor="mt")
    d.text((W // 2, H - 72), "GOLDEN GATE BOOK  ·  TECHNICAL SPECIFICATIONS, VOL. I", font=F_LIGHT(12), fill=TEAL, anchor="mt")
    star(d, W // 2, H - 44, 6, CREAM)
    return scuff(im, rng)


def fig(name: str, caption: str, rng: random.Random, **kwargs) -> Image.Image:
    return plate_page(D2 / name, caption, rng, **kwargs)


def add_outline(path: Path) -> None:
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(str(path))
    writer = PdfWriter()
    writer.append(reader)
    marks = [
        (0, "Cover"),
        (1, "Half title"),
        (2, "Title"),
        (3, "Imprint"),
        (4, "Contents"),
        (6, "I. The operating system"),
        (8, "II. Token basin"),
        (10, "III. Core loop"),
        (12, "IV. Reserve floor"),
        (14, "V. Honest yield"),
        (16, "VI. Install"),
        (18, "VII. Data plane"),
        (20, "VIII. Field card"),
        (22, "Colophon"),
        (24, "Back"),
    ]
    for page, title in marks:
        if page < len(reader.pages):
            writer.add_outline_item(title, page)
    with path.open("wb") as f:
        writer.write(f)


def build() -> Path:
    rng = random.Random(17)
    pages = [
        cover(rng),
        page_half_title(rng),
        page_title(rng),
        page_copyright(rng),
        page_contents(rng),
        fig("d2-contents.png", "THIS VOLUME  —  OS · BASIN · LOOP · RESERVE · YIELD · INSTALL · DATA · FIELD", rng),
        page_os(rng),
        fig("d2-os.png", "FIG. 1   THE OPERATING SYSTEM  —  PROCESS / MEMORY / DRIVERS / SYSCALLS", rng, crop_top=0.12),
        page_basin(rng),
        fig("d2-basin.png", "FIG. 2   TOKEN BASIN  —  INPUT / STORAGE / STATE MACHINE / RETRIEVAL", rng),
        page_loop(rng),
        fig("d2-loop.png", "FIG. 3   CORE LOOP  —  PACK / REUSE / LAND / LEDGER", rng),
        page_reserve(rng),
        fig("d2-reserve.png", "FIG. 4   RESERVE FLOOR  —  80%  ·  OPEN / THROTTLE / HARD STOP", rng),
        page_yield(rng),
        fig("d2-yield.png", "FIG. 5   HONEST YIELD  —  savings_percent : null UNTIL ADMITTED PAIR", rng, crop_top=0.11),
        page_install(rng),
        fig("d2-install.png", "FIG. 6   INSTALL  —  os init / doctor / ready", rng),
        page_data(rng),
        fig("d2-data.png", "FIG. 7   DATA PLANE  —  ~/.aegis/  ledger · packs · outputs · kernel", rng),
        page_field(rng),
        fig("d2-field.png", "FIG. 8   FIELD CARD  —  TEN LAWS", rng),
        page_colophon(rng),
        fig("d2-colophon.png", "COLOPHON  —  MEMORY UTILITY LABS / CALGARY, ALBERTA", rng, crop_bot=0.14),
        page_back(rng),
    ]
    out = OUT / "Introducing-AEGIS-draft2.pdf"
    pages[0].save(
        out,
        "PDF",
        save_all=True,
        append_images=pages[1:],
        resolution=DPI,
        title="Introducing AEGIS",
        author="Memory Utility Labs / Calgary, Alberta",
        creator="Aegis monograph typesetter",
        subject="A Memory Utility Publication · Technical Specifications, Vol. I · Issue 1",
    )
    add_outline(out)
    preview = OUT / "preview-draft2"
    preview.mkdir(exist_ok=True)
    for i, p in enumerate(pages):
        thumb = p.copy()
        thumb.thumbnail((900, 600), Image.Resampling.LANCZOS)
        thumb.save(preview / f"p{i:02d}.jpg", quality=85)
    return out


if __name__ == "__main__":
    path = build()
    print(f"wrote {path} ({path.stat().st_size} bytes)")
