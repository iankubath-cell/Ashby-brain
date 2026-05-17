"""
Ashby-Vira Core v2.0 — The Deterministic Brain
"""
import json
import time
import math
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Set, Tuple
from datetime import datetime

# Constants
ALPHA = 0.15
DEATH_SPIRAL_THRESHOLD = 0.045
STAGNATION_LIMIT = 3
STAGNATION_IGNORE_HOURS = 1
LOW_SEVERITY_CUTOFF = 0.10
RECOVERY_RESET_SCORE = 0.85

class LoopCategory(Enum):
    CATEGORY_I = "closed"
    CATEGORY_II = "open"

class SystemStatus(Enum):
    STABLE = "stable"
    WARNING = "warning"
    CRITICAL = "critical"
    FROZEN = "frozen"
    RECOVERING = "recovering"

class Severity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

SEVERITY_PENALTIES = {
    Severity.LOW: 0.05,
    Severity.MEDIUM: 0.15,
    Severity.HIGH: 0.25,
    Severity.CRITICAL: 0.40,
}

STAGNATION_PENALTY = 0.50
FEATURE_REQUEST_PENALTY = 0.05

@dataclass
class StabilityState:
    score: float = 1.0
    alpha: float = ALPHA
    stagnation_count: int = 0
    status: SystemStatus = SystemStatus.STABLE
    history: list = field(default_factory=list)
    last_mutation_blocked: bool = False
    last_penalty_time: float = 0.0
    noise_ignored_count: int = 0
    decay_cycle_count: int = 0
    stagnation_start_time: Optional[float] = None

    def _calculate_status(self) -> SystemStatus:
        if self.last_mutation_blocked:
            return SystemStatus.FROZEN
        if self.score >= 0.7:
            return SystemStatus.STABLE
        elif self.score >= 0.4:
            if self.stagnation_count == 0:
                return SystemStatus.RECOVERING
            return SystemStatus.WARNING
        else:
            return SystemStatus.CRITICAL

    def _cycles_to_stable(self) -> int:
        if self.score >= 0.7:
            return 0
        target_gap = 0.3
        current_gap = 1.0 - self.score
        if current_gap <= 0:
            return 0
        if current_gap <= 0.0001:
            return 0
        try:
            t = math.log(target_gap / current_gap) / math.log(1 - self.alpha)
            return max(0, math.ceil(t))
        except ValueError:
            return 999

    def apply_input(self, severity: Severity, input_type: str = "bug", timestamp: float = None) -> dict:
        ts = timestamp or time.time()
        self.last_penalty_time = ts

        if self.stagnation_count >= STAGNATION_LIMIT:
            if input_type == "bug" and severity in [Severity.LOW, Severity.MEDIUM]:
                if self.stagnation_start_time and (ts - self.stagnation_start_time) < STAGNATION_IGNORE_HOURS * 3600:
                    self.noise_ignored_count += 1
                    return {
                        "status": "filtered_noise",
                        "reason": "Stagnation limiter active. Low-severity noise ignored.",
                        "stability_score": round(self.score, 4),
                        "action": "IGNORE"
                    }
                else:
                    self.stagnation_start_time = ts

        penalty = 0.0
        if input_type == "bug":
            penalty = SEVERITY_PENALTIES[severity]
        elif input_type == "feature_request":
            penalty = FEATURE_REQUEST_PENALTY
        
        if self.stagnation_count >= STAGNATION_LIMIT:
            penalty += STAGNATION_PENALTY

        self.score -= penalty
        self.score = max(0.0, min(1.0, self.score))

        if penalty > 0:
            self.stagnation_count += 1
            if self.stagnation_count == STAGNATION_LIMIT:
                self.stagnation_start_time = ts
        else:
            self.stagnation_count = 0

        self.status = self._calculate_status()
        action = self._decide_action()

        self.history.append({
            "timestamp": ts,
            "input": input_type,
            "severity": severity.value if isinstance(severity, Severity) else severity,
            "penalty": penalty,
            "score_before": round(self.score + penalty, 4),
            "score_after": round(self.score, 4),
            "action": action["action"]
        })

        return {
            "stability_score": round(self.score, 4),
            "status": self.status.value,
            "penalty_applied": penalty,
            "action": action,
            "cycles_to_stable": self._cycles_to_stable()
        }

    def apply_decay(self) -> dict:
        self.decay_cycle_count += 1
        self.score = self.score + self.alpha * (1.0 - self.score)
        self.score = min(1.0, self.score)

        if self.stagnation_count > 0 and self.score >= 0.7:
            self.stagnation_count = 0
            self.stagnation_start_time = None

        self.status = self._calculate_status()

        return {
            "stability_score": round(self.score, 4),
            "status": self.status.value,
            "recovery_applied": True,
            "cycles_to_stable": self._cycles_to_stable()
        }

    def _decide_action(self) -> dict:
        if self.status == SystemStatus.FROZEN:
            return {
                "action": "ALERT_HUMAN",
                "reason": "Vira blocked the last mutation. Manual intervention required.",
                "loop_category": LoopCategory.CATEGORY_II.value
            }
        if self.status == SystemStatus.CRITICAL:
            return {
                "action": "TRIGGER_MUTATION",
                "reason": f"Stability critical ({self.score:.2f}). Structural shift required.",
                "loop_category": LoopCategory.CATEGORY_II.value,
                "mutation_type": "arnoldian_diversion"
            }
        if self.status == SystemStatus.WARNING:
            return {
                "action": "FLAG",
                "reason": f"Stability degraded ({self.score:.2f}). Monitor closely.",
                "loop_category": LoopCategory.CATEGORY_II.value
            }
        return {
            "action": "ALLOW",
            "reason": f"Stability nominal ({self.score:.2f}).",
            "loop_category": LoopCategory.CATEGORY_I.value
        }

    def reset_after_mutation(self) -> None:
        self.score = RECOVERY_RESET_SCORE
        self.stagnation_count = 0
        self.last_mutation_blocked = False
        self.stagnation_start_time = None
        self.status = self._calculate_status()

