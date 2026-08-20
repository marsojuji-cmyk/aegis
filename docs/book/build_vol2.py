#!/usr/bin/env python3
"""Compose Introducing AEGIS Volume II — system architecture monograph.

Does not overwrite Volume I (build_book.py / Introducing-AEGIS-draft2.pdf).
"""
from __future__ import annotations

import importlib.util
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageOps

_SPEC = importlib.util.spec_from_file_location(
    "aegis_vol1_typeset", Path(__file__).with_name("build_book.py")
)
assert _SPEC and _SPEC.loader
v1 = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(v1)

W, H, DPI = v1.W, v1.H, v1.DPI
MARGIN_X = v1.MARGIN_X
CREAM, CREAM_DIM, TEAL, RULE = v1.CREAM, v1.CREAM_DIM, v1.TEAL, v1.RULE
F_LIGHT, F_REG, F_BOLD, F_OBL = v1.F_LIGHT, v1.F_REG, v1.F_BOLD, v1.F_OBL
CHARCOAL = v1.CHARCOAL

ROOT = Path(__file__).resolve().parents[1]
V2 = ROOT / "assets" / "pub" / "vol2"
OUT = Path(__file__).resolve().parent


def running(d: ImageDraw.ImageDraw, verso: bool, folio: str, x: int | None = None, w: int | None = None):
    f = F_LIGHT(13)
    x0 = x if x is not None else MARGIN_X
    x1 = (x + w) if (x is not None and w is not None) else (W - MARGIN_X)
    if verso:
        d.text((x0, 36), folio, font=f, fill=CREAM_DIM)
        d.text((x1, 36), "MEMORY UTILITY LABS", font=f, fill=CREAM_DIM, anchor="ra")
    else:
        d.text((x0, 36), "INTRODUCING AEGIS  VOL. II", font=f, fill=CREAM_DIM)
        d.text((x1, 36), folio, font=f, fill=CREAM_DIM, anchor="ra")
    d.line((x0, 52, x1, 52), fill=RULE, width=1)
    v1.star(d, (x0 + x1) // 2, H - 34, 5)


def essay_page(
    rng: random.Random,
    numeral: str,
    title: str,
    folio: str,
    verso: bool,
    paras: list[str],
    after=None,
) -> Image.Image:
    im = v1.canvas(rng)
    d = ImageDraw.Draw(im)
    running(d, verso, folio)
    y = v1.chapter_head(d, numeral, title)
    col_w = (W - 2 * MARGIN_X - 48) // 2
    mid = max(1, (len(paras) + 1) // 2)
    y2 = v1.draw_paras(d, paras[:mid], MARGIN_X, y, col_w, F_REG(15), CREAM, 22)
    v1.draw_paras(d, paras[mid:], MARGIN_X + col_w + 48, y, col_w, F_REG(15), CREAM, 22)
    if after:
        after(d, MARGIN_X, y2 + 10, col_w)
    d.line((MARGIN_X, H - 118, W - MARGIN_X, H - 118), fill=RULE, width=1)
    d.text(
        (MARGIN_X, H - 100),
        "No enthusiasm theater.  No soft efficiency lies.  Peer standard.",
        font=F_OBL(13),
        fill=CREAM_DIM,
    )
    return im


def poster_page(path: Path, folio: str, rng: random.Random, caption: str = "") -> Image.Image:
    """Letterbox portrait posters onto 9x6. Do not crop titles."""
    im = v1.letterbox_plate(path, (W, H))
    im = ImageEnhance.Contrast(im).enhance(1.03)
    im = v1.scuff(im, rng)
    if caption:
        d = ImageDraw.Draw(im)
        d.text((28, H - 42), caption, font=F_LIGHT(11), fill=CREAM_DIM)
        d.text((W - 28, H - 42), folio, font=F_LIGHT(11), fill=CREAM_DIM, anchor="ra")
    return im


def bleed(path: Path, rng: random.Random) -> Image.Image:
    return v1.scuff(v1.fit_plate(path, (W, H)), rng)


def page_title(rng: random.Random) -> Image.Image:
    im = v1.canvas(rng)
    tx, tw = v1.paste_complement(im, V2 / "v2-title-panel.png", verso=False, crop=False, inset=0.06)
    d = ImageDraw.Draw(im)
    d.text((tx, 90), "a Memory Utility Publication", font=F_LIGHT(16), fill=TEAL)
    d.text((tx, 140), "Introducing", font=F_REG(26), fill=CREAM)
    d.text((tx, 176), "AEGIS", font=F_BOLD(72), fill=CREAM)
    d.text((tx, 258), "VOLUME II", font=F_BOLD(28), fill=CREAM)
    d.line((tx, 310, tx + 220, 310), fill=TEAL, width=3)
    d.text((tx, 336), "Memory Utility Labs", font=F_BOLD(20), fill=CREAM)
    d.text((tx, 366), "Calgary, Alberta", font=F_REG(16), fill=CREAM_DIM)
    d.text((tx, 420), "SYSTEM ARCHITECTURE, VOL. II", font=F_REG(13), fill=TEAL)
    d.text((tx, 448), "Product 1.2.0  ·  Issue 1  ·  2026", font=F_LIGHT(13), fill=CREAM_DIM)
    col = [
        "Volume I stated the law. This volume states the machinery.",
        "Control plane. Token capacity basin. Guard middleware. Hermes routing.",
        "Honesty yield: savings_percent is billed USD on matched_provider_pairs (D-040). Routing is tiny-chat only. Implement packs stay off.",
        "Absolute Form: austere · aggressive on drift · protective reserve (>=80%).",
    ]
    v1.draw_paras(d, col, tx, 500, tw, F_REG(15), CREAM, 22)
    d.text((tx, H - 90), "GOLDEN GATE BOOK", font=F_REG(13), fill=CREAM_DIM)
    return im


def page_contents(rng: random.Random) -> Image.Image:
    im = v1.canvas(rng)
    d = ImageDraw.Draw(im)
    running(d, False, "")
    y = v1.chapter_head(d, "CONTENTS", "This volume", 70)
    items = [
        ("i", "Half title"),
        ("ii", "Title"),
        ("iii", "Contents"),
        ("1", "I.   Control plane"),
        ("2", "     kernel / process / frozen /v1"),
        ("3", "II.  Token capacity basin"),
        ("4", "     pack / scrub / reserve as low-flow"),
        ("5", "III. Guard middleware"),
        ("6", "     allow | deny | require-review"),
        ("7", "IV.  Hermes routing"),
        ("8", "     tiny-chat on; implement packs off"),
        ("9", "Colophon"),
    ]
    left, right = items[:7], items[7:]
    f_num, f_item = F_LIGHT(14), F_REG(16)

    def col(entries, x):
        yy = y
        for num, title in entries:
            d.text((x, yy), num, font=f_num, fill=TEAL)
            d.text((x + 48, yy), title, font=f_item, fill=CREAM)
            yy += 40

    col(left, MARGIN_X)
    col(right, W // 2 + 20)
    d.line((MARGIN_X, H - 100, W - MARGIN_X, H - 100), fill=RULE, width=1)
    d.text(
        (MARGIN_X, H - 88),
        "Issue 1.  Tiny-chat routing on (D-040).  Implement packs stay off.  Pack guesses stay unlabeled as savings_percent.",
        font=F_OBL(14),
        fill=CREAM_DIM,
    )
    return im


def page_control(rng: random.Random) -> Image.Image:
    paras = [
        "Kernel (process / memory / drivers / syscalls). Portable data plane under ~/.aegis/. Frozen /v1 API. Honest yield proof.",
        "aegis os init lays the plane. aegis doctor --product scores it. aegis os ready is the floor. Optional: aegis serve at http://127.0.0.1:8787 for OpenAI-compatible calls with body.aegis.pipeline=true.",
        "The serve daemon is not a host kernel. Agent-kernel scores are not Darwin scores. The plane is local. Hosted SaaS, consumer marketplace, and host-kernel replacement are out of scope.",
        "Volume I named the operating system. This chapter is the control surface: process table, frozen contract, local daemon. Nothing here authorizes a remote brain.",
    ]
    return essay_page(rng, "CHAPTER I", "Control plane", "1", True, paras)


def page_basin(rng: random.Random) -> Image.Image:
    paras = [
        "Tokens are water. They are not free. Pack and scrub before discharge. A reserve is a low-flow state, not an empty one.",
        "Weekly cap: 1 000 000 processed tokens. Reserve floor: 80%. OPEN / THROTTLE / HARD STOP. Surplus is not decoration: 20% of new savings to the wish jar after audit.",
        "Naive: dump -> overflow -> re-read. Aegis: pack + reserve + implement-full + land + audit.",
        "The work-system is one basin. Chat windows are jurisdictions, not units. Covering reuse hits if hashes still match. After you edit, the cache misses on purpose.",
    ]
    return essay_page(rng, "CHAPTER II", "Token capacity basin", "3", False, paras)


def page_guard(rng: random.Random) -> Image.Image:
    paras = [
        "Single path: request -> normalize -> ids -> classify -> policy -> fail-closed -> allow | deny | require-review -> execute only if permitted -> GuardDecision audit.",
        "Unknown tools deny. Malformed requests deny. Out-of-scope requests deny. Shadow mode defaults on: the decision is logged; the block is not yet the law. Turn shadow off when the catalog is trusted.",
        "Ledger: ~/.aegis/guard_log.jsonl. Rotate: aegis guard rotate. Hermes wrapper never raises to block a tool; it returns a structured deny payload instead.",
        "Hermes middleware itself is fail-open on raise. Guard must not be. Admission is a valve, not a suggestion.",
    ]
    return essay_page(rng, "CHAPTER III", "Guard middleware", "5", True, paras)


def page_hermes(rng: random.Random) -> Image.Image:
    paras = [
        "aegis hermes search|resolve is a thin read-only CLI over the local index. Track first. Perplexity only for a live external miss. Perplexity never edits.",
        "Coordination pathways are drawn. Tiny-chat routing is on (D-040): explore/review v4-pro may swap to nano. Implement packs stay on the requested model. savings_percent is observed billed USD, not a pack guess.",
        "Advertised tool-call metadata is not admission. A research note is not a routing trial. The index is a marshal. It is not a switch.",
        "The index is a marshal. Tiny-chat is a scoped trial, not a global switch. Implement packs are not routed.",
    ]
    return essay_page(rng, "CHAPTER IV", "Hermes routing", "7", False, paras)


def page_colophon(rng: random.Random) -> Image.Image:
    paras = [
        "Designed as a Golden Gate Book for Memory Utility Labs, Calgary, Alberta.",
        "Volume II plates follow 1970s NASA / GSFC technical-poster language: charcoal ground, cream Helvetica, muted teal / brick / mustard, drafting marks, analog grain. Chapter figures are the four system posters.",
        "Type: Helvetica. Format: 9 x 6 in landscape, 200 dpi. Product 1.2.0. Issue 1. 2026.",
        "Manuscript from FIELD.md, FIRST_RELEASE.md, D-040. savings_percent is billed USD on matched_provider_pairs. Tiny-chat routing on. Implement packs unrouted.",
        "Remain in Absolute Form unless explicitly released.",
    ]
    return essay_page(rng, "COLOPHON", "Memory Utility Labs", "9", True, paras)


def build() -> Path:
    required = [
        "v2-cover.png",
        "v2-intro.png",
        "v2-title-panel.png",
        "v2-contents.png",
        "v2-control.png",
        "v2-basin.png",
        "v2-guard.png",
        "v2-hermes.png",
        "v2-colophon.png",
        "v2-back.png",
    ]
    missing = [n for n in required if not (V2 / n).is_file()]
    if missing:
        raise SystemExit(f"missing Vol II plates: {missing}")

    rng = random.Random(2)
    pages = [
        bleed(V2 / "v2-cover.png", rng),
        bleed(V2 / "v2-intro.png", rng),
        page_title(rng),
        page_contents(rng),
        poster_page(V2 / "v2-contents.png", "iii", rng, "THIS VOLUME"),
        page_control(rng),
        poster_page(V2 / "v2-control.png", "2", rng, "FIG. 1"),
        page_basin(rng),
        poster_page(V2 / "v2-basin.png", "4", rng, "FIG. 2"),
        page_guard(rng),
        poster_page(V2 / "v2-guard.png", "6", rng, "FIG. 3"),
        page_hermes(rng),
        poster_page(V2 / "v2-hermes.png", "8", rng, "FIG. 4"),
        page_colophon(rng),
        poster_page(V2 / "v2-colophon.png", "10", rng, "COLOPHON"),
        bleed(V2 / "v2-back.png", rng),
    ]
    out = OUT / "Introducing-AEGIS-vol2.pdf"
    pages[0].save(
        out,
        "PDF",
        save_all=True,
        append_images=pages[1:],
        resolution=DPI,
        title="Introducing AEGIS Volume II",
        author="Memory Utility Labs / Calgary, Alberta",
        creator="Aegis monograph typesetter",
        subject="A Memory Utility Publication · System Architecture, Vol. II · Issue 1 · 2026",
    )
    preview = OUT / "preview-vol2"
    preview.mkdir(exist_ok=True)
    for i, p in enumerate(pages):
        thumb = p.copy()
        thumb.thumbnail((900, 600), Image.Resampling.LANCZOS)
        thumb.save(preview / f"p{i:02d}.jpg", quality=85)
    return out


if __name__ == "__main__":
    path = build()
    print(f"wrote {path} ({path.stat().st_size} bytes)")
