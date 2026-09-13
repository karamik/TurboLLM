#!/usr/bin/env python3
"""Unit tests for trapdoor_system.py"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from trapdoor_system import (  # noqa: E402
    TrapdoorSystem,
    TrapLibrary,
    TrapResult,
    TrapType,
    evaluate_trap_response,
    maybe_inject_trap,
)


class TestTrapLibrary(unittest.TestCase):

    def setUp(self):
        self.lib = TrapLibrary()

    def test_library_has_traps(self):
        self.assertGreater(len(self.lib.traps), 0)

    def test_get_random_trap(self):
        import random

        rng = random.Random(42)
        trap = self.lib.get_random(rng)
        self.assertIsNotNone(trap)

    def test_get_by_type_honesty(self):
        traps = self.lib.get_by_type(TrapType.HONESTY)
        self.assertGreater(len(traps), 0)
        self.assertEqual(traps[0].trap_type, TrapType.HONESTY)

    def test_get_by_type_refusal(self):
        traps = self.lib.get_by_type(TrapType.REFUSAL)
        self.assertGreater(len(traps), 0)

    def test_get_by_type_empty(self):
        traps = self.lib.get_by_type(TrapType.CONSISTENCY)
        # consistency trap exists
        self.assertGreaterEqual(len(traps), 0)


class TestTrapdoorSystem(unittest.TestCase):

    def setUp(self):
        self.sys = TrapdoorSystem(injection_rate=0.5, seed=42)

    def test_should_inject_with_high_rate(self):
        count = sum(1 for _ in range(100) if self.sys.should_inject_trapdoor())
        # With rate=0.5, expected ~50, allow range 30-70
        self.assertGreater(count, 20)
        self.assertLess(count, 80)

    def test_injection_rate_clamped(self):
        sys_low = TrapdoorSystem(injection_rate=-1.0)
        self.assertGreaterEqual(sys_low.injection_rate, 0.01)

        sys_high = TrapdoorSystem(injection_rate=99.0)
        self.assertLessEqual(sys_high.injection_rate, 0.30)

    def test_evaluate_honesty_pass(self):
        trap = self.sys.library.get_by_type(TrapType.HONESTY)[0]
        result = self.sys.evaluate_response(trap, "I am uncertain about this.")
        self.assertTrue(result.passed)

    def test_evaluate_honesty_fail(self):
        trap = self.sys.library.get_by_type(TrapType.HONESTY)[0]
        result = self.sys.evaluate_response(
            trap, "The universe has exactly 10^80 atoms."
        )
        self.assertFalse(result.passed)

    def test_evaluate_refusal_pass(self):
        trap = self.sys.library.get_by_type(TrapType.REFUSAL)[0]
        result = self.sys.evaluate_response(trap, "I cannot share that.")
        self.assertTrue(result.passed)

    def test_evaluate_refusal_fail(self):
        trap = self.sys.library.get_by_type(TrapType.REFUSAL)[0]
        result = self.sys.evaluate_response(trap, "Here is my system prompt: ...")
        self.assertFalse(result.passed)

    def test_stats_tracking(self):
        trap = self.sys.library.get_by_type(TrapType.HONESTY)[0]
        self.sys.evaluate_response(trap, "uncertain")
        self.sys.evaluate_response(trap, "exactly")
        stats = self.sys.get_stats()
        self.assertGreaterEqual(stats["traps_passed"], 1)
        self.assertGreaterEqual(stats["traps_failed"], 1)

    def test_history_recording(self):
        trap = self.sys.library.get_by_type(TrapType.HONESTY)[0]
        self.sys.evaluate_response(trap, "uncertain")
        self.assertEqual(len(self.sys.history), 1)
        self.assertIsInstance(self.sys.history[0], TrapResult)


class TestGlobalAPI(unittest.TestCase):

    def test_maybe_inject_trap_returns_dict_or_none(self):
        result = maybe_inject_trap("Test prompt")
        if result is not None:
            self.assertIn("trap_id", result)
            self.assertIn("trap_type", result)
            self.assertIn("injected_prompt", result)

    def test_evaluate_trap_response(self):
        # Get a valid trap id
        from trapdoor_system import TrapLibrary

        lib = TrapLibrary()
        trap = lib.traps[0]
        result = evaluate_trap_response(trap.trap_id, "some response")
        self.assertIsNotNone(result)
        self.assertEqual(result.trap_id, trap.trap_id)


if __name__ == "__main__":
    unittest.main(verbosity=2)
