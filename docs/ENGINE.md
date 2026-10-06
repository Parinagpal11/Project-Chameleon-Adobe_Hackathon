# Engine v2 — design graph and the Understand stage

The new engine works in five stages: **Understand → Plan → Solve → Score → Explain**. This file covers what exists now: the input format, the Understand stage, Plan tiers, the Solve stage (`/adapt`), the test set and the X-ray view. Score comes next. See [STRATEGY.md](STRATEGY.md) §4 for the reasoning.

## 1. Input format: `chameleon-graph/1`

```json
{
  "format": "chameleon-graph/1",
  "name": "Spring promo",
  "page": { "width": 1080, "height": 1080, "background": "#F4EFE6" },
  "nodes": [
    { "id": "photo", "type": "image", "box": [0, 0, 600, 628], "src": "data:image/png;base64,...",
      "subject": [0.25, 0.2, 0.5, 0.65] },
    { "id": "headline", "type": "text", "box": [660, 170, 480, 126], "text": "Brew a little joy",
      "style": { "fontSize": 60, "fontWeight": 800, "fontFamily": "Inter", "color": "#1E1E1E", "align": "left", "lineHeight": 1.05 } },
    { "id": "cta-bg", "type": "shape", "shape": "rect", "box": [660, 410, 220, 64], "style": { "fill": "#C8693B", "radius": 32 } },
    { "id": "cta-label", "type": "text", "box": [672, 428, 196, 28], "text": "Start trial", "style": { "fontSize": 24, "fontWeight": 700, "align": "center" } },
    { "id": "cta", "type": "group", "children": ["cta-bg", "cta-label"] }
  ]
}
```

| Field | Meaning |
|---|---|
| `box` | `[x, y, w, h]` in page pixels. A group's box is computed from its children. |
| `type` | `text`, `image`, `shape` (`rect`, `ellipse`) or `group` |
| `z` | Optional paint order. The default is list order: later nodes are drawn on top. |
| `role` | Optional. Set it when you know it (`logo`, `headline`, `cta`, `legal`, `background`, `decoration`…). Given roles always win over inferred ones. |
| `subject` | Optional, images only: the region that must survive a crop, as image-relative `[x, y, w, h]` in 0–1 units. |
| `subjects[id].crop`, `kept`, `aspect`, `parts` | Subject-aware crop for photos whose subject was detected: the image-relative window `[x, y, w, h]` shown in the slot, and the share of the subject(s) it keeps. `parts` lists separate subjects (each face); if they can't all fit, the crop keeps the most of them rather than the gap between. Designer-given subjects get no crop (the photo keeps its default cover fit). | `subject.smart_crop` |
| `style` | Text: `fontSize`, `fontWeight`, `fontFamily`, `color`, `align`, `lineHeight`, `letterSpacing`. Shapes: `fill`, `radius`, `stroke`, `opacity`. |
| `meta` | Free-form, for example `label` for placeholder photos. |

**Limits and validation.** A design can have up to 300 nodes, and a request up to 30 targets of 16–8192 px. Numbers must be finite; `"40px"`, `"bold"` and `"centre"` are understood. Every bad input gets a 400 that names the node and the field. Group loops, self-groups and a node in two groups are rejected. Image `src` must be a `data:` URI: the server never opens file paths or URLs from a design. Images over 40 megapixels are refused, and photos are analysed on a copy of at most 800 px, cached per image.

The studio's older ad JSON (`canvas` + `elements`) is still accepted. `engine/graph.py` converts it, and buttons become a group of a shape and a label. When the official brief names an input format, we add one importer into this graph. The engine itself stays the same.

## 2. Understand: what `analyze()` returns

`POST /analyze` with `{"design": {...}, "targets": [...]}`. `targets` is optional and defaults to the 8 evaluation sizes. A design analyses in about 3 ms, and the same input always gives the same output.

| Key | What it is | How it's found |
|---|---|---|
| `layers` | Background, panels, containers, decoration, content | Coverage of the page, shapes that hold text, and thin or small shapes |
| `roles` | Per element: role, source (`given`/`inferred`/`layout`), confidence | Size hierarchy, position relative to the headline, button verbs, price and offer patterns, legal wording, captions under images, repeated styles |
| `groups` | Things that belong together: `text-stack`, `row`, `button`, `badge`, `card`, `lockup`, `image`, `text` | Union-find over proximity and alignment. Thresholds scale with font size; divider lines and things sitting in between block a join. Groups made by the author are kept as they are. |
| `blocks` | The parent level of groups. A **copy** block is a headline stack plus its button; **repeat** is cards or rows in a series; **stack** is other copy that moves together; **single** is everything else. Logos, legal lines, photos and corner-pinned badges stay single. | Hierarchical grouping as described in the layout literature: proximity, shared alignment edge, same column, and dividers that break a block. |
| `repeats` | Groups that repeat a pattern (cards in a row, rows in a list) | Same kind and size, aligned, with even gaps |
| `grid` | Margins, shared alignment lines, dominant alignment | Margins ignore full-bleed elements. Text adds only the edge it is aligned to. |
| `anchors` (per group) | `left`/`right`/`top`/`bottom`/`center-x`/`center-y`/`fill-x` | Distance to the margins. Groups that span margin to margin follow their own text alignment. |
| `reading_order` | Group ids in the order a reader meets them | Recursive XY-cut: true columns first, then rows |
| `subjects` | The part of each photo to keep (`page_box`, `page_parts`) | In order: a subject given in the design; faces (OpenCV Haar, which needs skin tone (or strict evidence on black-and-white photos), at least one eye, and a size of at least 30–50% of the main face); **objects** (the bundled U²-Net-P salient-object model, with wide or tall photos scanned in square tiles; equally strong separate objects are kept as parts); people (HOG full-body detector, only when no object stands out, and boxes cut off at the photo edge are rejected); otherwise centre (`assumed`). Without onnxruntime, classical colour-contrast saliency replaces the object step. |
| `style` | `structure` (overlay, split-horizontal, stacked, overlap, single), alignment, coverage, density | Hero vs headline-group geometry |
| `notes` | The findings in plain English | Shown in the X-ray view and used later for "why" explanations |
| `targets` | Per size: tier 1–3, strategy and reasons | `engine/plan.py` |

