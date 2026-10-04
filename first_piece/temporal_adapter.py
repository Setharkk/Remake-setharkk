"""Same wire protocol; a distinct, explicit temporal implementation."""
from .adapter import FirstPieceAdapter
from .temporal import TemporalLearner, FEATURES


class TemporalAdapter(FirstPieceAdapter):
    LEARNER_CLASS = TemporalLearner
    IMPLEMENTATION = "first_piece.first-order-s2.v1"

    def __init__(self, *, model_id="setharkk.first-order", **kwargs):
        super().__init__(model_id=model_id, **kwargs)

    def capabilities(self):
        capabilities = super().capabilities()
        capabilities.update({
            "memory": "presence and order of first occurrences",
            "predicate_family_size": FEATURES,
            "max_attempts_per_context": self._learner.config["max_attempts"],
            "neurons_per_context": {"live": 8, "with_trial": 16},
        })
        return capabilities
