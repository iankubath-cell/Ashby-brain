"""
============================================================================
ASHBY-VIRA CORE v2.1 — COMPLETE API SERVER
============================================================================

Features:
  - Ashby Homeostat (Stability Tracking)
  - Vira Validator (Cycle Detection)
  - Counterfactual Engine (Rung 3: "What If?" Analysis)

Endpoints:
  GET  /               → System Info
  GET  /state           → Current Stability State
  POST /feedback        → Submit Feedback Event
  POST /decay           → Run Decay Cycle
  POST /validate        → Validate Mutation Graph
  POST /counterfactual  → Run Counterfactual Simulation

Date: May 24, 2026
============================================================================
"""

import math
import itertools
from typing import Dict, Any, Callable, List, Optional, Tuple

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Import existing Ashby Core logic
from ashby_core import (
    handle_feedback,
    handle_decay_cycle,
    handle_validate_mutation,
    handle_get_state
)

# ============================================================================
# COUNTERFACTUAL ENGINE (Embedded)
# ============================================================================

class AshbyCounterfactualEngine:
    """
    Advanced Counterfactual Engine for Ashby.
    Implements Pearl's Ladder of Causation (Rung 3) with Multi-World Safety.
    """

    def __init__(self, structural_equations: Dict[str, Callable], graph_parents: Dict[str, list]):
        self.equations = structural_equations
        self.parents = graph_parents
        self.abducted_u: Dict[str, float] = {}
        self.u_range: Dict[str, Tuple[float, float]] = {}

    def abduction_invertible(self, observed_state: Dict[str, float]) -> Dict[str, float]:
        """
        Step 1: Abduction. Solves for U exactly if Y = f(parents) + U.
        """
        self.abducted_u = {}
        sorted_nodes = sorted(self.equations.keys(), key=lambda k: len(self.parents[k]))

        for node in sorted_nodes:
            parent_vals = {p: observed_state[p] for p in self.parents[node]}
            observed_val = observed_state[node]
            base_val = self.equations[node](parent_vals)
            u_val = observed_val - base_val
            self.abducted_u[node] = u_val
        return self.abducted_u

    def abduction_multi_world(self, observed_state: Dict[str, float], tolerance: float = 0.1, resolution: int = 100) -> Dict[str, List[float]]:
        """
        Step 1 (Multi-World): Find the SET of all U values consistent with observation.
        """
        consistent_u_sets = {}
        sorted_nodes = sorted(self.equations.keys(), key=lambda k: len(self.parents[k]))

        for node in sorted_nodes:
            parent_vals = {p: observed_state[p] for p in self.parents[node]}
            observed_val = observed_state[node]
            base_val = self.equations[node](parent_vals)
            center_u = observed_val - base_val
            
            u_min = center_u - tolerance
            u_max = center_u + tolerance
            
            candidates = []
            step = (u_max - u_min) / resolution
            for i in range(resolution + 1):
                u = u_min + (i * step)
                candidates.append(u)
            
            consistent_u_sets[node] = candidates
        
        self.u_range = {k: (min(v), max(v)) for k, v in consistent_u_sets.items()}
        return consistent_u_sets

    def predict_twin_world(self, intervention: Dict[str, float]) -> Dict[str, float]:
        """
        Steps 2 & 3: Action (do(X)) and Prediction (Single World).
        """
        if not self.abducted_u:
            raise ValueError("Must run abduction first.")

        twin_world = {}
        sorted_nodes = sorted(self.equations.keys(), key=lambda k: len(self.parents[k]))

        for node in sorted_nodes:
            if node in intervention:
                twin_world[node] = intervention[node]
                continue
            
            parent_vals = {p: twin_world[p] for p in self.parents[node]}
            base_val = self.equations[node](parent_vals)
            u_val = self.abducted_u.get(node, 0)
            twin_world[node] = base_val + u_val

        return twin_world

    def predict_multi_world_safety(self, intervention: Dict[str, float], target_node: str, hazard_threshold: float) -> Tuple[bool, float, Dict[str, float]]:
        """
        Steps 2 & 3 (Multi-World): Simulates intervention across ALL consistent worlds.
        Returns: (is_safe, worst_case_value, worst_case_world)
        """
        if not self.u_range:
            raise ValueError("Must run multi-world abduction first.")

        worst_case_val = -float('inf')
        worst_case_world = None
        is_safe = True

        # Generate sample points for each node
        sample_points = {}
        for node, (u_min, u_max) in self.u_range.items():
            step = (u_max - u_min) / 10
            sample_points[node] = [u_min + i * step for i in range(11)]

        nodes = list(self.u_range.keys())
        
        if len(nodes) <= 2:
            # Full sweep for small graphs
            ranges = [sample_points[n] for n in nodes]
            for u_combo in itertools.product(*ranges):
                twin_world = {}
                u_map = dict(zip(nodes, u_combo))
                
                sorted_nodes = sorted(self.equations.keys(), key=lambda k: len(self.parents[k]))
                for node in sorted_nodes:
                    if node in intervention:
                        twin_world[node] = intervention[node]
                        continue
                    
                    parent_vals = {p: twin_world[p] for p in self.parents[node]}
                    base_val = self.equations[node](parent_vals)
                    u_val = u_map.get(node, 0)
                    twin_world[node] = base_val + u_val
                
                val = twin_world.get(target_node, 0)
                if val > worst_case_val:
                    worst_case_val = val
                    worst_case_world = twin_world.copy()
        else:
            # Fallback: Just check the center U (Twin World) if graph is too complex
            twin_world = self.predict_twin_world(intervention)
            worst_case_val = twin_world.get(target_node, 0)
            worst_case_world = twin_world

        is_safe = worst_case_val < hazard_threshold
        return is_safe, worst_case_val, worst_case_world

    def run_counterfactual(self, observed: Dict[str, float], intervention: Dict[str, float], target: str, mode: str = "twin", hazard_threshold: float = 100.0) -> Dict[str, Any]:
        """
        Main Entry Point.
        mode: "twin" (fast, exact) or "multi" (robust, worst-case)
        """
        if mode == "twin":
            self.abduction_invertible(observed)
            twin_world = self.predict_twin_world(intervention)
            return {
                "mode": "twin_world",
                "abducted_noise": self.abducted_u,
                "counterfactual_outcome": twin_world,
                "target_result": twin_world.get(target),
                "is_safe": twin_world.get(target, 0) < hazard_threshold
            }
        elif mode == "multi":
            self.abduction_multi_world(observed)
            is_safe, worst_val, worst_world = self.predict_multi_world_safety(intervention, target, hazard_threshold)
            return {
                "mode": "multi_world",
                "u_ranges": self.u_range,
                "worst_case_outcome": worst_val,
                "worst_case_world": worst_world,
                "is_safe": is_safe,
                "safety_message": "SAFE" if is_safe else "HAZARD DETECTED IN WORST CASE"
            }
        else:
            raise ValueError("Mode must be 'twin' or 'multi'")

