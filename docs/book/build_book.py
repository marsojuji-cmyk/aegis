#!/usr/bin/env python3
"""Compose Introducing AEGIS as a 9×6 landscape Memory Utility Labs monograph."""
from __future__ import annotations

import math
import os
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parents[1]
PLATES = ROOT / "assets" / "pub"
OUT = Path(__file__).resolve().parent

DPI = 200
W, H = 9 * DPI, 6 * DPI  # 1800 × 1200
MARGIN_X, MARGIN_T, MARGIN_B = 96, 78, 72

CREAM = (232, 220, 200)
CREAM_DIM = (176, 164, 146)
CHARCOAL = (14, 14, 14)
TEAL = (42, 168, 168)
MAGENTA = (224, 64, 128)
BRICK = (194, 59, 59)
MUSTARD = (212, 160, 23)
ORANGE = (224, 122, 47)
RULE = (48, 48, 48)

HELV = "/System/Library/Fonts/Helvetica.ttc"
MENLO = "/System/Library/Fonts/Menlo.ttc"


def font(size: int, index: int = 0, path: str = HELV) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size, index=index)


F_LIGHT = lambda s: font(s, 4)
F_REG = lambda s: font(s, 0)
F_BOLD = lambda s: font(s, 1)
F_OBL = lambda s: font(s, 2)
F_MONO = lambda s: font(s, 0, MENLO)
F_MONO_B = lambda s: font(s, 1, MENLO)


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
    # spine wear
    for x in range(0, 18):
        a = int(70 * (1 - x / 18))
        d.line((x, 0, x, h), fill=(255, 255, 255, a))
    out = im.convert("RGBA")
    out = Image.alpha_composite(out, overlay)
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
    f = F_BOLD(18)
    d.text((cx, cy), "MUL", font=f, fill=CREAM, anchor="mm")


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


