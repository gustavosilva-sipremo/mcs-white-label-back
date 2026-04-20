import unittest
from unittest.mock import patch

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


class TestTriggerBlockValidation(unittest.TestCase):
    def test_trigger_requires_branch_key(self):
        nodes = [_node("t", "trigger", "T", {"mode": "preset", "branchKey": ""})]
        with self.assertRaisesRegex(ValueError, "branchKey is required"):
            validate_block_configs("tenant", nodes)

    def test_trigger_branch_key_charset(self):
        nodes = [
            _node("t", "trigger", "T", {"mode": "preset", "branchKey": "bad space"}),
        ]
        with self.assertRaisesRegex(ValueError, "branchKey may contain only"):
            validate_block_configs("tenant", nodes)

    def test_customizable_requires_fields(self):
        nodes = [
            _node(
                "t",
                "trigger",
                "T",
                {"mode": "customizable", "branchKey": "b1", "fields": []},
            ),
        ]
        with self.assertRaisesRegex(ValueError, "at least one field"):
            validate_block_configs("tenant", nodes)

    def test_customizable_field_key_snake(self):
        nodes = [
            _node(
                "t",
                "trigger",
                "T",
                {
                    "mode": "customizable",
                    "branchKey": "b1",
                    "fields": [{"key": "0bad", "label": "X"}],
                },
            ),
        ]
        with self.assertRaisesRegex(ValueError, "fields\\[0\\]\\.key"):
            validate_block_configs("tenant", nodes)

    def test_preset_valid(self):
        nodes = [
            _node("t", "trigger", "T", {"mode": "preset", "branchKey": "main"}),
        ]
        validate_block_configs("tenant", nodes)

    def test_customizable_valid(self):
        nodes = [
            _node(
                "t",
                "trigger",
                "T",
                {
                    "mode": "customizable",
                    "branchKey": "fauna",
                    "fields": [
                        {"key": "local", "label": "Local", "type": "text"},
                    ],
                },
            ),
        ]
        validate_block_configs("tenant", nodes)

    @patch(
        "app.services.flow_validation.questionnaire_service.get_questionnaire_by_id",
    )
    def test_customizable_questionnaire_id_without_fields(self, mock_get):
        qid = "507f1f77bcf86cd799439011"
        mock_get.return_value = {"_id": qid}
        nodes = [
            _node(
                "t",
                "trigger",
                "T",
                {"mode": "customizable", "branchKey": qid},
            ),
        ]
        validate_block_configs("tenant", nodes)
        mock_get.assert_called_with("tenant", qid)

    def test_duplicate_trigger_branch_key(self):
        nodes = [
            _node("t1", "trigger", "T1", {"mode": "preset", "branchKey": "dup"}),
            _node("t2", "trigger", "T2", {"mode": "preset", "branchKey": "dup"}),
        ]
        with self.assertRaisesRegex(ValueError, "Duplicate trigger branchKey"):
            validate_block_configs("tenant", nodes)

    @patch(
        "app.services.flow_validation.questionnaire_service.get_questionnaire_by_id",
    )
    def test_trigger_object_id_branch_resolves_questionnaire(self, mock_get):
        qid = "507f1f77bcf86cd799439011"
        mock_get.return_value = {"_id": qid}
        nodes = [_node("t", "trigger", "T", {"mode": "preset", "branchKey": qid})]
        validate_block_configs("tenant", nodes)
        mock_get.assert_called_once_with("tenant", qid)

    @patch(
        "app.services.flow_validation.questionnaire_service.get_questionnaire_by_id",
    )
    def test_trigger_object_id_branch_missing_questionnaire(self, mock_get):
        qid = "507f1f77bcf86cd799439011"
        mock_get.side_effect = ValueError("Questionnaire not found")
        nodes = [_node("t", "trigger", "T", {"mode": "preset", "branchKey": qid})]
        with self.assertRaisesRegex(ValueError, "Questionnaire not found"):
            validate_block_configs("tenant", nodes)


if __name__ == "__main__":
    unittest.main()