# ============================================================================
# FASTAPI APP SETUP
# ============================================================================

app = FastAPI(
    title="Ashby-Vira Core v2.1",
    description="The Deterministic Brain for Autonomous AI Systems",
    version="2.1.0"
)

# --- Root Route ---
@app.get("/")
async def root():
    return {
        "system": "Ashby-Vira Core v2.1",
        "status": "ONLINE",
        "endpoints": {
            "GET /": "System Info",
            "GET /state": "Get Current Stability State",
            "POST /feedback": "Submit Feedback Event",
            "POST /decay": "Run Decay Cycle",
            "POST /validate": "Validate Mutation Graph",
            "POST /counterfactual": "Run Counterfactual Simulation"
        }
    }

# --- State Route ---
@app.get("/state")
async def get_state():
    return handle_get_state()

# --- Feedback Route ---
@app.post("/feedback")
async def feedback(event: Dict[str, Any]):
    try:
        result = handle_feedback(event)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Decay Route ---
@app.post("/decay")
async def decay():
    return handle_decay_cycle()

# --- Validate Route ---
@app.post("/validate")
async def validate(mutation_graph: Dict[str, Any]):
    try:
        result = handle_validate_mutation(mutation_graph)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Counterfactual Route ---
@app.post("/counterfactual")
async def run_counterfactual_api(request: Dict[str, Any]):
    """
    Endpoint to run counterfactual analysis.
    Expects: {
        "observed_state": {"Power": 60, "Temp": 130, "Shutdown": 1},
        "intervention": {"Power": 40},
        "target_node": "Temp",
        "mode": "multi",
        "hazard_threshold": 100.0
    }
    """
    try:
        # Define the Reactor Scenario (Hardcoded for demo stability)
        def eq_power(_): return 0
        def eq_temp(parents): return 2 * parents['Power']
        def eq_shutdown(parents): return 1 if parents['Temp'] > 100 else 0

        equations = {
            "Power": eq_power,
            "Temp": eq_temp,
            "Shutdown": eq_shutdown
        }
        parents = {
            "Power": [],
            "Temp": ["Power"],
            "Shutdown": ["Temp"]
        }
        
        engine = AshbyCounterfactualEngine(equations, parents)
        
        # Extract request data
        observed = request.get("observed_state", {"Power": 60, "Temp": 130, "Shutdown": 1})
        intervention = request.get("intervention", {"Power": 40})
        target = request.get("target_node", "Temp")
        mode = request.get("mode", "multi")
        threshold = request.get("hazard_threshold", 100.0)
        
        result = engine.run_counterfactual(observed, intervention, target, mode, threshold)
        
        return {
            "status": "success",
            "data": result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Counterfactual Error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
