# Project Chameleon — Strategy & Build Plan

Oct 5, 2026 · Pari Nagpal

> Living version (with diagrams): https://claude.ai/code/artifact/7e04c014-11a7-48a2-9f5b-47b767a97e07. This file is a snapshot; update both when the plan changes.

**Decision:** keep the companion tool and infrastructure, rebuild the engine so it understands a design before adapting it, and win on proof: a 288-case evaluation against stretch and crop, an X-ray view of the engine's thinking, and "fix once, every size follows". Submissions close Oct 30, 2026.

## 1. The problem Adobe is really asking us to solve

**One sentence:** turn one finished design into any other size so a designer would believe a person laid it out, without stretching, without bad crops, and without losing what made the original look the way it did.

Why Adobe set it, and why it is still unsolved:

- **Express already has Resize, and it is basic.** It's Premium-only, works one page at a time (no bulk), and its "intelligence" is mostly optional Generative Expand for images. Adobe's help page offers *Crop page* as the alternative when you don't want elements disturbed ([Adobe help](https://helpx.adobe.com/express/web/arrange-layers-and-pages/change-page-size.html)).
- **The real cost is the cleanup.** Marketers make one design and need 10–20 sizes. Any auto-resize gets them 70% of the way; the last 30% (text that no longer fits, a logo jammed in a corner, a photo cut through a face, a button that disappeared) is manual, per size, every time.
- **It's hard because a design is not a picture.** A good resize needs to know *what each element is for*, *which things belong together*, *what the layout grid was*, *what part of each photo matters*, and *how much the shape changed*. Scaling math knows none of that.
- **Express users aren't designers.** They can't fix a broken layout themselves, so the engine has to get it right, explain itself, and make fixes easy.

What Adobe will judge (our reading, until the Hub brief arrives):

| They will ask | So we must show |
| --- | --- |
| Does it look intentionally designed? | Side-by-side vs stretch and crop, on real designs, at extreme sizes |
| Does it work on designs it has never seen? | A test set of 30+ varied designs across 3 tiers, run live |
| Is the engine sound engineering? | A clear pipeline, measurable quality scores, tests, speed numbers |
| Can a judge see it working? | A companion tool that is obvious in 30 seconds |
| Could this ship in Express? | Express-like data model, fast enough for interactive use, an add-on path |

**Open question:** the Hub's exact tier definitions, input format and scoring. The plan below is built so those change details, not direction.

## 2. What exists today, and what other teams will build

Every current tool either keeps the old layout and breaks it, or throws it away. Nobody adapts the design *and* explains *and* remembers corrections.

