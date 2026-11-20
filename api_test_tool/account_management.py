"""Owner edits and permanent removal of globally shared account registrations."""
from .orchestration import Conflict, digest, public_account, text, uid


class AccountManagement:
    def __init__(self, controller):
        self.controller = controller

    def _editable(self, s, owner, aid, data):
        a = self.controller.owned(s['accounts'], owner, aid)
        if data.get('revision') != a.get('revision', 1):
            raise Conflict('账号或绑定关系已变化，请刷新账号列表后再操作')
        if any(aid in lease['account_ids'] for lease in s['leases'].values()):
            raise Conflict('账号正在执行任务，请等待回收后再编辑或删除')
        return a

    def _invalidate(self, s, account):
        aid = account['id']
        account.update(state='needs_login', verified_identity=False, login_requested=False,
                       login_attempt=uid(), auth_generation=uid(), login_message='账号信息已更新，执行 Codex 将自行登录')
        for key in ('login_host', 'session_host'):
            account.pop(key, None)
        for node in s['nodes'].values():
            if aid in (node.get('reservation') or {}).get('accounts', []):
                node['reservation'] = None

    def edit(self, owner, aid, data):
        c = self.controller
        with c.transaction() as (db, s):
            a = self._editable(s, owner, aid, data)
            if data.get('target') and data['target'] != a.get('login', {}).get('url', a['target']):
                raise ValueError('登录地址请在项目上修改，账号只维护账号和密码')
            target = a['target']
            login_url = a.get('login', {}).get('url', target)
            identity = text(data.get('identity'), '账号', 200)
            secret = data.get('credential', '')
            clear = data.get('clear_password', False)
            if not isinstance(secret, str) or len(secret) > 16000 or not isinstance(clear, bool):
                raise ValueError('密码格式错误')
            if secret and clear:
                raise ValueError('填写新密码与清除密码不能同时选择')
            changed_identity = target != a['target'] or identity != a['identity']
            environment = target if target != a['target'] else a['environment']
            if changed_identity and any(other['id'] != aid and other['target'].lower() == target.lower()
                                        and other['identity'] == identity for other in s['accounts'].values()):
                raise Conflict('该系统中的账号已登记，请绑定已有账号，不能重复创建账号容量')
            if secret:
                a['credential'] = c.store._cipher.encrypt(secret.encode()).decode()
            elif clear:
                a['credential'] = ''
            if changed_identity:
                # Evidence and adapters for another identity cannot grant permissions here.
                a.update(tenant='', roles=[], policy_id='', pool='execution')
                if target != a['target']:
                    a['login'] = {}
                for pid in a['projects']:
                    if pid in s.get('account_projects', {}):
                        s['account_projects'][pid]['configuration'] = {}
            a.update(target=target, identity=identity, label=identity, environment=environment,
                     identity_key=digest([target.lower(), environment, identity]), revision=a.get('revision', 1)+1)
            a.setdefault('login', {})['url'] = login_url
            self._invalidate(s, a)
            c.audit(db, owner, 'account.updated', aid)
            return public_account(a)

    def delete(self, owner, aid, data):
        c = self.controller
        with c.transaction() as (db, s):
            a = self._editable(s, owner, aid, data)
            self._invalidate(s, a)
            for pid in a['projects']:
                if pid in s.get('account_projects', {}):
                    s['account_projects'][pid]['configuration'] = {}
            policy_id = a.get('policy_id')
            if policy_id and not any(x['id'] != aid and x.get('policy_id') == policy_id for x in s['accounts'].values()):
                policy = s['policies'].get(policy_id)
                if policy:
                    policy['enabled'] = False
            del s['accounts'][aid]
            c.audit(db, owner, 'account.deleted', aid)
            return {'deleted': True}
