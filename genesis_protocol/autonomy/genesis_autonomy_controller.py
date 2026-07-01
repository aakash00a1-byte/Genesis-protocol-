"""
⚡ Genesis Autonomy Controller ⚡
Unified controller connecting all autonomy components
"""

import os
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path

from genesis_protocol.gluttony_os.autonomy_controller import get_autonomy_controller
from genesis_protocol.improvement import (
    WeaknessDetector, ProposalGenerator, RiskEngine, SafetyRules,
    get_weakness_detector, get_proposal_generator
)
from genesis_protocol.autonomy.github_agent import GitHubAgent
from genesis_protocol.autonomy.memory_agent import get_memory_agent
from genesis_protocol.autonomy.scheduler_agent import get_scheduler_agent


class GenesisAutonomyController:
    """
    Unified Genesis Protocol Autonomy Controller.
    
    Connects:
    - Autonomy Directive (OS)
    - Self-Improvement System
    - GitHub Integration
    - Memory System
    - Scheduler
    """
    
    VERSION = "1.0.0"
    
    def __init__(self):
        # Initialize all components
        self.autonomy = get_autonomy_controller()
        self.weakness_detector = get_weakness_detector()
        self.proposal_generator = get_proposal_generator()
        self.risk_engine = RiskEngine()
        self.safety_rules = SafetyRules()
        self.memory = get_memory_agent()
        self.scheduler = get_scheduler_agent()
        self.github = GitHubAgent()
        
        self.journal = []
    
    def observe(self) -> Dict:
        """Observe current state - OS Evolution Cycle: observe."""
        return {
            "timestamp": datetime.now().isoformat(),
            "autonomy_level": self.autonomy.get_level(),
            "weaknesses": self.weakness_detector.get_summary(),
            "memory_stats": self.memory.get_stats(),
            "scheduler_status": self.scheduler.get_status(),
        }
    
    def evaluate(self) -> Dict:
        """Evaluate current state - OS Evolution Cycle: evaluate."""
        weaknesses = self.weakness_detector.get_top_weaknesses(5)
        proposals = self.proposal_generator.get_proposed_proposals()
        
        return {
            "timestamp": datetime.now().isoformat(),
            "top_weaknesses": weaknesses,
            "pending_proposals": len(proposals),
            "risks": self._assess_risks()
        }
    
    def propose(self) -> Dict:
        """Generate improvement proposals - OS Evolution Cycle: propose."""
        weaknesses = self.weakness_detector.get_top_weaknesses(5)
        new_proposals = []
        
        for weak in weaknesses:
            prop = self.proposal_generator.generate_from_weakness(weak)
            self.proposal_generator.propose(prop.id)
            new_proposals.append(prop.id)
        
        return {
            "timestamp": datetime.now().isoformat(),
            "proposals_generated": len(new_proposals),
            "proposal_ids": new_proposals
        }
    
    def experiment(self, proposal_id: str) -> Dict:
        """Simulate/experiment with proposal - OS Evolution Cycle: experiment."""
        proposal = self.proposal_generator.get_proposal(proposal_id)
        
        if not proposal:
            return {"error": "Proposal not found"}
        
        # Use simulation layer
        from genesis_protocol.improvement.simulation_layer import get_simulation_layer
        sim = get_simulation_layer()
        
        result = sim.simulate({
            "proposed_solution": proposal.proposed_solution,
            "problem": proposal.problem
        })
        
        return {
            "proposal_id": proposal_id,
            "simulation": result.__dict__ if hasattr(result, '__dict__') else str(result)
        }
    
    def prepare(self, proposal_id: str) -> Dict:
        """Prepare for implementation - OS Evolution Cycle: prepare."""
        proposal = self.proposal_generator.get_proposal(proposal_id)
        
        if not proposal:
            return {"error": "Proposal not found"}
        
        # Risk assessment
        risk = self.risk_engine.assess_risk({
            "proposed_solution": proposal.proposed_solution,
            "files_affected": ["unknown"]
        })
        
        # Safety check
        safety_ok = self.safety_rules.is_allowed("self_refactoring")
        
        return {
            "proposal_id": proposal_id,
            "risk_assessment": risk,
            "safety_check": safety_ok,
            "can_proceed": risk["risk_level"] in ["safe"] and safety_ok
        }
    
    def journal_entry(self, entry: str, category: str = "general"):
        """Log to journal - OS Evolution Cycle: journal."""
        self.journal.append({
            "timestamp": datetime.now().isoformat(),
            "category": category,
            "entry": entry
        })
        
        # Also save to memory
        self.memory.remember(
            content=entry,
            category="lesson",
            tags=[category, "journal"],
            importance=0.6
        )
        
        return {"journaled": True, "entries": len(self.journal)}
    
    def learn(self, lesson: str, context: str, outcome: str):
        """Learn from experience - OS Evolution Cycle: learn."""
        self.memory.remember_lesson(
            lesson=lesson,
            context=context,
            outcome=outcome
        )
        
        return {
            "learned": True,
            "lesson": lesson
        }
    
    def check_and_improve(self) -> Dict:
        """Run full OS evolution cycle."""
        results = {
            "timestamp": datetime.now().isoformat(),
            "cycle": ["observe", "evaluate", "propose", "experiment", "journal", "learn"]
        }
        
        # Observe
        results["observe"] = self.observe()
        
        # Evaluate
        results["evaluate"] = self.evaluate()
        
        # Propose
        results["propose"] = self.propose()
        
        # Journal
        results["journal"] = self.journal_entry(
            f"Autonomy check completed. "
            f"Weaknesses: {results['evaluate']['top_weaknesses']}, "
            f"Proposals: {results['propose']['proposals_generated']}"
        )
        
        # Learn
        results["learn"] = self.learn(
            lesson=f"Regular autonomy checks help maintain system health",
            context="Scheduled self-improvement cycle",
            outcome="All systems nominal"
        )
        
        return results
    
    def get_status(self) -> Dict:
        """Get complete status of all autonomy components."""
        return {
            "version": self.VERSION,
            "components": {
                "autonomy_controller": {
                    "level": self.autonomy.get_level(),
                    "directives_active": {
                        "autonomy": self.autonomy.is_autonomy_directive_active(),
                        "long_road": self.autonomy.is_long_road_directive_active(),
                        "evolution": self.autonomy.is_evolution_directive_active()
                    }
                },
                "improvement": {
                    "weakness_detector": self.weakness_detector.get_summary(),
                    "proposals_pending": len(self.proposal_generator.get_proposed_proposals()),
                    "safety_enabled": self.safety_rules.get_status()["enabled"]
                },
                "memory": self.memory.get_stats(),
                "scheduler": {
                    "total_tasks": self.scheduler.get_status()["total_tasks"],
                    "due_now": self.scheduler.get_status()["due_now"]
                },
                "github": {
                    "configured": bool(self.github.token),
                    "repo": f"{self.github.REPO_OWNER}/{self.github.REPO_NAME}"
                }
            },
            "journal_entries": len(self.journal)
        }
    
    def run_scheduled_checks(self) -> Dict:
        """Run all due scheduled tasks."""
        return self.scheduler.run_due_tasks()


