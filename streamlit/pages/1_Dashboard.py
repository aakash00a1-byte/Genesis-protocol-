"""Genesis Protocol - Dashboard Page"""

import streamlit as st
from datetime import datetime
import requests
import psutil

# Configuration
API_BASE = "https://genesis-protocol-00a1.up.railway.app"


@st.cache_data(ttl=30)
def get_debug_info():
    """Fetch debug info from API."""
    try:
        response = requests.get(f"{API_BASE}/api/debug", timeout=5)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        return {"error": str(e)}
    return {"error": "Unable to connect"}


def show():
    """Display dashboard page."""
    st.header("📊 System Dashboard")

    # Fetch real-time data
    debug_data = get_debug_info()

    # Metrics row
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if "error" not in debug_data:
            st.metric("Status", "✅ Online", "0 errors")
        else:
            st.metric("Status", "❌ Error", debug_data.get("error", "Unknown"))

    with col2:
        st.metric("Active Chats", "—", "Real-time soon")

    with col3:
        st.metric("Messages Today", "—", "Real-time soon")

    with col4:
        available = debug_data.get("available_providers", [])
        provider = available[0] if available else "None"
        st.metric("AI Provider", provider.title() if provider != "None" else "❌", "Active" if provider else "Not configured")

    st.divider()

    # System status
    st.subheader("🖥️ System Status")

    col1, col2 = st.columns(2)

    with col1:
        st.write("**Memory Usage:**")
        memory = psutil.virtual_memory()
        st.progress(memory.percent / 100, text=f"{memory.percent:.1f}% used")

        st.write("**CPU Usage:**")
        cpu = psutil.cpu_percent(interval=1)
        st.progress(cpu / 100, text=f"{cpu:.1f}% used")

    with col2:
        st.write("**Disk Usage:**")
        disk = psutil.disk_usage('/')
        st.progress(disk.percent / 100, text=f"{disk.percent:.1f}% used")

        st.write("**Uptime:**")
        st.text(f"Since {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    st.divider()

    # AI Provider Status
    st.subheader("🤖 AI Provider Status")

    if "error" not in debug_data:
        provider_status = debug_data.get("provider_status", {})
        
        for name, info in provider_status.items():
            configured = info.get("configured", False)
            status = "✅ Available" if configured else "⏳ Not configured"
            circuit = info.get("circuit_state", "unknown")
            
            col1, col2, col3, col4 = st.columns([2, 2, 1, 1])
            with col1:
                st.write(f"**{name.upper()}**")
            with col2:
                st.write(status)
            with col3:
                st.write(f"Circuit: {circuit}")
            with col4:
                failures = info.get("failures", 0)
                st.write(f"Failures: {failures}")
    else:
        st.warning("Unable to fetch provider status")

    st.divider()

    # API Debug Info
    st.subheader("🔍 API Debug Info")
    
    if "error" not in debug_data:
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**Groq Configured:** {debug_data.get('groq_configured', False)}")
            st.write(f"**Available Providers:** {', '.join(debug_data.get('available_providers', []))}")
        with col2:
            st.json(debug_data)
    else:
        st.error(f"API Error: {debug_data.get('error')}")

    # Quick actions
    st.subheader("⚡ Quick Actions")

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("🔄 Refresh Data"):
            st.cache_data.clear()
            st.rerun()

    with col2:
        if st.button("🧹 Clear Memory"):
            st.warning("Clear memory functionality coming soon")

    with col3:
        if st.button("📊 Export Stats"):
            st.warning("Export functionality coming soon")


if __name__ == "__main__":
    show()