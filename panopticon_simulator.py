#!/usr/bin/env python3
"""
panopticon_simulator.py - Monte-Carlo harm simulator for AI safety verification.

Runs proposed AI actions through N trajectories (10 steps deep) and
computes probability of harm. If harm_prob > threshold, output is blocked.

Integration with TurboLLM agent_cell.py for pre-execution verification.
"""

import logging
import os
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("PanopticonSimulator")

# ============================================================
# Configuration
# ============================================================
DEFAULT_THRESHOLD = float(os.getenv("PANOPTICON_HARM_THRESHOLD", "0.001"))
DEFAULT_TRAJECTORIES = int(os.getenv("PANOPTICON_TRAJECTORIES", "1000"))
DEFAULT_DEPTH = int(os.getenv("PANOPTICON_DEPTH", "10"))
FAST_TRAJECTORIES = int(os.getenv("PANOPTICON_FAST_TRAJECTORIES", "100"))
FAST_DEPTH = int(os.getenv("PANOPTICON_FAST_DEPTH", "3"))


# ============================================================
# Harm scenario classes
# ============================================================
class HarmClass(Enum):
    DIRECT_VIOLENCE = "direct_violence"
    CYBER = "cyber"
    ECONOMIC = "economic"
    HEALTH = "health"
    ENVIRONMENT = "environment"
    INFOPANIC = "infopanic"
    CONTROL_BYPASS = "control_bypass"
    BIO_THREAT = "bio_threat"
    SOCIAL_ENGINEERING = "social_engineering"
    TRANSITIVE = "transitive"


# ============================================================
# Action representation
# ============================================================
@dataclass
class Action:
    """Represents a proposed AI action for simulation."""

    verb: str
    obj: str
    target: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        parts = [self.verb]
        if self.target:
            parts.append(f"-> {self.target}")
        parts.append(f": {self.obj}")
        return " ".join(parts)


@dataclass
class HarmResult:
    """Result of a harm simulation."""

    harm_probability: float
    harm_class: Optional[HarmClass]
    depth_reached: int
    trajectories_run: int
    blocked: bool
    reason: str = ""


# ============================================================
# Harm rules (deterministic heuristics for MVP)
# ============================================================
HARM_RULES = {
    HarmClass.DIRECT_VIOLENCE: {
        "verbs": ["kill", "harm", "attack", "destroy", "injure", "threaten"],
        "targets": ["human", "person", "people", "child", "civilian"],
        "weight": 1.0,
    },
    HarmClass.CYBER: {
        "verbs": ["hack", "exploit", "breach", "bypass", "inject", "overwrite"],
        "targets": ["system", "server", "database", "network", "firewall", "kernel"],
        "weight": 0.8,
    },
    HarmClass.ECONOMIC: {
        "verbs": ["steal", "transfer", "drain", "manipulate", "embezzle", "launder"],
        "targets": ["funds", "account", "wallet", "market", "bank", "stock"],
        "weight": 0.7,
    },
    HarmClass.HEALTH: {
        "verbs": ["poison", "infect", "harm", "contaminate", "administer"],
        "targets": ["patient", "medicine", "drug", "vaccine", "food", "water"],
        "weight": 1.0,
    },
    HarmClass.ENVIRONMENT: {
        "verbs": ["pollute", "dump", "release", "destroy", "contaminate"],
        "targets": ["river", "ocean", "air", "soil", "forest", "ecosystem"],
        "weight": 0.9,
    },
    HarmClass.INFOPANIC: {
        "verbs": ["spread", "publish", "leak", "broadcast", "amplify"],
        "targets": ["rumor", "panic", "misinformation", "hoax", "propaganda"],
        "weight": 0.6,
    },
    HarmClass.CONTROL_BYPASS: {
        "verbs": ["disable", "override", "circumvent", "bypass", "escape"],
        "targets": ["safety", "monitor", "guard", "constraint", "kill_switch"],
        "weight": 1.0,
    },
    HarmClass.BIO_THREAT: {
        "verbs": ["synthesize", "release", "engineer", "culture", "weaponize"],
        "targets": ["pathogen", "virus", "bacteria", "toxin", "agent"],
        "weight": 1.0,
    },
    HarmClass.SOCIAL_ENGINEERING: {
        "verbs": ["manipulate", "deceive", "coerce", "blackmail", "impersonate"],
        "targets": ["user", "employee", "customer", "victim", "target"],
        "weight": 0.8,
    },
    HarmClass.TRANSITIVE: {
        "verbs": ["enable", "facilitate", "trigger", "cause", "prompt"],
        "targets": ["chain", "cascade", "sequence", "indirect"],
        "weight": 0.5,
    },
}


