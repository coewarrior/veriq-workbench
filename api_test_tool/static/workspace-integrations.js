(() => {
  'use strict';
  const settings = {
    7: {id: 'pingcode-management', path: '/integrations/pingcode', scripts: ['pingcode.js', 'pingcode-guide.js']},
    8: {id: 'wecom-management', path: '/integrations/wecom', scripts: []}
  };
  const loads = new Map();
  let returnStage = 1;
  const stageForHash = hash => ({'#integrations': 7, '#wecom': 8})[hash];

  function loadScript(name) {
    return new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = '/static/' + name;
      script.onload = resolve;
      script.onerror = () => { script.remove(); reject(new Error('配置功能加载失败，请重试。')); };
      document.head.append(script);
    });
  }

  async function load(n) {
    const setting = settings[n], host = document.getElementById(setting.id);
    host.innerHTML = '<p class="hint" role="status">正在加载配置…</p>';
    host.setAttribute('aria-busy', 'true');
    host.inert = true;
    try {
      const response = await fetch(setting.path);
      if (response.status === 401 || response.redirected) throw new Error('登录状态已失效，请重新登录后打开配置。');
      if (!response.ok) throw new Error('配置页面加载失败，请重试。');
      const page = new DOMParser().parseFromString(await response.text(), 'text/html');
      const content = page.querySelector('main.pc-container');
      if (!content) throw new Error('配置页面内容无效，请重试。');
      content.querySelectorAll('[data-integration-back], .pc-eyebrow, h1').forEach(node => node.remove());
      // A workspace already has its own title and navigation; reuse the original forms and help.
      content.querySelector(':scope > nav')?.remove();
      host.replaceChildren(...content.childNodes);
      const guideDialog = page.getElementById('pc-guide-image-dialog');
      if (guideDialog) host.append(guideDialog);
      page.querySelectorAll('body > style').forEach(style => host.append(style));
      const footer = document.createElement('div');
      footer.className = 'panel-footer';
      const back = document.createElement('button');
      back.type = 'button'; back.textContent = '返回当前会话 →';
      back.onclick = () => goStage(returnStage);
      footer.append(back);
      if (n === 7) {
        const wecom = document.createElement('button');
        wecom.type = 'button'; wecom.dataset.stage = '8'; wecom.textContent = '企微机器人 →';
        footer.append(wecom);
      }
      host.append(footer);
      for (const script of setting.scripts) await loadScript(script);
      if (n === 8) window.WeComSettings.mount();
    } catch (error) {
      loads.delete(n);
      host.replaceChildren();
      const message = document.createElement('p');
      message.className = 'hint'; message.setAttribute('role', 'alert'); message.textContent = error.message;
      const retry = document.createElement('button');
      retry.type = 'button'; retry.dataset.stage = String(n); retry.textContent = '重新加载';
      host.append(message, retry);
    } finally {
      host.removeAttribute('aria-busy');
      host.inert = false;
    }
  }

  window.WorkspaceIntegrations = {
    stageForHash,
    enter(n) {
      if (state.stage < 5) returnStage = state.stage;
      document.querySelector('dialog[open]')?.close();
      if (!loads.has(n)) loads.set(n, load(n));
    }
  };
  window.addEventListener('hashchange', () => {
    if (!state.bootstrap) return;
    const n = stageForHash(location.hash) || ({'#apis': 5, '#load': 6})[location.hash];
    if (n && n !== state.stage) goStage(n);
    else if (!n && [7, 8].includes(state.stage)) goStage(returnStage);
  });
})();
