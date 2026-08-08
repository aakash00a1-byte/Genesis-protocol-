"""
Auto-Updater Background Service - Genesis Protocol ∞

Runs in background and automatically applies scheduled updates.
"""

import os
import sys
import time
import json
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from genesis_protocol.infinity.auto_update_scheduler import (
    AutoUpdateScheduler, UpdateStatus, UpdatePriority
)
from genesis_protocol.infinity.self_evolution import SelfEvolution
from genesis_protocol.infinity.future_roadmap import FutureRoadmap

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)-8s] %(name)s: %(message)s'
)
logger = logging.getLogger("auto_updater")


class GenesisAutoUpdater:
    """
    Auto-Updater for Genesis Protocol
    
    Automatically:
    - Checks for scheduled updates every hour
    - Evolves when metrics meet threshold
    - Updates roadmap progress
    - Logs all activities
    """
    
    def __init__(self):
        self.running = False
        self.check_interval = 3600  # Check every hour (in seconds)
        self.auto_scheduler = AutoUpdateScheduler()
        self.self_evolution = SelfEvolution()
        self.roadmap = FutureRoadmap()
        
        # Evolution schedule (when to evolve)
        self.evolution_schedule = [
            {"name": "Daily Learning Check", "interval_hours": 24, "threshold": 10},
            {"name": "Weekly Evolution", "interval_hours": 168, "threshold": 50},
            {"name": "Monthly Major Update", "interval_hours": 720, "threshold": 100},
        ]
        
        self.last_check = datetime.now()
        
        logger.info("🧬 Genesis Auto-Updater initialized")
        logger.info(f"⏰ Check interval: {self.check_interval} seconds")
        logger.info(f"📅 Current version: {self.auto_scheduler.current_version}")
    
    def start(self):
        """Start the auto-updater in background"""
        self.running = True
        
        # Run initial check
        self._run_maintenance()
        
        # Start background thread
        thread = threading.Thread(target=self._background_loop, daemon=True)
        thread.start()
        
        logger.info("🚀 Auto-updater started in background")
        return True
    
    def stop(self):
        """Stop the auto-updater"""
        self.running = False
        logger.info("⏹️ Auto-updater stopped")
    
    def _background_loop(self):
        """Background loop that checks for updates"""
        while self.running:
            try:
                time.sleep(self.check_interval)
                if self.running:
                    self._run_maintenance()
            except Exception as e:
                logger.error(f"Auto-updater error: {e}")
    
    def _run_maintenance(self):
        """Run all maintenance tasks"""
        logger.info("🔧 Running scheduled maintenance...")
        
        self.last_check = datetime.now()
        
        # 1. Check and apply scheduled updates
        self._check_scheduled_updates()
        
        # 2. Check for evolution readiness
        self._check_evolution()
        
        # 3. Update roadmap progress based on time
        self._update_roadmap_progress()
        
        # 4. Log status
        status = self.auto_scheduler.get_status()
        logger.info(f"📊 Status: v{status['current_version']} | "
                   f"Pending: {status['pending_updates']} | "
                   f"Evolution Level: {status['evolution_level']}")
    
    def _check_scheduled_updates(self):
        """Check and apply pending updates"""
        pending = self.auto_scheduler.get_pending_updates()
        
        if pending:
            logger.info(f"📋 Found {len(pending)} pending updates")
            
            for update in pending[:3]:  # Apply max 3 at a time
                logger.info(f"🔄 Applying update: {update.name}")
                
                result = self.auto_scheduler.apply_update(update.id)
                
                if result['success']:
                    logger.info(f"✅ Update applied: {update.name}")
                    
                    # Learn from successful update
                    self.self_evolution.learn(
                        topic="system_update",
                        knowledge=f"Successfully applied update: {update.name}",
                        source="auto_updater"
                    )
                else:
                    logger.error(f"❌ Update failed: {result.get('error')}")
    
    def _check_evolution(self):
        """Check if ready to evolve"""
        metrics = self.self_evolution.metrics
        
        # Evolve if:
        # 1. Success rate is >= 85%
        # 2. At least 100 interactions
        # 3. Has learnings to apply
        
        if metrics.total_interactions >= 100:
            success_rate = metrics.get_success_rate()
            
            if success_rate >= 85 and len(self.self_evolution.learnings) >= 10:
                logger.info(f"🧬 Evolution conditions met!")
                logger.info(f"   - Interactions: {metrics.total_interactions}")
                logger.info(f"   - Success rate: {success_rate:.1f}%")
                logger.info(f"   - Learnings: {len(self.self_evolution.learnings)}")
                
                # Evolve!
                result = self.self_evolution.evolve()
                logger.info(f"🧬 EVOLVED: {result['message']}")
                
                # Schedule next major update
                self._schedule_next_update()
    
    def _update_roadmap_progress(self):
        """Update roadmap progress based on elapsed time"""
        now = datetime.now()
        
        for milestone_id, milestone in self.roadmap.milestones.items():
            if milestone.target_date and milestone.status == "planned":
                # Calculate progress based on time elapsed
                total_days = (milestone.target_date - datetime(2024, 1, 1)).days
                elapsed_days = (now - datetime(2024, 1, 1)).days
                
                if total_days > 0:
                    time_progress = min(100, (elapsed_days / total_days) * 100)
                    
                    # Only update if progress increased
                    if time_progress > milestone.progress:
                        self.roadmap.update_milestone_progress(milestone_id, int(time_progress))
    
    def _schedule_next_update(self):
        """Schedule the next automatic update"""
        # Schedule a learning update in 24 hours
        next_update = datetime.now() + timedelta(hours=24)
        
        self.auto_scheduler.schedule_update(
            name="Auto Learning Update",
            description="Weekly automatic learning and optimization",
            scheduled_date=next_update,
            priority=UpdatePriority.LOW,
            category="maintenance",
            code_changes={"type": "learning_optimization"}
        )
        
        logger.info(f"📅 Scheduled next update: {next_update.strftime('%Y-%m-%d %H:%M')}")
    
    def get_status(self) -> dict:
        """Get current status"""
        return {
            "running": self.running,
            "last_check": self.last_check.isoformat(),
            "next_check_in_seconds": self.check_interval,
            "auto_scheduler": self.auto_scheduler.get_status(),
            "evolution": self.self_evolution.get_status(),
            "roadmap": self.roadmap.get_status()
        }
    
    def force_check(self):
        """Force a maintenance check"""
        self._run_maintenance()


# Singleton instance
_instance = None

def get_auto_updater() -> GenesisAutoUpdater:
    """Get singleton instance"""
    global _instance
    if _instance is None:
        _instance = GenesisAutoUpdater()
    return _instance


def run_standalone():
    """Run as standalone service"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Genesis Auto-Updater')
    parser.add_argument('--interval', type=int, default=3600, help='Check interval in seconds')
    args = parser.parse_args()
    
    updater = get_auto_updater()
    updater.check_interval = args.interval
    
    print("=" * 50)
    print("🧬 Genesis Protocol ∞ Auto-Updater")
    print("=" * 50)
    print(f"Check interval: {args.interval} seconds")
    print("Press Ctrl+C to stop")
    print("=" * 50)
    
    try:
        updater.start()
        
        while True:
            time.sleep(60)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Status: Running...")
            
    except KeyboardInterrupt:
        print("\n🛑 Stopping...")
        updater.stop()


if __name__ == "__main__":
    run_standalone()
