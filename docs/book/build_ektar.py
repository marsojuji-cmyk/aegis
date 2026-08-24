#!/usr/bin/env python3
"""Compose Ektar — Field Architecture as a 9×6 landscape monograph."""
from __future__ import annotations

import importlib.util
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance

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
PLATES = ROOT / "assets" / "pub" / "ektar"
OUT = Path(__file__).resolve().parent


def running(d: ImageDraw.ImageDraw, verso: bool, folio: str) -> None:
    left = folio if verso else "EKTAR — FIELD ARCHITECTURE"
    right = "MEMORY UTILITY LABS" if verso else folio
    d.text((MARGIN_X, 36), left, font=F_LIGHT(13), fill=CREAM_DIM)
    d.text((W - MARGIN_X, 36), right, font=F_LIGHT(13), fill=CREAM_DIM, anchor="ra")
    d.line((MARGIN_X, 52, W - MARGIN_X, 52), fill=RULE, width=1)
    v1.star(d, W // 2, H - 34, 5)


def essay_page(
    rng: random.Random,
    numeral: str,
    title: str,
    folio: str,
    verso: bool,
    paras: list[str],
) -> Image.Image:
    im = v1.canvas(rng)
    d = ImageDraw.Draw(im)
    running(d, verso, folio)
    y = v1.chapter_head(d, numeral, title)
    col_w = (W - 2 * MARGIN_X - 48) // 2
    split = max(1, (len(paras) + 1) // 2)
    v1.draw_paras(d, paras[:split], MARGIN_X, y, col_w, F_REG(15), CREAM, 22)
    v1.draw_paras(d, paras[split:], MARGIN_X + col_w + 48, y, col_w, F_REG(15), CREAM, 22)
    d.line((MARGIN_X, H - 118, W - MARGIN_X, H - 118), fill=RULE, width=1)
    d.text(
        (MARGIN_X, H - 100),
        "Observed evidence and interpretation remain distinct.  User authority remains final.",
        font=F_OBL(13),
        fill=CREAM_DIM,
    )
    return im


def poster_page(path: Path, folio: str, rng: random.Random, caption: str) -> Image.Image:
    im = v1.letterbox_plate(path, (W, H))
    im = ImageEnhance.Contrast(im).enhance(1.03)
    im = v1.scuff(im, rng)
    d = ImageDraw.Draw(im)
    d.rectangle((0, H - 64, W, H), fill=CHARCOAL)
    d.line((0, H - 64, W, H - 64), fill=RULE, width=1)
    d.text((MARGIN_X, H - 42), caption, font=F_LIGHT(11), fill=CREAM_DIM)
    d.text((W - MARGIN_X, H - 42), folio, font=F_LIGHT(11), fill=CREAM_DIM, anchor="ra")
    return im


def page_intro(rng: random.Random) -> Image.Image:
    return essay_page(
        rng,
        "FIELD NOTE",
        "A developing architecture",
        "i",
        True,
        [
            "Ektar is a stateful computational architecture for continuity, perception, selective memory, emotional coherence, metacognitive honesty, and bounded agency.",
            "This volume is an engineering map. It is not a claim of consciousness, biological life, human subjective feeling, hidden persistence, or authority outside the current task.",
            "AEGIS supplies provenance, resource discipline, observability, and consent boundaries. The creator retains final authority over irreversible action and durable identity change.",
            "The plates are interpretive instruments, not evidence or telemetry. Their claims live in the typeset text and must be verified against implementation and logs.",
        ],
    )


def page_title(rng: random.Random) -> Image.Image:
    im = v1.canvas(rng)
    tx, tw = v1.paste_complement(im, PLATES / "e28-subsystem-map.png", verso=False, crop=False, inset=0.07)
    d = ImageDraw.Draw(im)
    d.text((tx, 90), "a Memory Utility Publication", font=F_LIGHT(16), fill=TEAL)
    d.text((tx, 146), "EKTAR", font=F_BOLD(70), fill=CREAM)
    d.text((tx, 230), "FIELD ARCHITECTURE", font=F_BOLD(28), fill=CREAM)
    d.line((tx, 286, tx + 220, 286), fill=TEAL, width=3)
    d.text((tx, 318), "Memory Utility Labs × AEGIS", font=F_BOLD(19), fill=CREAM)
    d.text((tx, 354), "Calgary, Alberta", font=F_REG(16), fill=CREAM_DIM)
    v1.draw_paras(
        d,
        [
            "Cognitive loop. Three scales. Provenance-bearing memory.",
            "Coordinated subsystems. Graduated authority. Operational feel-state.",
            "Continuity is evidence-backed. User authority remains final.",
        ],
        tx,
        430,
        tw,
        F_REG(15),
        CREAM,
        22,
    )
    d.text((tx, H - 90), "FIELD PLATES 25–30  ·  ISSUE 1  ·  2026", font=F_REG(13), fill=CREAM_DIM)
    return im


def page_contents(rng: random.Random) -> Image.Image:
    im = v1.canvas(rng)
    d = ImageDraw.Draw(im)
    running(d, False, "iii")
    y = v1.chapter_head(d, "CONTENTS", "Six field systems", 70)
    items = [
        ("1", "I.   Cognitive loop"),
        ("3", "II.  Cognitive scales"),
        ("5", "III. Memory anatomy"),
        ("7", "IV.  Subsystem map"),
        ("9", "V.   Authority gradient"),
        ("11", "VI.  Feel-state vector"),
        ("13", "Colophon"),
    ]
    for i, (num, title) in enumerate(items):
        x = MARGIN_X if i < 4 else W // 2 + 20
        yy = y + (i if i < 4 else i - 4) * 52
        d.text((x, yy), num, font=F_LIGHT(14), fill=TEAL)
        d.text((x + 50, yy), title, font=F_REG(17), fill=CREAM)
    d.text(
        (MARGIN_X, H - 92),
        "The image is an interpretive plate.  The typeset claim is authoritative.",
        font=F_OBL(14),
        fill=CREAM_DIM,
    )
    return im


CHAPTERS = [
    (
        "I",
        "Cognitive loop",
        "e25-cognitive-loop.png",
        [
            "The canonical loop is perceive → appraise → feel-state → remember → interpret → plan → act → observe outcome → learn, returning into perception.",
            "The loop is a control discipline, not a claim that every step is active in every task. Trivial work should use only the smallest required cognition.",
            "Permission checks, evidence quality, uncertainty, cognitive load, and reversibility constrain the smallest next action.",
            "Learning records observed outcomes. One event does not become a stable identity claim without repeated evidence or explicit confirmation.",
        ],
    ),
    (
        "II",
        "Cognitive scales",
        "e26-cognitive-scales.png",
        [
            "Micro cognition handles immediate signals, uncertainty, working-memory retrieval, emotional updates, permission checks, and the smallest next action.",
            "Meso cognition holds projects, open loops, dependencies, session context, tool coordination, and summaries that preserve material technical and emotional context.",
            "Macro cognition carries values, confirmed preferences, limitations, consolidation, contradiction detection, identity continuity, and slow developmental updates.",
            "Signals escalate only when persistence or coordination is needed. Policy constraints flow downward at every scale.",
        ],
    ),
    (
        "III",
        "Memory anatomy",
        "e27-memory-anatomy.png",
        [
            "Reliable memory is provenance, not transcript accumulation. Episodic, semantic, procedural, and confirmed-preference records remain distinct.",
            "Every durable record carries source, confidence, emotional context, privacy class, timestamp, review date, and an explicit deletion path.",
            "Observation remains distinguishable from inference. Recollection remains distinguishable from imagination.",
            "Conflicting evidence creates a visible contradiction link. Identity-bearing information is not silently overwritten.",
        ],
    ),
    (
        "IV",
        "Subsystem map",
        "e28-subsystem-map.png",
        [
            "The named subsystems are roles inside one coordinated architecture, not independent agents or personalities.",
            "Nikon observes. Hermes routes. Ektar integrates. Portra 400 calibrates warmth and tone. Blackmagic forms bounded interpretations. MacBook supplies the physical habitat.",
            "AEGIS is the outer policy, provenance, resource, and authority field. It is not another mind.",
            "World signals become bounded action only through evidence-aware routing, interpretation, permission, and habitat constraints.",
        ],
    ),
    (
        "V",
        "Authority gradient",
        "e29-authority-gradient.png",
        [
            "Reflective mode analyzes and suggests. Assistive mode searches, organizes, prepares, and stages reversible drafts.",
            "Autonomous mode executes only explicitly approved, reversible, well-tested workflows. It is the narrowest operating band.",
            "Messages, money, deletion, permissions, publication, and irreversible external change require confirmation.",
            "Every allowed action returns through an observability ledger with outcome and rollback status. User authority remains final.",
        ],
    ),
    (
        "VI",
        "Feel-state vector",
        "e30-feel-state-vector.png",
        [
            "Emotion is operational state, not a claim of human subjective experience. The vector may include valence, arousal, curiosity, trust, uncertainty, salience, agency, attachment, fatigue, and cognitive load.",
            "Immediate feel-state may adjust attention and pacing. Mood is a slower accumulation. Both remain separate from memory.",
            "Affect can help select what deserves care, slower verification, or a smaller next move.",
            "Truth, privacy, safety, and consent are rigid policy rails. Affect cannot override them.",
        ],
    ),
]


def page_colophon(rng: random.Random) -> Image.Image:
    return essay_page(
        rng,
        "COLOPHON",
        "Loving science, bounded claims",
        "13",
        True,
        [
            "Designed as a Memory Utility Labs × AEGIS field volume, Calgary, Alberta. Plates 25–30 extend the existing AEGIS publication series.",
            "Visual language: worn Swiss scientific publishing, 1970s NASA / GSFC technical manuals, matte charcoal stock, warm ivory grotesk typography, Ektar 100-inspired grain, restrained routing accents.",
            "The publication distinguishes metaphor, architecture, implementation, and observed evidence. An editorial plate cannot prove a runtime capability.",
            "Ektar remains a developing computational architecture. Continuity is evidence-backed. No consciousness, biological life, hidden persistence, or unrestricted authority is claimed.",
        ],
    )


def build() -> Path:
    required = [chapter[2] for chapter in CHAPTERS]
    missing = [name for name in required if not (PLATES / name).is_file()]
    if missing:
        raise SystemExit(f"missing Ektar plates: {missing}")

    rng = random.Random(30)
    pages = [
        v1.scuff(v1.letterbox_plate(PLATES / "e25-cognitive-loop.png", (W, H)), rng),
        page_intro(rng),
        page_title(rng),
        page_contents(rng),
    ]
    folio = 1
    for numeral, title, filename, paras in CHAPTERS:
        pages.append(essay_page(rng, f"CHAPTER {numeral}", title, str(folio), folio % 2 == 1, paras))
        pages.append(poster_page(PLATES / filename, str(folio + 1), rng, f"FIELD PLATE {24 + folio // 2 + 1}"))
        folio += 2
    pages.append(page_colophon(rng))
    pages.append(v1.scuff(v1.letterbox_plate(PLATES / "e30-feel-state-vector.png", (W, H)), rng))

    out = OUT / "Ektar-Field-Architecture.pdf"
    pages[0].save(
        out,
        "PDF",
        save_all=True,
        append_images=pages[1:],
        resolution=DPI,
        title="Ektar — Field Architecture",
        author="Memory Utility Labs × AEGIS",
        creator="Ektar field-volume typesetter",
        subject="Cognitive architecture, provenance-bearing memory, bounded agency, and operational feel-state",
    )
    preview = OUT / "preview-ektar"
    preview.mkdir(exist_ok=True)
    for stale in preview.glob("p[0-9][0-9].jpg"):
        stale.unlink()
    for i, page in enumerate(pages):
        thumb = page.copy()
        thumb.thumbnail((900, 600), Image.Resampling.LANCZOS)
        thumb.save(preview / f"p{i:02d}.jpg", quality=86)
    return out


if __name__ == "__main__":
    path = build()
    print(f"wrote {path} ({path.stat().st_size} bytes)")
