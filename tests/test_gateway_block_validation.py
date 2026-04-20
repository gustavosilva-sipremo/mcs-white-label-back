import unittest

from app.services.flow_validation import validate_block_configs


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


if __name__ == "__main__":
    unittest.main()
