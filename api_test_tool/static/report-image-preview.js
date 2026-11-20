/* In-page screenshot preview shared by reports and the full case/data page. */
(function(){
'use strict';
const selector='.report-image-preview,a[href*="asset-"]';
function source(control){return control.dataset.imageSrc||control.getAttribute('href')||control.querySelector('img')?.currentSrc||control.querySelector('img')?.src||''}
function close(dialog){if(dialog?.open)dialog.close()}
function open(control){
 const src=source(control);if(!src)return;
 let dialog=document.getElementById('report-image-dialog');
 if(!dialog){
  dialog=document.createElement('dialog');dialog.id='report-image-dialog';dialog.className='report-image-dialog';
  dialog.innerHTML='<button type="button" class="report-image-close" aria-label="关闭图片预览">×</button><figure><img alt=""><figcaption></figcaption></figure>';
  document.body.append(dialog);
  dialog.querySelector('button').onclick=()=>close(dialog);
  dialog.addEventListener('click',event=>{if(event.target===dialog)close(dialog)});
 }
 const thumbnail=control.querySelector('img'),image=dialog.querySelector('img'),caption=dialog.querySelector('figcaption');
 image.src=src;image.alt=thumbnail?.alt||'截图预览';caption.textContent=thumbnail?.alt||'';
 dialog.showModal();
}
function prepare(){for(const anchor of document.querySelectorAll('a[href*="asset-"]')){if(!anchor.querySelector('img'))continue;anchor.removeAttribute('target');anchor.removeAttribute('rel');anchor.classList.add('report-image-preview')}}
document.addEventListener('click',event=>{const control=event.target.closest?.(selector);if(!control||(!control.dataset.imageSrc&&!control.querySelector('img')))return;event.preventDefault();open(control)});
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',prepare,{once:true});else prepare();
})();
