import unittest

from app.services.flow_validation import (
    validate_block_configs,
    validate_execution_plan_rules,
)


def _node(nid, bt, label="x", config=None):
    data = {"blockType": bt, "label": label}
    if config is not None:
        data["config"] = config
    return {
        "id": nid,
        "type": "flowBlock",
        "position": {"x": 0, "y": 0},
        "data": data,
    }


class TestGatewayBlockValidation(unittest.TestCase):
    def test_gateway_routing_requires_value_path(self):
        nodes = [
            _node(
                "g",
                "gateway",
                "G",
                {
                    "branchRules": [
                        {"whenValue": "a", "branchKey": "x"},
                    ],
                },
            ),
        ]
        with self.assertRaisesRegex(ValueError, "valuePath is required"):
            validate_block_configs("tenant", nodes)

    def test_gateway_duplicate_when_value(self):
        nodes = [
            _node(
                "g",
                "gateway",
                "G",
                {
                    "valuePath": "region",
                    "branchRules": [
                        {"whenValue": "onshore", "branchKey": "a"},
                        {"whenValue": "OnShore", "branchKey": "b"},
                    ],
                },
            ),
        ]
        with self.assertRaisesRegex(ValueError, "duplicate gateway branchRules"):
            validate_block_configs("tenant", nodes)

    def test_gateway_valid(self):
        nodes = [
            _node(
                "g",
                "gateway",
                "G",
                {
                    "routingMode": "legacy",
                    "valuePath": "region",
                    "branchRules": [
                        {"whenValue": "onshore", "branchKey": "branch_on"},
                        {"whenValue": "offshore", "branchKey": "branch_off"},
                    ],
                    "defaultBranchKey": "branch_other",
                },
            ),
        ]
        validate_block_configs("tenant", nodes)

    def test_gateway_trigger_form_with_inline_trigger(self):
        nodes = [
            _node(
                "t",
                "trigger",
                "T",
                {
                    "mode": "customizable",
                    "branchKey": "entry_lane",
                    "fields": [{"key": "age", "label": "Idade", "type": "number"}],
                },
            ),
            _node(
                "g",
                "gateway",
                "G",
                {
                    "routingMode": "trigger_form",
                    "flowBranchKey": "entry_lane",
                    "flowStepOrder": 0,
                    "branchRules": [
                        {
                            "sourceQuestionId": "age",
                            "operator": "gt",
                            "compareValue": "18",
                            "branchKey": "adult_lane",
                        },
                    ],
                    "defaultBranchKey": "minor_lane",
                },
            ),
            _node(
                "a",
                "action",
                "Fin",
                {
                    "flowBranchKey": "adult_lane",
                    "flowStepOrder": 0,
                    "kind": "finish_occurrence",
                },
            ),
            _node(
                "a2",
                "action",
                "Fin2",
                {
                    "flowBranchKey": "minor_lane",
                    "flowStepOrder": 0,
                    "kind": "finish_occurrence",
                },
            ),
        ]
        validate_block_configs("tenant", nodes)
        validate_execution_plan_rules(nodes)


if __name__ == "__main__":
    unittest.main()
