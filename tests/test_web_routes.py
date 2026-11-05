"""Route-registration tests for web/app.py.

`web/app.py` once had `if __name__ == '__main__': app.run(...)` roughly 1050
lines above the end of the file. Every route defined after it never registered
when the app was started the documented way (`python web/app.py`), so those
endpoints answered 404. Importing the module registered them, which is why the
tests passed and the breakage only showed up against a running server.

These tests assert the structural invariant directly, so the same mistake
cannot come back unnoticed.
"""

import ast
from pathlib import Path

import pytest

from web.app import app

APP_PATH = Path(__file__).parent.parent / "web" / "app.py"


def _route_strings():
    return {str(r) for r in app.url_map.iter_rules()}


def test_main_block_is_the_last_statement():
    """The `__main__` guard must be the final top-level statement."""
    tree = ast.parse(APP_PATH.read_text())
    last = tree.body[-1]
    assert isinstance(last, ast.If), "expected the __main__ guard at the end of the file"
    test = last.test
    assert isinstance(test, ast.Compare), "expected `if __name__ == '__main__':`"


def test_no_route_is_defined_after_the_main_block():
    """No @app.route decorator may sit below the `__main__` guard."""
    source = APP_PATH.read_text()
    tree = ast.parse(source)
    main_lineno = tree.body[-1].lineno
    late_routes = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for deco in node.decorator_list:
                target = deco.func if isinstance(deco, ast.Call) else deco
                if isinstance(target, ast.Attribute) and target.attr == "route":
                    if node.lineno > main_lineno:
                        late_routes.append((node.name, node.lineno))
    assert late_routes == [], f"routes defined after the __main__ block: {late_routes}"


@pytest.mark.parametrize("path", [
    "/api/entity", "/api/state", "/api/timeline", "/api/journal",
    "/api/trust", "/api/wisdom", "/api/relationship", "/api/dream",
    "/api/continuity", "/api/archive", "/api/survival/status",
    "/api/garden/status", "/api/infinity/status", "/api/live-info",
    "/api/crypto/all", "/api/railway/status",
])
def test_late_defined_api_routes_are_registered(path):
    """Every endpoint that used to sit after the guard must be registered."""
    assert any(
        str(rule).startswith(path) for rule in app.url_map.iter_rules()
    ), f"{path} is not registered"


@pytest.mark.parametrize("path", [
    "/agents", "/models", "/knowledge", "/memory", "/tools",
    "/voice", "/files", "/prompts", "/history", "/infinity", "/infinity/roadmap",
])
def test_sidebar_pages_are_registered(path):
    """Every link in the base_v4 sidebar must resolve to a real page."""
    assert path in _route_strings(), f"{path} is not registered"


# --- The "hello" bug: a logged-out visitor must never land on a chat that
# --- cannot answer them.

def test_logged_out_homepage_is_a_landing_page_not_the_chat():
    """`/` used to render genesis_ultra.html for logged-out visitors.

    That page posts to /api/chat, which is @login_required, so every message
    came back 401 and the UI showed "Sorry, I encountered an error". The
    logged-out homepage must be a landing page instead.
    """
    client = app.test_client()
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "genesis_ultra.html" not in body
    assert "Message GLUTEN" not in body


def test_chat_api_requires_login_and_says_so_as_json():
    """A 401 must be machine-readable so the UI can redirect to /login."""
    client = app.test_client()
    resp = client.post("/api/chat", json={"message": "hello"})
    assert resp.status_code == 401
    data = resp.get_json()
    assert data.get("login_required") is True
    assert data.get("error")


def test_chat_templates_redirect_on_401():
    """Both chat templates must send an expired session to /login."""
    templates = Path(__file__).parent.parent / "web" / "templates"
    for name in ("genesis_ultra.html", "genesis_gemini.html"):
        text = (templates / name).read_text()
        assert "response.status === 401" in text, name
        assert "window.location.href = '/login'" in text, name


def test_chat_templates_have_no_websocket_reconnect_loop():
    """There is no /ws route; a reconnect loop hammered the server forever."""
    templates = Path(__file__).parent.parent / "web" / "templates"
    text = (templates / "genesis_ultra.html").read_text()
    assert "setTimeout(initWebSocket" not in text
    assert "Reconnecting..." not in text


def test_chat_page_does_not_hardcode_a_model_name():
    """The status bar claimed "Model: Groq LLama-3.1" with nothing configured."""
    templates = Path(__file__).parent.parent / "web" / "templates"
    text = (templates / "genesis_ultra.html").read_text()
    assert "Groq LLama" not in text
    assert 'id="modelLabel"' in text

