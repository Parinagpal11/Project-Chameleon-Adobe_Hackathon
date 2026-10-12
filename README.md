# Project Chameleon: one design, every size

**Adobe University Hackathon 2026 · Iowa State University · Pari Nagpal, Priyanshu, Anwar.**

Chameleon takes one ad design and lays it out again for every format: Instagram Story, feed post, LinkedIn banner, leaderboard and more. It doesn't stretch or crop the design. For each size it finds the people and products in the photo, moves and re-sizes the text and photo for the new shape, tries several layouts, scores them against a plain resize, and explains in plain words why it picked the one it did.

## Run it

Requires Python 3.10+.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python run.py
```

Open http://127.0.0.1:8000 and stop with Control+C.

- The app restarts itself when backend code changes. Use `python run.py --no-reload` for demos.
- If port 8000 is busy, use `python run.py --port 8001`.
- To host it, run `python run.py --host 0.0.0.0` (the `PORT` environment variable is respected).
- No Node, API key, build step or internet connection is needed. Fonts are served with the app.

### Host it on Render

`render.yaml` describes the service, so Render can set it up from the GitHub repo:

1. Sign in at https://dashboard.render.com, choose **New → Blueprint**, and pick this repository.
2. Render reads `render.yaml` and creates the `chameleon` web service. Click **Apply** and wait for the first build (a few minutes).
3. Open the `onrender.com` link it gives you.

Good to know about the free plan:

- It sleeps after 15 minutes without visits, and the next visit takes about a minute to wake it. Open the link a few minutes before a demo.
- It has a small CPU. Each new photo takes several seconds to analyse there; the templates, the home page and the report are ready at once.
- Saved campaigns are lost when it restarts. Each visitor sees only their own campaigns.
- For judging, the paid Starter plan (5x the CPU, never sleeps) is faster. Change `plan: free` in `render.yaml`, or change the plan in Render's dashboard.

## Try it in a minute

1. On the home page, click **Try on a sample**. One design appears laid out for six sizes on one canvas.
2. Click a size's name. **Why it looks like this** explains each decision. **Layouts tried** shows every option the engine built, with its score. Click one to use it.
3. Under **Photo framing**, choose **Focus area** and drag a box over what matters, or choose **Whole photo** to never crop it. Every size follows.
4. Drag anything in one size to adjust it by hand. Only that size changes.
5. Drop your own photo and logo on the canvas, then click **Export** for a ZIP with a PNG of every size.

**Tour** walks through all of this on the real canvas. **How it works** shows what the engine did on your design, step by step. **Engine room** (`/xray`) is the full technical view.

## How the engine works

| Stage | What it does | Code |
|---|---|---|
| Understand | Groups elements, gives each a role (headline, button, logo, photo…), and finds faces, people or the main object in each photo | `backend/engine/understand.py`, `subject.py` |
| Plan | Decides how much each size has to change: keep the layout, re-flow it, or rebuild it | `backend/engine/plan.py` |
| Solve | Builds several candidate layouts per size and keeps text readable on photos | `backend/engine/adapt.py` |
| Check and score | Flags overlaps, anything off the edge, text under 12 px and low contrast, and scores every layout against stretch, crop and letterbox | `backend/engine/score.py` |

More detail is in [docs/ENGINE.md](docs/ENGINE.md), with the strategy in [docs/STRATEGY.md](docs/STRATEGY.md) and the schedule in [docs/PLAN.md](docs/PLAN.md).

## Repository map

| Path | What's there |
|---|---|
| `backend/engine/` | The layout engine (above). `models/` holds the photo models (U²-Net-P for the main subject, YOLOX-Nano for people); `fonts.json` holds glyph widths for measuring text. |
| `backend/service.py` | Request handling, project storage (SQLite), templates, result cache, start-up warm-up |
| `backend/local_server.py` | The default HTTP server. `backend/main.py` is an optional FastAPI version of it. |
| `frontend/` | The Studio, home, How it works, Engine room and report pages: plain JS and Canvas, no build step |
| `examples/templates/` | Starter designs with real photos |
| `examples/testset/` | The test set used by the Engine room, the report and the tests: 36 designs (12 hand-laid seeds and 24 with real photos), from 160×600 to 1080×1920 |
| `tools/` | Scripts that regenerate `fonts.json`, the test set (`make_seed_testset.py`, `make_photo_testset.py`) and the saved report (`make_eval_report.py`) |
| `tests/` | Engine, HTTP and browser (Playwright) tests |
| `docs/`, `design-system/` | Engine notes, strategy, plan; UI tokens and rules |

## API

- `POST /adapt`: a design plus target sizes in; for each size, the adapted design, its reasons, checks, score, the alternatives it tried, and stretch/crop/letterbox baselines out.
- `POST /analyze`: groups, roles, grid, reading order, photo subjects and tiers.
- `POST /convert`: converts a design saved in the older Studio format to the current format.
- `GET /templates`, `GET /example?name=`: starter designs.
- `GET /projects`, `GET | PUT | DELETE /project?campaign=`: saved campaigns.
- `GET /testset`, `GET /testset/{id}`, `GET /eval`: the test set and its scores.
- Pages: `/`, `/how`, `/xray`, `/report`.

## Speed

- **Results are remembered.** The engine gives the same result for the same design and sizes, so recent results are kept in memory. Reopening a campaign, the home demo and How it works answer instantly.
- **Models load at start-up.** The photo models load in the background when the server starts, so the first visitor doesn't wait for them.
- **The background ribbon doesn't slow the page.** It is drawn in a background worker at 30 frames a second and stops when you scroll past it.
- **The home page loads in order.** The hero shows the design first. The sections below load as you scroll toward them.
- **The report is saved.** `examples/eval-report.json` holds the scores for the whole test set. The server uses it while the test set and engine are unchanged, so `/report` opens at once even on a small host. Run `python tools/make_eval_report.py` after changing either.

## Tests

```bash
python -m unittest discover -s tests
```

The browser tests (`test_ui_e2e.py`, `test_xray_e2e.py`) drive the real pages in Chromium. They cover the sample, layouts, hand edits, export, photo framing, adding frames, dropping a photo, reopening a project, How it works, and the guided tour. They skip themselves unless Playwright is installed (`pip install playwright && python -m playwright install chromium`).

## Limits

- Input is Chameleon JSON, the templates, or your own photo and logo. There is no Figma or PSD import yet.
- There are no accounts or sharing. On a shared server each browser sees only its own campaigns.
- Some subjects are hard to find: a face filling the whole frame, a small landmark far away, people sitting at the very edges of a photo.
- A small banner can't always show a wide subject whole, such as a row of eight people in a 300×250 ad. Those sizes are scored for what they lose.
