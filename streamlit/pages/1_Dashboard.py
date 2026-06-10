"""Genesis Protocol - Dashboard Page"""

import streamlit as st
from datetime import datetime
import psutil


def show():
    """Display dashboard page."""
    st.header("📊 System Dashboard")
    
    # Metrics row
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Status", "Running ✅", "0 errors")
    
    with col2:
        st.metric("Active Chats", "0", "+0 today")
    
    with col3:
        st.metric("Messages Today", "0", "+0")
    
    with col4:
        st.metric("AI Provider", "Groq", "Active")
    
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
    
    providers = {
        "Groq": {"status": "✅ Available", "requests": 0, "latency": "0ms"},
        "OpenAI": {"status": "⏳ Not configured", "requests": 0, "latency": "N/A"},
        "Gemini": {"status": "⏳ Not configured", "requests": 0, "latency": "N/A"},
        "HuggingFace": {"status": "⏳ Not configured", "requests": 0, "latency": "N/A"},
    }
    
    for name, info in providers.items():
        col1, col2, col3, col4 = st.columns([2, 2, 1, 1])
        with col1:
            st.write(f"**{name}**")
        with col2:
            st.write(info["status"])
        with col3:
            st.write(f"Requests: {info['requests']}")
        with col4:
            st.write(f"Latency: {info['latency']}")
    
    st.divider()
    
    # Recent Activity
    st.subheader("📝 Recent Activity")
    
    activity_data = [
        {"time": "Now", "event": "Dashboard opened", "details": "User viewing dashboard"},
    ]
    
    st.table(activity_data)
    
    # Quick actions
    st.subheader("⚡ Quick Actions")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("🔄 Restart Bot"):
            st.warning("Restart functionality coming soon")
    
    with col2:
        if st.button("🧹 Clear Memory"):
            st.warning("Clear memory functionality coming soon")
    
    with col3:
        if st.button("📊 Export Stats"):
            st.warning("Export functionality coming soon")


if __name__ == "__main__":
    show()