/* Inline SVG icon set (24×24, 1.75 stroke, round caps). Usage: <svg class="i"><use href="#i-move"/></svg> or Icon('move'). */
(function (root) {
  'use strict';
  const P = {
    move: '<path d="M5 3l14 7-6 2-2 6z"/>',
    hand: '<path d="M8 13V5.5a1.5 1.5 0 013 0V11m0-6.5a1.5 1.5 0 013 0V11m0-5a1.5 1.5 0 013 0v7c0 4-2.5 7-6.5 7-2.5 0-4-1-5.5-3l-2.6-3.6a1.5 1.5 0 012.3-1.9L8 15"/>',
    zoomIn: '<circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2M11 8v6M8 11h6"/>',
    zoomOut: '<circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2M8 11h6"/>',
    undo: '<path d="M9 14L4 9l5-5"/><path d="M4 9h10a6 6 0 010 12h-3"/>',
    redo: '<path d="M15 14l5-5-5-5"/><path d="M20 9H10a6 6 0 000 12h3"/>',
    download: '<path d="M12 4v11m-5-5l5 5 5-5M5 20h14"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M4.9 4.9l1.4 1.4m11.4 11.4l1.4 1.4M2 12h2m16 0h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    moon: '<path d="M20 14.5A8 8 0 019.5 4 8 8 0 1020 14.5z"/>',
    help: '<circle cx="12" cy="12" r="9"/><path d="M9.6 9.2a2.5 2.5 0 014.8 1c0 1.7-2.4 2.2-2.4 3.6M12 17h.01"/>',
    layers: '<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 13l9 5 9-5"/>',
    image: '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="M21 16l-5-5-9 9"/>',
    palette: '<path d="M12 3a9 9 0 100 18c1.1 0 1.5-.8 1.5-1.5 0-1.3-1-1.6-1-2.8 0-1 .8-1.7 1.8-1.7H17a4 4 0 004-4c0-4.4-4-8-9-8z"/><circle cx="7.5" cy="11" r="1"/><circle cx="10" cy="7" r="1"/><circle cx="15" cy="7.5" r="1"/>',
    type: '<path d="M5 6V4h14v2M12 4v16m-3 0h6"/>',
    frame: '<path d="M7 3v18M17 3v18M3 7h18M3 17h18"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    trash: '<path d="M4 7h16M10 11v6m4-6v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
    eye: '<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    eyeOff: '<path d="M3 3l18 18M10.6 5.1A10 10 0 0112 5c6.4 0 10 7 10 7a17 17 0 01-3.2 4M6.6 6.6C3.9 8.4 2 12 2 12s3.6 7 10 7a9.6 9.6 0 005.4-1.6M9.9 9.9a3 3 0 004.2 4.2"/>',
    alignLeft: '<path d="M4 4v16M8 8h10M8 12h6M8 16h12"/>',
    alignCenter: '<path d="M12 4v16M6 8h12M8 12h8M5 16h14"/>',
    alignRight: '<path d="M20 4v16M6 8h10M10 12h6M4 16h12"/>',
    chevronDown: '<path d="M6 9l6 6 6-6"/>',
    chevronRight: '<path d="M9 6l6 6-6 6"/>',
    chevronLeft: '<path d="M15 6l-6 6 6 6"/>',
    x: '<path d="M6 6l12 12M18 6L6 18"/>',
    check: '<path d="M5 12.5l4.5 4.5L19 7"/>',
    alert: '<path d="M12 3l9.5 17h-19z"/><path d="M12 10v4m0 3h.01"/>',
    sparkle: '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z"/>',
    wand: '<path d="M4 20L16 8m-3-3l1-2m4 6l2-1M17 3l1 3 3 1-3 1-1 3-1-3-3-1 3-1z"/>',
    grid: '<rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/><rect x="4" y="13" width="7" height="7" rx="1.5"/><rect x="13" y="13" width="7" height="7" rx="1.5"/>',
    play: '<path d="M7 5l12 7-12 7z"/>',
    pause: '<path d="M8 5v14M16 5v14"/>',
    upload: '<path d="M12 16V5m-5 5l5-5 5 5M5 20h14"/>',
    chart: '<path d="M4 4v16h16"/><path d="M9 16v-4"/><path d="M13.5 16V8"/><path d="M18 16v-6"/>',
    file: '<path d="M14 3H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V8z"/><path d="M14 3v5h5"/>',
    command: '<path d="M9 6a3 3 0 10-3 3h12a3 3 0 10-3-3v12a3 3 0 103-3H6a3 3 0 103 3z"/>',
    menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
    home: '<path d="M4 11l8-7 8 7v9a1 1 0 01-1 1h-4v-6h-6v6H5a1 1 0 01-1-1z"/>',
    pin: '<path d="M12 21s-6-5.3-6-11a6 6 0 0112 0c0 5.7-6 11-6 11z"/><circle cx="12" cy="10" r="2.2"/>',
    resize: '<path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7"/>',
    order: '<path d="M8 4v16m0 0l-3-3m3 3l3-3M16 20V4m0 0l-3 3m3-3l3 3"/>',
    hide: '<path d="M3 3l18 18"/><rect x="4" y="6" width="16" height="12" rx="2"/>',
    size: '<path d="M4 20l6-16 6 16M6.5 14h7M17 9v6m-3-3h6"/>',
    target: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/>',
    folder: '<path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    book: '<path d="M4 5a2 2 0 012-2h13v16H6a2 2 0 00-2 2zM4 5v16"/>',
    more: '<circle cx="5" cy="12" r="1.2"/><circle cx="12" cy="12" r="1.2"/><circle cx="19" cy="12" r="1.2"/>',
    lock: '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 018 0v3"/>',
    keyboard: '<rect x="2.5" y="6" width="19" height="12" rx="2"/><path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M7 14h10"/>',
  };
  const NS = 'http://www.w3.org/2000/svg';
  const sprite = document.createElementNS(NS, 'svg');
  sprite.setAttribute('aria-hidden', 'true');
  sprite.style.cssText = 'position:absolute;width:0;height:0;overflow:hidden';
  sprite.innerHTML = Object.entries(P).map(([k, v]) => `<symbol id="i-${k}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">${v}</symbol>`).join('');
  const inject = () => document.body.prepend(sprite);
  if (document.body) inject(); else document.addEventListener('DOMContentLoaded', inject);
  /** Returns an <svg> element for icon `name`. Decorative by default (aria-hidden). */
  root.Icon = function (name, cls = 'i') {
    const s = document.createElementNS(NS, 'svg');
    s.setAttribute('class', cls); s.setAttribute('aria-hidden', 'true'); s.setAttribute('focusable', 'false');
    const u = document.createElementNS(NS, 'use'); u.setAttribute('href', '#i-' + name); s.append(u);
    return s;
  };
  root.ICON_NAMES = Object.keys(P);
})(window);
