# Chameleon — from hackathon demo to product

## 1. Design critique of the v1 UI (why it was rebuilt)

**First impression:** a marketing landing page. The animated ribbon and headline took the whole first screen, and the product started below the fold.

| Finding | Severity | What v2 does |
|---|---|---|
| One format at a time, in a 5-step wizard; users never saw the core promise ("every format") at once | 🔴 Critical | An **all-formats board** is the home view; the editor is one click away |
| Adapted output was a single full-width column with tiny single-line text (Story headline about 20px tall in a 1920px canvas) | 🔴 Critical | New typographic layout engine: wrap-aware sizing, real buttons, headline-led type scale |
| Learning only by "Move below the offer"; one rule type | 🔴 Critical | Five rule types learned from drag, resize, hide and toolbar actions, plus plain-English rules |
| Layout cards all showed "100" (meaningless score) | 🟡 Moderate | Cards show *rules met* and *named warnings* instead of a score |
| No undo, no persistence of designs, no real export batch | 🟡 Moderate | Undo/redo, autosaved projects, one-click ZIP export |
| Placeholder art only | 🟡 Moderate | Product image and logo upload, brand colors, typefaces, copy editing |
| Rules buried in a collapsed "details & benchmarks" section | 🟡 Moderate | A persistent **rules panel** with status, switches and delete |
| Mobile: stacked desktop layout | 🟢 Minor | Slide-over panels, compact top bar |

**What already worked and was kept:** auditable, deterministic rule inference; server-side verification of learned rules; honest scoping; the dark studio palette; the silk visual (now on the welcome screen only).

## 2. What makes it a product rather than a prototype

### Built in this version
- Multi-format board (14 presets + custom) with live status
- Five learnable rule types, learned from edits and typed in plain English
- Rule management: on/off, delete, coverage ("met in 6/6"), replace-latest, loop rejection
- Per-format manual overrides ("only this format")
- Brand kit: uploads, colors, typefaces, copy, role tagging
- Projects with autosave, recent list, JSON import/export
- One-click ZIP export of every size
- Undo/redo, shortcuts, onboarding tour, responsive layout, accessibility basics
- Hostable server (`--host 0.0.0.0`, `PORT` env)

### Next 2 weeks (highest leverage)
1. **Figma plugin import/export.** Read frames → elements + roles; write adapted frames back. Designers live in Figma, so this is the adoption unlock.
2. **LLM rule parser** as a fallback when the keyword parser can't understand a sentence, plus an "explain this layout" assistant. Keep the deterministic parser as the fast path.
3. **Image to layers.** Upload a flat ad (PNG/JPG), and a vision model segments it into headline, CTA, logo and image with roles.
4. **Smart crop / focal point** for product images, so the subject is never cut off in extreme ratios.
5. **Accounts + team workspaces** (auth, per-user projects, shared brand kits, roles). This needs Postgres instead of SQLite.

### Month 2–3
- **Brand rules beyond layout:** minimum logo clear space, approved color pairs, contrast checks, legal copy always present.
- **Approval workflow:** comment on a format, request changes, approve, with a rule history ("who taught this, when").
- **Rule library:** reuse a campaign's rules on the next campaign, plus org-wide defaults.
- **Platform publishing:** push exports straight to Meta, Google Ads and LinkedIn Campaign Manager with the right specs (safe zones, file-size limits).
- **Animated formats:** export MP4/GIF variants for Stories.
- **Localization:** translate copy per market and re-layout for longer text (German, French), with RTL support.

### Measuring that it works (replace the synthetic benchmark)
- **Corrections saved:** manual fixes needed across N formats without memory vs. with memory, measured on real designer sessions.
- **Time to ship a 12-format campaign:** by hand vs. with Chameleon. A 5-person study is enough for a pitch.
- **Rule precision:** the share of suggested rules designers accept.

## v3 changes (this round)

- **Designer-familiar workspace:** one zoomable canvas with every format as a frame, Layers/Assets panel, Design/Rules inspector, and a bottom tool dock. The panels float, and the light/dark themes give it its own look rather than copying Figma.
- **Home screen:** a file browser (New from sample, drop your brand images, Import JSON), 3 templates, and recent campaigns with thumbnails.
- **Drag & drop inspired by Image Playground:** drop images anywhere (logo vs photo is detected automatically), drop onto the image or logo to replace it, drag rule bubbles onto elements, drag frame presets onto the canvas. Every drag also has a click or keyboard path.
- **Animated tour:** 9 steps, each with a looping example, plus a Feature guides grid.
- **Accuracy:** warnings come from rendered text sizes, size rules are actually verified, and wide-banner and skyscraper layouts are better.

### Opinion: is Image Playground-style drag & drop a good idea?
Yes, for getting assets in and for applying rules as "bubbles". It is quick, visual and matches what designers already do in Canva and Figma. Two limits apply. It must never be the only way to do something (accessibility). And it shouldn't imply generative AI, because Chameleon arranges your assets rather than inventing new ones.

### Next corrections worth making
1. **Figma plugin import/export.** This is still the biggest adoption unlock.
2. **Smart crop / focal point** for product photos in extreme ratios.
3. **Auto-fix for warnings:** one click proposes the rule that clears a warning, for example hiding small legal copy on a 320×100 banner.
4. **An LLM fallback** for rule sentences the keyword parser misses.
5. **Accounts and shared brand kits.**

## 3. Pitch framing

- **Pain:** one campaign becomes 20+ sizes, and designers repeat the same fixes in every one.
- **Demo:** fix one format → every format updates → type a rule → export all.
- **Moat:** a campaign "memory" of designer intent that compounds over time. Resizing tools reset to zero every time.
- **Say plainly:** layout heuristics, five rule types, JSON input today; Figma and image import are next.
