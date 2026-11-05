from http.server import BaseHTTPRequestHandler
import json, os, time

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({
            "status": "ok",
            "service": "sabi-identity-api",
            "supabase_configured": bool(os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_SERVICE_ROLE_KEY")),
            "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }).encode())
