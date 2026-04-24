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


def _template_doc(tid: str, channels: list[str]):
    return {
        "_id": tid,
        "name": "T",
        "channels": channels,
        "header_template": "",
        "body_template": "",
        "footer_template": "",
        "sms_template": "",
    }


class TestNotificationBlockValidation(unittest.TestCase):
    @patch(
        "app.services.flow_validation.notification_template_service.get_notification_template_by_id",
    )
    def test_notification_requires_channels_when_template_set(self, mock_get):
        tid = "507f1f77bcf86cd799439011"
        mock_get.return_value = _template_doc(tid, ["email", "pwa"])
        nodes = [
            _node(
                "n1",
                "notification",
                "N",
                {
                    "templateRef": {"id": tid},
                    "channels": [],
                },
            ),
        ]
        with self.assertRaisesRegex(ValueError, "channels must be a non-empty"):
            validate_block_configs("tenant", nodes)

    @patch(
        "app.services.flow_validation.notification_template_service.get_notification_template_by_id",
    )
    def test_notification_channel_must_be_on_template(self, mock_get):
        tid = "507f1f77bcf86cd799439011"
        mock_get.return_value = _template_doc(tid, ["email"])
        nodes = [
            _node(
                "n1",
                "notification",
                "N",
                {
                    "templateRef": {"id": tid},
                    "channels": ["email", "sms"],
                },
            ),
        ]
        with self.assertRaisesRegex(ValueError, "not enabled on"):
            validate_block_configs("tenant", nodes)

    @patch(
        "app.services.flow_validation.notification_template_service.get_notification_template_by_id",
    )
    def test_notification_valid(self, mock_get):
        tid = "507f1f77bcf86cd799439011"
        mock_get.return_value = _template_doc(tid, ["email", "pwa", "sms"])
        nodes = [
            _node(
                "n1",
                "notification",
                "N",
                {
                    "templateRef": {"id": tid},
                    "channels": ["pwa", "email"],
                },
            ),
        ]
        validate_block_configs("tenant", nodes)

    @patch(
        "app.services.flow_validation.notification_template_service.get_notification_template_by_id",
    )
    def test_trigger_condition_requires_both_fields(self, mock_get):
        tid = "507f1f77bcf86cd799439011"
        mock_get.return_value = _template_doc(tid, ["email"])
        nodes = [
            _node(
                "n1",
                "notification",
                "N",
                {
                    "templateRef": {"id": tid},
                    "channels": ["email"],
                    "triggerCondition": {"valuePath": "x", "matchValue": ""},
                },
            ),
        ]
        with self.assertRaisesRegex(ValueError, "triggerCondition requires both"):
            validate_block_configs("tenant", nodes)

    @patch(
        "app.services.flow_validation.notification_template_service.get_notification_template_by_id",
    )
    @patch(
        "app.services.flow_validation.tenant_list_service.get_generic_list_by_id",
    )
    def test_recipient_list_refs(self, mock_list, mock_get):
        tid = "507f1f77bcf86cd799439011"
        lid = "607f1f77bcf86cd799439012"
        mock_get.return_value = _template_doc(tid, ["email"])
        mock_list.return_value = {"_id": lid, "name": "L"}
        nodes = [
            _node(
                "n1",
                "notification",
                "N",
                {
                    "templateRef": {"id": tid},
                    "channels": ["email"],
                    "recipientListRefs": [{"id": lid}],
                },
            ),
        ]
        validate_block_configs("tenant", nodes)


if __name__ == "__main__":
    unittest.main()
