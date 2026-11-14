"""Prompt honesty/style rules and the chat UI's Markdown renderer.

Two live complaints drove these: the model invented a Telegram bot name, and the
web UI printed literal ``**`` because it rendered replies with ``textContent``.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _agent():
    import os

    os.environ.setdefault("GLUTEN_OWNER_IDS", "1")
    from genesis_protocol.ai.agent import GenesisAgent

    return GenesisAgent()


class TestPromptCarriesRealFacts:
    def test_telegram_username_is_injected(self):
        prompt = _agent()._get_system_prompt()
        assert "TELEGRAM BOT" in prompt
        # The prompt must name the configured bot, not leave the model guessing.
        assert "@" in prompt.split("TELEGRAM BOT", 1)[1].split("\n", 1)[0]

    def test_prompt_forbids_inventing_handles(self):
        prompt = _agent()._get_system_prompt()
        assert "NEVER invent a username" in prompt

    def test_prompt_asks_for_flowing_prose(self):
        prompt = _agent()._get_system_prompt()
        assert "flowing Hinglish" in prompt
        assert "No headings" in prompt


class TestChatUiRendersMarkdownSafely:
    """The renderer is JavaScript, so drive it with node and assert the HTML."""

    def _renderer(self):
        html = (ROOT / "web" / "templates" / "chat.html").read_text()
        start = html.index("function renderMarkdown")
        end = html.index("function addTyping")
        return html[start:end]

    def test_assistant_messages_use_the_renderer(self):
        html = (ROOT / "web" / "templates" / "chat.html").read_text()
        assert "body.innerHTML = renderMarkdown(text)" in html

    @pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
    def test_renderer_outputs_html_and_escapes_input(self, tmp_path):
        script = tmp_path / "check.mjs"
        script.write_text(
            "import { readFileSync } from 'fs';\n"
            f"const html = readFileSync({str(ROOT / 'web/templates/chat.html')!r}, 'utf8');\n"
            "const code = html.slice(html.indexOf('function renderMarkdown'),"
            " html.indexOf('function addTyping'));\n"
            "const shim = \"function esc(s){return String(s==null?'':s)"
            ".replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}\\n\";\n"
            "const fn = new Function(shim + code + '\\nreturn renderMarkdown;')();\n"
            "const out = [\n"
            "  fn('**bold**').includes('<strong>bold</strong>'),\n"
            "  fn('- a\\n- b').includes('<ul><li>a</li><li>b</li></ul>'),\n"
            "  fn('<script>alert(1)</script>').includes('&lt;script&gt;'),\n"
            "];\n"
            "if (!out.every(Boolean)) { console.error(out); process.exit(1); }\n"
        )
        proc = subprocess.run(["node", str(script)], capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr


class TestTelegramDefaultIsTheRealBot:
    def test_default_username_matches_the_deployed_bot(self):
        from genesis_protocol.config import TelegramConfig

        assert TelegramConfig().bot_username == "Genesis_autonomousbot"

    def test_prompt_does_not_name_the_legacy_maker_bot(self):
        prompt = _agent()._get_system_prompt()
        assert "Genesis_makebot" not in prompt


class TestToolListIsPerRequest:
    """_tools_used was never reset, so the list grew with every request and the
    UI showed stale tools (['calculator', 'calculator'] on the second query).
    """

    def test_tool_list_does_not_accumulate(self):
        import asyncio
        import os

        os.environ.setdefault("GLUTEN_OWNER_IDS", "1")
        from genesis_protocol.ai.agent import GenesisAgent

        agent = GenesisAgent()

        async def run(query):
            result = await agent.process(query, chat_id=1, user_id=1)
            return result.tools_used

        first = asyncio.run(run("17*23"))
        second = asyncio.run(run("144/12"))
        assert first == ["calculator"]
        assert second == ["calculator"]


class TestPromptGivesIdentityAndStaysPrivate:
    """A live probe showed the model quoting its own rules back ("rules mein
    likha hai") and calling itself a Telegram bot instead of GLUTEN.
    """

    def test_prompt_states_identity(self):
        prompt = _agent()._get_system_prompt()
        assert "YOU ARE GLUTEN" in prompt
        assert "NOT a Telegram bot" in prompt

    def test_prompt_forbids_revealing_instructions(self):
        prompt = _agent()._get_system_prompt()
        assert "CONFIDENTIALITY" in prompt
        assert "system prompt" in prompt
