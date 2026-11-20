"""Health must remain real and responsive during unrelated request contention."""
import asyncio
import threading
import time
from unittest.mock import patch
import anyio
import httpx
from api_test_tool.web import create_app


def test_health_does_not_wait_for_mcp_auth_store_lock(tmp_path):
    app=create_app(tmp_path,start_fixture=False,testing=True)
    entered=threading.Event();release=threading.Event()
    def blocked_auth(*args):
        entered.set();release.wait(2);raise PermissionError('test')
    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as client:
            task=asyncio.create_task(client.post('/api/mcp/call',json={'action':'workspace','arguments':{}}))
            while not entered.is_set(): await asyncio.sleep(.005)
            before=time.monotonic()
            try:
                response=await asyncio.wait_for(client.get('/healthz'),.5)
                assert response.status_code==200 and time.monotonic()-before<.5
                assert response.json()['deployment']['active_jobs']==0
            finally: release.set()
            assert (await task).status_code==401
    with patch('api_test_tool.mcp_access.MCPAccess.authentication',blocked_auth): asyncio.run(exercise())


def test_health_has_independent_worker_and_real_activity(tmp_path):
    app=create_app(tmp_path,start_fixture=False,testing=True)
    app.state.jobs['active']={'status':'running'}
    async def exercise():
        limiter=anyio.to_thread.current_default_thread_limiter()
        old=limiter.total_tokens;limiter.total_tokens=1
        await limiter.acquire()
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as client:
                response=await asyncio.wait_for(client.get('/healthz'),.5)
                assert response.status_code==200
                assert response.json()['deployment']['active_jobs']==3
        finally:
            limiter.release();limiter.total_tokens=old
    with patch.object(app.state.orchestration,'active_count',return_value=2): asyncio.run(exercise())
