import unittest
from pathlib import Path


class MessagesTemplateTests(unittest.TestCase):
    def test_messages_path_prefers_local_storage_and_not_server_conversation_path(self) -> None:
        template_source = Path("app/templates/messages.html").read_text(encoding="utf-8")
        self.assertIn("window.localStorage.getItem", template_source)
        self.assertIn("window.localStorage.setItem", template_source)
        self.assertIn("window.localStorage.removeItem", template_source)
        self.assertIn("resolveConversationPath(conversation)", template_source)
        self.assertNotIn("/conversations/${encodeURIComponent(conversation.id)}/path", template_source)


if __name__ == "__main__":
    unittest.main()
