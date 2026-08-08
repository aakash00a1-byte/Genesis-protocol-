"""Genesis Protocol - Streamlit Dashboard

Monitoring and management dashboard for Genesis Protocol.
"""

import streamlit as st
from datetime import datetime

# Page config
st.set_page_config(
    page_title="Genesis Protocol Dashboard",
    page_icon="🤖",
    layout="wide",
)

# Title
st.title("🤖 Genesis Protocol Dashboard")

# Sidebar
st.sidebar.title("Navigation")
page = st.sidebar.radio(
    "Go to",
    ["Dashboard", "Conversation History", "Memory Inspector", "Settings"]
)

# Import pages dynamically
if page == "Dashboard":
    from streamlit.pages import dashboard
    dashboard.show()
elif page == "Conversation History":
    from streamlit.pages import conversation_history
    conversation_history.show()
elif page == "Memory Inspector":
    from streamlit.pages import memory_inspector
    memory_inspector.show()
elif page == "Settings":
    from streamlit.pages import settings
    settings.show()

# Footer
st.sidebar.markdown("---")
st.sidebar.markdown(f"*Genesis Protocol v1.0.0-dev*")
st.sidebar.markdown(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")