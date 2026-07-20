"""Servidor HTTP simples para SPA (Single Page Application): retorna index.html para qualquer rota."""
import os, sys
from http.server import HTTPServer, SimpleHTTPRequestHandler

DIST_DIR = os.path.join(os.path.dirname(__file__), "frontend", "dist")

class SPAHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIST_DIR, **kwargs)

    def do_GET(self):
        # Arquivos reais: assets, vite.svg, etc.
        real_path = os.path.join(DIST_DIR, self.path.lstrip("/"))
        if os.path.isfile(real_path):
            return super().do_GET()
        # Qualquer outra rota → index.html (SPA routing)
        self.path = "/index.html"
        return super().do_GET()

    def log_message(self, fmt, *args):
        pass  # silencioso

port = int(sys.argv[1]) if len(sys.argv) > 1 else 5173
print(f"SPA server em http://0.0.0.0:{port}/ (dist: {DIST_DIR})")
HTTPServer(("", port), SPAHandler).serve_forever()
