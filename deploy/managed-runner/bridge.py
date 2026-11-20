"""Container-local bridge; the host owns and restricts the only egress socket."""
import os
import select
import socket
import socketserver
import threading

class Bridge(socketserver.BaseRequestHandler):
    def handle(self):
        with socket.socket(socket.AF_UNIX) as upstream:
            upstream.connect('/egress/proxy.sock')
            while True:
                ready,_,_=select.select([self.request,upstream],[],[],60)
                if not ready:
                    continue
                for source in ready:
                    data=source.recv(65536)
                    if not data:
                        return
                    (upstream if source is self.request else self.request).sendall(data)

class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address=True
    daemon_threads=True

server=Server(('127.0.0.1',18080),Bridge)
threading.Thread(target=server.serve_forever,daemon=True).start()
# Keep the bridge alive while Codex owns stdio; no shell and no host mounts.
import subprocess
raise SystemExit(subprocess.call(['codex','app-server']))
