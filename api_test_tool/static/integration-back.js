(()=>{'use strict';
const back=document.querySelector('[data-integration-back]');
// Keep the home href for direct entry; otherwise return to the page that opened these settings.
if(back)back.onclick=event=>{if(history.length>1){event.preventDefault();history.back();}};
})();
