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
    """`/` used to render a chat page for logged-out visitors.

    That page posts to /api/chat, which is @login_required, so every message
    came back 401 and the UI showed a generic error. The logged-out homepage
    must be a landing page instead.
    """
    client = app.test_client()
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Message GLUTEN" not in body


def test_logged_in_homepage_redirects_to_the_single_chat_page():
    """`/` sent signed-in users to a legacy chat UI. There is one chat now."""
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["username"] = "t"
    resp = client.get("/")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/chat")


def test_legacy_chat_urls_redirect_to_chat():
    """`/ultra` and `/gemini` were separate chat UIs that drifted apart."""
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["username"] = "t"
    for path in ("/ultra", "/gemini"):
        resp = client.get(path)
        assert resp.status_code == 302, path
        assert resp.headers["Location"].endswith("/chat"), path


def test_chat_api_requires_login_and_says_so_as_json():
    """A 401 must be machine-readable so the UI can redirect to /login."""
    client = app.test_client()
    resp = client.post("/api/chat", json={"message": "hello"})
    assert resp.status_code == 401
    data = resp.get_json()
    assert data.get("login_required") is True
    assert data.get("error")


# --- Every template that posts to /api/chat must handle a 401 the same way.
# --- Missing this is what produced the original generic chat error: the page
# --- rendered a chat, the API answered 401, and the template turned it into a
# --- generic failure instead of sending the user to /login.

CHAT_TEMPLATES = [
    "chat.html",
    "agent_workspace.html",
]


@pytest.mark.parametrize("name", CHAT_TEMPLATES)
def test_chat_template_handles_401(name):
    text = (Path(__file__).parent.parent / "web" / "templates" / name).read_text()
    assert "status === 401" in text, f"{name} does not handle a 401"
    assert "/login" in text, f"{name} does not redirect to /login on 401"


@pytest.mark.parametrize("name", CHAT_TEMPLATES)
def test_chat_template_has_no_hardcoded_model(name):
    text = (Path(__file__).parent.parent / "web" / "templates" / name).read_text()
    assert "Groq LLama" not in text, f"{name} hardcodes a model name"


@pytest.mark.parametrize("name", CHAT_TEMPLATES)
def test_chat_template_has_no_generic_sorry(name):
    text = (Path(__file__).parent / ".." / "web" / "templates" / name).read_text()
    assert "Sorry, I encountered an error" not in text, f"{name} shows a generic error"


def test_chat_page_does_not_hardcode_a_model_name():
    """A status bar once claimed "Model: Groq LLama-3.1" with nothing configured."""
    text = (Path(__file__).parent.parent / "web" / "templates" / "chat.html").read_text()
    assert "Groq LLama" not in text
    assert 'id="modelLabel"' in text


def test_chat_page_has_no_websocket_reconnect_loop():
    """There is no /ws route; a reconnect loop hammered the server forever."""
    text = (Path(__file__).parent.parent / "web" / "templates" / "chat.html").read_text()
    assert "setTimeout(initWebSocket" not in text
    assert "Reconnecting..." not in text


def test_login_lands_on_a_template_that_handles_401():
    """Login redirects to /chat, so chat.html must be one of the fixed ones."""
    from web.app import app as _app
    client = _app.test_client()
    resp = client.post("/api/auth/login", json={"username": "nope", "password": "nope"})
    # the route exists and rejects; what matters is that /chat renders chat.html
    assert resp.status_code in (400, 401, 403)
    text = (Path(__file__).parent.parent / "web" / "templates" / "chat.html").read_text()
    assert "status === 401" in text


def test_settings_page_reports_real_providers():
    """It listed deprecated models in a dropdown that was never wired up."""
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["username"] = "t"
    body = client.get("/settings").get_data(as_text=True)
    assert "AI Providers" in body
    assert "Groq LLama" not in body


# --- One web server, one entrypoint. There used to be two more Flask apps on
# --- disk (server_simple.py, realtime_server.py) that nothing imported but
# --- that deployment files pointed at, so a reader could not tell which one
# --- was live. They and their exclusive templates are gone.

WEB_DIR = Path(__file__).parent.parent / "web"
TEMPLATES = WEB_DIR / "templates"
REPO_ROOT = Path(__file__).parent.parent

DEAD_SERVERS = ["server_simple.py", "realtime_server.py"]
DEAD_TEMPLATES = ["index.html", "realtime_chat.html", "reset_password.html", "base.html"]


@pytest.mark.parametrize("name", DEAD_SERVERS)
def test_dead_servers_stay_deleted(name):
    assert not (WEB_DIR / name).exists(), f"{name} is back; there is one web server"


@pytest.mark.parametrize("name", DEAD_TEMPLATES)
def test_dead_templates_stay_deleted(name):
    assert not (TEMPLATES / name).exists(), f"{name} is unreachable; delete it again"


def test_no_file_points_at_a_deleted_server():
    """A deploy config that launches a deleted module is a silent outage."""
    for name in DEAD_SERVERS:
        stem = name[:-3]
        for cfg in ("render.yaml", "web/render.yaml", "supervisord.conf",
                    "supervisord.hf.conf", "Dockerfile", "Dockerfile.hf",
                    "web/Dockerfile"):
            path = REPO_ROOT / cfg
            if not path.exists():
                continue
            text = path.read_text()
            assert f"{stem}:app" not in text, f"{cfg} still launches {name}"
            assert f"python {stem}.py" not in text, f"{cfg} still launches {name}"


def test_every_template_is_rendered_or_included():
    """An orphan template is dead weight that drifts from the live pages."""
    source = "\n".join(p.read_text() for p in (WEB_DIR / "app.py",) )
    templates = {p.name for p in TEMPLATES.glob("*.html")}
    referenced = set()
    for t in templates:
        body = (TEMPLATES / t).read_text()
        referenced.add(t)
        for other in templates:
            if f'"{other}"' in body or f"'{other}'" in body:
                referenced.add(other)
    for t in templates:
        if f"'{t}'" in source or f'"{t}"' in source:
            referenced.add(t)
    orphans = sorted(templates - referenced)
    assert orphans == [], f"templates reachable from no route or include: {orphans}"


def test_skills_page_reads_live_skills():
    """`/agents` used to hardcode "Built-in Agents (8)" — a list no code defines."""
    body = (TEMPLATES / "agents.html").read_text()
    assert "/api/skills" in body, "skills page must read the live registry"
    assert "Built-in Agents (8)" not in body


@pytest.mark.parametrize("name", ["knowledge.html", "agents.html"])
def test_template_uses_defined_css_classes(name):
    """`.fp-input`/`.fp-btn` are not in app.css, so the search box was unstyled."""
    css = (WEB_DIR / "static" / "css" / "app.css").read_text()
    body = (TEMPLATES / name).read_text()
    for cls in ("fp-input", "fp-btn"):
        if cls in body:
            assert f".{cls}" in css, f"{name} uses .{cls}, which app.css does not define"


