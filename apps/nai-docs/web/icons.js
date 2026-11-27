// nAI's icons, all in one place: a name goes in, an icon comes out.
//
// Today these are line icons (24 grid, 2 px stroke). The shared Nithron pixel set (16 x 16, ink) replaces the
// whole map in this one file when it arrives; nothing else changes. Sizes are 16 px (rows, buttons, navigation)
// or 32 px (a screen title), never in between: a pixel icon cannot be scaled by a fraction.
//
//   <span class="icon" data-icon="search"></span>      filled in when the page loads
//   icon('close')                                       markup for templates in main.js

const ICON_SHAPES = {
  'search': '<circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/>',
  'upload': '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>',
  'file': '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>',
  'chat': '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
  'folder': '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>',
  'settings': '<circle cx="12" cy="12" r="3"/><path d="M12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4"/>',
  'arrow-right': '<line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>',
  'upload-arrow': '<polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>',
  'refresh': '<polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>',
  'plus': '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
  'send': '<line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>',
  'trash': '<polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>',
  'close': '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
};

const ICON_SIZES = [16, 32];

function icon(name, size = 16) {
  const shape = ICON_SHAPES[name];
  if (!shape) throw new Error(`unknown icon: ${name}`);
  if (!ICON_SIZES.includes(size)) throw new Error(`icon size must be 16 or 32, not ${size}`);
  return `<svg class="icon" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor"`
    + ` stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${shape}</svg>`;
}

function fillIcons(root = document) {
  root.querySelectorAll('[data-icon]').forEach((slot) => {
    slot.innerHTML = icon(slot.dataset.icon, Number(slot.dataset.iconSize || 16));
  });
}

fillIcons();
