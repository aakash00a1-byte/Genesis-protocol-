"""Decision Learner - Genesis Protocol v1.9"""

class DecisionLearner:
    def __init__(self):
        self.stats = {"approved": 0, "rejected": 0}
        self.risk_preference = {"safe": 0, "moderate": 0, "dangerous": 0}
    
    def record_approval(self, risk_level: str = "safe"):
        self.stats["approved"] += 1
        self.risk_preference[risk_level] = self.risk_preference.get(risk_level, 0) + 1
    
    def record_rejection(self, risk_level: str = "safe"):
        self.stats["rejected"] += 1
    
    def get_preferred_risk_level(self) -> str:
        if self.stats["approved"] == 0:
            return "safe"
        return max(self.risk_preference, key=self.risk_preference.get)
    
    def get_approval_rate(self) -> float:
        total = self.stats["approved"] + self.stats["rejected"]
        return self.stats["approved"] / max(1, total)


_learner = None

def get_decision_learner() -> DecisionLearner:
    global _learner
    if _learner is None:
        _learner = DecisionLearner()
    return _learner