class ViraValidator:
    @staticmethod
    def has_cycle(graph: Dict[str, List[str]]) -> bool:
        visited = set()
        rec_stack = set()

        def dfs(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)
            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    if dfs(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True
            rec_stack.remove(node)
            return False

        for node in graph:
            if node not in visited:
                if dfs(node):
                    return True
        return False

    @staticmethod
    def is_goal_reachable(graph: Dict[str, List[str]], start: str = "Self", goal: str = "Goal") -> bool:
        queue = [start]
        visited = set()
        while queue:
            node = queue.pop(0)
            if node == goal:
                return True
            if node in visited:
                continue
            visited.add(node)
            for neighbor in graph.get(node, []):
                queue.append(neighbor)
        return False

    @staticmethod
    def verify_closure(graph: Dict[str, List[str]], start: str = "Self", goal: str = "Goal") -> dict:
        has_cycle_flag = ViraValidator.has_cycle(graph)
        reachable = ViraValidator.is_goal_reachable(graph, start, goal)

        if has_cycle_flag:
            return {
                "closure": LoopCategory.CATEGORY_II.value,
                "valid": False,
                "reason": "Graph contains a cycle (Feedback Loop). Category II.",
                "path": None
            }
        
        if not reachable:
            return {
                "closure": LoopCategory.CATEGORY_II.value,
                "valid": False,
                "reason": "Goal is not reachable from Start.",
                "path": None
            }

        return {
            "closure": LoopCategory.CATEGORY_I.value,
            "valid": True,
            "reason": "Graph is acyclic and Goal is reachable. Category I.",
            "path": [start, goal]
        }

    @staticmethod
    def validate_mutation(mutation_graph: Dict[str, List[str]], stability: StabilityState) -> dict:
        result = ViraValidator.verify_closure(mutation_graph)
        if not result["valid"]:
            stability.last_mutation_blocked = True
            stability.status = SystemStatus.FROZEN
            return {
                "approved": False,
                "reason": f"Mutation rejected: {result['reason']}",
                "closure": result["closure"],
                "action": "ALERT_HUMAN"
            }
        return {
            "approved": True,
            "reason": "Mutation achieves Category I closure.",
            "closure": result["closure"],
            "action": "APPLY_MUTATION"
        }

system_state = StabilityState()

def handle_feedback(event: dict) -> dict:
    input_type = event.get("type", "general_feedback")
    severity_str = event.get("severity", "medium")
    try:
        severity = Severity(severity_str)
    except ValueError:
        severity = Severity.MEDIUM
    result = system_state.apply_input(severity, input_type)
    return {
        "status": "processed",
        "stability_score": result["stability_score"],
        "system_status": result["status"],
        "action": result["action"],
        "cycles_to_stable": result["cycles_to_stable"],
        "noise_ignored": system_state.noise_ignored_count
    }

def handle_decay_cycle() -> dict:
    result = system_state.apply_decay()
    return {
        "status": "decay_applied",
        "stability_score": result["stability_score"],
        "system_status": result["status"],
        "cycles_to_stable": result["cycles_to_stable"]
    }

def handle_validate_mutation(mutation_graph: dict) -> dict:
    result = ViraValidator.validate_mutation(mutation_graph, system_state)
    if result["approved"]:
        system_state.reset_after_mutation()
    return result

def handle_get_state() -> dict:
    return {
        "stability_score": round(system_state.score, 4),
        "status": system_state.status.value,
        "stagnation_count": system_state.stagnation_count,
        "history_length": len(system_state.history),
        "cycles_to_stable": system_state._cycles_to_stable(),
        "noise_ignored": system_state.noise_ignored_count
    }