## 3. Plan: tiers

| Tier | When | Strategy |
|---|---|---|
| 1 Same family | Aspect ratio changes ≤ 1.5× and orientation is kept | Scale; keep anchors, margins and alignment; re-wrap text; re-crop photos around the subject |
| 2 New orientation | Portrait ↔ landscape, a change of up to 4×, or the same shape at under 35% of the size | Keep groups intact and re-flow them along the new axis |
| 3 Extreme | Change > 4×, or the short side ≤ 160 px | Rebuild by importance: essentials only, one row or column, protect text size |

## 3b. Solve: what `adapt()` does

`POST /adapt` with `{"design": {...}, "targets": [...]}` (targets optional, default the 8 evaluation sizes). Each result has the adapted `design` (same node ids; photos come back as `srcFrom` instead of repeating the image), `tier`, plain-English `reasons`, `checks` and `baselines`. All 12 test designs × 8 sizes pass the checks; a design adapts to all 8 sizes in about 10 ms.

| Tier | What Solve does |
|---|---|
| 1 | **Keep the layout.** Every group stays anchored to the edges it hugs (left/right/centre, top/bottom). Text re-wraps in its own lane, type scales by the geometric mean of the two axes, photos re-crop around their subject, and a longer headline pushes what sits under it down. The original size returns the design unchanged. If that can't be done cleanly (overlap, off canvas, text under 12 px), it falls back to tier 2. |
| 2 | **Re-flow by blocks.** Photo and copy go side by side on wide canvases and stacked on tall ones (a product cut-out keeps roughly its own shape, and the photo column narrows until the subject fits whole). Without a photo, cards go beside the copy on wide canvases. Type starts from the area ratio, then shrinks to fit. |
| 3 | **Rebuild by importance.** One row on banners (the logo joins the row), one column on skyscrapers, photo as a subject-shaped thumbnail. Shrink type down to 12 px, then show fewer cards (never fewer than 2), then drop pieces in this order: decoration, legal, caption, body, item, price, eyebrow, badge, cards, subhead, offer. Headline and button are never dropped. Every drop is listed in `reasons`. |

Building blocks: text stacks re-wrap; buttons re-size around their label; a group of several buttons (store badges) sits in a row or stacks; cards in a series (a `repeat` block) move together as a row, a grid or a column and never get text under 12 px; text rows (menu item … price) re-lay out instead of shrinking; a text logo is sized to its words. Full-bleed photos stay full-bleed with copy placed away from the subject; when the canvas is too extreme to keep the subject behind the copy, the photo becomes a side or top panel.

**Text measurement.** Text is wrapped with the real advance widths of the web fonts the studio loads (`engine/fonts.json`, built by `tools/make_font_metrics.py` from the Google Fonts files), with 3% slack. For fonts other than Inter the wider of the font and Inter is used, so text still fits if the web font fails to load and the page falls back to Inter. A light logo made to sit on the photo (white on a light page) stays on the photo or is dropped with a reason. A photo that would leave the copy no room is dropped. If nothing else fits, only the headline is kept, and the reasons say the size is too small.

`checks`: `overlaps` (except ones the designer made on purpose), `off_canvas`, `small_text` (text the renderer would draw under 12 px, measured the way it draws), `low_contrast` (text or logo that became hard to read where it now sits), `dropped`, `subject_kept`, `ok`. `baselines`: what plain stretching (distortion), centre crop (elements cut, subject kept) and letterboxing (empty share) would do at the same size.

## 4. Test set

`examples/testset/` holds 12 seed designs in this format (simple / medium / hard: centred promo, photo split, full-bleed overlay, poster with speaker cards, sale banner, quote card, product grid, webinar, story, dense menu, asymmetric big type, app download). `tools/make_seed_testset.py` regenerates them.

**To add a real design** (the goal is 36, built in Adobe Express):

1. Build it in Express and note every layer's position, size, text and style. Export the photos.
2. Write it as `examples/testset/<id>.json` in the format above. Use lowercase ids with dashes.
3. Add it to `examples/testset/index.json` (`id`, `name`, `width`, `height`, `level`, `tags`).
4. Open `/xray#d=<id>` and check that the groups, roles and reading order look right. Where they don't, fix the engine or add a `role`.

## 5. X-ray view

Open http://127.0.0.1:8000/xray. Pick a design, or import your own JSON, to see the groups, roles, alignment lines, margins, anchors, reading order, photo subjects and background or decoration layers drawn on the design. The side panel lists the findings, the groups (hover to locate them) and the tier for each of the 8 target sizes. The **Resize** tab shows every size three ways (Stretch, Centre crop, Chameleon) with the checks and the reasons.
