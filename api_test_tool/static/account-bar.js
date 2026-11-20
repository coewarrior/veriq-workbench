'use strict';
(async () => {
  try {
    const response = await fetch('/api/auth/me');
    if (!response.ok) return;
    const info = await response.json();
    if (!info.enabled) return;
    if (!info.user) {
      if (document.querySelector('meta[name="api-test-public-report"]')) return;
      location.replace('/login?next=' + encodeURIComponent(location.pathname + location.search + location.hash));
      return;
    }
    if (!document.querySelector('link[href="/static/account-bar.css"], link[href^="/static/account-bar.css?"]')) {
      const stylesheet = document.createElement('link');
      stylesheet.rel = 'stylesheet';
      stylesheet.href = '/static/account-bar.css';
      document.head.append(stylesheet);
    }

    const bar = document.createElement('div');
    bar.className = 'account-bar';
    bar.setAttribute('role', 'group');
    bar.setAttribute('aria-label', '账号信息');

    const avatar = document.createElement('span');
    avatar.className = 'account-avatar';
    avatar.setAttribute('aria-hidden', 'true');
    avatar.textContent = Array.from(info.user.username)[0].toUpperCase();

    const identity = document.createElement('span');
    identity.className = 'account-identity';
    const label = document.createElement('span');
    label.className = 'account-label';
    label.textContent = '当前账号';
    const name = document.createElement('span');
    name.className = 'account-name';
    name.textContent = info.user.username;
    name.title = info.user.username;
    identity.append(label, name);

    const logout = document.createElement('button');
    logout.type = 'button';
    logout.className = 'account-logout';
    logout.title = '退出登录';
    logout.setAttribute('aria-label', '退出登录');
    logout.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 4H5a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h4m6-12 4 4-4 4m-7-4h11"/></svg>';
    bar.append(avatar, identity, logout);

    const slot = document.getElementById('sidebar-account') || document.getElementById('home-account') || document.getElementById('ui-account');
    if (slot) slot.append(bar);
    else {
      bar.classList.add('account-bar-floating');
      document.body.append(bar);
    }

    logout.onclick = async () => {
      logout.disabled = true;
      try {
        const result = await fetch('/api/auth/logout', {
          method: 'POST',
          headers: {'Content-Type': 'application/json', 'X-CSRF-Token': info.csrf},
          body: '{}',
        });
        if (!result.ok) throw Error('退出失败，请刷新后重试');
        location.replace('/login');
      } catch (error) {
        logout.disabled = false;
        alert(error.message);
      }
    };
  } catch {}
})();
