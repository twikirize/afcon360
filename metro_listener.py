#!/usr/bin/env python3
"""
AFCON360 Metro Listener (Trigger-file version)
Listens for wake requests and writes a trigger file.
A separate Metro Manager script watches the trigger and starts Metro.
Run: python metro_listener.py
In another window: python metro_manager.py
"""
import os
import sys
import json
import time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

REPO_ROOT = Path(__file__).parent.resolve()
TRIGGER_FILE = REPO_ROOT / "metro_trigger.json"
STATUS_FILE = REPO_ROOT / "metro_status.json"
LISTENER_PORT = 8082
METRO_DEFAULT_PORT = 8081

class WakeHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == "/wake":
            self.handle_wake()
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            status = self.read_status()
            self.wfile.write(json.dumps(status).encode())
        elif self.path == "/trigger":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            trigger = self.read_trigger()
            self.wfile.write(json.dumps(trigger).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def handle_wake(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode() if content_length > 0 else "{}"
        
        try:
            request = json.loads(body)
        except json.JSONDecodeError:
            request = {}
        
        client_id = request.get("clientId", "unknown")
        print(f"[{time.strftime('%H:%M:%S')}] Wake request from {client_id}")
        
        # Write trigger file
        trigger = {
            "requestedAt": time.time(),
            "clientId": client_id,
            "action": "start",
        }
        TRIGGER_FILE.write_text(json.dumps(trigger))
        
        response = {
            "ip": self.get_server_ip(),
            "metroPort": METRO_DEFAULT_PORT,
            "status": "triggered",
            "message": "Wake trigger written. Metro Manager will start Metro."
        }
        
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(response).encode())
    
    def read_status(self):
        if STATUS_FILE.exists():
            try:
                return json.loads(STATUS_FILE.read_text())
            except:
                pass
        return {"status": "unknown", "port": METRO_DEFAULT_PORT}
    
    def read_trigger(self):
        if TRIGGER_FILE.exists():
            try:
                return json.loads(TRIGGER_FILE.read_text())
            except:
                pass
        return {"action": "none"}
    
    def get_server_ip(self):
        return self.client_address[0]
    
    def log_message(self, format, *args):
        print(f"[{time.strftime('%H:%M:%S')}] {format % args}")

def run_server():
    server = ThreadingHTTPServer(("0.0.0.0", LISTENER_PORT), WakeHandler)
    print(f"AFCON360 Metro Listener starting on port {LISTENER_PORT}")
    print(f"Trigger file: {TRIGGER_FILE}")
    print(f"Status file: {STATUS_FILE}")
    print(f"Endpoints:")
    print(f"  POST http://<laptop-ip>:{LISTENER_PORT}/wake - Write wake trigger")
    print(f"  GET  http://<laptop-ip>:{LISTENER_PORT}/health - Check Metro status (from status file)")
    print(f"  GET  http://<laptop-ip>:{LISTENER_PORT}/trigger - Check trigger status")
    print("Press Ctrl+C to stop")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")

if __name__ == "__main__":
    run_server()