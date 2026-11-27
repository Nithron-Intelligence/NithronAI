// nAI's icons, all in one place: a name goes in, an icon comes out.
//
// The shapes are the shared Nithron pixel set, @nithron/icons 0.1.0 (Nithron Community License v1.0), copied
// from its svg/<name>.svg files: a 16 x 16 grid, ink (currentColor), crisp edges. Only the icons nAI uses are
// here; an update copies them again, never edits them. Shown at 16 px (rows, buttons, navigation, states) or
// 32 px, nothing in between: a pixel icon cannot be scaled by a fraction.
//
//   <span class="icon" data-icon="search"></span>      filled in when the page loads
//   icon('close')                                       markup for templates in main.js

const ICON_SHAPES = {
  'search': '<path d="M4 1H8V2H10V4H11V8H10V10H12V11H13V12H14V13H15V15H13V14H12V13H11V12H10V11H9V10H8V11H4V10H2V8H1V4H2V2H4ZM4 3V4H3V8H4V9H8V8H9V4H8V3Z"/>',
  'file': '<path d="M2 1H9V7H14V15H2ZM10 2H11V3H12V4H13V5H14V6H10Z"/>',
  'folder': '<path d="M1 2H7V3H9V4H15V14H1Z"/>',
  'upload': '<path d="M7 1H9V2H10V3H11V4H12V5H13V6H10V5H9V11H7V5H6V6H3V5H4V4H5V3H6V2H7ZM1 10H3V13H13V10H15V15H1Z"/>',
  'chat': '<path d="M2 2H14V3H15V9H14V10H7V11H6V12H5V13H3V10H2V9H1V3H2ZM4 5V7H6V5ZM7 5V7H9V5ZM10 5V7H12V5Z"/>',
  'settings': '<path d="M6 1H10V3H11V4H12V3H14V5H13V6H15V10H13V11H14V13H12V12H11V13H10V15H6V13H5V12H4V13H2V11H3V10H1V6H3V5H2V3H4V4H5V3H6ZM6 6V10H10V6Z"/>',
  'close': '<path d="M2 2H5V3H6V4H7V5H9V4H10V3H11V2H14V3H13V4H12V5H11V6H10V10H11V11H12V12H13V13H14V14H11V13H10V12H9V11H7V12H6V13H5V14H2V13H3V12H4V11H5V10H6V6H5V5H4V4H3V3H2Z"/>',
  'delete': '<path d="M6 1H10V2H15V4H13V14H3V4H1V2H6ZM5 5V12H7V5ZM9 5V12H11V5Z"/>',
  'refresh': '<path d="M12 1H14V6H8V4H5V5H4V11H5V12H11V11H12V7H14V11H13V12H12V13H10V14H6V13H4V12H3V11H2V5H3V4H4V3H6V2H10V3H11V4H12Z"/>',
  'send': '<path d="M13 1H15V3H14V5H13V7H12V10H11V12H10V14H8V12H7V9H8V8H9V7H10V6H11V5H12V4H13V3H12V4H11V5H10V6H9V7H8V8H7V9H5V8H2V6H4V5H6V4H9V3H11V2H13Z"/>',
  'external-link': '<path d="M8 1H15V8H13V4H12V5H11V6H10V7H9V8H8V9H5V8H6V7H7V6H8V5H9V4H10V3H8ZM1 4H7V6H3V13H10V9H12V15H1Z"/>',
  'copy': '<path d="M1 1H11V4H9V3H3V9H4V11H1ZM5 5H15V15H5Z"/>',
  'add': '<path d="M7 2H9V7H14V9H9V14H7V9H2V7H7Z"/>',
  'remove': '<path d="M3 3H5V4H6V5H7V6H9V5H10V4H11V3H13V4H12V5H11V6H10V7H9V9H10V10H11V11H12V12H13V13H11V12H10V11H9V10H7V11H6V12H5V13H3V12H4V11H5V10H6V9H7V7H6V6H5V5H4V4H3Z"/>',
  'sync': '<path d="M11 2H13V3H14V4H15V6H14V7H13V8H11V6H1V4H11ZM3 8H5V10H15V12H5V14H3V13H2V12H1V10H2V9H3Z"/>',
  'ok': '<path d="M4 4H12V12H4Z"/>',
  'warning': '<path d="M4 4H12V12H4ZM6 6V10H10V6Z"/>',
  'failed': '<path d="M4 4H6V5H7V6H9V5H10V4H12V6H11V7H10V9H11V10H12V12H10V11H9V10H7V11H6V12H4V10H5V9H6V7H5V6H4Z"/>',
  'running': '<path d="M6 6H10V10H6Z"/>',
  'notice': '<path d="M7 3H9V5H7ZM5 6H9V11H11V13H5V11H7V8H5Z"/>',
  'off': '<path d="M4 7H12V9H4Z"/>',
};

const ICON_SIZES = [16, 32];

function icon(name, size = 16) {
  const shape = ICON_SHAPES[name];
  if (!shape) throw new Error(`unknown icon: ${name}`);
  if (!ICON_SIZES.includes(size)) throw new Error(`icon size must be 16 or 32, not ${size}`);
  return `<svg class="icon icon-${name}" width="${size}" height="${size}" viewBox="0 0 16 16" fill="currentColor"`
    + ` shape-rendering="crispEdges" aria-hidden="true" focusable="false">${shape}</svg>`;
}

function fillIcons(root = document) {
  root.querySelectorAll('[data-icon]').forEach((slot) => {
    slot.innerHTML = icon(slot.dataset.icon, Number(slot.dataset.iconSize || 16));
  });
}

fillIcons();
