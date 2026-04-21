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


class TestInteractionAuthValidation(unittest.TestCase):
    def test_trigger_any_by_default(self):
        nodes = [_node("t", "trigger", "T", {"mode": "preset", "branchKey": "bk"})]
        validate_block_configs("tenant", nodes)

    def test_data_any_by_default(self):
        nodes = [_node("d", "data", "D", {})]
        validate_block_configs("tenant", nodes)

    def test_both_refs_rejected(self):
        uid = "507f1f77bcf86cd799439011"
        tid = "507f1f77bcf86cd799439012"
        nodes = [
            _node(
                "t",
                "trigger",
                "T",
                {
                    "mode": "preset",
                    "branchKey": "bk",
                    "allowedUserRef": {"id": uid},
                    "allowedTeamRef": {"id": tid},
                },
            ),
        ]
        with self.assertRaisesRegex(
            ValueError,
            "mutually exclusive",
        ):
            validate_block_configs("tenant", nodes)

    @patch("app.services.flow_validation.user_service.get_user_by_id")
    def test_trigger_allowed_user_resolves(self, mock_user):
        uid = "507f1f77bcf86cd799439011"
        mock_user.return_value = {"_id": uid}
        nodes = [
            _node(
                "t",
                "trigger",
                "T",
                {
                    "mode": "preset",
                    "branchKey": "bk",
                    "allowedUserRef": {"id": uid, "snapshot": {"name": "A"}},
                },
            ),
        ]
        validate_block_configs("tenant", nodes)
        mock_user.assert_called_once_with("tenant", uid)

    @patch("app.services.flow_validation.team_service.get_team_by_id")
    def test_data_allowed_team_resolves(self, mock_team):
        tid = "507f1f77bcf86cd799439012"
        mock_team.return_value = {"_id": tid}
        nodes = [
            _node(
                "d",
                "data",
                "D",
                {"allowedTeamRef": {"id": tid}},
            ),
        ]
        validate_block_configs("tenant", nodes)
        mock_team.assert_called_once_with("tenant", tid)


if __name__ == "__main__":
    unittest.main()
