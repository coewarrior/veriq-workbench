"""Ephemeral owner-only browser console. Never exposes CDP, cookies or a desktop.

Commands are claimed once. A lost response is UNKNOWN, never requeued. Sessions
and their input buffers die with the web process; old session IDs cannot replay.
"""
from __future__ import annotations
import copy
import hashlib
import json
import threading
import time
from uuid import uuid4
from .orchestration import Conflict


class BrowserConsole:
    def __init__(self, controller):
        self.controller=controller;self.lock=threading.RLock();self.sessions={}

    def authorize(self, owner, target, action):
        if not isinstance(target,dict) or not isinstance(target.get('account_id'),str):raise ValueError('现场账号无效')
        c=self.controller
        with c.transaction() as (_,s):
            aid=target['account_id'];a=c.owned(s['accounts'],owner,aid)
            lid=target.get('lease_id')
            if lid:
                l=s['leases'].get(lid)
                if not l or aid not in l['account_ids']:raise PermissionError('现场不属于此账号租约')
                n=c.owned(s['nodes'],owner,l['node_id']);hid=l['runner_id']
                editable=bool(l.get('human_mode') and l.get('executor_fenced') and l['mode']=='exclusive'
                    and n['state'] in {'waiting_human','retained','isolated'} and s['tasks'][n['task_id']]['intent']=='run'
                    and not any(x['id']!=lid and set(l['account_ids'])&set(x['account_ids']) for x in s['leases'].values()))
                if action!='view' and not editable:raise Conflict('此现场只读；须先停止模型并开启原现场人工操作')
            else:
                hid=a.get('login_host');editable=True
                if target.get('login_attempt') is not None and target['login_attempt']!=a.get('login_attempt',''):
                    raise Conflict('登录资料已更新，请重新打开登录现场')
                if not a.get('login_requested') or not hid or any(aid in l['account_ids'] for l in s['leases'].values()):
                    raise Conflict('当前没有专属登录窗口，或账号已进入任务')
            r=c.owned(s['runners'],owner,hid)
            if not r['enabled'] or time.time()-r['heartbeat']>60 or not r.get('evidence',{}).get('remote_browser'):
                raise Conflict('执行连接离线或尚不支持网页现场')
            return {'host_id':hid,'editable':editable,'account_id':aid,'lease_id':lid,'login_attempt':a.get('login_attempt',''),
                    'allowed_origins':[a['target'],*a.get('login',{}).get('allowed_origins',[])]}

    def _prune(self):
        now=time.time()
        for sid,x in list(self.sessions.items()):
            if x['expires']<now:self.sessions.pop(sid,None)
            else:
                for cid,v in list(x['commands'].items()):
                    if v['expires']<now and v['state'] in {'queued','claimed'}:
                        v.update(state='unknown' if v['state']=='claimed' else 'not_sent',result={'error':'现场操作超时；请查看原现场核实，不自动重试'})
                        v.pop('parameters',None)
        # Commands live only inside a bounded, explicitly opened console session.

    def open(self,owner,target):
        auth=self.authorize(owner,target,'view')
        if not target.get('lease_id'):target={**target,'login_attempt':auth['login_attempt']}
        with self.lock:
            self._prune()
            if sum(x['owner']==owner for x in self.sessions.values())>=32:raise Conflict('请先关闭不用的浏览器现场窗口')
            sid=uuid4().hex
            self.sessions[sid]={'owner':owner,'target':copy.deepcopy(target),'host_id':auth['host_id'],
                'expires':time.time()+1800,'commands':{}}
        return {'session_id':sid,**auth}

    def session(self,owner,sid):
        self._prune();x=self.sessions.get(sid)
        if not x or x['owner']!=owner:raise PermissionError('现场窗口已失效，请重新打开')
        return x

    def submit(self,owner,sid,data):
        action=data.get('action');p=data.get('parameters',{});cid=data.get('request_id')
        if action not in {'view','click','drag','scroll','text','key','navigate'}:raise ValueError('不支持此人工操作')
        if not isinstance(p,dict) or len(json.dumps(p))>24000:raise ValueError('操作参数过大')
        if not isinstance(cid,str) or len(cid)!=32 or any(c not in '0123456789abcdef' for c in cid):raise ValueError('操作标识无效')
        fingerprint=hashlib.sha256(json.dumps([action,p],sort_keys=True).encode()).hexdigest()
        with self.lock:
            x=self.session(owner,sid)
            if x.get('closed'):raise Conflict('现场窗口已关闭')
            auth=self.authorize(owner,x['target'],action)
            if auth['host_id']!=x['host_id']:raise Conflict('原现场已转移，需重新打开')
            old=x['commands'].get(cid)
            if old:
                if old['fingerprint']!=fingerprint:raise Conflict('操作标识被复用')
                return {'request_id':cid,'state':old['state']}
            if any(v['state'] in {'queued','claimed'} for v in x['commands'].values()):raise Conflict('上一现场操作尚未核实完成')
            # Keep deduplication receipts for the entire session. Bound memory by
            # expiring this console, not by dropping old mutation IDs for replay.
            if len(x['commands'])>=2000:raise Conflict('此现场窗口需重新打开以继续')
            for v in x['commands'].values():v.pop('result',None)
            x['commands'][cid]={'action':action,'parameters':copy.deepcopy(p),'fingerprint':fingerprint,
                'state':'queued','expires':time.time()+25,'result':None}
            x['expires']=time.time()+1800
        return {'request_id':cid,'state':'queued'}

    def result(self,owner,sid,cid):
        with self.lock:
            x=self.session(owner,sid);self.authorize(owner,x['target'],'view')
            v=x['commands'].get(cid)
            if not v:raise PermissionError('现场操作不存在')
            return {'state':v['state'],'result':v.get('result')}

    def close(self,owner,sid):
        with self.lock:
            x=self.session(owner,sid);x['closed']=True
            for v in x['commands'].values():
                if v['state']=='queued':v.update(state='not_sent');v.pop('parameters',None)
            # Keep an in-flight receipt long enough for the host to settle it.
            if not any(v['state']=='claimed' for v in x['commands'].values()):self.sessions.pop(sid)
        return {'closed':True}

    def assert_idle(self,owner,lid):
        with self.lock:
            self._prune()
            if any(x['owner']==owner and x['target'].get('lease_id')==lid and any(v['state'] in {'queued','claimed'} for v in x['commands'].values()) for x in self.sessions.values()):
                raise Conflict('浏览器现场仍有操作在途，请等待回执后核实')

    def host(self,auth,action,args):
        owner,hid=auth['owner'],auth['host_id']
        with self.lock:
            self._prune()
            if action=='console_poll':
                for sid,x in self.sessions.items():
                    if x['owner']!=owner or x['host_id']!=hid:continue
                    for cid,v in x['commands'].items():
                        if v['state']!='queued':continue
                        try:self.authorize(owner,x['target'],v['action'])
                        except (Conflict,PermissionError):
                            v.update(state='not_sent',result={'error':'现场授权已改变'});v.pop('parameters',None);continue
                        v['state']='claimed'
                        return {'command':{'session_id':sid,'request_id':cid,'target':x['target'],'action':v['action'],
                                           'parameters':v.pop('parameters'),'expires':v['expires']}}
                return {'command':None}
            x=self.session(owner,args['session_id'])
            if x['host_id']!=hid:raise PermissionError('现场不属于此执行连接')
            v=x['commands'].get(args['request_id'])
            if not v or v['state']!='claimed':raise Conflict('操作已失效，不能再次执行')
            if action=='console_authorize':
                if v.get('authorized'):raise Conflict('操作授权已消费，禁止重放')
                result=self.authorize(owner,x['target'],v['action'])
                lid=x['target'].get('lease_id')
                if lid and v['action']!='view':
                    with self.controller.transaction() as (_,s):
                        l=s['leases'].get(lid)
                        if not l or not l.get('human_mode') or not l.get('executor_fenced'):raise Conflict('现场授权已改变')
                        oid='console-'+args['request_id']
                        if oid in s['operations']:raise Conflict('人工操作已登记，不能重放')
                        s['operations'][oid]={'id':oid,'lease_id':lid,'node_id':l['node_id'],'action':'human_input',
                            'effect':'unknown','state':'pending','created':time.time()}
                        l['may_write']=True
                        l.pop('human_scene_evidence',None)
                v['authorized']=True
                return result
            if action=='console_result':
                if args['state'] not in {'confirmed','unknown','not_sent'}:raise ValueError('结果格式错误')
                result=args.get('result',{})
                if len(json.dumps(result))>1_200_000:raise ValueError('现场帧过大')
                lid=x['target'].get('lease_id')
                if lid and v.get('authorized') and v['action']!='view':
                    self.controller.operation_result(owner,'console-'+args['request_id'],state=args['state'],
                        result={'transport':'human_console','state':args['state']})
                v.update(state=args['state'],result=result)
                return {'recorded':True}
        raise ValueError('未知现场协议')
