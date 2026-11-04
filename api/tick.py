from http.server import BaseHTTPRequestHandler
import json, os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot.tick import tick


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        secret = os.environ.get("CRON_SECRET", "")
        auth = self.headers.get("Authorization", "")
        if not secret or auth != f"Bearer {secret}":
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b'{"ok":false,"reason":"unauthorized"}')
            return
        env = {k: os.environ[k] for k in ("BLOB_READ_WRITE_TOKEN",) if k in os.environ}
        if len(env) < 1:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b'{"ok":false,"reason":"BLOB_READ_WRITE_TOKEN hilang"}')
            return
        try:
            result = tick(env)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode())
        except Exception as e:  # retry terbatas: Vercel memanggil ulang via cron
            self.send_response(500)
            self.end_headers()
            self.wfile.write(json.dumps({"ok": False, "reason": str(e)[:200]}).encode())
