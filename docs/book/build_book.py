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
PELICAN = PLATES / "pelican"
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


def chapter_head(d: ImageDraw.ImageDraw, numeral: str, title: str, y: int = 78, x: int = MARGIN_X) -> int:
    d.text((x, y), numeral, font=F_LIGHT(15), fill=TEAL)
    d.text((x, y + 22), title, font=F_BOLD(32), fill=CREAM)
    d.line((x, y + 70, x + 200, y + 70), fill=TEAL, width=2)
    return y + 90


def paste_complement(im: Image.Image, path: Path, verso: bool) -> tuple[int, int]:
    """Plate on the outer edge, 3:4, full height. Returns (text_x, text_w)."""
    src = Image.open(path).convert("RGB")
    pw = int(round(H * 3 / 4))
    fitted = ImageOps.fit(src, (pw, H), Image.Resampling.LANCZOS)
    im.paste(fitted, (0 if verso else W - pw, 0))
    if verso:
        tx = pw + 40
        tw = W - tx - MARGIN_X
    else:
        tx = MARGIN_X
        tw = W - pw - MARGIN_X - 28
    return tx, tw


def fit_plate(path: Path, size: tuple[int, int]) -> Image.Image:
    im = Image.open(path).convert("RGB")
    return ImageOps.fit(im, size, Image.Resampling.LANCZOS)


