"""Bounded stdio adapter for managed Codex App Server processes.

This is a transport, not an isolation boundary. Production construction belongs
inside an independently verified execution host. Never attach an arbitrary desktop
chat or forward model-generated method names to this adapter.
"""
from __future__ import annotations

import json
import queue
import subprocess
import threading


class AppServerError(RuntimeError):
    pass


class ThreadNotFound(AppServerError):
    """The server positively reports no persisted rollout for this exact ID."""


class AppServer:
    ALLOWED = {'initialize', 'account/read', 'thread/start', 'thread/resume', 'thread/read', 'turn/start', 'turn/interrupt'}

    def __init__(self, command, *, cwd, env, timeout=30, on_spawn=None, start_new_session=False):
        if not isinstance(command, list) or not command:
            raise ValueError('An explicit trusted executable is required')
        self.timeout=timeout
        self.process=subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1,
            start_new_session=start_new_session)
        try:
            # Persist ownership before any initialize/turn request is sent.
            if on_spawn:
                on_spawn(self.process)
        except BaseException:
            self.process.kill();self.process.wait(timeout=5)
            self.process.stdin.close();self.process.stdout.close()
            raise
        self._serial=0
        self._write_lock=threading.Lock()
        self._lock=threading.Lock()
        self._pending={}
        self.events=queue.Queue(maxsize=4096)
        self.closed=False
        self._reader=threading.Thread(target=self._read, daemon=True, name='managed-codex-stdio')
        self._reader.start()
        try:
            self.call('initialize', {'clientInfo':{'name':'testing_workspace','title':'测试工作台','version':'0.1.0'},
                                     'capabilities':{'experimentalApi':True}})
            self._send({'method':'initialized','params':{}})
        except BaseException:
            self.close()
            raise

    def _send(self, value):
        with self._write_lock:
            if self.closed or self.process.poll() is not None:
                raise AppServerError('Codex 连接已断开；需核实原轮次，不能盲目重发')
            self.process.stdin.write(json.dumps(value,ensure_ascii=False)+'\n')
            self.process.stdin.flush()

    def _read(self):
        try:
            while True:
                # Bound protocol frame size; an invalid peer must not exhaust memory.
                line=self.process.stdout.readline(4_000_001)
                if not line:
                    break
                if len(line)>4_000_000 or not line.endswith('\n'):
                    raise AppServerError('Codex 协议帧超过限制')
                packet=json.loads(line)
                if not isinstance(packet,dict):
                    raise AppServerError('Codex 协议帧格式错误')
                if 'method' in packet:
                    # Requests for permission, shell/filesystem access or unknown
                    # methods are denied, not auto-approved by the transport.
                    if 'id' in packet and packet['method']!='item/tool/call':
                        self._send({'id':packet['id'],'error':{'code':-32601,'message':'Unsupported managed request'}})
                    else:
                        self.events.put_nowait(packet)
                else:
                    with self._lock:
                        target=self._pending.get(packet.get('id'))
                    if target:
                        target.put_nowait(packet)
        except Exception:
            # Do not log raw packets; they can contain secrets or business data.
            pass
        finally:
            with self._lock:
                for pending in self._pending.values():
                    try:
                        pending.put_nowait({'error':{'message':'Codex transport disconnected; reconcile before retry'}})
                    except queue.Full:
                        pass
            self.closed=True

    def call(self, method, params):
        if method not in self.ALLOWED:
            raise AppServerError('不允许调用此 App Server 控制方法')
        with self._lock:
            self._serial+=1
            key=self._serial
            target=queue.Queue(maxsize=1)
            self._pending[key]=target
        try:
            self._send({'id':key,'method':method,'params':params})
            try:
                packet=target.get(timeout=self.timeout)
            except queue.Empty:
                raise AppServerError('Codex 请求超时，执行结果未知；不得直接重复启动') from None
            if 'error' in packet:
                error=packet['error']
                if (method=='thread/resume' and error.get('code')==-32600 and
                    error.get('message')=='no rollout found for thread id '+params['threadId']):
                    raise ThreadNotFound('原线程尚无持久化记录；必须核对是否曾启动轮次，不能盲目重建')
                raise AppServerError('Codex 控制请求失败；请核实执行上下文')
            return packet.get('result',{})
        finally:
            with self._lock:
                self._pending.pop(key,None)

    def start_thread(self, *, cwd, tools, model=None):
        params={'cwd':str(cwd),'approvalPolicy':'never','sandbox':'read-only','dynamicTools':tools}
        if model:
            params['model']=model
        return self.call('thread/start',params)['thread']['id']

    def check_auth(self):
        # Do not return account identity or tokens to the model or startup logs.
        result=self.call('account/read',{'refreshToken':False})
        if result.get('requiresOpenaiAuth',True) and not result.get('account'):
            raise AppServerError('选定的 Codex 登录凭据不可用，请先在本机登录 Codex')

    def resume_thread(self, thread_id):
        return self.call('thread/resume',{'threadId':thread_id,'approvalPolicy':'never','sandbox':'read-only','excludeTurns':True})

    def start_turn(self, thread_id, prompt):
        return self.call('turn/start',{'threadId':thread_id,'input':[{'type':'text','text':prompt}]})['turn']['id']

    def interrupt(self, thread_id, turn_id):
        # RPC acknowledgement is not confirmation of cancellation/cleanup.
        return self.call('turn/interrupt',{'threadId':thread_id,'turnId':turn_id})

    def read_thread(self, thread_id):
        return self.call('thread/read',{'threadId':thread_id,'includeTurns':True})

    def tool_response(self, request_id, result, success):
        result=dict(result) if isinstance(result,dict) else result
        image=result.pop('_image_url',None) if isinstance(result,dict) else None
        items=[{'type':'inputText','text':json.dumps(result,ensure_ascii=False)}]
        if image:items.append({'type':'inputImage','imageUrl':image})
        self._send({'id':request_id,'result':{'contentItems':items,'success':bool(success)}})

    def close(self):
        self.closed=True
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        for stream in (self.process.stdin,self.process.stdout):
            if stream:
                stream.close()
        if threading.current_thread() is not self._reader:
            self._reader.join(timeout=1)
