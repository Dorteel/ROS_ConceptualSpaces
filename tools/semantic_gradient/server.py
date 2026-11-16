"""Local HTTP API; no ROS imports or services are required."""
import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .backend import Conflict, GradientStore, ResourceUnavailable, WordNetService

STATIC = Path(__file__).with_name('static')


def make_server(host, port, store, wordnet):
    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, data, mime='application/json'):
            payload = json.dumps(data).encode() if mime == 'application/json' else data
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(payload)

        def handle_request(self):
            try:
                url = urlsplit(self.path)
                query = parse_qs(url.query)
                if self.command == 'GET':
                    if url.path == '/api/saved':
                        return self.reply(200, store.list(query.get('q', [''])[0]))
                    if url.path.startswith('/api/saved/'):
                        return self.reply(200, store.load(url.path.rsplit('/', 1)[-1]))
                    files = {'/': ('index.html', 'text/html; charset=utf-8'),
                             '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                             '/style.css': ('style.css', 'text/css; charset=utf-8')}
                    if url.path in files:
                        filename, mime = files[url.path]
                        return self.reply(200, (STATIC / filename).read_bytes(), mime)
                elif self.command == 'POST':
                    # JSON plus same-origin checks prevent cross-site writes to localhost.
                    origin = self.headers.get('Origin')
                    if origin and origin != 'http://' + self.headers.get('Host', ''):
                        return self.reply(403, {'error': 'Cross-origin requests are not allowed.'})
                    if self.headers.get_content_type() != 'application/json':
                        raise ValueError('Expected application/json.')
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= 1_000_000:
                        raise ValueError('Invalid request size.')
                    data = json.loads(self.rfile.read(length))
                    if not isinstance(data, dict):
                        raise ValueError('Expected a JSON object.')
                    if url.path == '/api/sample':
                        return self.reply(200, wordnet.sample(data.get('count', 5), data.get('exclude', []), data.get('retain', [])))
                    if url.path == '/api/lookup':
                        return self.reply(200, wordnet.lookup(data.get('word')))
                    if url.path == '/api/suggest':
                        return self.reply(200, wordnet.suggestions(data['endpoints']))
                    if url.path == '/api/save':
                        return self.reply(200, store.save(data))
                self.reply(404, {'error': 'Not found.'})
            except ResourceUnavailable as exc:
                self.reply(503, {'error': str(exc)})
            except Conflict as exc:
                self.reply(409, {'error': str(exc)})
            except FileNotFoundError as exc:
                self.reply(404, {'error': str(exc)})
            except (ValueError, KeyError, TypeError, AttributeError) as exc:
                self.reply(400, {'error': str(exc)})
            except OSError as exc:
                self.reply(500, {'error': f'Could not access saved gradients: {exc}'})

        do_GET = handle_request
        do_POST = handle_request

    return HTTPServer((host, port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--data-dir', type=Path, default=Path(__file__).with_name('saved_gradients'))
    args = parser.parse_args()
    server = make_server('127.0.0.1', args.port, GradientStore(args.data_dir), WordNetService())
    print(f'Semantic Gradient Editor: http://127.0.0.1:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
