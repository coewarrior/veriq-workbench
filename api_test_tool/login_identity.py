"""Read current-session identity without user-authored selectors or page-wide matching.

Only explicitly labelled current-account/profile information is eligible. Merely
finding the expected text in a user table, login form or document is not proof.
Missing/ambiguous evidence stays unverified; target-specific adapters can retain
precise selectors in the privately maintained login profile.
"""
from __future__ import annotations

# Fixed, read-only DOM inspection in the broker, never model-supplied JavaScript.
CURRENT_IDENTITY = r"""() => {
  const visible = e => e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden';
  const clean = value => (value || '').trim();
  const fields = {identity: [], tenant: [], roles: []};
  const aliases = {
    identity: ['当前账号','登录账号','账号标识','用户名','电子邮箱','邮箱','Current account','Username','Email','Account ID'],
    tenant: ['当前租户','租户','当前企业','所属企业','Current tenant','Tenant','Organization'],
    roles: ['当前角色','角色','权限角色','Current role','Role','Roles']
  };
  const regions = [...document.querySelectorAll('header,nav,[role=banner],[data-current-account],[data-current-user],[aria-label="个人信息"],[aria-label="账号信息"],[aria-label="当前用户"],[aria-label="User profile"],[aria-label="Account information"]')].filter(visible);
  const eligible = e => visible(e) && !e.closest('form,table,[role=table],[role=grid],input,textarea,[contenteditable=true]');
  const add = (key,e,value) => { value=clean(value); if(eligible(e) && value && value.length<=200) fields[key].push(value); };
  const attributes = {identity:['data-current-user-id','data-current-account-id'],tenant:['data-current-tenant'],roles:['data-current-role']};
  for(const [key,attrs] of Object.entries(attributes)) for(const attr of attrs)
    for(const e of document.querySelectorAll('['+attr+']')) if(regions.some(r=>r===e||r.contains(e))) add(key,e,e.getAttribute(attr));
  for(const region of regions) for(const [key,names] of Object.entries(aliases)) {
    for(const e of region.querySelectorAll('[aria-label],dt,[data-label]')) {
      if(!eligible(e)) continue;
      const label=clean(e.getAttribute('aria-label')||e.getAttribute('data-label')||e.textContent).replace(/[：:]$/, '');
      if(!names.some(n=>n.toLowerCase()===label.toLowerCase())) continue;
      if(e.tagName==='DT') {
        const value=e.nextElementSibling;
        if(value?.tagName==='DD') add(key,value,value.textContent);
      } else add(key,e,e.textContent);
    }
  }
  const logout=[...document.querySelectorAll('button,a,[role=menuitem]')].some(e=>visible(e)&&/^(退出登录|退出账号|注销|sign out|log out|logout)$/i.test(clean(e.textContent)));
  const password=[...document.querySelectorAll('input[type=password]')].some(visible);
  return {fields:Object.fromEntries(Object.entries(fields).map(([k,v])=>[k,[...new Set(v)]])),authenticated:logout&&!password};
}"""


async def identify(page, account, profile):
    # Existing precise, maintained adapters remain valid. Automatic discovery is
    # bounded to current-account semantic fields, not arbitrary body text.
    if all(profile.get(k) for k in ('identity_selector','tenant_selector','role_selector')):
        selectors=[page.locator(profile[k]) for k in ('identity_selector','tenant_selector','role_selector')]
        if not all([await loc.first.is_visible() for loc in selectors]):return None
        return {'identity':(await selectors[0].inner_text(timeout=1000)).strip(),
                'tenant':(await selectors[1].inner_text(timeout=1000)).strip(),
                'roles':[x.strip() for x in await selectors[2].all_inner_texts()]}
    observed=await page.evaluate(CURRENT_IDENTITY)
    if not observed.get('authenticated'):return None
    fields=observed['fields']
    if len(fields['identity'])!=1 or len(fields['tenant'])!=1 or not fields['roles']:return None
    return {'identity':fields['identity'][0],'tenant':fields['tenant'][0],'roles':fields['roles']}


async def fill_standard_login(page, account, credential):
    """Recognize a single same-origin login form; leave challenges to the human."""
    from urllib.parse import urljoin, urlsplit
    target=urlsplit(account['target'])
    current=urlsplit(page.url)
    if (current.scheme,current.netloc)!=(target.scheme,target.netloc):return False
    passwords=page.locator('input[type=password]:visible')
    if await passwords.count()!=1:return False
    password=passwords.first
    form=password.locator('xpath=ancestor::form[1]')
    if await form.count()!=1:return False
    destination=urlsplit(urljoin(page.url,await form.get_attribute('action') or page.url))
    if (destination.scheme,destination.netloc)!=(target.scheme,target.netloc):return False
    username=form.locator('input[autocomplete=username]:visible,input[type=email]:visible,input[name=username]:visible,input[name=account]:visible')
    submit=form.locator('button[type=submit]:visible,input[type=submit]:visible')
    challenge=form.locator('input[autocomplete=one-time-code]:visible,input[name*=captcha i]:visible,iframe:visible')
    if await username.count()!=1 or await submit.count()!=1 or await challenge.count():return False
    if await username.input_value() or await password.input_value():return False
    await username.fill(account['identity'])
    await password.fill(credential)
    await submit.click()
    return True
