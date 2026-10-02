#!/usr/bin/env python3
"""Loopback read-only archive API and mobile review UI. No sportsbook calls."""
import argparse
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from agent_tool import query


class Handler(BaseHTTPRequestHandler):
    def __init__(self,*args,data_dir,**kwargs):
        self.data_dir=data_dir
        super().__init__(*args,**kwargs)
    def do_GET(self):
        path=urlparse(self.path)
        if path.path in ('/','/dashboard'):
            payload=(Path(__file__).parent/'dashboard'/'index.html').read_bytes(); mime='text/html; charset=utf-8'
        elif path.path=='/archive-client.js':
            payload=(Path(__file__).parent/'dashboard'/'archive-client.js').read_bytes(); mime='text/javascript; charset=utf-8'
        elif path.path.startswith('/api/'):
            command=path.path[5:]
            if command not in ('status','candidates','player','performance','research'):return self.send_error(404)
            params=parse_qs(path.query)
            try:
                player=int(params['player_id'][0]) if command=='player' else None
                if player is not None and player<=0:raise ValueError()
            except (ValueError,KeyError):return self.send_error(400,'Positive player_id required')
            try:payload=json.dumps(query(self.data_dir,command,player),allow_nan=False).encode()
            except Exception:return self.send_error(503,'Archive unavailable or invalid')
            mime='application/json'
        else:return self.send_error(404)
        self.send_response(200)
        self.send_header('Content-Type',mime);self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'")
        self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
    def log_message(self,*args):pass


def server(data_dir,port=8765):
    return ThreadingHTTPServer(('127.0.0.1',port),partial(Handler,data_dir=Path(data_dir)))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--data-dir',type=Path,required=True)
    p.add_argument('--port',type=int,default=8765);a=p.parse_args()
    print(f'Paper review only: http://127.0.0.1:{a.port} (archive must be refreshed separately)',flush=True)
    server(a.data_dir,a.port).serve_forever()

if __name__=='__main__':main()
