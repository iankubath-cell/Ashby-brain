import json, time, math, threading, os
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List, Dict
from collections import deque

STATE_FILE = "ashby_state.json"
_rate_limit_store = {}
_rate_limit_lock = threading.Lock()

def check_rate_limit(user_id, max_requests=5, window_seconds=60):
    now = time.time()
    with _rate_limit_lock:
        if user_id not in _rate_limit_store:
            _rate_limit_store[user_id] = deque()
        h = _rate_limit_store[user_id]
        while h and h[0] < now - window_seconds:
            h.popleft()
        if len(h) >= max_requests:
            return False
        h.append(now)
        return True

def validate_input(data):
    if "type" not in data:
        raise ValueError("Missing type")
    if data["type"] not in ["bug", "feature_request", "general_feedback"]:
        raise ValueError("Invalid type")
    if "severity" in data and data["severity"] not in ["low", "medium", "high", "critical"]:
        raise ValueError("Invalid severity")
    uid = data.get("user_email", "anonymous")
    if not check_rate_limit(uid):
        raise ValueError("Rate limit exceeded")
    return True

ALPHA = 0.15
STAGNATION_LIMIT = 3
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

SEVERITY_PENALTIES = {Severity.LOW: 0.05, Severity.MEDIUM: 0.15, Severity.HIGH: 0.25, Severity.CRITICAL: 0.40}
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

    def _calculate_status(self):
        if self.last_mutation_blocked:
            return SystemStatus.FROZEN
        if self.score >= 0.7:
            return SystemStatus.STABLE
        if self.score >= 0.4:
            return SystemStatus.RECOVERING if self.stagnation_count == 0 else SystemStatus.WARNING
        return SystemStatus.CRITICAL

    def _cycles_to_stable(self):
        if self.score >= 0.7:
            return 0
        gap = 1.0 - self.score
        if gap <= 0:
            return 0
        try:
            return max(0, math.ceil(math.log(0.3 / gap) / math.log(1 - self.alpha)))
        except:
            return 999

    def calculate_weighted_penalty(self, severity, trust_score=1.0):
        return SEVERITY_PENALTIES[severity] * max(0.1, min(1.0, trust_score))

    def apply_input(self, severity, input_type="bug", timestamp=None, trust_score=1.0):
        ts = timestamp or time.time()
        self.last_penalty_time = ts
        if self.stagnation_count >= STAGNATION_LIMIT:
            if input_type == "bug" and severity in [Severity.LOW, Severity.MEDIUM]:
                if self.stagnation_start_time and (ts - self.stagnation_start_time) < 3600:
                    self.noise_ignored_count += 1
                    return {"status": "filtered_noise", "reason": "Ignored", "stability_score": round(self.score, 4), "action": "IGNORE"}
                self.stagnation_start_time = ts
        penalty = self.calculate_weighted_penalty(severity, trust_score)
        if input_type == "feature_request":
            penalty = FEATURE_REQUEST_PENALTY * trust_score
        if self.stagnation_count >= STAGNATION_LIMIT:
            penalty += STAGNATION_PENALTY
        self.score = max(0.0, min(1.0, self.score - penalty))
        if penalty > 0:
            self.stagnation_count += 1
            if self.stagnation_count == STAGNATION_LIMIT:
                self.stagnation_start_time = ts
        else:
            self.stagnation_count = 0
        self.status = self._calculate_status()
        action = self._decide_action()
        self.history.append({"timestamp": ts, "input": input_type, "severity": severity.value, "penalty": penalty, "score_after": round(self.score, 4), "action": action["action"]})
        return {"stability_score": round(self.score, 4), "status": self.status.value, "penalty_applied": penalty, "action": action, "cycles_to_stable": self._cycles_to_stable()}

    def apply_decay(self):
        self.decay_cycle_count += 1
        self.score = min(1.0, self.score + self.alpha * (1.0 - self.score))
        if self.stagnation_count > 0 and self.score >= 0.7:
            self.stagnation_count = 0
            self.stagnation_start_time = None
        self.status = self._calculate_status()
        return {"stability_score": round(self.score, 4), "status": self.status.value, "recovery_applied": True, "cycles_to_stable": self._cycles_to_stable()}

    def _decide_action(self):
        if self.status == SystemStatus.FROZEN:
            return {"action": "ALERT_HUMAN", "reason": "Blocked", "loop_category": "open"}
        if self.status == SystemStatus.CRITICAL:
            return {"action": "TRIGGER_MUTATION", "reason": "Critical", "loop_category": "open", "mutation_type": "diversion"}
        if self.status == SystemStatus.WARNING:
            return {"action": "FLAG", "reason": "Degraded", "loop_category": "open"}
        return {"action": "ALLOW", "reason": "Nominal", "loop_category": "closed"}

    def reset_after_mutation(self):
        self.score = RECOVERY_RESET_SCORE
        self.stagnation_count = 0
        self.last_mutation_blocked = False
        self.stagnation_start_time = None
        self.status = self._calculate_status()

