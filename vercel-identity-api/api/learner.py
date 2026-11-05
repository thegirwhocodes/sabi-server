from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import json, os, urllib.request

def _supabase(path, key, url):
    req = urllib.request.Request(
        f"{url}/rest/v1/{path}",
        headers={"apikey": key, "Authorization": f"Bearer {key}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        phone = (parse_qs(urlparse(self.path).query).get("phone") or [""])[0].strip()
        body = {"error": "phone query parameter required"}
        status = 400
        if phone and url and key:
            try:
                sel = "select=student_id,verified_name,phone_e164,name_status,current_level,tarl_level,total_sessions,consents_granted,pilot_ready"
                rows = _supabase(f"sabi_learner_canonical?{sel}&phone_e164=eq.{urllib.parse.quote(phone)}", key, url)
                body = {"phone": phone, "learners": rows, "count": len(rows)}
                status = 200
            except Exception as exc:
                body, status = {"error": str(exc)[:200]}, 502
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())
