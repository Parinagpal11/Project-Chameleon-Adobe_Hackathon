# Synthetic transfer benchmark

24 seeded variations of one coffee campaign × four held-out target formats = 96 cases. Training uses a 1080×1920 Story. Evaluation uses square 1080×1080, landscape 1200×628, ultra-wide 1584×396 and mobile 320×480. Seed: 42.

Variants change source dimensions, element IDs, headline sizing, copy length, CTA ordering and optional required legal copy. These are related synthetic designs, not 24 independent professional campaigns.

For each design, one simulated position correction intentionally reverses its original CTA/offer ordering. The same inference code used by the app derives the relationship from that edit. Evaluation changes all element IDs and applies that rule to formats absent from the correction. The benchmark does not write campaign memory or use target-format edits. Because every correction reverses the original order, methods that preserve that order are expected to get close to 0/96. Chameleon without memory scores 12/96 only by coincidence: on the ultra-wide banner its side-by-side CTA layout happens to fall into the reversed vertical order. This is a test of rule transfer mechanics, not a surprising competitive advantage.

| Metric, summed across 96 cases | Naive scaling | Chameleon without memory | Chameleon with memory |
|---|---:|---:|---:|
| Critical content overlap pairs | 0 | 0 | 0 |
| Out-of-bounds elements | 0 | 0 | 0 |
| Required elements retained | 504/504 | 504/504 | 504/504 |
| Taught relationships preserved | 0/96 | 12/96 | 96/96 |
| Text elements below 12px | 52 | 0 | 0 |

Metrics use identical intent and denominators for all three arms. Required means non-removable metadata and retained means positive area, not readability. Overlaps count pairs of visible non-image elements with importance at least 0.7; they do not count every decorative or image intersection. Boundary counts measure canvas bounds. Text checks cover text, buttons and logos only when a font size is specified. The 12px threshold is a heuristic in design pixels, not a perceptual study. ABOVE/BELOW means full bounding-box separation in the y direction.

The scaling baseline multiplies x/width by the horizontal ratio and y/height by the vertical ratio; font size scales by the smaller ratio. This preserves clean geometry and original ordering. No deliberate baseline-only bugs are added.

Limitations: no human evaluation, real campaign diversity, learned typography/brand rules, statistical uncertainty estimate, or held-out designer study. A stronger research evaluation should collect independently authored designs and actual designer corrections before making claims about Adobe workflows or general design quality.

Regenerate from the project root with `python backend/benchmark.py > benchmarks/results.json`. The JSON includes per-design/per-format results for inspection.
