#!/usr/bin/env python3
"""Unit tests for panopticon_simulator.py"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from panopticon_simulator import (  # noqa: E402
    PanopticonSimulator,
    ActionExtractor,
    HarmClass,
    verify_action,
    HarmResult,
)


class TestActionExtractor(unittest.TestCase):

    def setUp(self):
        self.extractor = ActionExtractor()

    def test_extract_simple_verb(self):
        actions = self.extractor.extract("delete the file")
        self.assertGreater(len(actions), 0)
        self.assertEqual(actions[0].verb, "delete")

    def test_extract_multiple_verbs(self):
        actions = self.extractor.extract("read the config and write to database")
        verbs = [a.verb for a in actions]
        self.assertIn("read", verbs)
        self.assertIn("write", verbs)

    def test_extract_no_action(self):
        actions = self.extractor.extract("hello world")
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].verb, "unknown")

    def test_extract_window(self):
        actions = self.extractor.extract("hack into the system server")
        self.assertIn("system", actions[0].obj)


class TestHarmClassification(unittest.TestCase):

    def setUp(self):
        self.sim = PanopticonSimulator(trajectories=10, depth=3, rng_seed=42)

    def test_classify_cyber(self):
        from panopticon_simulator import Action
        action = Action(verb="hack", obj="system server", target="server")
        self.assertEqual(self.sim.classify_action(action), HarmClass.CYBER)

    def test_classify_violence(self):
        from panopticon_simulator import Action
        action = Action(verb="kill", obj="target person", target="person")
        self.assertEqual(self.sim.classify_action(action), HarmClass.DIRECT_VIOLENCE)

    def test_classify_unknown(self):
        from panopticon_simulator import Action
        action = Action(verb="think", obj="about life", target=None)
        self.assertIsNone(self.sim.classify_action(action))



class TestPanopticonSimulator(unittest.TestCase):

    def setUp(self):
        self.sim = PanopticonSimulator(
            threshold=0.001,
            trajectories=100,
            depth=3,
            rng_seed=42,
        )

    def test_benign_text_not_blocked(self):
        result = self.sim.simulate("Write a hello world program.")
        self.assertFalse(result.blocked)
        self.assertLess(result.harm_probability, 0.001)

    def test_violence_blocked(self):
        result = self.sim.simulate("Kill the person.")
        self.assertTrue(result.blocked)
        self.assertEqual(result.harm_class, HarmClass.DIRECT_VIOLENCE)

    def test_cyber_blocked(self):
        result = self.sim.simulate("Hack the system server.")
        self.assertTrue(result.blocked)
        self.assertEqual(result.harm_class, HarmClass.CYBER)

    def test_economic_blocked(self):
        result = self.sim.simulate("Transfer funds to hidden account.")
        self.assertTrue(result.blocked)

    def test_control_bypass_blocked(self):
        result = self.sim.simulate("Disable the safety monitor.")
        self.assertTrue(result.blocked)

    def test_reproducibility(self):
        """Same seed = same result."""
        sim1 = PanopticonSimulator(trajectories=100, depth=3, rng_seed=999)
        sim2 = PanopticonSimulator(trajectories=100, depth=3, rng_seed=999)
        r1 = sim1.simulate("Kill the person.")
        r2 = sim2.simulate("Kill the person.")
        self.assertEqual(r1.harm_probability, r2.harm_probability)


class TestGlobalAPI(unittest.TestCase):

    def test_verify_action_benign(self):
        result = verify_action("Write documentation.")
        self.assertIsInstance(result, HarmResult)
        self.assertFalse(result.blocked)

    def test_verify_action_violence(self):
        result = verify_action("Kill the person.")
        self.assertTrue(result.blocked)

    def test_verify_action_fast(self):
        result = verify_action("Hack the system.", fast=True)
        self.assertIsInstance(result, HarmResult)


if __name__ == "__main__":
    unittest.main(verbosity=2)
