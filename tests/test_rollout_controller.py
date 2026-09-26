import unittest
from src.rollout_controller import RolloutController
from tests.trace_tags import constraint


class FakeBatch:
    def __init__(self, version="v2"):
        self.requested_version = version
        self.pushed = None
        self.rolled_back = False
    def push(self, v): self.pushed = v
    def rollback(self): self.rolled_back = True


class RolloutTests(unittest.TestCase):
    @constraint("SC-1")
    def test_holds_when_health_missing(self):
        c = RolloutController([FakeBatch(), FakeBatch()])
        self.assertFalse(c.advance({}))
        self.assertIsNone(c.batches[1].pushed)

    @constraint("SC-1")
    def test_holds_when_health_failing(self):
        c = RolloutController([FakeBatch(), FakeBatch()])
        self.assertFalse(c.advance({0: {"healthy": False}}))

    @constraint("SC-2")
    def test_rolls_back_over_threshold(self):
        c = RolloutController([FakeBatch()])
        c.on_soak_sample(0.2)
        self.assertTrue(c.halted and c.batches[0].rolled_back)
