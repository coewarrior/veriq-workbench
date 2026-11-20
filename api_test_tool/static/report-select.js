/* Custom report pickers keep the original select only as the form value source. */
(function(root){
'use strict';
let sequence=0,active=null;const pickers=new WeakMap();
function close(restore=false){
 const picker=active;if(!picker)return;active=null;
 if(picker.topLayer&&picker.menu.matches(':popover-open'))picker.menu.hidePopover();
 picker.menu.hidden=true;picker.trigger.setAttribute('aria-expanded','false');
 picker.trigger.removeAttribute('aria-activedescendant');
 if(restore&&picker.trigger.isConnected)picker.trigger.focus({preventScroll:true});
}
function position(){
 const picker=active;if(!picker)return;
 const {trigger,menu,wrapper}=picker,dialog=trigger.closest('dialog');
 if(!trigger.isConnected||trigger.disabled||(dialog&&!dialog.open)){close();return;}
 const rect=trigger.getBoundingClientRect(),view=root.visualViewport;
 const left=view?.offsetLeft||0,top=view?.offsetTop||0;
 const right=left+(view?.width||document.documentElement.clientWidth);
 const bottom=top+(view?.height||document.documentElement.clientHeight);
 const bounds=dialog?.getBoundingClientRect();
 if(!rect.width||rect.bottom<=Math.max(top,bounds?.top??top)||rect.top>=Math.min(bottom,bounds?.bottom??bottom)){close();return;}
 const floor=picker.topLayer?bottom:Math.min(bottom,bounds?.bottom??bottom);
 const ceiling=picker.topLayer?top:Math.max(top,bounds?.top??top);
 const below=Math.max(0,floor-rect.bottom-12),above=Math.max(0,rect.top-ceiling-12);
 const up=below<Math.min(240,menu.scrollHeight)&&above>below;
 const height=Math.min(280,up?above:below),width=Math.min(rect.width,right-left-16);
 menu.style.width=width+'px';menu.style.maxHeight=height+'px';
 if(picker.topLayer){
  menu.style.left=Math.max(left+8,Math.min(rect.left,right-width-8))+'px';
  menu.style.top=(up?rect.top-menu.getBoundingClientRect().height-6:rect.bottom+6)+'px';
 }else{
  // Older browsers still use a custom menu inside the dialog, never a native popup.
  menu.style.left='0';menu.style.top=up?'auto':'calc(100% + 6px)';
  menu.style.bottom=up?'calc(100% + 6px)':'auto';
  wrapper.classList.add('rr-select-fallback');
 }
}
function focusOption(picker,index){
 const options=picker.choices.filter(item=>!item.disabled);if(!options.length)return;
 const item=options[Math.max(0,Math.min(index,options.length-1))];
 picker.index=options.indexOf(item);
 picker.choices.forEach(choice=>choice.node.classList.toggle('rr-select-active',choice===item));
 picker.trigger.setAttribute('aria-activedescendant',item.node.id);
 const y=item.node.offsetTop,bottom=y+item.node.offsetHeight;
 if(y<picker.menu.scrollTop)picker.menu.scrollTop=y;
 else if(bottom>picker.menu.scrollTop+picker.menu.clientHeight)picker.menu.scrollTop=bottom-picker.menu.clientHeight;
}
function sync(picker){
 const {select,trigger,text,label}=picker;
 text.textContent=select.selectedOptions[0]?.textContent||'请选择';
 trigger.disabled=select.disabled;trigger.setAttribute('aria-label',label+'，'+text.textContent);
 trigger.title=text.textContent;
}
function choose(picker,index){
 const item=picker.choices.filter(choice=>!choice.disabled)[index];if(!item)return;
 const changed=picker.select.selectedIndex!==item.option.index;
 picker.select.selectedIndex=item.option.index;sync(picker);close(true);
 if(changed){
  picker.select.dispatchEvent(new Event('input',{bubbles:true}));
  picker.select.dispatchEvent(new Event('change',{bubbles:true}));
 }
}
function open(picker,last=false){
 close();sync(picker);if(picker.trigger.disabled)return;
 picker.menu.replaceChildren();picker.choices=[];
 let group=null;
 for(const option of picker.select.options){
  const parent=option.parentElement;if(parent?.tagName==='OPTGROUP'&&parent!==group){group=parent;const heading=document.createElement('div');heading.className='rr-select-group';heading.textContent=parent.label;picker.menu.append(heading);}
  if(option.hidden)continue;
  const node=document.createElement('div');node.id=picker.menu.id+'-'+option.index;
  node.className='rr-select-option';node.setAttribute('role','option');
  node.setAttribute('aria-selected',String(option.selected));node.textContent=option.textContent;
  const disabled=option.disabled||option.parentElement?.disabled;
  node.setAttribute('aria-disabled',String(Boolean(disabled)));
  const item={node,option,disabled};picker.choices.push(item);picker.menu.append(node);
  // Keep focus on the combobox until click commits the selection. Otherwise a
  // non-focusable option can move focus to the dialog and close the menu first.
  node.addEventListener('pointerdown',event=>event.preventDefault());
  node.addEventListener('pointermove',()=>{if(!disabled)focusOption(picker,picker.choices.filter(choice=>!choice.disabled).indexOf(item));});
  node.addEventListener('click',event=>{event.preventDefault();if(!disabled)choose(picker,picker.choices.filter(choice=>!choice.disabled).indexOf(item));});
 }
 active=picker;picker.menu.hidden=false;
 if(picker.topLayer)picker.menu.showPopover();
 picker.trigger.setAttribute('aria-expanded','true');position();
 if(active!==picker)return;
 const options=picker.choices.filter(choice=>!choice.disabled),selected=options.findIndex(choice=>choice.option.selected);
 focusOption(picker,selected>=0?selected:last?options.length-1:0);
}
function upgrade(container){
 for(const select of container.querySelectorAll('select:not([multiple])')){
  if(select.dataset.reportSelect)continue;select.dataset.reportSelect='true';
  const label=select.getAttribute('aria-label')||[...(select.closest('label')?.childNodes||[])].filter(node=>node.nodeType===3).map(node=>node.textContent.trim()).join(' ')||select.name||'选择';
  const wrapper=document.createElement('span');wrapper.className='rr-select';
  select.before(wrapper);wrapper.append(select);select.hidden=true;
  const trigger=document.createElement('button');trigger.type='button';trigger.className='rr-select-trigger';
  trigger.setAttribute('role','combobox');trigger.setAttribute('aria-haspopup','listbox');trigger.setAttribute('aria-expanded','false');
  const text=document.createElement('span');text.className='rr-select-value';trigger.append(text);
  const menu=document.createElement('div');menu.id='rr-select-menu-'+(++sequence);menu.className='rr-select-menu';
  menu.setAttribute('role','listbox');menu.setAttribute('aria-label',label);menu.hidden=true;
  trigger.setAttribute('aria-controls',menu.id);
  const topLayer=typeof menu.showPopover==='function';if(topLayer)menu.setAttribute('popover','manual');
  wrapper.append(trigger,menu);
  const picker={select,wrapper,trigger,text,menu,label,topLayer,choices:[],index:0,search:'',searchedAt:0};pickers.set(select,picker);sync(picker);
  trigger.addEventListener('click',event=>{event.preventDefault();if(active===picker)close();else open(picker);});
  trigger.addEventListener('keydown',event=>{
   const isOpen=active===picker,key=event.key;
   if(['ArrowDown','ArrowUp','Home','End','Enter',' '].includes(key)){
    event.preventDefault();
    if(!isOpen){open(picker,key==='ArrowUp'||key==='End');if(key==='Home')focusOption(picker,0);return;}
    if(key==='Enter'||key===' '){choose(picker,picker.index);return;}
    focusOption(picker,key==='Home'?0:key==='End'?picker.choices.length-1:picker.index+(key==='ArrowDown'?1:-1));
   }else if(key==='Tab')close();
   else if(key.length===1&&!event.ctrlKey&&!event.metaKey&&!event.altKey){
    event.preventDefault();if(!isOpen)open(picker);
    const now=Date.now();picker.search=(now-picker.searchedAt<700?picker.search:'')+key.toLocaleLowerCase();picker.searchedAt=now;
    const index=picker.choices.filter(choice=>!choice.disabled).findIndex(choice=>choice.option.textContent.trim().toLocaleLowerCase().startsWith(picker.search));
    if(index>=0)focusOption(picker,index);
   }
  });
  select.addEventListener('change',()=>sync(picker));
  select.form?.addEventListener('reset',()=>{close();setTimeout(()=>sync(picker),0);});
 }
}
document.addEventListener('pointerdown',event=>{if(active&&!active.wrapper.contains(event.target))close();},true);
document.addEventListener('focusin',event=>{if(active&&!active.wrapper.contains(event.target))close();});
document.addEventListener('keydown',event=>{if(active&&event.key==='Escape'){event.preventDefault();event.stopImmediatePropagation();close(true);}},true);
document.addEventListener('scroll',event=>{if(active&&!active.menu.contains(event.target))position();},true);
document.addEventListener('close',()=>{if(active&&!active.trigger.closest('dialog')?.open)close();},true);
root.addEventListener('resize',position);root.visualViewport?.addEventListener('resize',position);root.visualViewport?.addEventListener('scroll',position);
new MutationObserver(()=>{if(active&&!active.trigger.isConnected)close();}).observe(document.body,{childList:true,subtree:true});
root.ReportSelects={upgrade,sync:container=>{for(const select of container.querySelectorAll('select')){const picker=pickers.get(select);if(picker)sync(picker);}}};
})(globalThis);
