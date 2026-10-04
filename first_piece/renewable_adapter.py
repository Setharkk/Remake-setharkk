"""Renewable search using the existing observation/action/receipt contract."""
from .renewable import RenewableLearner
from .shared_adapter import SharedAdapter


class RenewableAdapter(SharedAdapter):
    LEARNER_CLASS = RenewableLearner
    IMPLEMENTATION = RenewableLearner.IMPLEMENTATION

    @classmethod
    def from_finite_checkpoint(cls, snapshot):
        finite = SharedAdapter.restore(snapshot)
        data = finite.checkpoint()
        data["implementation"] = cls.IMPLEMENTATION
        data["learner"] = RenewableLearner.from_finite_checkpoint(data["learner"])
        return cls.restore(data).checkpoint()

    @classmethod
    def migrate_checkpoint_v1(cls, snapshot):
        raise ValueError("Migrate with SharedAdapter.migrate_checkpoint_v1, then from_finite_checkpoint")

    def capabilities(self):
        with self._lock:
            result = super().capabilities()
            result.update({"search_mode": "renewable",
                           "attempts_per_block": self._learner.config["max_attempts"],
                           "lifetime_alpha_upper_bound": self._learner.metrics()["lifetime_alpha_upper_bound"]})
            return result
