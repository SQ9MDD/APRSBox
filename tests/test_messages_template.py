import unittest
from pathlib import Path


class MessagesTemplateTests(unittest.TestCase):
    def test_message_settings_are_rendered_in_a_separate_panel_below_conversations(self) -> None:
        template_source = Path("app/templates/messages.html").read_text(encoding="utf-8")
        conversations_panel = template_source.index('<section class="panel messages-page-panel">')
        settings_panel = template_source.index('<section class="panel messages-settings-panel">')
        self.assertGreater(settings_panel, conversations_panel)
        self.assertNotIn('id="messages-settings-form"', template_source[conversations_panel:settings_panel])
        self.assertIn('class="form-grid messages-settings"', template_source[settings_panel:])
        self.assertIn('class="full checkbox-row"', template_source[settings_panel:])
        self.assertNotIn("messages-settings-checkbox", template_source)

    def test_message_settings_panel_keeps_explanations_in_help(self) -> None:
        template_source = Path("app/templates/messages.html").read_text(encoding="utf-8")
        settings_panel = template_source[template_source.index('<section class="panel messages-settings-panel">'):]
        self.assertNotIn("Defaults for new conversations and automatic APRS responses.", settings_panel)
        self.assertNotIn("Used for new conversations and automatic APRS responses.", settings_panel)
        self.assertNotIn("Only explicitly defined groups are received.", settings_panel)
        self.assertNotIn("Only messages addressed to the configured callsign-SSID", settings_panel)
        self.assertIn('class="form-actions messages-settings-actions"', settings_panel)
        self.assertIn('class="field-validation-error messages-settings-error"', settings_panel)

    def test_group_threads_render_the_sender_above_each_message(self) -> None:
        template_source = Path("app/templates/messages.html").read_text(encoding="utf-8")
        self.assertIn('conversation.kind === "group"', template_source)
        self.assertIn('class="message-bubble-sender"', template_source)
        self.assertIn('message.sender', template_source)

    def test_target_groups_are_validated_and_canonicalized_before_save(self) -> None:
        template_source = Path("app/templates/messages.html").read_text(encoding="utf-8")
        self.assertIn("function validateTargetGroups(value)", template_source)
        self.assertIn('/^[A-Z0-9]{1,9}$/', template_source)
        self.assertIn('groups.join(", ")', template_source)
        self.assertIn('target_groups: groupValidation.groups', template_source)

    def test_messages_path_prefers_local_storage_and_not_server_conversation_path(self) -> None:
        template_source = Path("app/templates/messages.html").read_text(encoding="utf-8")
        self.assertIn("window.localStorage.getItem", template_source)
        self.assertIn("window.localStorage.setItem", template_source)
        self.assertIn("window.localStorage.removeItem", template_source)
        self.assertIn("resolveConversationPath(conversation)", template_source)
        self.assertNotIn("/conversations/${encodeURIComponent(conversation.id)}/path", template_source)


if __name__ == "__main__":
    unittest.main()
