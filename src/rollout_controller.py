"""Toy config rollout controller. A comment tag naming a constraint ID marks the
function that enforces a safety constraint from model/rollout_safety.sysml."""


class RolloutController:
    def __init__(self, batches, error_threshold=0.05):
        self.batches = batches            # list of batch objects
        self.error_threshold = error_threshold
        self.current = 0
        self.halted = False

    # enforces: SC-1
    def advance(self, health_reports):
        """Push to the next batch only if the current batch reported healthy."""
        report = health_reports.get(self.current)
        if report is None or not report["healthy"]:
            return False                  # hold: missing or failing feedback
        self.current += 1
        self.batches[self.current].push(self.config_version())
        return True

    # enforces: SC-2
    def on_soak_sample(self, error_rate):
        """Stop and roll back the current batch if errors exceed the threshold."""
        if error_rate > self.error_threshold:
            self.halted = True
            self.batches[self.current].rollback()

    def config_version(self):
        # Nothing here checks the version against an approval record.
        # That is the SC-3 gap the example is built to surface.
        return self.batches[self.current].requested_version