# Global singleton
_genesis_autonomy_controller: Optional[GenesisAutonomyController] = None


def get_genesis_autonomy_controller() -> GenesisAutonomyController:
    """Get global genesis autonomy controller."""
    global _genesis_autonomy_controller
    if _genesis_autonomy_controller is None:
        _genesis_autonomy_controller = GenesisAutonomyController()
    return _genesis_autonomy_controller


if __name__ == "__main__":
    print("""
╔═══════════════════════════════════════════════════════════╗
║     ⚡ GENESIS AUTONOMY CONTROLLER v1.0.0 ⚡    ║
╚═══════════════════════════════════════════════════════════╝
    """)
    
    controller = GenesisAutonomyController()
    status = controller.get_status()
    
    print("\n📊 System Status:")
    print(f"   Version: {status['version']}")
    print(f"   Autonomy Level: {status['components']['autonomy_controller']['level']}")
    print(f"   Memories: {status['components']['memory']['total_memories']}")
    print(f"   Scheduled Tasks: {status['components']['scheduler']['total_tasks']}")
    print(f"   GitHub Configured: {status['components']['github']['configured']}")
    
    print("\n🔍 Running Self-Check...")
    result = controller.check_and_improve()
    print(f"\n✅ Self-check complete!")
    print(f"   Weaknesses found: {len(result['evaluate']['top_weaknesses'])}")
    print(f"   Proposals generated: {result['propose']['proposals_generated']}")
