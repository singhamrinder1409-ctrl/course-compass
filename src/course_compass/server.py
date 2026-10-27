"""Loopback-only local web app. Run with python -m course_compass serve."""
import json
import os
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from .answers import answer
from .examples import EXAMPLES, saved_answer
from .ingest import EDITION, ROOT
from .search import SearchIndex

STATIC = Path(__file__).parent / 'static'


def make_handler(index):
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(55)

        def log_message(self, format, *args):
            # Do not log questions or request bodies.
            pass

        def send(self, status, data, content_type='application/json; charset=utf-8'):
            body = json.dumps(data, ensure_ascii=False).encode() if 'application/json' in content_type else data
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
            self.end_headers()
            self.wfile.write(body)

        def valid_host(self):
            return self.headers.get('Host') in {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}

        def do_GET(self):
            if not self.valid_host():
                return self.send(403, {'error': 'Local host required.'})
            path = urlsplit(self.path).path
            assets = {'/': ('index.html', 'text/html; charset=utf-8'),
                      '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                      '/style.css': ('style.css', 'text/css; charset=utf-8')}
            if path in assets:
                name, mime = assets[path]
                return self.send(200, (STATIC / name).read_bytes(), mime)
            if path == '/api/config':
                return self.send(200, {'edition': EDITION, 'courses': ([{'code': c['course_code'], 'title': c['title']} for c in index.courses] if index else
                                [{'code': e['citations'][0]['course_code'], 'title': 'Saved example available'} for e in EXAMPLES]),
                    'corpus_ready': index is not None, 'examples': [e['question'] for e in EXAMPLES],
                    'model_ready': bool(os.environ.get('OPENAI_API_KEY', '').strip() and os.environ.get('OPENAI_MODEL', '').strip()),
                    'model': os.environ.get('OPENAI_MODEL', '') or None})
            if path == '/api/evaluation':
                report = ROOT / 'evaluation' / 'holdout-report.json'
                if not report.exists():
                    report = ROOT / 'evaluation' / 'holdout-summary.json'
                if not report.exists():
                    return self.send(200, {'available': False})
                result = json.loads(report.read_text())
                summary = {k: result[k] for k in ('question_count', 'answerable_count', 'k', 'behavior', 'model_evaluation')}
                summary['retrieval'] = [{k: v for k, v in method.items() if k != 'cases'} for method in result['retrieval']]
                return self.send(200, {'available': True, 'report': summary})
            return self.send(404, {'error': 'Not found.'})

        def do_POST(self):
            if not self.valid_host():
                return self.send(403, {'error': 'Local host required.'})
            origin = self.headers.get('Origin')
            if origin and origin not in {f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}'}:
                return self.send(403, {'error': 'Cross-origin requests are not allowed.'})
            if self.path != '/api/ask':
                return self.send(404, {'error': 'Not found.'})
            if self.headers.get_content_type() != 'application/json':
                return self.send(415, {'error': 'Use application/json.'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if length < 1 or length > 20000:
                    return self.send(413, {'error': 'Request is empty or too large.'})
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict) or not isinstance(data.get('question'), str):
                    raise ValueError('Provide a question as text.')
                mode = data.get('mode', 'evidence')
                if mode == 'examples':
                    result = saved_answer(data['question'])
                elif index is None:
                    raise ValueError('Import course data first with python -m course_compass ingest, or use Saved examples.')
                else:
                    result = answer(index, data['question'], mode)
                return self.send(502 if result['status'] == 'error' else 200, result)
            except (ValueError, UnicodeDecodeError) as error:
                return self.send(400, {'error': str(error)})
            except Exception:
                return self.send(500, {'error': 'Unable to process this question. Try again.'})
    return Handler


def serve(port=8766):
    try:
        index = SearchIndex.load()
    except FileNotFoundError:
        index = None
    server = ThreadingHTTPServer(('127.0.0.1', port), make_handler(index))
    print(f'Course Compass: http://127.0.0.1:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
