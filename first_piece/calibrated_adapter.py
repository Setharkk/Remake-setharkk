"""Calibrated probability forecasts through the existing ordered wire ABI."""
from .calibrated import CalibratedLearner, MIN_RECORDS
from .consolidated_adapter import ConsolidatedAdapter


class CalibratedAdapter(ConsolidatedAdapter):
    LEARNER_CLASS = CalibratedLearner
    IMPLEMENTATION = CalibratedLearner.IMPLEMENTATION

    @classmethod
    def from_consolidated_checkpoint(cls, snapshot):
        old = ConsolidatedAdapter.restore(snapshot)
        data = old.checkpoint()
        data["implementation"] = cls.IMPLEMENTATION
        data["learner"] = CalibratedLearner.from_consolidated_checkpoint(data["learner"])
        return cls.restore(data).checkpoint()

    @classmethod
    def from_renewable_checkpoint(cls, snapshot):
        return cls.from_consolidated_checkpoint(
            ConsolidatedAdapter.from_renewable_checkpoint(snapshot))

    @classmethod
    def from_finite_checkpoint(cls, snapshot):
        return cls.from_consolidated_checkpoint(
            ConsolidatedAdapter.from_finite_checkpoint(snapshot))

    def capabilities(self):
        with self._lock:
            result = super().capabilities()
            result.update(
                search_mode="calibrated",
                probability_calibration="rolling-mixture-v1",
                calibration_window=self._learner._window(),
                calibration_min_records=MIN_RECORDS,
                calibration_uses="recent_chosen_action_outcomes",
                validation_reference="raw_protected_competence")
            return result