| Approach | Who | What it gets right | Where it fails |
| --- | --- | --- | --- |
| Page resize + Generative Expand | [Adobe Express](https://helpx.adobe.com/express/web/arrange-layers-and-pages/change-page-size.html) | Fast; AI fills extra background | Premium only, one page at a time; layout fixes left to the user |
| Magic Resize / Magic Switch | [Canva](https://www.canva.com/help/resize/) | Bulk: up to 50 designs, 5 sizes each, 250 outputs | Counts against AI limits; results still need manual fixing at odd ratios |
| Constraints and auto layout | Figma (designer-built) | Precise once set up | Only works if a designer prepared every frame by hand |
| Responsive ad templates | Ad-tech creative tools | Reliable within a template | Locked to templates made in advance; can't take an arbitrary design |
| Scale + snap heuristics | Most student teams | Easy, works for similar ratios | Breaks at extreme ratios; text overflows; no notion of grouping |
| "Ask an LLM for new coordinates" | Many student teams | Impressive demo | Slow, costly, inconsistent run to run; overlaps and off-canvas text; hard to verify |
| Train a layout model | A few ML-heavy teams | Sounds advanced | No training data in 25 days; can't guarantee constraints; judges ask "how do you know it's right?" |

**Where we win:** a deterministic engine that *understands* the design first, solves the layout with hard guarantees (no overlap, nothing off canvas, readable text), scores every result against the original, explains its choices, and learns from the user's fixes. AI is used where it is strong (recognising roles and the subject of a photo, reading a plain-English instruction), not to guess pixel positions.

## 3. Honest evaluation of what we have

The current build is a good start: about 40% of the final product. The companion tool, server, storage and test setup are competition-grade. The engine is the weak part, because it replaces the original layout instead of adapting it.

| Area | Today | Verdict |
| --- | --- | --- |
| Companion tool (canvas of all sizes, inspector, before/after, export, undo, tour, light/dark) | Polished, tested in a browser, no console errors | **Keep**, reshape the main flow for judges |
| Rules learned from edits + plain-English rules | Works; 5 rule types, verified per size | **Keep** as the differentiator "Chameleon remembers" |
| Layout engine | Tags elements by role, discards their positions, drops them into 3 stock layouts | **Rebuild**: must preserve the original's grouping, alignment, margins and style |
| Input format | One simple ad schema: one image, one of each text role | **Rebuild**: multiple images, shapes, groups, backgrounds, layer order, text styles |
| Images | Cover-fit into a box; no subject detection | **Rebuild**: crop around the subject; extend backgrounds instead of stretching |
| Text sizing | Server estimate, then the browser shrinks to fit | **Fix**: one measurement source with real font metrics |
| Decorations | Always deleted | **Fix**: keep, move, scale or drop by importance and room |
| Quality checks | Overlap, off-canvas, text < 12px, rules met | **Extend**: add faithfulness to the original, balance, alignment, whitespace |
| Benchmark | Synthetic; the result is built in | **Replace** with a real test set and baselines |
| Tests | 25 automated + a 50-step browser script | **Keep** and grow with the new engine |
| Templates | 3 marketing samples | **Replace** with a tiered test set |

The main risk if we only polished the current engine: on Adobe's own designs it would lose each design's character and give every input the same look. Judges would notice in the first minute.

## 4. Our approach: understand, then adapt as little as needed

The engine works like a designer: read the design, decide how much has to change, change only that, check the result, and explain it. Five stages, each testable on its own.

1. **Understand (design graph).** Turn the input into a graph: elements with type, box, style and layer; then infer what a designer knows by looking.
   - Background vs foreground; repeated decorations.
   - Groups: elements that belong together, by proximity, alignment and shared style (headline + subhead, logo + tagline, price + button).
   - The grid: shared left/centre/right lines, margins, gutters.
   - Hierarchy and reading order from size, weight and position.
   - Anchors: what hugs an edge or corner.
   - Roles (headline, CTA, logo, legal, product image) from rules plus an optional vision model.
   - The subject of each photo (saliency / face detection), so crops keep it.
2. **Plan (how big is the change?).** Compare old and new aspect ratio and size, then pick a strategy tier. This also gives us a natural answer to Adobe's three tiers.
3. **Solve (constraint layout).** Express the plan as constraints (stay inside margins, keep groups together, keep alignments, keep order, minimum text size, keep the photo subject in view) and solve. Generate several candidates, not one.
4. **Score.** Rate every candidate: faithfulness to the original, legibility, balance, alignment, whitespace, nothing important lost, no overlap. Pick the best; keep the runners-up as alternatives.
5. **Explain and learn.** Say why in plain words ("kept your left alignment; moved the button beside the headline because the canvas is 6× wider"). When the user fixes something, offer to save it as a rule for all sizes.

| Tier | When | Strategy | Example |
| --- | --- | --- | --- |
| 1. Same family | Aspect ratio changes ≤ \~1.5× | Scale, keep anchors and margins, re-wrap text, re-crop photos around the subject | 1080×1080 → 1080×1350 |
| 2. New orientation | Portrait ↔ landscape | Keep groups intact, re-flow them along the new main axis, rebalance image and text areas | Post → Story or Feed banner |
| 3. Extreme | Ratio changes > \~4× or tiny canvases | Rebuild by importance: keep essentials, drop decoration, single-row or single-column layout, enforce minimum text size | Post → 728×90 or 160×600 |

Where AI helps, and where it doesn't:

- **Yes:** recognising roles and groups on messy designs, finding the subject of a photo, turning "keep the logo top-left" into a rule, writing the explanation.
- **No:** placing pixels. Positions come from the solver, so results are the same every run, fast, and guaranteed to have no overlaps or off-canvas text.

## 5. How we stand out

Five differentiators, each something a judge can see in under a minute.

1. **Faithful, not generic.** Each result keeps the original's grouping, alignment, colours and spacing. A "faithfulness score" proves it, next to the stretch and crop baselines.
2. **Hard guarantees.** No overlapping text, nothing off canvas, text never under 12px unless we warn. LLM-based teams can't promise this.
3. **It explains itself.** Every result comes with plain reasons and a tier label, so non-designers trust it and judges see the thinking.
4. **It remembers fixes.** Fix one size once and every other size follows. No competitor does this; it turns a one-off tool into a brand system.
5. **Fast and shippable.** Under \~200 ms per size on a laptop, same result every run, an Express-like data model, and a path to an Express add-on.

Why a user picks Chameleon over Canva or Express resize:

| They want | Others | Chameleon |
| --- | --- | --- |
| Fewer manual fixes | Layout fixes per size, every time | Fix once, applied everywhere |
| Confidence | Black box | Reasons, warnings, quality score |
| All sizes at once | One page (Express) or capped batches (Canva) | Every size on one canvas, one-click ZIP |
| Brand consistency | Not remembered | Rules saved per campaign |

Pitch line: **"Resize once. Fix once. Chameleon remembers."**

## 6. Product: features and the companion tool

The companion tool has one job for judges: show the engine winning in 30 seconds. Power features stay, one click deeper.

**Main flow (judge mode, the default):**

1. **Bring a design**: drop a file, pick from the tiered test set, or import JSON.
2. **Pick sizes**: presets grouped by Social / Display / Custom, with a "Tier 1 / 2 / 3" badge on each.
3. **Compare**: for each size, Stretch | Crop | Chameleon side by side. Slider to swipe between original and result.
4. **Understand**: each result shows its tier, faithfulness and legibility scores, and 2–3 plain reasons. Click a reason to highlight what it refers to.
5. **Fix and teach**: drag anything; Chameleon offers "apply to all sizes". "Show alternatives" cycles the runner-up layouts.
6. **Export**: one ZIP of PNGs plus a JSON report of scores.

**Advanced mode** (what we already built): canvas of all frames, layers, inspector with pin/align/size, rule list, brand assets, undo, projects, tour.

**Engine "X-ray" view** (our demo moment): overlay the detected groups, grid lines, anchors, photo subject and reading order on the original. It makes the intelligence visible.

| Feature | Priority | Status |
| --- | --- | --- |
| New engine with 3 tiers | Must | Rebuild |
| Stretch / Crop / Chameleon comparison + scores | Must | New (baseline exists) |
| X-ray overlay | Must | New |
| Tiered test set as built-in samples | Must | New |
| Plain-language reasons | Must | Extend explanations |
| Photo subject crop + background extend | Must | New |
| Fix once, apply everywhere | Should | Built |
| Alternatives per size | Should | Partly built (3 candidates) |
| Upload real designs (SVG/PNG → layers) | Could | New |
| Adobe Express add-on | Could | New |

UX principles we hold to: obvious in 30 seconds, every action undoable, no dead ends, keyboard and click alternatives for every drag, readable contrast in both themes, motion only where it explains.

## 7. Architecture: backend, frontend, data, infrastructure

One Python engine behind one API; everything else is a client of it. This keeps the engine testable on its own and lets an Express add-on reuse it later.

```
Clients:   Companion tool (judge mode + studio)  |  Evaluation runner  |  Express add-on (later)
                         \                 |                 /
API:                      FastAPI  —  /adapt  /analyze  /learn  /rules  /eval/report
                                            |
Engine:    1 Understand → 2 Plan (tier) → 3 Solve (constraints) → 4 Score → 5 Explain & learn
                                            |
Services:  OpenCV saliency/faces  |  Pillow font metrics  |  SQLite (projects, rules, eval runs)
```

| Layer | Choice | Why |
| --- | --- | --- |
| Engine | Python 3.11, pure functions per stage, Pydantic models | Already in place; easy to test and explain |
| Layout solver | Constraint solving (kiwisolver, the Cassowary algorithm used in UI layout) + scored candidates | Hard guarantees, fast, deterministic |
| Vision helpers | OpenCV saliency + face detection; optional small vision model for role hints | Runs locally, no API keys, no cost |
| Text measurement | Pillow with bundled open fonts, same metrics in browser and server | Ends the estimate-then-shrink mismatch |
| API | FastAPI (keep the zero-dependency server as a fallback) | Typed endpoints, auto docs for judges |
| Storage | SQLite: projects, rules, assets, evaluation runs | No setup; one file |
| Frontend | Current vanilla JS studio + new judge mode; Canvas rendering | No build step; already tested |
| Data model | Design graph: page, nodes (text, image, shape, group, background), styles, layers, constraints | Mirrors how Express documents are structured |
| Infrastructure | One-command run locally; Docker image; hosted demo (Render or Fly) for judges | Judges can click a link |
| Quality | Unit tests per stage, golden-image tests for the test set, browser E2E, GitHub Actions CI | Shows engineering discipline |

Key endpoints: `POST /adapt` (design + sizes → layouts, scores, reasons), `POST /analyze` (design → groups, grid, roles, subject for the X-ray), `POST /learn` and `/rules` (fixes → rules), `GET /eval/report`.

## 8. Evaluation: how we prove it works

We win on evidence: 36 designs × 8 target sizes = 288 cases, each scored against two baselines, plus a small human study.

**Test set (36 designs, 9 of each type):**

- Simple: text + one photo (promos, quotes, event posters).
- Medium: several images, shapes, grouped text, logo + legal line.
- Hard: full-bleed photo background, many elements, decorative shapes, dense text.
- Mixed styles: centred, left-aligned, grid, asymmetric. Built by the team in Express and exported, so they look like real Express work.

**Target sizes (8):** 1080×1350, 1080×1920, 1200×628, 1600×900, 1584×396, 300×250, 728×90, 160×600 (covers all three tiers).

| Metric | What it measures | Goal |
| --- | --- | --- |
| Overlap | Important elements overlapping | 0 |
| Off-canvas | Anything outside the frame | 0 |
| Legibility | Text smaller than 12px (as rendered) | 0, or warned |
| Content kept | Required elements still visible | 100% |
| Faithfulness | Similarity of grouping, alignment, order and relative size to the original | Beat both baselines |
| Subject kept | Photo subject inside the crop | ≥ 95% |
| Speed | Time per size on a laptop | < 200 ms |
| Human preference | 5–8 students pick the better of two results, blind | Chameleon preferred in most pairs |

**Baselines:** stretch (scale x and y), uniform scale + centre (letterbox), and centre crop. The report shows numbers plus a grid of before/after images.

The evaluation runs from one command and writes an HTML report, so judges can reproduce it.

## 9. The 25-day build plan

Build the engine first, prove it second, polish last. A working end-to-end version exists by Oct 19; everything after that makes it better and proves it.

See [PLAN.md](PLAN.md) for the week-by-week schedule.

**Team roles (3 people; merge for 2):**

| Person | Owns |
| --- | --- |
| A: engine lead | Design graph, Understand, solver, tier strategies |
| B: vision and quality | Photo subject crop, font metrics, scoring, evaluation report, test set |
| C: product and demo | Judge mode, X-ray view, hosting, README, video, pitch |

**Risks and fallbacks:**

| Risk | Fallback |
| --- | --- |
| Hub brief specifies an input format we don't support | Write an adapter into our design graph on day 1; the engine is unchanged |
| Solver too slow or unstable on complex designs | Keep the current layout generator as a fallback strategy and pick by score |
| Vision model adds setup pain | OpenCV-only saliency; role hints stay rule-based |
| Not enough real designs | Recreate popular Express templates by hand; vary copy length and images |
| Time runs out | Cut in this order: Express add-on, upload from PNG/SVG, alternatives UI |

**Submission checklist:**

- [ ] Engine adapts all 36 test designs to all 8 sizes with 0 overlaps and 0 off-canvas
- [ ] Evaluation report beats stretch and crop baselines on faithfulness and legibility
- [ ] Judge mode shows Stretch | Crop | Chameleon with scores and reasons
- [ ] X-ray view works on every sample
- [ ] One-command setup, README with sample inputs and outputs
- [ ] Hosted demo link
- [ ] 3-minute demo video
- [ ] CI green: unit, golden-image and browser tests
- [ ] Pitch deck: problem, insight, live demo, numbers, limits

## Sources

- [Adobe Express help: Resize page](https://helpx.adobe.com/express/web/arrange-layers-and-pages/change-page-size.html)
- [Canva help: Resize and Magic Switch](https://www.canva.com/help/resize/)
- Challenge description: Iowa State CyHire listing and the official hackathon flyer (shared by the team)
