// nAI's own confirmation dialog, in place of the browser's confirm() (DESIGN-APPS.md: destructive actions are
// confirmed in the product's own dialog, which names what it acts on).
//
//   if (await confirmDialog({ title: 'Delete car.pdf?', body: '…', confirmLabel: 'Delete document' })) { … }
//
// Resolves true on the confirm button, false on Cancel, Escape or a click on the backdrop. Focus goes to Cancel
// (the safe choice) and returns to where it was.

function confirmDialog({ title, body, confirmLabel, cancelLabel = 'Cancel' }) {
  return new Promise((resolve) => {
    const previousFocus = document.activeElement;
    const modal = document.createElement('div');
    modal.className = 'modal';
    modal.innerHTML = `
      <div class="modal-backdrop"></div>
      <div class="modal-content" role="alertdialog" aria-modal="true" aria-labelledby="confirmTitle" aria-describedby="confirmBody">
        <div class="modal-header"><h2 class="modal-title" id="confirmTitle"></h2></div>
        <div class="modal-body"><p id="confirmBody"></p></div>
        <div class="modal-footer">
          <button class="btn btn-secondary" type="button" data-answer="no"></button>
          <button class="btn btn-primary" type="button" data-answer="yes"></button>
        </div>
      </div>`;
    modal.querySelector('#confirmTitle').textContent = title;
    modal.querySelector('#confirmBody').textContent = body;
    const cancel = modal.querySelector('[data-answer="no"]');
    const confirm = modal.querySelector('[data-answer="yes"]');
    cancel.textContent = cancelLabel;
    confirm.textContent = confirmLabel;

    const close = (answer) => {
      document.removeEventListener('keydown', onKey, true);
      modal.remove();
      if (previousFocus && typeof previousFocus.focus === 'function') previousFocus.focus();
      resolve(answer);
    };
    const onKey = (event) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        close(false);
      } else if (event.key === 'Tab') {
        // Keep focus inside the dialog: it has two buttons.
        event.preventDefault();
        (document.activeElement === cancel ? confirm : cancel).focus();
      }
    };
    cancel.addEventListener('click', () => close(false));
    confirm.addEventListener('click', () => close(true));
    modal.querySelector('.modal-backdrop').addEventListener('click', () => close(false));
    document.addEventListener('keydown', onKey, true);
    document.body.appendChild(modal);
    cancel.focus();
  });
}
