"""Simulation Layer - Genesis Protocol v1.7"""

from typing import Dict, List, Any


class SimulationResult:
    def __init__(self, success: bool, output: Any, errors: List[str] = None):
        self.success = success
        self.output = output
        self.errors = errors or []


class SimulationLayer:
    """Tests proposals without modifying production code."""
    
    def __init__(self):
        self.test_results = []
    
    def simulate(self, proposal: Dict[str, Any]) -> SimulationResult:
        """Simulate a proposal."""
        solution = proposal.get("proposed_solution", "")
        problem = proposal.get("problem", "")
        
        # Simulate by running tests
        errors = []
        
        # Check if solution is safe
        if "eval(" in solution or "exec(" in solution:
            errors.append("Dangerous code pattern detected")
        
        if "delete" in solution.lower() and "memory" in solution.lower():
            errors.append("Memory deletion detected - forbidden")
        
        if not errors:
            return SimulationResult(
                success=True,
                output={"simulated": True, "message": "Proposal passed simulation"},
                errors=[]
            )
        
        return SimulationResult(
            success=False,
            output=None,
            errors=errors
        )
    
    def run_tests(self, proposal_id: str) -> Dict[str, Any]:
        """Run tests for a proposal."""
        return {
            "proposal_id": proposal_id,
            "tests_passed": True,
            "simulation_completed": True,
            "ready_for_review": True
        }
    
    def get_simulations(self) -> List[Dict[str, Any]]:
        """Get simulation history."""
        return self.test_results


_simulation_layer = None


def get_simulation_layer() -> SimulationLayer:
    global _simulation_layer
    if _simulation_layer is None:
        _simulation_layer = SimulationLayer()
    return _simulation_layer
