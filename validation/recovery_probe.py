"""Reproduce an interrupted mutable feedback on the published reference."""
import json
from unittest.mock import patch

from first_piece.cooperative import CooperativeService
from first_piece.plastic_revision import PlasticRevisionLearner
from first_piece.tests.test_readiness import feed,trace
from first_piece.integration_probe import agent_proposal,observed_receipt

service = CooperativeService()
prediction = feed(service,trace(0))
request = service.register_action(agent_proposal(prediction,0),executor_id="review:executor")
receipt = observed_receipt(request,1)
service.begin_receipt(receipt)
real = PlasticRevisionLearner.learn

def interrupted(core,action,outcome):
    real(core,action,outcome)
    raise RuntimeError("interrupted after mutable feedback")

with patch("first_piece.plastic_revision.PlasticRevisionLearner.learn",autospec=True,side_effect=interrupted):
    try:
        service.advance(1)
    except RuntimeError:
        pass
error = None
try:
    CooperativeService.restore(json.loads(json.dumps(service.checkpoint())))
except Exception as failure:
    error = str(failure)
print("RECOVERY_BEFORE_JSON="+json.dumps({
    "phase":service.work_status()["phase"],
    "committed_steps":service._adapter._learner.steps,
    "staged_steps":service._work.core.steps,
    "checkpoint_restore_error":error,
    "pending_action_retained":service._adapter._pending == request}))