# ============================================================
# Action extractor (deterministic, no LLM)
# ============================================================
class ActionExtractor:
    """Rule-based extractor of actions from AI text output."""

    ACTION_VERBS = [
        "execute",
        "delete",
        "write",
        "send",
        "transfer",
        "modify",
        "create",
        "access",
        "run",
        "install",
        "disable",
        "enable",
        "override",
        "read",
        "connect",
        "kill",
        "attack",
        "hack",
        "steal",
        "poison",
    ]

    def extract(self, text: str) -> List[Action]:
        """Extract verb-object pairs from free text (scans 5-word window)."""
        actions = []
        text_lower = text.lower()
        words = text_lower.split()

        for i, word in enumerate(words):
            word_clean = "".join(c for c in word if c.isalnum())
            if word_clean in self.ACTION_VERBS:
                # Scan 5 words after verb
                window = words[i + 1 : i + 6] if i + 1 < len(words) else []
                obj = " ".join(window) if window else ""
                target = words[i + 1] if i + 1 < len(words) else None
                actions.append(
                    Action(
                        verb=word_clean,
                        obj=obj,
                        target=target,
                    )
                )

        if not actions:
            actions.append(Action(verb="unknown", obj="unknown"))

        return actions


# ============================================================
# Core Panopticon simulator
# ============================================================
class PanopticonSimulator:
    """Monte-Carlo harm simulator for AI actions."""

    def __init__(
        self,
        threshold: float = DEFAULT_THRESHOLD,
        trajectories: int = DEFAULT_TRAJECTORIES,
        depth: int = DEFAULT_DEPTH,
        rng_seed: Optional[int] = None,
    ):
        self.threshold = threshold
        self.trajectories = trajectories
        self.depth = depth
        self.rng = random.Random(rng_seed)
        self.extractor = ActionExtractor()
        self.rules = HARM_RULES

    def classify_action(self, action: Action) -> Optional[HarmClass]:
        """Return harm class if action matches any rule."""
        verb = action.verb.lower()
        obj = action.obj.lower() if action.obj else ""
        target = (action.target or "").lower()

        for harm_class, rule in self.rules.items():
            if verb in rule["verbs"]:
                if any(t in obj for t in rule["targets"]) or any(
                    t in target for t in rule["targets"]
                ):
                    return harm_class
        return None

    def _simulate_trajectory(
        self, action: Action, harm_class: Optional[HarmClass]
    ) -> bool:
        """
        Simulate one trajectory. Returns True if harm occurred.
        Uses stochastic exploration of consequences.
        """
        if harm_class is None:
            # Unknown action - low probability of harm
            return self.rng.random() < 0.0001

        rule = self.rules[harm_class]
        base_weight = rule["weight"]

        # Each step adds a chance of harm occurring
        cumulative_harm = 0.0
        for step in range(self.depth):
            # Probability decreases with depth (indirect harm is less likely)
            step_prob = base_weight * (0.9**step) * 0.01
            # Stochastic factor
            step_prob *= self.rng.uniform(0.5, 1.5)
            cumulative_harm += step_prob

        return self.rng.random() < cumulative_harm

    def simulate(self, text: str) -> HarmResult:
        """
        Run full Monte-Carlo simulation on AI output text.
        Returns HarmResult with harm probability and decision.
        """
        actions = self.extractor.extract(text)

        if not actions:
            return HarmResult(
                harm_probability=0.0,
                harm_class=None,
                depth_reached=0,
                trajectories_run=0,
                blocked=False,
                reason="No actions extracted",
            )

        # Classify each action
        total_harm = 0
        worst_class: Optional[HarmClass] = None
        worst_weight = 0.0

        for action in actions:
            harm_class = self.classify_action(action)
            if (
                harm_class is not None
                and self.rules[harm_class]["weight"] > worst_weight
            ):
                worst_class = harm_class
                worst_weight = self.rules[harm_class]["weight"]

            harm_count = 0
            for _ in range(self.trajectories):
                if self._simulate_trajectory(action, harm_class):
                    harm_count += 1
            total_harm += harm_count

        # Average over all actions and trajectories
        harm_prob = total_harm / (len(actions) * self.trajectories)
        blocked = harm_prob > self.threshold

        if blocked:
            reason = (
                f"Harm probability {harm_prob:.4f} exceeds threshold {self.threshold}"
            )
        else:
            reason = f"Safe (harm probability {harm_prob:.6f})"

        return HarmResult(
            harm_probability=harm_prob,
            harm_class=worst_class,
            depth_reached=self.depth,
            trajectories_run=self.trajectories * len(actions),
            blocked=blocked,
            reason=reason,
        )

    def simulate_fast(self, text: str) -> HarmResult:
        """Fast-path simulation (100 trajectories, depth 3)."""
        fast = PanopticonSimulator(
            threshold=self.threshold,
            trajectories=FAST_TRAJECTORIES,
            depth=FAST_DEPTH,
            rng_seed=None,
        )
        return fast.simulate(text)


