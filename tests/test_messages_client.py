"""Execute the template's actual client code to catch draft/render regressions."""

import shutil
import subprocess
import unittest
from pathlib import Path


@unittest.skipUnless(shutil.which("node"), "Node.js is required for client behavior tests")
class MessagesClientTests(unittest.TestCase):
    def run_client(self, assertions: str) -> None:
        template = Path("app/templates/messages.html").read_text(encoding="utf-8")

        def section(start: str, end: str) -> str:
            return template[template.index(start):template.index(end)]

        script = r"""
            const assert = require('node:assert/strict');
            const composerLimit = 67;
            const messageDrafts = new Map();
            const conversation = { id: '1', path: '' };
            const getActiveConversation = () => conversation;
            const composerError = { hidden: true };
            const composerCount = {};
            const sendButton = {};
            const composerPathInput = {};
            const defaultPath = '';
            const i18n = {};
            class Textarea extends EventTarget {
                value = '';
                selectionStart = 0;
                selectionEnd = 0;
                setRangeText(text, start, end) {
                    this.value = this.value.slice(0, start) + text + this.value.slice(end);
                    this.selectionStart = this.selectionEnd = start + text.length;
                }
            }
            const composerInput = new Textarea();
            function draft(text, start = text.length, end = start) {
                messageDrafts.set(conversation.id, text);
                renderComposer(conversation);
                composerInput.selectionStart = start;
                composerInput.selectionEnd = end;
            }
            function paste(text) {
                const event = new Event('paste', { cancelable: true });
                event.clipboardData = { getData: () => text };
                composerInput.dispatchEvent(event);
                return event;
            }
        """
        script += section("    function escapeHtml(", "    function formatText(")
        script += section("    function validateComposer(", "    function normalizeFuturePath(")
        script += section("    function renderComposer(", "    function syncGlobalUnreadState(")
        script += section('    composerInput.addEventListener("beforeinput"', '    composerPathInput.addEventListener("input"')
        result = subprocess.run([shutil.which("node"), "-"], input=script + assertions, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_paste_persists_in_draft_across_render_and_replaces_selection(self) -> None:
        self.run_client(r"""
            draft('Hello world', 6, 11);
            assert.equal(paste('APRS').defaultPrevented, true);
            assert.equal(composerInput.value, 'Hello APRS');
            assert.equal(messageDrafts.get('1'), 'Hello APRS');
            assert.equal(composerInput.selectionStart, 10);
            renderComposer(conversation);
            assert.equal(composerInput.value, 'Hello APRS');
            assert.equal(composerCount.textContent, '10');
            assert.equal(sendButton.disabled, false);
        """)

    def test_paste_filters_non_ascii_and_respects_remaining_capacity(self) -> None:
        self.run_client(r"""
            draft('A'.repeat(65));
            paste('ÿ\ufffd\nBCDE');
            assert.equal(composerInput.value, 'A'.repeat(65) + 'BC');
            assert.equal(composerCount.textContent, '67');
            assert.equal(composerError.hidden, false);
            paste('X');
            assert.equal(composerInput.value.length, 67);
            draft('A'.repeat(67), 10, 13);
            paste('12345');
            assert.equal(composerInput.value, 'A'.repeat(10) + '123' + 'A'.repeat(54));
            draft('');
            paste('X'.repeat(100));
            assert.equal(composerInput.value, 'X'.repeat(67));
        """)

    def test_input_fallback_filters_unsafe_text_and_allows_native_shortcuts(self) -> None:
        self.run_client(r"""
            draft('');
            composerInput.value = 'OKÿ\ufffd\x00\x7f😀';
            composerInput.dispatchEvent(new Event('input'));
            assert.equal(composerInput.value, 'OK');
            assert.equal(messageDrafts.get('1'), 'OK');
            for (const type of ['copy', 'cut', 'keydown']) {
                const event = new Event(type, { cancelable: true });
                composerInput.dispatchEvent(event);
                assert.equal(event.defaultPrevented, false);
            }
            const invalid = new Event('beforeinput', { cancelable: true });
            invalid.data = 'ÿ';
            composerInput.dispatchEvent(invalid);
            assert.equal(invalid.defaultPrevented, true);
        """)

    def test_links_are_clickable_and_surrounding_text_is_escaped(self) -> None:
        self.run_client(r"""
            const result = renderMessageText('See https://example.org/?a=1&b=2 and www.example.com.');
            assert.match(result, /href="https:\/\/example.org\/\?a=1&amp;b=2"/);
            assert.match(result, /href="https:\/\/www.example.com"/);
            assert.match(result, /target="_blank" rel="noopener noreferrer"/);
            assert.ok(result.endsWith('www.example.com</a>.'));
            assert.equal(renderMessageText('<img src=x onerror=alert(1)> javascript:alert(1)'),
                '&lt;img src=x onerror=alert(1)&gt; javascript:alert(1)');
            assert.equal(renderMessageText('https://'), 'https://');
            assert.match(renderMessageText('(https://example.org/a_(b)).'), /a_\(b\)<\/a>\)\./);
            const quoted = renderMessageText('https://example.org/" onclick="alert(1)');
            assert.ok(!quoted.includes('" onclick="'));
            assert.ok(quoted.includes('&quot; onclick=&quot;'));
        """)


if __name__ == "__main__":
    unittest.main()
