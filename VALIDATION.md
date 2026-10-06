# Validation (v3)

Verified in the build environment with Python 3.13, Pydantic 2.13 and headless Chromium through Playwright.

## Automated: 25 tests, all passing
- **Engine:** every preset stays in bounds with no critical overlaps, down to 64×64. All 3 templates × 13 presets have no overlap, nothing out of bounds and no missing elements.
- **Rules:** order, pin, align, size and hide rules are met in 6 formats. Size rules are really verified: a layout that ignores the rule fails the check. Wide banners place the CTA beside the text.
- **Learning:** rules are inferred from move, resize, hide and corner-drag edits, and the server refuses rules the edit didn't demonstrate. The plain-English parser handles multi-clause sentences.
- **Persistence:** projects round-trip, rules support create, delete, toggle and replace, order loops roll back, and v1 databases migrate.
- **HTTP:** the full demo flow works, and every frontend asset and template is served.
- **Browser E2E (3 tests):**
  - Learn a rule by dragging, then undo/redo and export a ZIP of 6 PNGs at exact sizes.
  - Keep a frame-only tweak, add a rule from the inspector, add a typed rule.
  - Drag a bubble onto an element, add a frame, drop a file, reload and reopen.

## Manual browser runs (50 scripted checks passed)
- **Home:** templates and recents with thumbnails, back navigation, JSON import with unique naming.
- **Canvas:** zoom to fit, zoom to frame, Tab to cycle elements, nudge leading to the rule popover, Esc to cancel, Delete to hide in one frame, frame labels with warning and tweak flags.
- **Inspector:** the All frames / This frame scope, pin picker, alignment, size stepper, visibility switch (hide rule), and layout options per frame.
- **Rules:** ⌘K typed rule, bubble drag, bubble click, rule toggle and delete, coverage status.
- **Frames:** add from presets (click and drag), custom size, remove.
- **Drag & drop:** a photo dropped on the image slot becomes the product image, and a transparent PNG dropped anywhere becomes the logo.
- **Export and persistence:** ZIP (8 PNGs with exact sizes and a manifest), project JSON, reload via the `#c=` link, theme persisted.
- **Tour:** all 9 steps plus the feature-guide grid. The looping animations were checked frame by frame, and they freeze under reduced motion.
- Checked in light and dark themes at 1440×900 and at phone width (390×844). There were no console errors in any run.

## Design QA (ui-ux-pro-max checklist)
- SVG icons throughout, with no emoji used as icons. Icon-only buttons have accessible names.
- Text contrast is at least 4.5:1 for every text token on every surface in both themes. The light-theme warning and success colors were darkened to pass.
- Visible focus rings, pointer cursors, and 120–260 ms hover/press transitions.
- `prefers-reduced-motion` turns off transitions and freezes tour animations on a representative frame.
- The tour has Skip, Back, dot navigation and pause. Every drag has a click or keyboard equivalent (WCAG 2.2 dragging movements).

## Not verified here
- Safari and Firefox. Only Chromium is available in the build environment.
- Real typefaces. Google Fonts were blocked in the sandbox, so the fallback font was used. Because warnings use measured text, they stay accurate either way, but check how the typefaces look on your Mac.
- The optional FastAPI adapter.
