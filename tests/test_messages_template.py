import unittest
from pathlib import Path


class MessagesTemplateTests(unittest.TestCase):
    def test_message_settings_are_rendered_in_a_separate_panel_below_conversations(self) -> None:
        template_source = Path("app/templates/messages.html").read_text(encoding="utf-8")
        conversations_panel = template_source.index('<section class="panel messages-page-panel">')
        settings_panel = template_source.index('<section class="panel messages-settings-panel">')
        self.assertGreater(settings_panel, conversations_panel)
        self.assertNotIn('id="messages-settings-form"', template_source[conversations_panel:settings_panel])

    def test_messages_path_prefers_local_storage_and_not_server_conversation_path(self) -> None:
        template_source = Path("app/templates/messages.html").read_text(encoding="utf-8")
        self.assertIn("window.localStorage.getItem", template_source)
        self.assertIn("window.localStorage.setItem", template_source)
        self.assertIn("window.localStorage.removeItem", template_source)
        self.assertIn("resolveConversationPath(conversation)", template_source)
        self.assertNotIn("/conversations/${encodeURIComponent(conversation.id)}/path", template_source)


if __name__ == "__main__":
    unittest.main()