class ViraValidator:
    @staticmethod
    def has_cycle(graph):
        visited, rec_stack = set(), set()
        def dfs(node):
            visited.add(node)
            rec_stack.add(node)
            for nb in graph.get(node, []):
                if nb not in visited:
                    if dfs(nb):
                        return True
                elif nb in rec_stack:
                    return True
            rec_stack.remove(node)
            return False
        for node in graph:
            if node not in visited and dfs(node):
                return True
        return False

    @staticmethod
    def is_goal_reachable(graph, start="Self", goal="Goal"):
        queue, visited = [start], set()
        while queue:
            node = queue.pop(0)
            if node == goal:
                return True
            if node in visited:
                continue
            visited.add(node)
            queue.extend(graph.get(node, []))
        return False

    @staticmethod
    def verify_closure(graph, start="Self", goal="Goal"):
        if ViraValidator.has_cycle(graph):
            return {"closure": "open", "valid": False, "reason": "Cycle detected", "path": None}
        if not ViraValidator.is_goal_reachable(graph, start, goal):
            return {"closure": "open", "valid": False, "reason": "Goal unreachable", "path": None}
        return {"closure": "closed", "valid": True, "reason": "Valid", "path": [start, goal]}

    @staticmethod
    def validate_mutation(mutation_graph, stability):
        result = ViraValidator.verify_closure(mutation_graph)
        if not result["valid"]:
            stability.last_mutation_blocked = True
            stability.status = SystemStatus.FROZEN
            return {"approved": False, "reason": result["reason"], "closure": result["closure"], "action": "ALERT_HUMAN"}
        return {"approved": True, "reason": "Valid", "closure": result["closure"], "action": "APPLY_MUTATION"}

def save_state():
    try:
        with open(STATE_FILE, "w") as f:
            json.dump({"score": system_state.score, "stagnation_count": system_state.stagnation_count, "history": system_state.history[-100:], "last_mutation_blocked": system_state.last_mutation_blocked, "noise_ignored_count": system_state.noise_ignored_count, "decay_cycle_count": system_state.decay_cycle_count}, f)
    except Exception as e:
        print(f"Save error: {e}")

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
            system_state.score = data.get("score", 1.0)
            system_state.stagnation_count = data.get("stagnation_count", 0)
            system_state.history = data.get("history", [])
            system_state.last_mutation_blocked = data.get("last_mutation_blocked", False)
            system_state.noise_ignored_count = data.get("noise_ignored_count", 0)
            system_state.decay_cycle_count = data.get("decay_cycle_count", 0)
            system_state.status = system_state._calculate_status()
        except Exception as e:
            print(f"Load error: {e}")

system_state = StabilityState()
load_state()

def handle_feedback(event):
    try:
        validate_input(event)
        input_type = event.get("type", "general_feedback")
        severity_str = event.get("severity", "medium")
        trust_score = event.get("trust_score", 1.0)
        try:
            severity = Severity(severity_str)
        except:
            severity = Severity.MEDIUM
        result = system_state.apply_input(severity, input_type, trust_score=trust_score)
        save_state()
        return {"status": "processed", "stability_score": result["stability_score"], "system_status": result["status"], "action": result["action"], "cycles_to_stable": result["cycles_to_stable"], "noise_ignored": system_state.noise_ignored_count}
    except ValueError as e:
        return {"status": "blocked", "reason": str(e), "stability_score": round(system_state.score, 4), "action": {"action": "IGNORE"}}

def handle_decay_cycle():
    result = system_state.apply_decay()
    save_state()
    return {"status": "decay_applied", "stability_score": result["stability_score"], "system_status": result["status"], "cycles_to_stable": result["cycles_to_stable"]}

def handle_validate_mutation(mutation_graph):
    result = ViraValidator.validate_mutation(mutation_graph, system_state)
    if result["approved"]:
        system_state.reset_after_mutation()
        save_state()
    return result

def handle_get_state():
    return {"stability_score": round(system_state.score, 4), "status": system_state.status.value, "stagnation_count": system_state.stagnation_count, "history_length": len(system_state.history), "cycles_to_stable": system_state._cycles_to_stable(), "noise_ignored": system_state.noise_ignored_count}