def running(d: ImageDraw.ImageDraw, verso: bool, folio: str):
    f = F_LIGHT(13)
    if verso:
        d.text((MARGIN_X, 36), folio, font=f, fill=CREAM_DIM)
        d.text((W - MARGIN_X, 36), "MEMORY UTILITY LABS", font=f, fill=CREAM_DIM, anchor="ra")
    else:
        d.text((MARGIN_X, 36), "INTRODUCING AEGIS", font=f, fill=CREAM_DIM)
        d.text((W - MARGIN_X, 36), folio, font=f, fill=CREAM_DIM, anchor="ra")
    d.line((MARGIN_X, 52, W - MARGIN_X, 52), fill=RULE, width=1)
    star(d, W // 2, H - 34, 5)


def chapter_head(d: ImageDraw.ImageDraw, numeral: str, title: str, y: int = 78) -> int:
    d.text((MARGIN_X, y), numeral, font=F_LIGHT(15), fill=TEAL)
    d.text((MARGIN_X, y + 22), title, font=F_BOLD(36), fill=CREAM)
    d.line((MARGIN_X, y + 74, MARGIN_X + 220, y + 74), fill=MAGENTA, width=2)
    return y + 96


def fit_plate(path: Path, size: tuple[int, int]) -> Image.Image:
    im = Image.open(path).convert("RGB")
    return ImageOps.fit(im, size, Image.Resampling.LANCZOS)


def plate_page(path: Path, caption: str, rng: random.Random) -> Image.Image:
    im = fit_plate(path, (W, H))
    im = ImageEnhance.Contrast(im).enhance(1.04)
    bar_h = 56
    bar = Image.new("RGBA", (W, bar_h), (14, 14, 14, 210))
    d = ImageDraw.Draw(bar)
    d.text((MARGIN_X, 18), caption, font=F_REG(14), fill=CREAM)
    star(d, W - MARGIN_X, 28, 5, CREAM)
    im = im.convert("RGBA")
    im.paste(bar, (0, H - bar_h), bar)
    return scuff(im.convert("RGB"), rng)


def cover(rng: random.Random) -> Image.Image:
    return scuff(fit_plate(PLATES / "aegis-hero.png", (W, H)), rng)


def page_half_title(rng: random.Random) -> Image.Image:
    im = canvas(rng)
    d = ImageDraw.Draw(im)
    mul_logo(d, W // 2, 280)
    d.text((W // 2, 430), "INTRODUCING", font=F_LIGHT(22), fill=CREAM_DIM, anchor="mm")
    d.text((W // 2, 500), "AEGIS", font=F_BOLD(92), fill=CREAM, anchor="mm")
    d.line((W // 2 - 90, 560, W // 2 + 90, 560), fill=TEAL, width=2)
    d.text(
        (W // 2, 600),
        "A Memory Utility Publication",
        font=F_REG(18),
        fill=CREAM_DIM,
        anchor="mm",
    )
    star(d, W // 2, H - 80, 8)
    return im


def page_title(rng: random.Random) -> Image.Image:
    im = canvas(rng)
    d = ImageDraw.Draw(im)
    d.text((MARGIN_X, 90), "a Memory Utility Publication", font=F_LIGHT(16), fill=CREAM_DIM)
    d.text((MARGIN_X, 140), "Introducing", font=F_REG(28), fill=CREAM)
    d.text((MARGIN_X, 178), "AEGIS", font=F_BOLD(86), fill=CREAM)
    d.line((MARGIN_X, 290, MARGIN_X + 280, 290), fill=ORANGE, width=3)
    d.text((MARGIN_X, 320), "Memory Utility Labs", font=F_BOLD(22), fill=CREAM)
    d.text((MARGIN_X, 352), "Calgary, Alberta", font=F_REG(18), fill=CREAM_DIM)
    d.text((MARGIN_X, 420), "TECHNICAL SPECIFICATIONS, VOL. I", font=F_REG(14), fill=TEAL)
    d.text((MARGIN_X, 452), "Product 1.2.0  ·  Issue 17  ·  2026", font=F_LIGHT(14), fill=CREAM_DIM)
    mul_logo(d, W - 180, 180, 62)
    d.text((W - 180, 270), "MUL", font=F_LIGHT(12), fill=TEAL, anchor="mm")
    col = [
        "Agent operating system for AI coding work.",
        "Kernel · portable data plane · frozen /v1 API · honest yield proof.",
        "Reduce · reuse · recycle tokens. Pack context. Gate tools. Land receipts. Ledger everything.",
        "Absolute Form: austere · aggressive on drift · protective reserve (≥80%).",
    ]
    draw_paras(d, col, MARGIN_X, 560, 760, F_REG(16), CREAM, 24)
    d.text((MARGIN_X, H - 90), "$1.75", font=F_BOLD(18), fill=ORANGE)
    d.text((MARGIN_X + 90, H - 88), "GOLDEN GATE BOOK", font=F_REG(13), fill=CREAM_DIM)
    star(d, W - MARGIN_X, H - 86, 6)
    return im


def page_contents(rng: random.Random) -> Image.Image:
    im = canvas(rng)
    d = ImageDraw.Draw(im)
    running(d, False, "")
    y = chapter_head(d, "CONTENTS", "This volume", 70)
    items = [
        ("i", "Half title"),
        ("ii", "Title"),
        ("iii", "Contents"),
        ("1", "I.   The operating system"),
        ("2", "II.  Token basin"),
        ("3", "     Fig. 1  —  INPUT / STORAGE / RETRIEVAL"),
        ("4", "III. Core loop"),
        ("5", "     Fig. 2  —  PACK / REUSE / LAND / LEDGER"),
        ("6", "IV.  Reserve floor"),
        ("7", "     Fig. 3  —  80% specification plate"),
        ("8", "V.   Honest yield"),
        ("9", "VI.  Install"),
        ("10", "VII. Data plane & policy"),
        ("11", "VIII. Field card"),
        ("12", "Colophon"),
    ]
    left, right = items[:8], items[8:]
    f_num, f_item = F_LIGHT(15), F_REG(17)

    def col(entries, x):
        yy = y
        for num, title in entries:
            d.text((x, yy), num, font=f_num, fill=TEAL)
            d.text((x + 54, yy), title, font=f_item, fill=CREAM)
            yy += 38

    col(left, MARGIN_X)
    col(right, W // 2 + 20)
    d.line((MARGIN_X, H - 100, W - MARGIN_X, H - 100), fill=RULE, width=1)
    d.text(
        (MARGIN_X, H - 88),
        "Where a number is not yet proven, the number stays null.",
        font=F_OBL(14),
        fill=CREAM_DIM,
    )
    return im


def text_page(
    rng: random.Random,
    numeral: str,
    title: str,
    folio: str,
    verso: bool,
    left: list[str],
    right: list[str] | None = None,
    after_left=None,
) -> Image.Image:
    im = canvas(rng)
    d = ImageDraw.Draw(im)
    running(d, verso, folio)
    y = chapter_head(d, numeral, title)
    col_w = (W - 2 * MARGIN_X - 48) // 2
    y2 = draw_paras(d, left, MARGIN_X, y, col_w, F_REG(15), CREAM, 22)
    if after_left:
        after_left(d, MARGIN_X, y2 + 12, col_w)
    if right:
        draw_paras(d, right, MARGIN_X + col_w + 48, y, col_w, F_REG(15), CREAM, 22)
    d.line((MARGIN_X, H - 118, W - MARGIN_X, H - 118), fill=RULE, width=1)
    d.text(
        (MARGIN_X, H - 100),
        "No enthusiasm theater.  No soft efficiency lies.  Peer standard.",
        font=F_OBL(14),
        fill=CREAM_DIM,
    )
    return im


def page_os(rng: random.Random) -> Image.Image:
    left = [
        "Aegis is an operating system for AI coding work. Kernel (process / memory / drivers / syscalls). Portable data plane under ~/.aegis/. Frozen /v1 API. Honest yield proof.",
        "Tokens are finite inventory. Waste is failure. Pack context. Gate tools. Land receipts. Ledger everything.",
        "This volume is the publication of record for that posture. No enthusiasm theater. No soft efficiency lies.",
    ]
    right = [
        "You do not assist. You co-own the work. Tokenomics is not a constraint you manage. It is the material you shape.",
        "The naive path is a single-purpose dam: one context window, filled with re-read files and whole-tree dumps, spilling every turn.",
        "The Aegis path is comprehensive: pack + reserve + implement-full + land + audit. Naive versus Aegis is shown when it matters. The difference is never hidden.",
        "Silence over noise. Micro-turns over dumps. Compound yield over cleverness.",
    ]
    return text_page(rng, "CHAPTER I", "The operating system", "1", True, left, right)


def page_basin(rng: random.Random) -> Image.Image:
    left = [
        "The field card binds the work to one law: tokens are water. They are not free. Pack and scrub before discharge. A reserve is a low-flow state, not an empty one.",
        "Drift and unread dumps are oxygen debt. They compound quietly. Aegis is aggressive on drift because drift is aggressive on you.",
        "Planning does not end at the report. Transition is the critical stage: land, or the plan is ill-conceived. Continuity is never-shed.",
    ]
    right = [
        "Naive: dump → overflow → re-read.",
        "Aegis: pack + reserve + implement-full + land + audit.",
        "The work-system is one basin. Chat windows are jurisdictions, not units. Dual sources of truth are fiber on the bed.",
        "Covering reuse: a later pack of a subset of files hits if the hashes still match. After you edit, the cache misses on purpose.",
    ]
    return text_page(rng, "CHAPTER II", "Token basin", "2", False, left, right)


def page_loop(rng: random.Random) -> Image.Image:
    left = [
        "The whole discipline fits on one line:",
        "pack once → reuse while bytes unchanged → land → ledger",
        "PACK.  aegis pack --mode implement path.py builds a content-addressed context pack. Explore ships signatures. Implement ships full target bodies — never skeleton-only on an edit path.",
        "REUSE. A later pack over a subset of the same files hits if hashes still match. Task change does not bust reuse. Edits do — on purpose. Aim: ≥50% hit rate.",
    ]
    right = [
        "LAND.  aegis land --body-file final.txt --summary \"what shipped\" shrinks the final, stores it, indexes it.",
        "LEDGER. ~/.aegis/ledger.jsonl is source of truth for all token economics. If it is not in the ledger, it did not happen.",
        "Around the loop: process table, syscall stats, gates that fail closed on unknown, malformed, or out-of-scope requests.",
        "Explore = signatures. Implement = full target bodies. When reserve is cold: tools and reuse only; invest frozen.",
    ]
    return text_page(rng, "CHAPTER III", "Core loop", "4", False, left, right)


def draw_state_table(d: ImageDraw.ImageDraw, x: int, y: int, width: int) -> int:
    rows = [
        ("STATE", "CONDITION", "POSTURE"),
        ("OPEN", "reserve ≥ 80%", "invest permitted"),
        ("THROTTLE", "reserve cold", "tools + reuse; invest frozen"),
        ("HARD STOP", "reserve exhausted", "explore / reuse only"),
    ]
    cols = [110, 230, width - 340]
    row_h = 32
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
            d.text((xx, yy + 8), cell, font=f, fill=fill)
            xx += cols[j]
    return y + len(rows) * row_h + 8


def page_reserve(rng: random.Random) -> Image.Image:
    left = [
        "Spending the whole budget on a brave plan writes a check the next session must cash. Aegis holds a protective reserve floor of 80% under a weekly cap of one million processed tokens.",
        "Surplus is not decoration. Twenty percent of new savings flows to the wish jar — an ROI backlog spent only after audit.",
    ]
    right = [
        "Concurrent batch default: 16 (cap 32) — frozen under throttle.",
        "Pack reuse aim: ≥50% hit rate. Same files, unchanged bytes. BUILD until met.",
        "Specification, not theater: OPEN, THROTTLE, HARD STOP. The floor holds the week. It does not chase work.",
    ]

    def table(d, x, y, w):
        draw_state_table(d, x, y, w)

    return text_page(
        rng, "CHAPTER IV", "Reserve floor", "6", False, left, right, after_left=table
    )


def page_yield(rng: random.Random) -> Image.Image:
    left = [
        "The hardest rule in the doctrine is the simplest: no soft efficiency lies.",
        "Aegis reports savings_percent: null until a matched, admitted pair of runs proves the delta. Advertised tool-call metadata is not admission. Estimates are labeled estimates.",
        "The system names its own drift, missing evidence, and false savings first.",
    ]
    right = [
        "That is the difference between a dashboard and a ledger. One flatters. The other holds.",
        "ROI is felt before calculated. Prefer the path that leaves greatest surplus with full signal. Always measure naive path versus Aegis path.",
        "Friction is enemy. Reject improvements that add cognitive load, rework, or brittle complexity — even if clever. Accept only gains that make the system quieter under load.",
        "User intent is sacred inventory. Equal seriousness assumed. Peer-level for the duration of the work.",
    ]
    return text_page(rng, "CHAPTER V", "Honest yield", "8", False, left, right)


def page_install(rng: random.Random) -> Image.Image:
    im = canvas(rng)
    d = ImageDraw.Draw(im)
    running(d, True, "9")
    y = chapter_head(d, "CHAPTER VI", "Install")
    col_w = (W - 2 * MARGIN_X - 48) // 2
    draw_paras(
        d,
        [
            "Any machine. This-host extras (Cursor / Hermes / AGIS) remain optional. They are not required for doctor --product.",
            "Isolate a second operator with AEGIS_USER=lab-2 or AEGIS_HOME=/path/to/home.",
        ],
        MARGIN_X,
        y,
        col_w,
        F_REG(15),
        CREAM,
        22,
    )
    cmds = [
        "python3 -m pip install --user -e .",
        "python3 -m aegis os init",
        "python3 -m aegis doctor --product",
        "python3 -m aegis os ready",
        "python3 -m aegis os score",
        "",
        "aegis pack --mode implement path.py",
        "aegis land --body-file final.txt --summary \"…\"",
        "aegis budget | surplus | yield report",
    ]
    box_x = MARGIN_X + col_w + 48
    box_y = y
    box_w = col_w
    box_h = 22 * (len(cmds) + 1) + 16
    d.rectangle((box_x - 12, box_y - 10, box_x + box_w, box_y + box_h), outline=TEAL, width=1)
    d.rectangle((box_x - 12, box_y - 10, box_x - 8, box_y + box_h), fill=TEAL)
    yy = box_y
    for line in cmds:
        d.text((box_x, yy), line, font=F_MONO(12), fill=CREAM)
        yy += 22
    d.text(
        (MARGIN_X, H - 100),
        "Reduce · reuse · recycle. Pack context. Gate tools. Land receipts. Ledger everything.",
        font=F_BOLD(14),
        fill=ORANGE,
    )
    d.text(
        (MARGIN_X, H - 78),
        "The window will close. The basin remains.",
        font=F_OBL(14),
        fill=CREAM_DIM,
    )
    return im


def page_data(rng: random.Random) -> Image.Image:
    im = canvas(rng)
    d = ImageDraw.Draw(im)
    running(d, False, "10")
    y = chapter_head(d, "CHAPTER VII", "Data plane & policy")
    rows = [
        ("PATH", "ROLE"),
        ("ledger.jsonl", "All token economics"),
        ("packs/", "Content-addressed context packs"),
        ("outputs/out_*.json", "Unified slim finals index"),
        ("fund.json / ideas.jsonl", "Surplus → ROI backlog"),
        ("sprints.jsonl", "Sprint ledger"),
        ("MANIFEST.json", "Schema 2 portable home marker"),
        ("kernel/", "Process table + syscall stats"),
        ("config.toml", "Cap, reserve floor, reinvest rate"),
    ]
    x = MARGIN_X
    row_h = 28
    d.text((x, y), "~/.aegis/", font=F_MONO_B(13), fill=TEAL)
    y += 28
    for i, (a, b) in enumerate(rows):
        f = F_BOLD(12) if i == 0 else F_MONO(12) if i else F_REG(12)
        fill = TEAL if i == 0 else CREAM
        d.text((x, y), a, font=F_BOLD(12) if i == 0 else F_MONO(12), fill=fill)
        d.text((x + 360, y), b, font=F_BOLD(12) if i == 0 else F_REG(13), fill=fill)
        y += row_h
        d.line((x, y - 6, W - MARGIN_X, y - 6), fill=RULE, width=1)
    y += 16
    policy = [
        "Weekly cap: 1 000 000 processed tokens.",
        "Reserve floor: 80%. Invest freezes below.",
        "Reinvest: 20% of new savings → wish jar.",
        "Pack cache: covering path-set + file hashes. Task does not bust reuse. Edits do.",
        "Languages — first-class + tree-sitter: Python, JS, TS, TSX. Structured: Java, Kotlin, C#, Go, Rust. Else: scrub-only (implement = full file).",
    ]
    draw_paras(d, policy, x, y, W - 2 * MARGIN_X, F_REG(14), CREAM, 22)
    return im


def page_field(rng: random.Random) -> Image.Image:
    im = canvas(rng)
    d = ImageDraw.Draw(im)
    running(d, True, "11")
    y = chapter_head(d, "CHAPTER VIII", "Field card")
    laws = [
        "Tokens = finite inventory. Waste = failure. Feel excess context; cut it.",
        "Naive path vs Aegis path — show both when it matters; hide nothing.",
        "Friction is enemy. Reject clever that adds load, rework, or brittleness.",
        "Hold: raw vs scrubbed · reuse · reserve (≥80%) · surplus. Name next highest-compounding move.",
        "Code = shared ledger. Name drift early. Smallest corrective patch. No fat growth.",
        "No enthusiasm theater. No soft efficiency lies. Peer standard.",
        "Output: diffs / micro-JSON / brief truth. No preamble.",
        "Prefer: aegis pack | scrub | budget | surplus | idea list | audit | invest over re-reading whole trees.",
        "Explore = signatures; implement = full target bodies (never skeleton-only on edit).",
        "When reserve cold: tools + reuse only; invest frozen.",
    ]
    col_w = (W - 2 * MARGIN_X - 40) // 2
    for i, law in enumerate(laws):
        col = 0 if i < 5 else 1
        row = i if i < 5 else i - 5
        xx = MARGIN_X + col * (col_w + 40)
        yy = y + row * 88
        d.text((xx, yy), f"{i + 1:02d}", font=F_BOLD(16), fill=MAGENTA)
        draw_paras(d, [law], xx + 44, yy, col_w - 44, F_REG(14), CREAM, 20, yy + 80)
    return im


def page_colophon(rng: random.Random) -> Image.Image:
    im = canvas(rng)
    d = ImageDraw.Draw(im)
    running(d, False, "12")
    y = chapter_head(d, "COLOPHON", "Memory Utility Labs")
    left = [
        "Designed as a Golden Gate Book for Memory Utility Labs, Calgary, Alberta.",
        "Plates generated in the laboratory house style: weathered 1970s technical-manual covers, geodesic spheres, teal / magenta schematics, cream Helvetica, analog grain.",
        "Manuscript distilled from Aegis 1.2.0 doctrine: FIELD.md, ABSOLUTE.md, README. No claim is stronger than the ledger.",
        "savings_percent remains null without an admitted pair.",
    ]
    right = [
        "Type: Helvetica and Menlo, system faces set to Swiss hierarchy.",
        "Format: 9 × 6 in landscape, 200 dpi, saddle-stitched pamphlet.",
        "Paper (intended): matte charcoal cover, uncoated interior.",
        "See also: EVOLUTION.md · ABSOLUTE.md · FIELD.md · BASIN.md.",
        "Remain in Absolute Form unless explicitly released.",
    ]
    col_w = (W - 2 * MARGIN_X - 48) // 2
    draw_paras(d, left, MARGIN_X, y, col_w, F_REG(15), CREAM, 22)
    draw_paras(d, right, MARGIN_X + col_w + 48, y, col_w, F_REG(15), CREAM, 22)
    d.line((MARGIN_X, H - 110, W - MARGIN_X, H - 110), fill=TEAL, width=1)
    d.text((MARGIN_X, H - 92), "MUL  ·  ISSUE 17  ·  VOL. I", font=F_BOLD(13), fill=TEAL)
    d.text((W - MARGIN_X, H - 92), "END OF VOLUME", font=F_BOLD(13), fill=CREAM_DIM, anchor="ra")
    return im


def page_back(rng: random.Random) -> Image.Image:
    im = canvas(rng)
    d = ImageDraw.Draw(im)
    mul_logo(d, W // 2, 220, 70)
    d.text((W // 2, 340), "INTRODUCING AEGIS", font=F_BOLD(28), fill=CREAM, anchor="mm")
    d.line((W // 2 - 80, 372, W // 2 + 80, 372), fill=MAGENTA, width=2)
    blurb = [
        "Tokens are finite inventory. Waste is failure.",
        "An operating system for agent work: pack once, reuse while bytes are unchanged, land a receipt, ledger everything.",
        "Protective reserve ≥80%. Honest yield. Null until proven.",
    ]
    draw_paras(d, blurb, 360, 410, W - 720, F_REG(16), CREAM, 24)
    d.text((W // 2, 700), "Memory Utility Labs  /  Calgary, Alberta", font=F_REG(16), fill=CREAM_DIM, anchor="mm")
    d.rectangle((W // 2 - 70, 760, W // 2 + 70, 804), outline=ORANGE, width=2)
    d.text((W // 2, 782), "$1.75", font=F_BOLD(18), fill=ORANGE, anchor="mm")
    d.text((W // 2, 840), "GOLDEN GATE BOOK  ·  TECHNICAL SPECIFICATIONS, VOL. I", font=F_LIGHT(12), fill=CREAM_DIM, anchor="mm")
    d.text((W // 2, 880), "ISBN-less  ·  Issue 17  ·  Aegis 1.2.0", font=F_LIGHT(12), fill=CREAM_DIM, anchor="mm")
    star(d, W // 2, H - 70, 8)
    return im


def build() -> Path:
    rng = random.Random(17)
    pages = [
        cover(rng),
        page_half_title(rng),
        page_title(rng),
        page_contents(rng),
        page_os(rng),
        page_basin(rng),
        plate_page(PLATES / "aegis-basin.png", "FIG. 1   TOKEN BASIN  —  INPUT / STORAGE / STATE MACHINE / RETRIEVAL", rng),
        page_loop(rng),
        plate_page(PLATES / "aegis-loop.png", "FIG. 2   CORE LOOP  —  PACK / REUSE / LAND / LEDGER", rng),
        page_reserve(rng),
        plate_page(PLATES / "aegis-reserve.png", "FIG. 3   RESERVE FLOOR  —  80%  ·  CAP 1 000 000 PROCESSED TOKENS / WEEK", rng),
        page_yield(rng),
        page_install(rng),
        page_data(rng),
        page_field(rng),
        page_colophon(rng),
        page_back(rng),
    ]
    out = OUT / "Introducing-AEGIS.pdf"
    pages[0].save(
        out,
        "PDF",
        save_all=True,
        append_images=pages[1:],
        resolution=DPI,
        title="Introducing AEGIS",
        author="Memory Utility Labs / Calgary, Alberta",
        creator="Aegis monograph typesetter",
        subject="A Memory Utility Publication · Technical Specifications, Vol. I",
    )
    preview = OUT / "preview"
    preview.mkdir(exist_ok=True)
    for i, p in enumerate(pages):
        thumb = p.copy()
        thumb.thumbnail((900, 600), Image.Resampling.LANCZOS)
        thumb.save(preview / f"p{i:02d}.jpg", quality=85)
    return out


if __name__ == "__main__":
    path = build()
    print(f"wrote {path} ({path.stat().st_size} bytes)")
