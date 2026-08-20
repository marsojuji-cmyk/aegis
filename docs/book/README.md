# Introducing AEGIS

Memory Utility Labs monograph. 9 × 6 in landscape, 200 dpi.

**Draft 2** (current build): geodesic laboratory plates — iridescent sphere, teal/magenta schematics, cream Helvetica. Each chapter is an essay page plus a full-bleed figure that matches that chapter. No generator watermarks, no cite tags.

```bash
python3 docs/book/build_book.py
```

Writes `Introducing-AEGIS-draft2.pdf`.

Saved alternate: [`Introducing-AEGIS-draft2-live-type.pdf`](Introducing-AEGIS-draft2-live-type.pdf) (unlabeled plates, live type only). Branch `archive/draft2-live-type`.

- Draft 2 plates: `docs/assets/pub/draft2/`
- Draft 1 (Pelican interiors): `Introducing-AEGIS.pdf` + `docs/assets/pub/pelican/`
- Cover/fig archive: `docs/assets/pub/aegis-*.png`

Manuscript: [`../PUBLICATION.md`](../PUBLICATION.md).

**Volume II** (system architecture): NASA/GSFC 1970s technical-poster plates — control plane, token capacity basin, guard middleware, Hermes routing. Does not replace Draft 2.

```bash
python3 docs/book/build_vol2.py
```

Writes `Introducing-AEGIS-vol2.pdf`. Plates: `docs/assets/pub/vol2/`. Manuscript: [`../PUBLICATION-VOL2.md`](../PUBLICATION-VOL2.md).
