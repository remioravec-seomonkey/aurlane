#!/usr/bin/env python3
"""
preview.py — aperçu en direct du site, qui se rafraîchit tout seul.

    python3 tools/preview.py            # sert site/ sur http://localhost:8000
    python3 tools/preview.py site --port 8000 --no-open

Sert le dossier du clone et injecte dans chaque page un petit script qui
surveille les fichiers : dès que Claude Code modifie index.html, style.css
ou app.js, l'onglet se recharge tout seul. C'est l'aperçu « temps réel »
pendant qu'on retravaille la page en discutant avec le chatbot.

Rien à installer : uniquement la bibliothèque standard de Python. Aucune
connexion sortante, aucune API. Ctrl+C pour arrêter.
"""
from __future__ import annotations

import argparse
import http.server
import os
import socketserver
import threading
import time
import webbrowser

# injecté avant </body> : interroge /__mtime chaque seconde et recharge au
# moindre changement de fichier dans le dossier servi.
RELOAD_JS = b"""
<script>
(function () {
  var last = null;
  setInterval(function () {
    fetch('/__mtime', { cache: 'no-store' })
      .then(function (r) { return r.text(); })
      .then(function (t) {
        if (last !== null && t !== last) location.reload();
        last = t;
      })
      .catch(function () {});
  }, 1000);
})();
</script>
"""


def latest_mtime(root: str) -> float:
    newest = 0.0
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            try:
                m = os.path.getmtime(os.path.join(dirpath, name))
                if m > newest:
                    newest = m
            except OSError:
                pass
    return newest


def make_handler(root: str):
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=root, **kw)

        def log_message(self, *a):
            pass  # pas de bruit dans le terminal

        def do_GET(self):
            if self.path == "/__mtime":
                body = str(latest_mtime(root)).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            path = self.translate_path(self.path)
            if os.path.isdir(path):
                path = os.path.join(path, "index.html")

            if path.endswith(".html") and os.path.isfile(path):
                with open(path, "rb") as f:
                    html = f.read()
                if b"</body>" in html:
                    html = html.replace(b"</body>", RELOAD_JS + b"</body>", 1)
                else:
                    html += RELOAD_JS
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(html)))
                self.end_headers()
                self.wfile.write(html)
                return

            super().do_GET()

    return Handler


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def serve(root: str, port: int, open_browser: bool) -> None:
    if not os.path.isfile(os.path.join(root, "index.html")):
        raise SystemExit(f"Pas de index.html dans {root} — éclater la capture d'abord.")

    with Server(("127.0.0.1", port), make_handler(os.path.abspath(root))) as httpd:
        url = f"http://localhost:{port}/"
        print(f"\n  Aperçu en direct : {url}")
        print(f"  Dossier servi    : {root}")
        print("  L'onglet se recharge tout seul à chaque modification.")
        print("  Ctrl+C pour arrêter.\n")
        if open_browser:
            threading.Thread(
                target=lambda: (time.sleep(0.6), webbrowser.open(url)),
                daemon=True,
            ).start()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n  Aperçu arrêté.\n")


def main():
    ap = argparse.ArgumentParser(description="Aperçu en direct du clone.")
    ap.add_argument("root", nargs="?", default="site", help="dossier à servir (défaut: site)")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-open", action="store_true", help="ne pas ouvrir le navigateur")
    a = ap.parse_args()
    serve(a.root, a.port, not a.no_open)


if __name__ == "__main__":
    main()
