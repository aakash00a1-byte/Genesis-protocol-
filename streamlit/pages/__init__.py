"""Streamlit pages for Genesis Protocol dashboard."""

from streamlit.pages.dashboard import show as dashboard_show
from streamlit.pages.conversation_history import show as conversation_show
from streamlit.pages.memory_inspector import show as memory_show
from streamlit.pages.settings import show as settings_show

# Export for dynamic import
def get_show(page_name):
    pages = {
        "dashboard": dashboard_show,
        "conversation_history": conversation_show,
        "memory_inspector": memory_show,
        "settings": settings_show,
    }
    return pages.get(page_name, dashboard_show)