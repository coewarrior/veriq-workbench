"""Verify the real HTTP server in an isolated container without outbound or business-network access."""
import subprocess
import sys
import time

container, revision = sys.argv[1:]
code = '''
import json, urllib.request
import asyncio
from pathlib import Path
from api_test_tool.managed_browser import ManagedBrowser
base = 'http://127.0.0.1:18089'
health = json.load(urllib.request.urlopen(base + '/healthz', timeout=3))
assert health['status'] == 'ok' and health['revision'] == %r
assert not health['deployment']['draining']
for path, content in [('/login', b'<html'), ('/static/brand-orbit.svg', b'<svg'),
                      ('/static/signal-background/frame.html', b'signal-background'),
                      ('/static/spark-background/frame.html', b'spark-background'),
                      ('/static/spark-background/spark-badge.html', b'spark-badge-controls'),
                      ('/static/spark-background/veriq-badge.html', b"const str = 'VERIQ'"),
                      ('/static/home-water/water.js', b'home-water'),
                      ('/static/home-induction/induction.js', b'workspace-induction'),
                      ('/static/home-water/water.css', b'threeui-background'),
                      ('/static/app.js', b'function')]:
    assert content in urllib.request.urlopen(base + path, timeout=3).read()
async def browser_startup():
    browser = ManagedBrowser(None, Path('/tmp/browser-startup-check'))
    try:
        await browser.start()
        await browser.check_runtime()
    finally:
        await browser.close()
asyncio.run(browser_startup())
''' % revision
for _ in range(30):
    result = subprocess.run(['docker', 'exec', container, 'python', '-c', code], capture_output=True, text=True)
    if result.returncode == 0:
        print('HTTP, static assets and Chromium startup verified in isolated container.')
        break
    time.sleep(1)
else:
    raise SystemExit('Isolated HTTP smoke failed: ' + result.stderr[-1500:])
