import unittest
from unittest.mock import patch

from app.services.notification_dispatch_service import dispatch_template_test


class _FakeInsertResult:
    inserted_id = "507f1f77bcf86cd799439011"


class _FakeCollection:
    def insert_one(self, _payload):
        return _FakeInsertResult()


class _FakeDb:
    def __getitem__(self, _name):
        return _FakeCollection()


class TestNotificationDispatchService(unittest.TestCase):
    @patch("app.services.notification_dispatch_service.get_tenant_db")
    @patch("app.services.notification_dispatch_service.preview_notification_templates")
    @patch("app.services.notification_dispatch_service.get_notification_template_by_id")
    @patch("app.services.notification_dispatch_service.send_email")
    def test_dispatch_email_success_and_missing_contact(
        self,
        mock_send_email,
        mock_get_template,
        mock_preview,
        mock_get_db,
    ):
        mock_get_db.return_value = _FakeDb()
        mock_get_template.return_value = {
            "_id": "t1",
            "name": "Template",
            "channels": ["email"],
            "channel_templates": {},
        }
        mock_preview.return_value = {
            "email_html": "<p>ok</p>",
            "main_plain": "ok",
            "sms_text": "",
            "whatsapp_text": "",
            "pwa": {"title": "x", "body": "y"},
        }
        mock_send_email.return_value = {
            "status": "sent",
            "provider_message_id": "mail-1",
            "error": None,
        }

        result = dispatch_template_test(
            tenant_database="tenant",
            template_id="t1",
            channels=["email"],
            current_user={"_id": "u1", "name": "Admin", "email": "a@a.com", "phone": ""},
            use_logged_user=True,
            manual_targets=[{"name": "Sem email", "phone": "+5511999999999"}],
            preview_title="Teste",
            channel_templates=None,
        )

        self.assertEqual(result["summary"]["sent"], 1)
        self.assertEqual(result["summary"]["ignored"], 1)
        self.assertEqual(len(result["deliveries"]), 2)


if __name__ == "__main__":
    unittest.main()
