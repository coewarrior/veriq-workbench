'use strict';
// Keep existing model-management bookmarks working after the workspace moves.
function openLegacyAPIManager() {
  if (location.hash === '#apis') {
    location.replace('/api-testing' + location.search + location.hash);
  }
}
window.addEventListener('hashchange', openLegacyAPIManager);
openLegacyAPIManager();
