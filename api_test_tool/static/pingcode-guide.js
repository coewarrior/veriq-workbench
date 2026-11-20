'use strict';
(() => {
  const guide = document.getElementById('credentials-guide');
  const dialog = document.getElementById('pc-guide-image-dialog');
  const imageLink = document.getElementById('pc-guide-open-image');
  if (!guide || !dialog || !imageLink) return;

  function revealGuide() {
    guide.open = true;
    guide.scrollIntoView({block: 'start'});
  }
  document.querySelectorAll('a[href="#credentials-guide"]').forEach(link => {
    link.addEventListener('click', revealGuide);
  });
  function followHash() {
    if (location.hash === '#credentials-guide') revealGuide();
  }
  window.addEventListener('hashchange', followHash);
  followHash();

  document.getElementById('pc-guide-collapse').addEventListener('click', () => {
    guide.open = false;
    guide.querySelector('summary').focus();
    guide.scrollIntoView({block: 'start'});
  });
  imageLink.addEventListener('click', event => {
    if (typeof dialog.showModal !== 'function') return;
    event.preventDefault();
    if (!dialog.open) dialog.showModal();
  });
  document.getElementById('pc-guide-close-image').addEventListener('click', () => dialog.close());
  // Only close on a click that both starts and ends on the backdrop.
  const outside = event => {
    const r = dialog.getBoundingClientRect();
    return event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom;
  };
  let backdropDown = false;
  dialog.addEventListener('pointerdown', event => { backdropDown = outside(event); });
  dialog.addEventListener('click', event => {
    if (backdropDown && outside(event)) dialog.close();
    backdropDown = false;
  });
  // Native dialog handles Escape and restores focus to the image link.
})();
