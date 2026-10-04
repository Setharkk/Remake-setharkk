"""Protected competence through the same ordered observation/action wire ABI."""
from .consolidated import ConsolidatedLearner
from .renewable_adapter import RenewableAdapter


class ConsolidatedAdapter(RenewableAdapter):
    LEARNER_CLASS = ConsolidatedLearner
    IMPLEMENTATION = ConsolidatedLearner.IMPLEMENTATION

    @classmethod
    def from_renewable_checkpoint(cls, snapshot):
        old = RenewableAdapter.restore(snapshot)
        data = old.checkpoint()
        data["implementation"] = cls.IMPLEMENTATION
        data["learner"] = ConsolidatedLearner.from_renewable_checkpoint(data["learner"])
        return cls.restore(data).checkpoint()

    @classmethod
    def from_finite_checkpoint(cls, snapshot):
        return cls.from_renewable_checkpoint(RenewableAdapter.from_finite_checkpoint(snapshot))

    @classmethod
    def migrate_checkpoint_v1(cls, snapshot):
        raise ValueError("Migrate with SharedAdapter, then use from_finite_checkpoint")

    def capabilities(self):
        with self._lock:
            result = super().capabilities()
            result.update(search_mode="consolidated", protected_competence=True,
                          validation_horizons=list(self._learner._horizons()),
                          max_protected_banks=1)
            return result
