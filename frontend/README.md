# Frontend (v3)

Native HTML/CSS/JS with no build step, served by `backend/local_server.py` under `/assets/`. Scripts load in this order:

- `icons.js`: inline SVG icon sprite and the `Icon()` helper
- `zip.js`: dependency-free ZIP writer
- `render.js`: Canvas renderer (text fitting with measured sizes, image cover/contain, template art)
- `core.js`: state, server sync, rules, history (undo/redo), projects, assets, export, theme, menus
- `canvas.js`: infinite canvas with frames, pan/zoom, selection, drag/resize, keyboard
- `panels.js`: Layers, Assets, Design inspector, Rules tab, Add-frame popover
- `dnd.js`: file drops, rule bubbles, frame presets (each with a click alternative)
- `tour.js`: 9-step animated tour and Feature guides (`tour.css` holds the animations)
- `home.js`: home screen; boots the app
- `silk.js`: kinetic silk ribbon drawn behind the home screen (transparent mode via `data-transparent`, pausable, paused under reduced motion, stops when the editor opens)

`app.css` defines light/dark tokens on `:root[data-theme]`.
