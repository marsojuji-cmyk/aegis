# Introducing AEGIS

Memory Utility Labs monograph. 9 × 6 in landscape, 200 dpi.

**Volume I** (canonical current edition, 24 pages): geodesic laboratory plates — iridescent sphere, teal/magenta schematics, cream Helvetica. Each chapter is an essay page plus a full-bleed figure that matches that chapter. Its evidence table is rebuilt from the frozen, source-attributed `evidence-2026-08-20.json` snapshot so the prose, plate caption, and numbers cannot silently diverge.

```bash
PYTHONPATH=src python3 docs/book/build_book.py
```

Writes `Introducing-AEGIS-draft2.pdf`.

Preserved archives: [`Introducing-AEGIS.pdf`](Introducing-AEGIS.pdf) (17-page Pelican edition) and [`Introducing-AEGIS-draft2-live-type.pdf`](Introducing-AEGIS-draft2-live-type.pdf) (25-page live-type edition). Branch `archive/draft2-live-type`.

- Draft 2 plates: `docs/assets/pub/draft2/`
- Draft 1 (Pelican interiors): `Introducing-AEGIS.pdf` + `docs/assets/pub/pelican/`
- Cover/fig archive: `docs/assets/pub/aegis-*.png`

Manuscript: [`../PUBLICATION.md`](../PUBLICATION.md).

**Volume II** (system architecture, 16 pages): NASA/GSFC 1970s technical-poster plates — control plane, token capacity basin, guard middleware, Hermes routing. It extends Volume I rather than replacing it. The website is the living Volume III: a navigable laboratory for modules, experiments, evidence, and the knowledge layer.

```bash
PYTHONPATH=src python3 docs/book/build_vol2.py
```

Writes `Introducing-AEGIS-vol2.pdf`. Plates: `docs/assets/pub/vol2/`. Manuscript: [`../PUBLICATION-VOL2.md`](../PUBLICATION-VOL2.md).
