"""Resource Monitor - GLUTTONY v3.0 Survival Layer"""

import psutil
import platform
from datetime import datetime
from typing import Dict


class ResourceMonitor:
    """Monitor system resources in real-time."""
    
    def __init__(self):
        self.start_time = datetime.now()
        self._cpu_samples = []
        self._memory_samples = []
    
    def get_cpu_usage(self) -> float:
        """Get current CPU usage percentage."""
        return psutil.cpu_percent(interval=0.1)
    
    def get_memory_usage(self) -> Dict:
        """Get memory usage stats."""
        mem = psutil.virtual_memory()
        return {
            "total_mb": mem.total / (1024 * 1024),
            "used_mb": mem.used / (1024 * 1024),
            "available_mb": mem.available / (1024 * 1024),
            "percent": mem.percent
        }
    
    def get_disk_usage(self) -> Dict:
        """Get disk usage stats."""
        disk = psutil.disk_usage('/')
        return {
            "total_gb": disk.total / (1024**3),
            "used_gb": disk.used / (1024**3),
            "free_gb": disk.free / (1024**3),
            "percent": disk.percent
        }
    
    def get_network_io(self) -> Dict:
        """Get network I/O stats."""
        net = psutil.net_io_counters()
        return {
            "bytes_sent_mb": net.bytes_sent / (1024 * 1024),
            "bytes_recv_mb": net.bytes_recv / (1024 * 1024)
        }
    
    def get_uptime(self) -> str:
        """Get system uptime."""
        boot_time = datetime.fromtimestamp(psutil.boot_time())
        uptime = datetime.now() - boot_time
        return str(uptime).split('.')[0]
    
    def get_all_stats(self) -> Dict:
        """Get all resource stats."""
        return {
            "timestamp": datetime.now().isoformat(),
            "cpu_percent": self.get_cpu_usage(),
            "memory": self.get_memory_usage(),
            "disk": self.get_disk_usage(),
            "network": self.get_network_io(),
            "uptime": self.get_uptime(),
            "platform": platform.system()
        }


_resource_monitor = None


def get_resource_monitor() -> ResourceMonitor:
    global _resource_monitor
    if _resource_monitor is None:
        _resource_monitor = ResourceMonitor()
    return _resource_monitor
