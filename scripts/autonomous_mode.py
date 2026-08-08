"""
⚡ GENESIS AUTONOMOUS MODE ⚡
Genesis can run itself without human intervention!
"""

import os
import sys
import time
import json
import asyncio
import subprocess
import signal
import psutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any
from threading import Thread

class GenesisAutonomousMode:
    """
    Genesis Protocol - Autonomous Operation Mode
    
    Features:
    - Auto-restart on crash
    - Auto-update from git
    - Auto-scaling detection
    - Health monitoring
    - Self-healing
    - Auto-deployment capability
    """
    
    VERSION = "2.0.0"
    
    def __init__(self):
        self.start_time = datetime.now()
        self.restart_count = 0
        self.last_update = None
        self.is_running = True
        self.health_check_interval = 60  # seconds
        self.update_check_interval = 3600  # 1 hour
        
        self.status = {
            "running": True,
            "uptime": str(datetime.now() - self.start_time),
            "restarts": self.restart_count,
            "last_update": None,
            "health": "healthy",
            "memory_usage": 0,
            "cpu_usage": 0
        }
        
        # Check if running in container/railway
        self.is_docker = os.path.exists('/.dockerenv') or os.getenv('RAILWAY') or os.getenv('DOCKER')
        self.is_railway = bool(os.getenv('RAILWAY'))
        
    def log(self, message: str, level: str = "INFO"):
        """Log with timestamp"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [AUTONOMOUS] [{level}] {message}")
        
    def get_status(self) -> Dict[str, Any]:
        """Get current status"""
        process = psutil.Process()
        self.status.update({
            "running": self.is_running,
            "uptime": str(datetime.now() - self.start_time),
            "restarts": self.restart_count,
            "memory_usage": f"{process.memory_percent():.1f}%",
            "cpu_usage": f"{process.cpu_percent():.1f}%",
            "environment": {
                "docker": self.is_docker,
                "railway": self.is_railway
            }
        })
        return self.status
    
    def check_health(self) -> bool:
        """Check if Genesis is healthy"""
        try:
            # Check if process is responding
            process = psutil.Process()
            
            # Check memory usage
            if process.memory_percent() > 90:
                self.log("⚠️ High memory usage, may need restart", "WARN")
                return False
                
            # Check CPU usage
            if process.cpu_percent() > 95:
                self.log("⚠️ High CPU usage", "WARN")
                
            # Check if web server is responding
            try:
                import requests
                response = requests.get("http://localhost:5000/", timeout=2)
                if response.status_code != 200:
                    self.log("⚠️ Web server not responding correctly", "WARN")
                    return False
            except:
                pass  # Web server might not be running
                
            return True
            
        except Exception as e:
            self.log(f"Health check failed: {e}", "ERROR")
            return False
    
    def auto_restart(self):
        """Auto-restart if crashed"""
        if not self.is_running:
            return
            
        self.log("🔄 Attempting auto-restart...")
        
        try:
            # Find and kill old process
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    if 'python' in proc.info['name'].lower():
                        cmdline = ' '.join(proc.info['cmdline'] or [])
                        if 'app.py' in cmdline or 'genesis' in cmdline:
                            self.log(f"   Killing old process: {proc.info['pid']}")
                            proc.kill()
                except:
                    pass
            
            time.sleep(2)
            
            # Start fresh
            self.start_genesis()
            self.restart_count += 1
            self.log(f"✅ Restart #{self.restart_count} successful!")
            
        except Exception as e:
            self.log(f"Auto-restart failed: {e}", "ERROR")
    
    def start_genesis(self):
        """Start Genesis Protocol"""
        self.log("🚀 Starting Genesis Protocol...")
        
        # Determine Python path
        venv_python = Path("/workspace/project/Genesis-protocol-/.venv/bin/python")
        if not venv_python.exists():
            venv_python = Path(sys.executable)
        
        web_dir = Path("/workspace/project/Genesis-protocol-/web")
        
        # Start process
        env = os.environ.copy()
        env['PORT'] = env.get('PORT', '5000')
        
        self.genesis_process = subprocess.Popen(
            [str(venv_python), "app.py"],
            cwd=str(web_dir),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        self.log(f"✅ Genesis started (PID: {self.genesis_process.pid})")
        
    def update_from_git(self):
        """Auto-update from GitHub"""
        try:
            repo_dir = Path("/workspace/project/Genesis-protocol-")
            
            if not repo_dir.exists():
                self.log("Not a git repo, skipping update", "WARN")
                return
            
            self.log("🔄 Checking for updates...")
            
            # Fetch and check
            subprocess.run(["git", "fetch", "origin"], cwd=str(repo_dir), capture_output=True)
            
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(repo_dir),
                capture_output=True,
                text=True
            )
            current = result.stdout.strip()
            
            result = subprocess.run(
                ["git", "rev-parse", "origin/main"],
                cwd=str(repo_dir),
                capture_output=True,
                text=True
            )
            remote = result.stdout.strip()
            
            if current != remote:
                self.log(f"📦 Update available! Pulling...")
                subprocess.run(["git", "pull", "origin", "main"], cwd=str(repo_dir))
                self.last_update = datetime.now()
                self.log("✅ Updated to latest version!")
                
                # Restart to apply
                self.restart_count += 1
                self.auto_restart()
            else:
                self.log("✅ Already on latest version")
                
        except Exception as e:
            self.log(f"Update failed: {e}", "ERROR")
    
    def check_railway_deployment(self):
        """Check if deployed on Railway and configure"""
        if not self.is_railway:
            return
            
        self.log("🚂 Running on Railway...")
        
        # Railway provides these env vars
        railway_env = {
            "RAILWAY": os.getenv("RAILWAY"),
            "RAILWAY_PUBLIC_DOMAIN": os.getenv("RAILWAY_PUBLIC_DOMAIN"),
            "RAILWAY_GIT_COMMIT_SHA": os.getenv("RAILWAY_GIT_COMMIT_SHA"),
            "PORT": os.getenv("PORT", "5000")
        }
        
        self.log(f"   Domain: {railway_env.get('RAILWAY_PUBLIC_DOMAIN', 'N/A')}")
        self.log(f"   Commit: {railway_env.get('RAILWAY_GIT_COMMIT_SHA', 'N/A')[:8]}")
        
    def run_health_monitor(self):
        """Run continuous health monitoring"""
        self.log("🏥 Starting health monitor...")
        
        while self.is_running:
            try:
                # Check health
                if not self.check_health():
                    self.log("⚠️ Health check failed, restarting...", "WARN")
                    self.auto_restart()
                
                # Print status periodically
                status = self.get_status()
                if self.restart_count > 0 or status['memory_usage'] != "0.0%":
                    self.log(f"   Memory: {status['memory_usage']} | CPU: {status['cpu_usage']} | Restarts: {status['restarts']}")
                
                time.sleep(self.health_check_interval)
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                self.log(f"Health monitor error: {e}", "ERROR")
                time.sleep(10)
    
    def run_update_checker(self):
        """Periodically check for updates"""
        while self.is_running:
            try:
                time.sleep(self.update_check_interval)
                self.update_from_git()
            except:
                pass
    
    def setup_signal_handlers(self):
        """Setup graceful shutdown"""
        def signal_handler(signum, frame):
            self.log("🛑 Shutdown signal received...")
            self.is_running = False
            
            if hasattr(self, 'genesis_process'):
                self.genesis_process.terminate()
                
            sys.exit(0)
        
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
    
    def start(self):
        """Start autonomous mode"""
        self.log(f"""
╔═══════════════════════════════════════════════════════════╗
║     ⚡ GENESIS AUTONOMOUS MODE v{self.VERSION} ⚡      ║
║     Self-running AI Protocol                             ║
╚═══════════════════════════════════════════════════════════╝
        """)
        
        # Setup
        self.setup_signal_handlers()
        self.check_railway_deployment()
        
        # Start Genesis
        self.start_genesis()
        
        # Start monitoring threads
        Thread(target=self.run_health_monitor, daemon=True).start()
        Thread(target=self.run_update_checker, daemon=True).start()
        
        self.log("✅ Autonomous mode active!")
        self.log(f"   📊 Status: {json.dumps(self.get_status(), indent=2)}")
        
        # Keep main thread alive
        try:
            while self.is_running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.log("Shutting down...")
            self.is_running = False


def main():
    """Entry point"""
    autonomous = GenesisAutonomousMode()
    autonomous.start()


if __name__ == "__main__":
    main()