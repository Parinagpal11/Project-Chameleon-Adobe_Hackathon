# Project Chameleon — resize a design without breaking it

**Adobe University Hackathon 2026 · Iowa State University team.** Chameleon takes an existing design and reshapes it for a new canvas size so it still looks intentionally designed: not stretched, not badly cropped. Fix one size once and every other size follows.

> **Status (Oct 6):** the companion tool, server, storage and tests below are working (v3). The design-preserving engine described in [docs/STRATEGY.md](docs/STRATEGY.md) is being built now. Schedule and checklist: [docs/PLAN.md](docs/PLAN.md). Submissions close **Oct 30, 2026**.

## Repository map

| Path | What's there |
|---|---|
| `backend/` | Python engine (`engine/`), service layer, HTTP server |
| `frontend/` | Companion tool: vanilla JS + Canvas, no build step |
| `examples/` | Sample designs (becomes the 36-design tiered test set) |
| `tests/` | Unit, HTTP and browser (Playwright) tests |
| `docs/` | Strategy, build plan |
| `design-system/` | UI tokens and rules for the companion tool |
| `benchmarks/`, `previews/` | Current benchmark output and screenshots |

## Run on your Mac

Requires Python 3.10+.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python run.py
```

Open http://127.0.0.1:8000. Stop with Control+C. If port 8000 is busy, use `python run.py --port 8001`. To host it for a demo, run `python run.py --host 0.0.0.0` (the `PORT` environment variable is respected). There is no login yet.

You don't need Node, an API key or a build step. Fonts load from Google Fonts when online and fall back to system fonts offline.

## 60-second demo

1. Home → **New from sample** (or pick the Stride / Northwind template). Six formats appear as frames on one canvas.
2. Drag the logo into a corner of **Instagram Post**. A popover asks *“Make this a rule? Logo pinned bottom right”*. Click **All frames**, and every frame updates with a green flash. Click **This frame only** instead to keep a one-off tweak.
3. Press **⌘K**, type “hide the offer on small banners”, and press Enter, then **Add rule**. The Leaderboard drops the offer.
4. Drag a **rule bubble** such as “Pin top-left” from the Rules tab onto a headline.
5. Drag a product photo and a logo from Finder onto the canvas. Chameleon sorts out which is which.
6. **Export** gives you a ZIP of PNGs, one per frame, plus a manifest.

Use **Tour** (top right) or **Main menu → Feature guides** for animated walkthroughs of every feature.

## Interface (familiar to designers)

| Area | What it does |
|---|---|
| Canvas | Every format is a labelled frame. Scroll to pan, ⌘/Ctrl + scroll to zoom, Space-drag or **H** to pan, **⇧1** zoom to fit, **⇧2** zoom to selection. Click to select, drag to move, corner handles to resize. |
| Layers (left) | Frames and their elements in a tree. Eye toggles hide an element in one frame. **+** adds frames from 14 presets or a custom size (click, or drag a preset onto the canvas). |
| Assets (left) | Product image and logo slots, four brand colors, six typefaces and shared copy. |
| Design (right) | Depends on the selection: campaign overview, frame (layout options, checks, tweaks, export) or element (All frames / This frame switch, role, copy, 9-dot pin picker, alignment, size, visibility). |
| Rules (right) | Plain-English rule box, draggable rule bubbles, and the campaign rule list with on/off switches and “Met in N frames” status. |
| Tool dock (bottom) | Move / Hand tools, zoom, and a ⌘K rule box. |
| Theme | Light and dark. Follows your system until you choose one with the sun/moon button. |

Keyboard: **V** move, **H** hand, **Tab** next element, arrows nudge (⇧ = 10 px), **Delete** hide in this frame, **Esc** undo a pending change, **⌘Z / ⇧⌘Z** undo/redo, **⌘K** rule box, **⌘E** export, **?** shortcuts sheet.

## What it can learn

| Rule | From an edit | From a bubble or inspector control | Typed |
|---|---|---|---|
| Order (A above/below B) | drag one element above or below another | — | “CTA below the offer” |
| Corner pin | drag into a corner | Pin bubbles · 9-dot picker | “logo top-left” |
| Alignment | drag a button or logo left, centre or right | Align bubbles · align control | “center the headline” |
| Size (prominence) | resize with a corner handle | Bigger/Smaller · size stepper | “make the CTA bigger” |
| Hide on small sizes | — | Hide bubble · visibility switch · Delete key, then “Hide in all frames this small” | “hide the offer on small banners” |

Rules are keyed by semantic **role** (headline, offer, CTA, logo, image, legal…), so they transfer to new designs. Rules learned from edits are re-verified on the server. The newest rule for a role replaces the older one, and contradictory order rules are rejected.

## Accuracy

- **Warnings come from what is actually drawn.** The renderer reports each text element's final fitted font size, so “Text under 12px” matches the exported PNG rather than a server estimate. The checks also cover overlaps, elements outside the frame, missing required elements and unmet rules.
- **Every rule is checked in every frame.** Size rules compare the element's size against the headline, using the expected type-scale ratio. They are no longer reported as met automatically.
- Wide banners get a dedicated layout (text | CTA | image), and narrow skyscrapers get a small-image layout.
- Each project is autosaved. Its link (`/#c=…`) reopens it, and browser Back returns to the home screen.

## Architecture

- `backend/engine/rules.py`: rule vocabulary, binding by role, per-frame checks (including real size verification) and the plain-English parser.
- `backend/engine/intent.py`: infers rules from a move, resize or hide.
- `backend/engine/generator.py`: layouts, including the banner and small-image strategies, per-glyph text measurement, pins, alignment, emphasis and hiding.
- `backend/service.py`: compile, score, batch transform, SQLite rules and projects, templates.
- `backend/local_server.py`: the default HTTP server. `backend/main.py` is an optional FastAPI adapter that hasn't been integration-tested.
- `frontend/`: `index.html`, `app.css` (light/dark tokens), `tour.css`, `silk.js` (animated ribbon behind the home screen), `icons.js` (SVG icons), `core.js` (state, sync, rules, history, projects, export), `canvas.js` (pan/zoom/select/drag), `panels.js` (layers, assets, inspector, rules), `dnd.js` (drag & drop), `tour.js` (animated tour and guides), `home.js`, `render.js`, `zip.js`.

API: `POST /transform-batch` · `/transform` · `/infer-edit` · `/learn` · `/parse-rule` · `GET|POST|DELETE /rules` · `PATCH|DELETE /rules/{id}` · `GET /projects` · `GET|PUT|DELETE /project?campaign=` · `GET /templates` · `GET /example?name=` · `GET /benchmark`

## Tests

```bash
python -m unittest discover -s tests -v        # 25 tests
```

`tests/test_ui_e2e.py` drives the real UI in Chromium. It covers dragging to learn a rule, undo/redo, ZIP export, frame-only tweaks, inspector rules, typed rules, bubble drag, adding frames, file drop and reopening a project. It skips itself unless Playwright is installed (`pip install playwright && python -m playwright install chromium`).

## Honest limits

- Layouts are heuristic: three strategies per shape and no aesthetic scoring.
- Input is Chameleon JSON or the templates. There's no Figma, PSD or image-to-layers import yet.
- It's single-user and local, with no accounts or sharing.
- Five rule types are learned. Brand-safety and color rules are not.

See `ROADMAP.md` for what comes next.
