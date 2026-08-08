"""Genesis Protocol - Dashboard Page"""

import streamlit as st
from datetime import datetime
import requests
import psutil

# Configuration
API_BASE = "https://genesis-protocol-00a1.up.railway.app"


@st.cache_data(ttl=10)
def get_health():
    """Fetch health check."""
    try:
        r = requests.get(f"{API_BASE}/api/health", timeout=3)
        return r.status_code == 200
    except:
        return False


@st.cache_data(ttl=10)
def get_version():
    """Fetch version info."""
    try:
        r = requests.get(f"{API_BASE}/api/version", timeout=3)
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return None


@st.cache_data(ttl=10)
def get_status():
    """Fetch metrics status."""
    try:
        r = requests.get(f"{API_BASE}/api/status", timeout=3)
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return None


@st.cache_data(ttl=30)
def get_diagnostics():
    """Fetch full diagnostics."""
    try:
        r = requests.get(f"{API_BASE}/api/diagnostics", timeout=5)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        return {"error": str(e)}
    return {"error": "Unable to connect"}


def show():
    """Display dashboard page."""
    st.header("📊 Genesis Protocol Dashboard")
    
    # Version info
    version_info = get_version()
    if version_info:
        st.caption(f"v{version_info.get('version', '?')} | Build: {version_info.get('build_date', '?')}")
    
    st.divider()

    # Health Panel
    col1, col2, col3 = st.columns(3)
    
    with col1:
        healthy = get_health()
        if healthy:
            st.success("🟢 Server Healthy")
        else:
            st.error("🔴 Server Unreachable")
    
    with col2:
        status = get_status()
        if status:
            metrics = status.get('metrics', {})
            st.metric("Requests", metrics.get('request_count', 0))
        else:
            st.metric("Requests", "—")
    
    with col3:
        if status:
            metrics = status.get('metrics', {})
            errors = metrics.get('error_count', 0)
            if errors > 0:
                st.error(f"Errors: {errors}")
            else:
                st.success("Errors: 0")
        else:
            st.metric("Errors", "—")

    st.divider()

    # Metrics Section
    st.subheader("📈 Performance Metrics")
    
    if status:
        metrics = status.get('metrics', {})
        avg_latency = metrics.get('avg_latency_ms', 0)
        uptime = metrics.get('uptime_seconds', 0)
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Avg Latency", f"{avg_latency:.0f}ms")
        
        with col2:
            hours = int(uptime // 3600)
            mins = int((uptime % 3600) // 60)
            st.metric("Uptime", f"{hours}h {mins}m")
        
        with col3:
            st.metric("Requests", metrics.get('request_count', 0))
        
        with col4:
            st.metric("Errors", metrics.get('error_count', 0))
        
        # Provider Latencies
        avg_latencies = metrics.get('avg_provider_latency', {})
        if avg_latencies:
            st.write("**Provider Latency:**")
            for provider, latency in avg_latencies.items():
                st.text(f"  {provider}: {latency:.0f}ms avg")
    else:
        st.warning("Metrics unavailable")

    st.divider()

    # Diagnostics
    diagnostics = get_diagnostics()
    
    if "error" not in diagnostics:
        # Provider Status
        st.subheader("🤖 AI Provider Status")
        
        providers = diagnostics.get('providers', {})
        available = providers.get('available', [])
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.write(f"**Available:** {', '.join(available) if available else 'None'}")
        
        with col2:
            if available:
                st.success("Providers Active")
            else:
                st.error("No Providers")
        
        # Database Status
        st.subheader("💾 Database Status")
        
        db = diagnostics.get('database', {})
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Users", db.get('user_count', 0))
        
        with col2:
            st.metric("Conversations", db.get('history_count', 0))
        
        with col3:
            db_status = db.get('status', 'unknown')
            if db_status == 'ok':
                st.success("✅ Database OK")
            else:
                st.error(f"❌ {db_status}")
        
        # Expand full diagnostics
        with st.expander("🔍 Full Diagnostics JSON"):
            st.json(diagnostics)
    else:
        st.error(f"Diagnostics Error: {diagnostics.get('error')}")

    st.divider()

    # System Info (Local)
    st.subheader("🖥️ Local System (Dashboard Host)")
    
    col1, col2 = st.columns(2)
    
    with col1:
        memory = psutil.virtual_memory()
        st.write(f"**Memory:** {memory.percent:.1f}% used")
        st.progress(memory.percent / 100)
    
    with col2:
        cpu = psutil.cpu_percent(interval=0.5)
        st.write(f"**CPU:** {cpu:.1f}%")
        st.progress(cpu / 100)

    st.divider()

    # Quick Actions
    st.subheader("⚡ Quick Actions")

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("🔄 Refresh All"):
            st.cache_data.clear()
            st.rerun()

    with col2:
        if st.button("📊 View History API"):
            st.info("Use: GET /api/history")

    with col3:
        if st.button("📋 View Full Status"):
            st.json(status if status else {})


if __name__ == "__main__":
    show()