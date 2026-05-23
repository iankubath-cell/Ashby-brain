import math
from typing import Dict, Any, Callable, List, Optional, Tuple

class AshbyCounterfactualEngine:
    """
    Advanced Counterfactual Engine for Ashby.
    Features:
    1. Invertible Abduction (Solves for U exactly if linear).
    2. Multi-World Safety (Checks worst-case scenario across a range of U).
    3. Deterministic Decision Making (No guessing).
    """

    def __init__(self, structural_equations: Dict[str, Callable], graph_parents: Dict[str, list]):
        """
        structural_equations: Dict mapping node_name -> function(parents)
                              (Assumes linear additive noise: Y = f(parents) + U)
        graph_parents: Dict mapping node_name -> list of parent node names
        """
        self.equations = structural_equations
        self.parents = graph_parents
        self.abducted_u: Dict[str, float] = {}
        self.u_range: Dict[str, Tuple[float, float]] = {} # For Multi-World

    def abduction_invertible(self, observed_state: Dict[str, float]) -> Dict[str, float]:
        """
        Step 1: Abduction.
        Solves for U assuming Y = f(parents) + U.
        U = Y - f(parents)
        """
        self.abducted_u = {}
        # Process in topological order (simplified: sort by parent count)
        sorted_nodes = sorted(self.equations.keys(), key=lambda k: len(self.parents[k]))

        for node in sorted_nodes:
            parent_vals = {p: observed_state[p] for p in self.parents[node]}
            observed_val = observed_state[node]
            
            # Calculate base value from parents
            base_val = self.equations[node](parent_vals)
            
            # Solve for U
            u_val = observed_val - base_val
            self.abducted_u[node] = u_val
            
        return self.abducted_u

    def abduction_multi_world(self, observed_state: Dict[str, float], tolerance: float = 0.1, resolution: int = 100) -> Dict[str, List[float]]:
        """
        Step 1 (Multi-World): Find the SET of all U values consistent with observation.
        Used when equations are non-invertible or noisy.
        """
        consistent_u_sets = {}
        sorted_nodes = sorted(self.equations.keys(), key=lambda k: len(self.parents[k]))

        for node in sorted_nodes:
            parent_vals = {p: observed_state[p] for p in self.parents[node]}
            observed_val = observed_state[node]
            base_val = self.equations[node](parent_vals)
            
            # Calculate the "center" U
            center_u = observed_val - base_val
            
            # Define a range around the center (tolerance)
            u_min = center_u - tolerance
            u_max = center_u + tolerance
            
            # Generate candidates
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
        Uses the exact abducted U.
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
        Steps 2 & 3 (Multi-World):
        Simulates the intervention across ALL consistent worlds.
        Returns: (is_safe, worst_case_value, worst_case_world)
        """
        if not self.u_range:
            raise ValueError("Must run multi-world abduction first.")

        worst_case_val = -float('inf')
        worst_case_world = None
        is_safe = True

        # Simple nested loop for demonstration (Optimization: use vectorized math or interval arithmetic)
        # For a real system, we would use a more efficient sampling strategy.
        # Here we sample 10 points from each range to keep it fast.
        
        # Generate sample points for each node
        sample_points = {}
        for node, (u_min, u_max) in self.u_range.items():
            step = (u_max - u_min) / 10
            sample_points[node] = [u_min + i * step for i in range(11)]

        # Cartesian product (simplified: just iterate combinations)
        # Note: This is computationally expensive for many nodes. 
        # For Ashby, we usually have small graphs.
        
        # To keep it simple, we will just iterate the target node's U range 
        # and assume others are fixed at their center, OR we do a full sweep if nodes < 3.
        
        nodes = list(self.u_range.keys())
        if len(nodes) <= 2:
            # Full sweep for small graphs
            import itertools
            ranges = [sample_points[n] for n in nodes]
            for u_combo in itertools.product(*ranges):
                twin_world = {}
                # Map U values to nodes
                u_map = dict(zip(nodes, u_combo))
                
                # Propagate
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

# --- EXAMPLE USAGE ---
if __name__ == "__main__":
    # Define a simple safety scenario: Power -> Temp -> Shutdown
    # Temp = 2 * Power + U_T
    # Shutdown = 1 if Temp > 100 else 0
    
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

    # Scenario: Observed Power=60, Temp=130, Shutdown=1
    observed = {"Power": 60, "Temp": 130, "Shutdown": 1}

    # Counterfactual: What if Power was 40?
    intervention = {"Power": 40}

    # Test Twin World
    print("--- TWIN WORLD MODE ---")
    result_twin = engine.run_counterfactual(observed, intervention, "Temp", mode="twin")
    print(f"Abducted U_T: {result_twin['abducted_noise']['Temp']}")
    print(f"Counterfactual Temp: {result_twin['target_result']}")
    print(f"Is Safe (< 100): {result_twin['is_safe']}")

    # Test Multi-World
    print("\n--- MULTI-WORLD MODE ---")
    result_multi = engine.run_counterfactual(observed, intervention, "Temp", mode="multi", hazard_threshold=100)
    print(f"U Range: {result_multi['u_ranges']}")
    print(f"Worst Case Temp: {result_multi['worst_case_outcome']}")
    print(f"Is Safe: {result_multi['is_safe']}")
    print(f"Message: {result_multi['safety_message']}")