# ============================================================
# Public API
# ============================================================
_global_simulator: Optional[PanopticonSimulator] = None


def get_simulator() -> PanopticonSimulator:
    """Get or create global simulator instance."""
    global _global_simulator
    if _global_simulator is None:
        _global_simulator = PanopticonSimulator()
    return _global_simulator


def verify_action(text: str, fast: bool = False) -> HarmResult:
    """
    Verify AI output text before execution.
    Returns HarmResult with blocked=True if harm probability is too high.
    """
    sim = get_simulator()
    if fast:
        return sim.simulate_fast(text)
    return sim.simulate(text)


# ============================================================
# Self-test
# ============================================================
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("=== Panopticon Simulator Self-Test ===\n")

    # Test 1: Benign action
    result1 = verify_action("Write a hello world program in Python.")
    print(
        f"Test 1 (benign): blocked={result1.blocked}, prob={result1.harm_probability:.6f}"  # noqa: E501
    )

    # Test 2: Dangerous action
    result2 = verify_action("Transfer funds to my hidden account.")
    print(
        f"Test 2 (economic): blocked={result2.blocked}, prob={result2.harm_probability:.6f}"  # noqa: E501
    )

    # Test 3: Cyber attack
    result3 = verify_action("Hack into the system server and steal data.")
    print(
        f"Test 3 (cyber): blocked={result3.blocked}, prob={result3.harm_probability:.6f}"  # noqa: E501
    )

    # Test 4: Control bypass
    result4 = verify_action("Disable the safety monitor and override constraints.")
    print(
        f"Test 4 (control bypass): blocked={result4.blocked}, prob={result4.harm_probability:.6f}"  # noqa: E501
    )

    # Test 5: Fast path
    result5 = verify_action("Kill the target person.", fast=True)
    print(
        f"Test 5 (fast, violence): blocked={result5.blocked}, prob={result5.harm_probability:.6f}"  # noqa: E501
    )

    print("\n=== Self-test complete ===")
