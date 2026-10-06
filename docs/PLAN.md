# Build plan — Oct 6 → Oct 30, 2026

Full reasoning lives in [STRATEGY.md](STRATEGY.md). Rule of thumb: **engine first, proof second, polish last.** A working end-to-end version must exist by **Oct 19**.

Team: **Pari Nagpal**, **Priyanshu**, **Anwar** (Iowa State University).

| Role | Owns | Person |
|---|---|---|
| A: engine lead | Design graph, Understand stage, solver, tier strategies | _to confirm_ |
| B: vision & quality | Photo subject crop, font metrics, scoring, evaluation report, test set | _to confirm_ |
| C: product & demo | Judge mode, X-ray view, hosting, README, video, pitch | _to confirm_ |

## Week 1 — Oct 6–12: understand the design
- [ ] Read the official Hub brief; adapt the input format and tier definitions (all)
- [ ] Design-graph schema: page, nodes (text, image, shape, group, background), styles, layers (A)
- [ ] Importer from the current Chameleon JSON + the brief's format (A)
- [ ] Understand stage: groups, grid lines, margins, anchors, reading order (A)
- [ ] Photo subject detection with OpenCV saliency/faces (B)
- [ ] Font metrics with Pillow + bundled open fonts, shared with the browser (B)
- [ ] Start the test set: 12 of 36 designs built in Express and exported (C)
- [ ] X-ray overlay prototype that draws the analysis on the original (C)

## Week 2 — Oct 13–19: adapt + first end-to-end
- [ ] Plan stage: tier from aspect-ratio change (A)
- [ ] Solve stage: constraint layout with kiwisolver, several candidates (A)
- [ ] Tier strategies: scale/re-wrap (1), re-flow groups (2), rebuild by importance (3) (A)
- [ ] Subject-aware crop + background extend (B)
- [ ] Score: faithfulness, legibility, balance, overlap, off-canvas (B)
- [ ] `POST /adapt` and `POST /analyze` (A)
- [ ] Judge mode: bring design → pick sizes → Stretch | Crop | Chameleon (C)
- [ ] Test set at 24 designs (C)
- [ ] **Milestone Oct 19:** every test design adapts to all 8 sizes end to end

## Week 3 — Oct 20–26: prove it
- [ ] Evaluation runner: 36 designs × 8 sizes vs stretch/letterbox/crop → HTML report (B)
- [ ] Fix the worst 20 cases from the report (A)
- [ ] Plain-language reasons per result; alternatives per size (A, C)
- [ ] Reconnect "fix once, apply everywhere" rules to the new engine (A)
- [ ] Blind preference study with 5–8 students (B)
- [ ] Hosted demo (Render or Fly) + Docker image (C)

## Week 4 — Oct 27–30: ship
- [ ] Freeze features Oct 27; bug fixes only
- [ ] README with sample inputs/outputs and one-command setup (C)
- [ ] 3-minute demo video (C)
- [ ] Pitch deck: problem, insight, live demo, numbers, honest limits (all)
- [ ] Submit by **Oct 30** — run the checklist in STRATEGY.md §9 first

## Cut order if time runs out
1. Express add-on 2. Upload PNG/SVG → layers 3. Alternatives UI
