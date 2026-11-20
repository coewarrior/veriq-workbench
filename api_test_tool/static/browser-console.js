'use strict';
globalThis.BrowserConsole=(()=>{
  async function open(target){
    const csrf=(await (await fetch('/api/orchestration/bootstrap')).json()).csrf;
    async function call(path,data){const r=await fetch(path,{method:data?'POST':'GET',headers:data?{'Content-Type':'application/json','X-CSRF-Token':csrf}:{},...(data?{body:JSON.stringify(data)}:{})});const v=await r.json();if(!r.ok)throw Error(v.detail||'现场请求失败');return v;}
    const info=await call('/api/orchestration/console',target),base='/api/orchestration/console/'+info.session_id;
    const d=document.createElement('dialog');d.className='managed-dialog';
    d.innerHTML='<div class="managed-heading"><h2>原浏览器现场</h2><button type="button" data-close>关闭</button></div><p class="managed-console-note" role="status"></p><div data-tabs class="managed-console-tools"></div><img class="managed-console-image" alt="等待原浏览器画面"><div class="managed-console-tools" data-input><input type="password" autocomplete="off" placeholder="先点击页面输入框，再在此输入文字"><button type="button" data-send>输入到页面</button><button type="button" data-key="Tab">Tab</button><button type="button" data-key="Enter">Enter</button><button type="button" data-key="Backspace">退格</button><button type="button" data-key="Control+A">全选</button><button type="button" data-key="Escape">Esc</button></div><button type="button" data-refresh>刷新现场</button>';
    document.body.append(d);d.showModal();let busy=false,frame=null,closed=false,timer,pageIndex;
    const image=d.querySelector('img'),note=d.querySelector('[role=status]');
    async function command(action,parameters={}){
      const request_id=Array.from(crypto.getRandomValues(new Uint8Array(16)),x=>x.toString(16).padStart(2,'0')).join('');
      await call(base+'/command',{action,parameters,request_id});
      for(let i=0;i<60&&!closed;i++){
        await new Promise(r=>setTimeout(r,500));const v=await call(base+'/command/'+request_id);
        if(v.state==='confirmed')return v.result;
        if(['unknown','not_sent'].includes(v.state))throw Error(v.result?.error||'结果未确认，请查看现场核实，勿重复操作');
      }
      throw Error('现场响应未确认，请查看任务状态；本次操作不会自动重发');
    }
    async function refresh(){
      if(busy||closed)return;busy=true;
      try{
        const result=await command('view',pageIndex===undefined?{}:{page_index:pageIndex});
        if(!result.image?.startsWith('data:image/jpeg;base64,'))throw Error('现场图像格式无效');
        frame=result;image.src=result.image;note.textContent=(result.editable?'可人工操作：点击或拖动现场；输入文字后按“输入到页面”。':'只读现场：模型执行期间不能人工输入。')+'\n'+result.url;
        d.querySelector('[data-input]').hidden=!result.editable;
        const tabs=d.querySelector('[data-tabs]');tabs.replaceChildren();for(const tab of result.tabs){const b=document.createElement('button');b.type='button';b.textContent=(tab.page_index+1)+'. '+tab.url;b.disabled=tab.page_index===result.page_index;b.onclick=()=>{pageIndex=tab.page_index;refresh();};tabs.append(b);}
      }catch(e){note.textContent=e.message;}finally{busy=false;}
    }
    async function input(action,parameters){if(busy||closed||!frame?.editable)return;busy=true;try{await command(action,{frame_id:frame.frame_id,...parameters});}catch(e){note.textContent=e.message;}finally{busy=false;}await refresh();}
    const point=e=>{const r=image.getBoundingClientRect();return {x:Math.floor((e.clientX-r.left)*frame.width/r.width),y:Math.floor((e.clientY-r.top)*frame.height/r.height)};};let down;
    image.onpointerdown=e=>{if(!frame?.editable||busy)return;down=point(e);image.setPointerCapture(e.pointerId);};
    image.onpointerup=e=>{if(!down)return;const p=point(e),start=down;down=null;input(Math.abs(p.x-start.x)+Math.abs(p.y-start.y)>8?'drag':'click',{...start,x2:p.x,y2:p.y});};
    image.onwheel=e=>{if(frame?.editable){e.preventDefault();input('scroll',{dx:e.deltaX,dy:e.deltaY});}};
    d.querySelector('[data-send]').onclick=()=>{const t=d.querySelector('input'),text=t.value;t.value='';input('text',{text});};
    d.querySelectorAll('[data-key]').forEach(b=>b.onclick=()=>input('key',{key:b.dataset.key}));
    d.querySelector('[data-refresh]').onclick=refresh;d.querySelector('[data-close]').onclick=()=>d.close();
    d.onclose=()=>{closed=true;clearInterval(timer);call(base+'/close',{}).catch(()=>{});d.remove();};
    await refresh();timer=setInterval(refresh,2500);
  }
  return {open};
})();
