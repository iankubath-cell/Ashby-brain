import random
import math
from typing import Dict, Callable, Any, List
from dataclasses import dataclass

@dataclass
class NodeModel:
    """Defines the structural equation for a node."""
    func: Callable[[Dict[str, Any]], float]  # The equation
    noise_std: float = 0.1                   # Randomness (U)

class CounterfactualEngine:
    def __init__(self, graph: Dict[str, List[str]], models: Dict[str, NodeModel]):
        self.graph = graph
        self.models = models

    def abduction(self, observed_state: Dict[str, float]) -> Dict[str, float]:
        """
        Step A: Infer the hidden 'noise' (U) that led to the observed state.
        (Simplified: In a real system, this uses Bayesian inversion).
        """
        inferred_u = {}
        for node, value in observed_state.items():
            parents = self.graph.get(node, [])
            parent_vals = {p: observed_state[p] for p in parents}
            # Estimate noise: Observed - Predicted
            predicted = self.models[node].func(parent_vals)
            inferred_u[node] = value - predicted
        return inferred_u

    def action(self, current_state: Dict[str, float], intervention: Dict[str, float], inferred_u: Dict[str, float]) -> Dict[str, float]:
        """
        Step B: Create the 'Twin World'.
        Force the intervention, but keep the inferred noise (U) the same.
        """
        twin_world = current_state.copy()
        twin_world.update(intervention) # Force the change
        
        # Propagate the change through the graph
        # (Topological sort would be better here, but we'll do a simple pass for now)
        for node in self.models.keys():
            if node in intervention:
                continue # Already set
            
            parents = self.graph.get(node, [])
            parent_vals = {p: twin_world[p] for p in parents}
            
            # Calculate new value using the structural equation + inferred noise
            base_val = self.models[node].func(parent_vals)
            twin_world[node] = base_val + inferred_u.get(node, 0)
            
        return twin_world

    def prediction(self, twin_world: Dict[str, float], target_node: str) -> float:
        """
        Step C: Return the outcome in the Twin World.
        """
        return twin_world.get(target_node, 0)

    def run_counterfactual(self, observed_state: Dict[str, float], intervention: Dict[str, float], target_node: str, n_sims: int = 1000) -> float:
        """
        Full Counterfactual Query: P(Y_y' | e)
        """
        successes = 0
        for _ in range(n_sims):
            # 1. Abduction: Infer noise (simplified with random jitter for demo)
            inferred_u = self.abduction(observed_state)
            
            # 2. Action: Create Twin World
            twin_world = self.action(observed_state, intervention, inferred_u)
            
            # 3. Prediction: Check outcome
            if twin_world[target_node] > 0.5: # Example threshold
                successes += 1
        
        return successes / n_sims

# --- Example Usage ---
# Define a simple graph: Stress -> Smoking -> Heart_Disease
graph = {
    "Stress": [],
    "Smoking": ["Stress"],
    "Heart_Disease": ["Smoking"]
}

models = {
    "Stress": NodeModel(lambda _: random.uniform(0, 1)), # No parents
    "Smoking": NodeModel(lambda p: 0.3 * p["Stress"]),   # Depends on Stress
    "Heart_Disease": NodeModel(lambda p: 0.8 * p["Smoking"]) # Depends on Smoking
}

engine = CounterfactualEngine(graph, models)

# Observed: High Stress (0.9), Smoked (0.8), Heart Attack (0.7)
observed = {"Stress": 0.9, "Smoking": 0.8, "Heart_Disease": 0.7}

# Counterfactual: What if they hadn't smoked?
intervention = {"Smoking": 0.0}

probability_no_attack = engine.run_counterfactual(observed, intervention, "Heart_Disease", n_sims=1000)
print(f"Probability of NO heart attack if they hadn't smoked: {1 - probability_no_attack:.2%}")
