"""Compile the saved shared-operation contract once per browser lease.

No remote request validation is introduced: ordinary exclusive browsing keeps
its existing network path, and shared requests use only this local snapshot.
"""
from __future__ import annotations
import fnmatch
import json
import re
from urllib.parse import parse_qs, unquote, urlsplit


class ExclusiveRequired(PermissionError):
    """An unexplored request needs an exclusive account, not a failing test."""


def origin(url):
    parsed=urlsplit(url)
    if parsed.scheme not in {'http','https'} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('导航地址须为不含凭据的 HTTP(S) 地址')
    port=parsed.port
    return parsed.scheme+'://'+parsed.hostname.lower()+((':'+str(port)) if port and port!={'http':80,'https':443}[parsed.scheme] else '')


class BrowserPolicy:
    def __init__(self,account,policy,namespace):
        from .exploration_profiles import builtin
        self.builtin=builtin(policy or {},account)
        self.enabled=bool(policy and policy.get('enabled'))
        self.namespace=namespace
        self.version=(policy or {}).get('version','')
        self.rules=[]
        for item in (policy or {}).get('rules',[]):
            rule=dict(item)
            rule['query_patterns']={k:re.compile(v) for k,v in item.get('query_patterns',{}).items()}
            rule['body_patterns']={k:re.compile(v) for k,v in item.get('body_patterns',{}).items()}
            rule['optional_query_patterns']={k:re.compile(v) for k,v in item.get('optional_query_patterns',{}).items()}
            rule['optional_body_patterns']={k:re.compile(v) for k,v in item.get('optional_body_patterns',{}).items()}
            self.rules.append(rule)

    def request(self,url,method,body=None):
        return self.match_request(url,method,body)['effect']

    def match_request(self,url,method,body=None):
        if not self.enabled:raise ExclusiveRequired('共享探索策略未生效，需申请独占资源继续此分支')
        target=origin(url);parsed=urlsplit(url);path=unquote(parsed.path)
        if any(x in {'.','..'} for x in path.split('/')) or '\\' in path or re.search(r'%2f|%5c|%25',parsed.path,re.I):
            raise ExclusiveRequired('此请求路径未经共享策略核验，需独占继续')
        query=parse_qs(parsed.query,keep_blank_values=True)
        if body is None or body=='':body={}
        if isinstance(body,str):
            try:body=json.loads(body)
            except (ValueError,TypeError):
                # Explicit form fields are checked against exactly the same
                # saved rule; arbitrary multipart/file bodies stay exclusive.
                fields=parse_qs(body,keep_blank_values=True)
                body={k:v[0] if len(v)==1 else v for k,v in fields.items()}
        if not isinstance(body,dict):raise ExclusiveRequired('请求体未经共享策略核验，需独占继续')
        for rule in self.rules:
            if rule.get('origin','').rstrip('/')!=target or rule.get('method','').upper()!=method.upper() or not fnmatch.fnmatchcase(parsed.path,rule.get('path','')):continue
            if rule.get('path_pattern') and not re.fullmatch(rule['path_pattern'],parsed.path):continue
            if rule.get('effect') not in ({'verified_read','observed_read','isolated_write','isolated_session','prepared_read'} if self.builtin else {'verified_read','isolated_write'}):continue
            if rule['effect']=='observed_read':
                from .exploration_learning import value_hash
                if rule.get('query_hash')==value_hash(query) and rule.get('body_hash')==value_hash(body):return rule
                continue
            qeq=rule.get('query_equals',{});beq=rule.get('body_equals',{})
            qp=rule.get('query_patterns',{});bp=rule.get('body_patterns',{})
            oq=rule.get('optional_query_patterns',{});ob=rule.get('optional_body_patterns',{})
            namespace=rule.get('namespace_field')
            if set(query)-set(qeq)-set(qp)-set(oq) or set(body)-set(beq)-set(bp)-set(ob)-({namespace} if namespace else set()):continue
            if any(query.get(k)!=([v] if isinstance(v,str) else v) for k,v in qeq.items()):continue
            if any(k not in query or any(not pattern.fullmatch(v) for v in query[k]) for k,pattern in qp.items()):continue
            if any(body.get(k)!=v for k,v in beq.items()):continue
            if any(k not in body or not isinstance(body[k],str) or not pattern.fullmatch(body[k]) for k,pattern in bp.items()):continue
            if any(k in query and (len(query[k])!=1 or not pattern.fullmatch(query[k][0])) for k,pattern in oq.items()):continue
            if any(k in body and (not isinstance(body[k],str) or not pattern.fullmatch(body[k])) for k,pattern in ob.items()):continue
            if rule['effect']=='isolated_write' and (not namespace or body.get(namespace)!=self.namespace):continue
            return rule
        raise ExclusiveRequired('此请求不在已核验的共享探索集合内；保存已有探索，申请独占资源继续，不能记为业务失败')
