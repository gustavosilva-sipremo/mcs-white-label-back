import unittest

from app.models.notification_template import (
    ChannelSubtemplates,
    NotificationTemplateCreate,
)


class TestNotificationTemplateModels(unittest.TestCase):
    def test_accepts_three_subtemplates_for_selected_channels(self):
        data = NotificationTemplateCreate(
            name="Template",
            channels=["email", "sms"],
            channel_templates={
                "email": ChannelSubtemplates(
                    header_template="h",
                    body_template="b",
                    footer_template="f",
                ),
                "sms": ChannelSubtemplates(
                    header_template="h2",
                    body_template="b2",
                    footer_template="f2",
                ),
            },
        )
        self.assertEqual(data.channels, ["email", "sms"])

    def test_rejects_missing_subtemplate_for_active_channel(self):
        with self.assertRaisesRegex(ValueError, "must contain 3 non-empty"):
            NotificationTemplateCreate(
                name="Template",
                channels=["pwa"],
                channel_templates={
                    "pwa": ChannelSubtemplates(
                        header_template="",
                        body_template="body",
                        footer_template="footer",
                    ),
                },
            )


if __name__ == "__main__":
    unittest.main()
