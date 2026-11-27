// Keeps the pixel face on whole device pixels.
//
// Nithron Pixel is sharp only where each glyph starts on a whole device pixel. Body text above it (17 px at a 1.5
// line height), centred boxes and grid columns put it on fractions, and the browser then smooths its edges. This
// nudges every .pixel element by its own remainder with a relative offset (a layout position, not a transform),
// whenever the page changes, its size changes or the fonts arrive.

function snapPixelText() {
  const ratio = window.devicePixelRatio || 1;
  document.querySelectorAll('.pixel').forEach((element) => {
    element.style.left = '0px';
    element.style.top = '0px';
  });
  document.querySelectorAll('.pixel').forEach((element) => {
    const box = element.getBoundingClientRect();
    if (!box.width) return; // hidden
    const dx = Math.round(box.left * ratio) / ratio - box.left;
    const dy = Math.round(box.top * ratio) / ratio - box.top;
    element.style.left = `${dx}px`;
    element.style.top = `${dy}px`;
  });
}

let pixelSnapPending = false;

function schedulePixelSnap() {
  if (pixelSnapPending) return;
  pixelSnapPending = true;
  requestAnimationFrame(() => {
    pixelSnapPending = false;
    snapPixelText();
  });
}

new MutationObserver((records) => {
  // Our own offsets change only style attributes; react to content and class changes.
  if (records.some((record) => record.type === 'childList' || record.attributeName === 'class')) schedulePixelSnap();
}).observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['class'] });
window.addEventListener('resize', schedulePixelSnap);
if (document.fonts) document.fonts.ready.then(schedulePixelSnap);
schedulePixelSnap();