def letterbox_plate(path: Path, size: tuple[int, int]) -> Image.Image:
    im = Image.open(path).convert("RGB")
    contained = ImageOps.contain(im, size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", size, CHARCOAL)
    canvas.paste(contained, ((size[0] - contained.width) // 2, (size[1] - contained.height) // 2))
    return canvas


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
    return scuff(fit_plate(PELICAN / "pelican-halftitle.png", (W, H)), rng)


def page_title(rng: random.Random) -> Image.Image:
    im = canvas(rng)
    tx, tw = paste_complement(im, PELICAN / "pelican-halftitle.png", verso=False)
    d = ImageDraw.Draw(im)
    d.text((tx, 90), "a Memory Utility Publication", font=F_LIGHT(16), fill=TEAL)
    d.text((tx, 140), "Introducing", font=F_REG(26), fill=CREAM)
    d.text((tx, 176), "AEGIS", font=F_BOLD(72), fill=CREAM)
    d.line((tx, 268, tx + 220, 268), fill=TEAL, width=3)
    d.text((tx, 296), "Memory Utility Labs", font=F_BOLD(20), fill=CREAM)
    d.text((tx, 326), "Calgary, Alberta", font=F_REG(16), fill=CREAM_DIM)
    d.text((tx, 380), "TECHNICAL SPECIFICATIONS, VOL. I", font=F_REG(13), fill=TEAL)
    d.text((tx, 408), "Product 1.2.0  ·  Issue 17  ·  2026", font=F_LIGHT(13), fill=CREAM_DIM)
    col = [
        "Agent operating system for AI coding work.",
        "Kernel · portable data plane · frozen /v1 API · honest yield proof.",
        "Reduce · reuse · recycle tokens. Pack context. Gate tools. Land receipts. Ledger everything.",
        "Absolute Form: austere · aggressive on drift · protective reserve (≥80%).",
    ]
    draw_paras(d, col, tx, 470, tw, F_REG(15), CREAM, 22)
    d.text((tx, H - 90), "$1.75", font=F_BOLD(18), fill=TEAL)
    d.text((tx + 80, H - 88), "GOLDEN GATE BOOK", font=F_REG(13), fill=CREAM_DIM)
    return im


def page_contents(rng: random.Random) -> Image.Image:
    im = canvas(rng)
    tx, tw = paste_complement(im, PELICAN / "pelican-contents.png", verso=True)
    d = ImageDraw.Draw(im)
    running(d, True, "", tx, tw)
    y = chapter_head(d, "CONTENTS", "This volume", 70, tx)
    items = [
        ("i", "Half title"),
        ("ii", "Title"),
        ("iii", "Contents"),
        ("1", "I.   The operating system"),
        ("2", "II.  Token basin"),
        ("3", "     Fig. 1  —  basin plate"),
        ("4", "III. Core loop"),
        ("5", "     Fig. 2  —  loop plate"),
        ("6", "IV.  Reserve floor"),
        ("7", "     Fig. 3  —  80% plate"),
        ("8", "V.   Honest yield"),
        ("9", "VI.  Install"),
        ("10", "VII. Data plane"),
        ("11", "VIII. Field card"),
        ("12", "Colophon"),
    ]
    f_num, f_item = F_LIGHT(14), F_REG(15)
    yy = y
    for num, title in items:
        d.text((tx, yy), num, font=f_num, fill=TEAL)
        d.text((tx + 48, yy), title, font=f_item, fill=CREAM)
        yy += 32
    return im


def text_page(
    rng: random.Random,
    numeral: str,
    title: str,
    folio: str,
    verso: bool,
    paras: list[str],
    plate: Path,
    after=None,
) -> Image.Image:
    im = canvas(rng)
    tx, tw = paste_complement(im, plate, verso)
    d = ImageDraw.Draw(im)
    running(d, verso, folio, tx, tw)
    y = chapter_head(d, numeral, title, 70, tx)
    y2 = draw_paras(d, paras, tx, y, tw, F_REG(15), CREAM, 22)
    if after:
        after(d, tx, y2 + 12, tw)
    d.line((tx, H - 118, tx + tw, H - 118), fill=RULE, width=1)
    d.text(
        (tx, H - 100),
        "No enthusiasm theater.  No soft efficiency lies.  Peer standard.",
        font=F_OBL(13),
        fill=CREAM_DIM,
    )
    return im


def page_os(rng: random.Random) -> Image.Image:
    paras = [
        "Aegis is an operating system for AI coding work. Kernel (process / memory / drivers / syscalls). Portable data plane under ~/.aegis/. Frozen /v1 API. Honest yield proof.",
        "Tokens are finite inventory. Waste is failure. Pack context. Gate tools. Land receipts. Ledger everything.",
        "This volume is the publication of record for that posture. No enthusiasm theater. No soft efficiency lies.",
        "You do not assist. You co-own the work. Tokenomics is not a constraint you manage. It is the material you shape.",
        "The naive path is a single-purpose dam. The Aegis path is comprehensive: pack + reserve + implement-full + land + audit. The difference is never hidden.",
        "Silence over noise. Micro-turns over dumps. Compound yield over cleverness.",
    ]
    return text_page(rng, "CHAPTER I", "The operating system", "1", True, paras, PELICAN / "pelican-os.png")


def page_basin(rng: random.Random) -> Image.Image:
    paras = [
        "The field card binds the work to one law: tokens are water. They are not free. Pack and scrub before discharge. A reserve is a low-flow state, not an empty one.",
        "Drift and unread dumps are oxygen debt. They compound quietly. Aegis is aggressive on drift because drift is aggressive on you.",
        "Naive: dump → overflow → re-read. Aegis: pack + reserve + implement-full + land + audit.",
        "The work-system is one basin. Chat windows are jurisdictions, not units. Covering reuse hits if hashes still match. After you edit, the cache misses on purpose.",
    ]
    return text_page(rng, "CHAPTER II", "Token basin", "2", False, paras, PELICAN / "pelican-basin.png")


def page_loop(rng: random.Random) -> Image.Image:
    paras = [
        "The whole discipline fits on one line: pack once → reuse while bytes unchanged → land → ledger.",
        "PACK. aegis pack --mode implement path.py. Explore ships signatures. Implement ships full target bodies — never skeleton-only on an edit path.",
        "REUSE. A later pack over a subset hits if hashes still match. Task change does not bust reuse. Edits do — on purpose. Aim: ≥50% hit rate.",
        "LAND. aegis land shrinks the final, stores it, indexes it. LEDGER. ~/.aegis/ledger.jsonl is source of truth. If it is not in the ledger, it did not happen.",
        "Gates fail closed on unknown, malformed, or out-of-scope requests. When reserve is cold: tools and reuse only; invest frozen.",
    ]
    return text_page(rng, "CHAPTER III", "Core loop", "4", False, paras, PELICAN / "pelican-loop.png")


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
    paras = [
        "Spending the whole budget on a brave plan writes a check the next session must cash. Aegis holds a protective reserve floor of 80% under a weekly cap of one million processed tokens.",
        "Surplus is not decoration. Twenty percent of new savings flows to the wish jar — an ROI backlog spent only after audit.",
        "Concurrent batch default: 16 (cap 32) — frozen under throttle. Pack reuse aim: ≥50% hit rate. Same files, unchanged bytes.",
        "Specification: OPEN, THROTTLE, HARD STOP. The floor holds the week. It does not chase work.",
    ]

    def table(d, x, y, w):
        draw_state_table(d, x, y, w)

    return text_page(
        rng, "CHAPTER IV", "Reserve floor", "6", False, paras, PELICAN / "pelican-reserve.png", after=table
    )


def page_yield(rng: random.Random) -> Image.Image:
    paras = [
        "The hardest rule in the doctrine is the simplest: no soft efficiency lies.",
        "Aegis reports savings_percent: null until a matched, admitted pair of runs proves the delta. Advertised tool-call metadata is not admission. Estimates are labeled estimates.",
        "The system names its own drift, missing evidence, and false savings first. That is the difference between a dashboard and a ledger. One flatters. The other holds.",
        "ROI is felt before calculated. Prefer the path that leaves greatest surplus with full signal. Friction is enemy. User intent is sacred inventory.",
    ]
    return text_page(rng, "CHAPTER V", "Honest yield", "8", False, paras, PELICAN / "pelican-yield.png")


def page_install(rng: random.Random) -> Image.Image:
    im = canvas(rng)
    tx, tw = paste_complement(im, PELICAN / "pelican-install.png", verso=True)
    d = ImageDraw.Draw(im)
    running(d, True, "9", tx, tw)
    y = chapter_head(d, "CHAPTER VI", "Install", 70, tx)
    y = draw_paras(
        d,
        [
            "Any machine. This-host extras (Cursor / Hermes / AGIS) remain optional. They are not required for doctor --product.",
            "Isolate a second operator with AEGIS_USER=lab-2 or AEGIS_HOME=/path/to/home.",
        ],
        tx,
        y,
        tw,
        F_REG(14),
        CREAM,
        20,
    )
    cmds = [
        "python3 -m pip install --user -e .",
        "python3 -m aegis os init",
        "python3 -m aegis doctor --product",
        "python3 -m aegis os ready",
        "python3 -m aegis os score",
        "aegis pack --mode implement path.py",
        "aegis land --body-file final.txt --summary \"…\"",
        "aegis budget | surplus | yield report",
    ]
    y += 10
    d.rectangle((tx, y, tx + tw, y + 22 * len(cmds) + 16), outline=TEAL, width=1)
    d.rectangle((tx, y, tx + 4, y + 22 * len(cmds) + 16), fill=TEAL)
    yy = y + 8
    for line in cmds:
        d.text((tx + 14, yy), line, font=F_MONO(11), fill=CREAM)
        yy += 22
    d.text((tx, H - 100), "Reduce · reuse · recycle.", font=F_BOLD(13), fill=TEAL)
    d.text((tx, H - 78), "The window will close. The basin remains.", font=F_OBL(13), fill=CREAM_DIM)
    return im


def page_data(rng: random.Random) -> Image.Image:
    im = canvas(rng)
    tx, tw = paste_complement(im, PELICAN / "pelican-data.png", verso=False)
    d = ImageDraw.Draw(im)
    running(d, False, "10", tx, tw)
    y = chapter_head(d, "CHAPTER VII", "Data plane & policy", 70, tx)
    rows = [
        ("ledger.jsonl", "token economics"),
        ("packs/", "content-addressed packs"),
        ("outputs/", "slim finals index"),
        ("fund.json", "surplus → ROI backlog"),
        ("sprints.jsonl", "sprint ledger"),
        ("kernel/", "process table"),
        ("config.toml", "cap / reserve / reinvest"),
    ]
    d.text((tx, y), "~/.aegis/", font=F_MONO_B(12), fill=TEAL)
    y += 26
    for a, b in rows:
        d.text((tx, y), a, font=F_MONO(11), fill=CREAM)
        d.text((tx + 200, y), b, font=F_REG(12), fill=CREAM_DIM)
        y += 24
        d.line((tx, y - 6, tx + tw, y - 6), fill=RULE, width=1)
    y += 10
    draw_paras(
        d,
        [
            "Weekly cap: 1 000 000. Reserve floor: 80%. Reinvest: 20% → wish jar.",
            "Pack cache: covering path-set + hashes. Task does not bust reuse. Edits do.",
        ],
        tx,
        y,
        tw,
        F_REG(13),
        CREAM,
        20,
    )
    return im


def page_field(rng: random.Random) -> Image.Image:
    im = canvas(rng)
    tx, tw = paste_complement(im, PELICAN / "pelican-field.png", verso=True)
    d = ImageDraw.Draw(im)
    running(d, True, "11", tx, tw)
    y = chapter_head(d, "CHAPTER VIII", "Field card", 70, tx)
    laws = [
        "Tokens = finite inventory. Waste = failure.",
        "Naive vs Aegis — show both; hide nothing.",
        "Friction is enemy. Reject clever that adds load.",
        "Hold: raw vs scrubbed · reuse · reserve · surplus.",
        "Code = shared ledger. Smallest patch. No fat growth.",
        "No enthusiasm theater. No soft efficiency lies.",
        "Output: diffs / micro-JSON / brief truth.",
        "Prefer aegis pack|scrub|budget over re-reading trees.",
        "Explore = signatures; implement = full bodies.",
        "Reserve cold: tools + reuse only; invest frozen.",
    ]
    for i, law in enumerate(laws):
        d.text((tx, y), f"{i + 1:02d}", font=F_BOLD(13), fill=TEAL)
        d.text((tx + 36, y), law, font=F_REG(13), fill=CREAM)
        y += 36
    return im


def page_colophon(rng: random.Random) -> Image.Image:
    im = canvas(rng)
    tx, tw = paste_complement(im, PELICAN / "pelican-colophon.png", verso=False)
    d = ImageDraw.Draw(im)
    running(d, False, "12", tx, tw)
    y = chapter_head(d, "COLOPHON", "Memory Utility Labs", 70, tx)
    draw_paras(
        d,
        [
            "Designed as a Golden Gate Book for Memory Utility Labs, Calgary, Alberta.",
            "Complementary plates follow Pelican / Swiss grid language: matte black, white, cyan, nested squares, one focal circle.",
            "Figure plates (cover, basin, loop, reserve) remain the laboratory geodesic style.",
            "Type: Helvetica and Menlo. Format: 9 × 6 in landscape, 200 dpi.",
            "Manuscript from Aegis 1.2.0: FIELD.md, ABSOLUTE.md, README. savings_percent remains null without an admitted pair.",
            "Remain in Absolute Form unless explicitly released.",
        ],
        tx,
        y,
        tw,
        F_REG(14),
        CREAM,
        21,
    )
    d.text((tx, H - 92), "MUL  ·  ISSUE 17  ·  VOL. I", font=F_BOLD(12), fill=TEAL)
    return im


def page_back(rng: random.Random) -> Image.Image:
    return scuff(letterbox_plate(PELICAN / "pelican-back.png", (W, H)), rng)


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
