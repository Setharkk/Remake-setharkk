"""Wire semantics stay independent of a laboratory vocabulary."""
import copy
import unittest

from setharkk import contracts as wire


def generic_prediction():
    return {
        "schema_version": 1, "prediction_id": "prediction:disk",
        "model_id": "model:future", "model_revision": 72,
        "event_id": "event:disk", "stream_id": "stream:pc",
        "sequence": 203, "context_id": "context:workspace",
        "forecasts": [
            {"candidate_id": name, "action_name": "filesystem.write",
             "arguments": {"path": path, "content": "hello"},
             "measure": "written_bytes", "unit": "bytes",
             "distribution": {"kind": "discrete", "parameters": {"values": [0, 5], "p": [.1, .9]}}}
            for name, path in (("candidate:one", "one.txt"), ("candidate:two", "two.txt"))
        ],
    }


class ContractTests(unittest.TestCase):
    def test_parameterized_actions_and_other_distributions_are_not_lab_binary(self):
        data = generic_prediction()
        validated = wire.prediction(data)
        self.assertEqual(validated, data)
        self.assertEqual(validated["forecasts"][0]["action_name"],
                         validated["forecasts"][1]["action_name"])
        validated["forecasts"][0]["arguments"]["path"] = "changed"
        self.assertEqual(data["forecasts"][0]["arguments"]["path"], "one.txt")
        event = {"schema_version": 1, "event_id": "disk:1", "stream_id": "pc:main",
                 "sequence": 0, "context_id": "workspace:abc", "source_id": "file.sensor",
                 "kind": "filesystem.changed", "payload": {"size": 100, "path": "one.txt"}}
        self.assertEqual(wire.observation(event), event)

    def test_invalid_wire_values_and_versions_rejected(self):
        for value in (float("inf"), float("nan"), b"binary", (1, 2), 2**54):
            with self.subTest(value=repr(value)):
                event = {"schema_version": 1, "event_id": "e", "stream_id": "s",
                         "sequence": 0, "context_id": "c", "source_id": "sensor",
                         "kind": "test", "payload": {"value": value}}
                with self.assertRaises(ValueError):
                    wire.observation(event)
        cyclic = {}
        cyclic["self"] = cyclic
        with self.assertRaises(ValueError):
            wire.json_value(cyclic)
        for change in ({"schema_version": True}, {"schema_version": 2},
                       {"sequence": True}, {"event_id": ""}, {"extra": "unexpected"}):
            data = generic_prediction()
            data.update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                wire.prediction(data)

    def test_candidate_identity_not_operation_name_is_unique(self):
        data = generic_prediction()
        data["forecasts"][1]["candidate_id"] = data["forecasts"][0]["candidate_id"]
        with self.assertRaises(ValueError):
            wire.prediction(data)

    def test_bernoulli_parameters_validated(self):
        for p in (True, -.1, 1.1, float("nan")):
            data = generic_prediction()
            data["forecasts"][0]["distribution"] = {"kind": "bernoulli", "parameters": {"p": p}}
            with self.subTest(p=p), self.assertRaises(ValueError):
                wire.prediction(data)

    def test_technical_failure_is_not_a_measured_zero(self):
        message = {"schema_version": 1, "receipt_id": "receipt:1",
                   "request_id": "request:1", "source_id": "executor:1",
                   "status": "failed", "outcome": None}
        self.assertEqual(wire.receipt(message), message)
        invalid = copy.deepcopy(message)
        invalid["outcome"] = {"measure": "success", "unit": "binary", "value": 0}
        with self.assertRaises(ValueError):
            wire.receipt(invalid)


if __name__ == "__main__":
    unittest.main()
