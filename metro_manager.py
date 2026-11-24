#!/usr/bin/env python3
"""
AFCON360 Metro Manager
Watches for trigger file and starts/stops Metro accordingly.
Run: python metro_manager.py
"""
import os
import sys
import json
import subprocess
import time
import signal
from pathlib import Path

REPO_ROOT = Path(__file__).parent.resolve()
TRIGGER_FILE = REPO_ROOT / "metro_trigger.json"
STATUS_FILE = REPO_ROOT / "metro_status.json"
METRO_SCRIPT = REPO_ROOT / "mobile" / "scripts" / "windows" / "start-user-metro.ps1"
METRO_DEFAULT_PORT = 8081
POLL_INTERVAL = 2  # seconds
CONNECTION_MODE = (os.environ.get("AFCON_METRO_CONNECTION_MODE", "Usb").strip() or "Usb")
API_BASE_URL = os.environ.get("AFCON_API_BASE_URL", "").strip()
CLEAR_CACHE = os.environ.get("AFCON_METRO_CLEAR_CACHE", "").strip().lower() in ("1", "true", "yes", "on")
METRO_STDOUT_LOG = REPO_ROOT / "metro_stdout.log"
METRO_STDERR_LOG = REPO_ROOT / "metro_stderr.log"

class MetroManager:
    def __init__(self):
        self.metro_process = None
        self.metro_port = METRO_DEFAULT_PORT
        # Ignore any trigger that predates this manager instance
        self.last_trigger_mtime = TRIGGER_FILE.stat().st_mtime if TRIGGER_FILE.exists() else 0
    
    def is_metro_running(self):
        if self.metro_process is None:
            return False
        return self.metro_process.poll() is None
    
    def write_status(self, status, message=""):
        status_data = {
            "status": status,
            "port": self.metro_port,
            "message": message,
            "updatedAt": time.time(),
        }
        STATUS_FILE.write_text(json.dumps(status_data))
    
    def read_trigger(self):
        if not TRIGGER_FILE.exists():
            return None
        try:
            mtime = TRIGGER_FILE.stat().st_mtime
            if mtime <= self.last_trigger_mtime:
                return None
            self.last_trigger_mtime = mtime
            return json.loads(TRIGGER_FILE.read_text())
        except:
            return None
    
    def build_metro_command(self):
        args = [
            "powershell.exe", "-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass",
            "-File", str(METRO_SCRIPT), "-ConnectionMode", CONNECTION_MODE,
        ]
        if API_BASE_URL:
            args.extend(["-ApiBaseUrl", API_BASE_URL])
        if CLEAR_CACHE:
            args.append("-ClearCache")
        return args

    def start_metro(self):
        if self.is_metro_running():
            self.write_status("running", "Metro already running")
            return
        
        if CONNECTION_MODE.lower() == "lan" and not API_BASE_URL:
            self.write_status("error", "LAN mode requires AFCON_API_BASE_URL")
            print("LAN mode requires AFCON_API_BASE_URL")
            return
        
        if not METRO_SCRIPT.exists():
            self.write_status("error", f"Metro start script not found: {METRO_SCRIPT}")
            return
        
        try:
            print(f"[{time.strftime('%H:%M:%S')}] Starting Metro ({CONNECTION_MODE})...")
            print(f"[{time.strftime('%H:%M:%S')}] Command: {' '.join(self.build_metro_command())}")
            self.write_status("starting", "Metro start initiated")

            self.metro_log = open(METRO_STDOUT_LOG, "w", encoding="utf-8", errors="replace")
            self.metro_err_log = open(METRO_STDERR_LOG, "w", encoding="utf-8", errors="replace")
            
            # Start Metro in a new console window
            if sys.platform == "win32":
                self.metro_process = subprocess.Popen(
                    self.build_metro_command(),
                    cwd=str(REPO_ROOT),
                    creationflags=subprocess.CREATE_NEW_CONSOLE,
                    stdout=self.metro_log,
                    stderr=self.metro_err_log,
                    stdin=subprocess.DEVNULL,
                )
            else:
                self.metro_process = subprocess.Popen(
                    self.build_metro_command(),
                    cwd=str(REPO_ROOT),
                    start_new_session=True,
                    stdout=self.metro_log,
                    stderr=self.metro_err_log,
                    stdin=subprocess.DEVNULL,
                )
            
            print(f"[{time.strftime('%H:%M:%S')}] Metro process started with PID {self.metro_process.pid}")
            self.write_status("starting", "Metro process launched")
            
        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}] Failed to start Metro: {e}")
            self.write_status("error", f"Failed to start Metro: {str(e)}")
    
    def stop_metro(self):
        if self.metro_process and self.metro_process.poll() is None:
            print(f"[{time.strftime('%H:%M:%S')}] Stopping Metro...")
            if sys.platform == "win32":
                try:
                    self.metro_process.send_signal(signal.CTRL_BREAK_EVENT)
                except:
                    pass
            else:
                self.metro_process.terminate()
            try:
                self.metro_process.wait(timeout=10)
            except:
                pass
        self.metro_process = None
        self.write_status("stopped", "Metro stopped")
    
    def check_metro_health(self):
        """Check if Metro is actually responding on its port"""
        import socket
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex(('127.0.0.1', self.metro_port))
            sock.close()
            return result == 0
        except:
            return False
    
    def run(self):
        print(f"AFCON360 Metro Manager started")
        print(f"Watching trigger file: {TRIGGER_FILE}")
        print(f"Status file: {STATUS_FILE}")
        print(f"Metro script: {METRO_SCRIPT}")
        print(f"Connection mode: {CONNECTION_MODE}")
        print(f"API base URL: {API_BASE_URL or '(USB default)'}")
        print(f"Poll interval: {POLL_INTERVAL}s")
        print("Press Ctrl+C to stop")
        
        # Initial status
        self.write_status("stopped", "Metro Manager started")
        
        try:
            while True:
                trigger = self.read_trigger()
                if trigger:
                    action = trigger.get("action", "start")
                    print(f"[{time.strftime('%H:%M:%S')}] Trigger received: {action}")
                    if action == "start":
                        self.start_metro()
                    elif action == "stop":
                        self.stop_metro()
                
                # Update status based on actual Metro health
                if self.is_metro_running():
                    if self.check_metro_health():
                        self.write_status("running", "Metro responding on port")
                    else:
                        self.write_status("starting", "Metro process running but port not ready")
                else:
                    # Check if status file says starting but process died
                    if STATUS_FILE.exists():
                        try:
                            status = json.loads(STATUS_FILE.read_text())
                            if status.get("status") in ("starting", "running"):
                                self.write_status("stopped", "Metro process ended unexpectedly")
                        except:
                            pass
                
                time.sleep(POLL_INTERVAL)
        except KeyboardInterrupt:
            print("\nShutting down...")
            self.stop_metro()
            self.write_status("stopped", "Metro Manager stopped")

if __name__ == "__main__":
    manager = MetroManager()
    manager.run()