"""Use the checksum-pinned archive with Playwright's original installer."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading

import playwright

version = '156.0.8078.4'
manifest = json.loads((Path(playwright.__file__).parent / 'driver/package/browsers.json').read_text())
headless = next(b for b in manifest['browsers'] if b['name'] == 'chromium-headless-shell')
if headless['browserVersion'] != version:
    raise SystemExit('Update the pinned Chromium archive alongside the Playwright version')

class QuietFiles(SimpleHTTPRequestHandler):
    def log_message(self, *_):
        pass

with tempfile.TemporaryDirectory(prefix='platform-browser-install-') as directory:
    archive = Path(directory) / 'builds/cft' / version / 'linux64/chrome-headless-shell-linux64.zip'
    archive.parent.mkdir(parents=True)
    archive.symlink_to('/tmp/platform-chromium.zip')
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietFiles, directory=directory))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        subprocess.run([sys.executable, '-m', 'playwright', 'install', '--only-shell', 'chromium'],
                       env={**os.environ, 'PLAYWRIGHT_CHROMIUM_DOWNLOAD_HOST':
                            f'http://127.0.0.1:{server.server_port}'}, check=True)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
