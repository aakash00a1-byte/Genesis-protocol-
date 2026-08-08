"""Genesis Protocol - Settings Page"""

import streamlit as st


def show():
    """Display settings page."""
    st.header("⚙️ Settings")
    
    # Configuration tabs
    tab1, tab2, tab3, tab4 = st.tabs(["AI Providers", "Memory", "Integrations", "System"])
    
    with tab1:
        st.subheader("AI Provider Configuration")
        
        st.write("**Groq (Primary)**")
        groq_key = st.text_input("Groq API Key", type="password", help="Get key from console.groq.com")
        st.write(f"Status: {'Configured' if groq_key else 'Not configured'}")
        
        st.write("**OpenAI (Fallback)**")
        openai_key = st.text_input("OpenAI API Key", type="password", help="Get key from platform.openai.com")
        st.write(f"Status: {'Configured' if openai_key else 'Not configured'}")
        
        st.write("**Google Gemini (Fallback)**")
        gemini_key = st.text_input("Gemini API Key", type="password", help="Get key from aistudio.google.com")
        st.write(f"Status: {'Configured' if gemini_key else 'Not configured'}")
        
        st.write("**HuggingFace (Fallback)**")
        hf_key = st.text_input("HuggingFace API Key", type="password", help="Get key from huggingface.co")
        st.write(f"Status: {'Configured' if hf_key else 'Not configured'}")
    
    with tab2:
        st.subheader("Memory Configuration")
        
        st.write("**Redis**")
        redis_host = st.text_input("Redis Host", value="localhost")
        redis_port = st.number_input("Redis Port", value=6379, min_value=1, max_value=65535)
        
        st.write("**ChromaDB**")
        chroma_path = st.text_input("ChromaDB Path", value="./data/chroma_db")
        vector_dims = st.number_input("Vector Dimensions", value=1536, min_value=128, max_value=4096)
    
    with tab3:
        st.subheader("Integration Configuration")
        
        st.write("**Tavily Search**")
        tavily_key = st.text_input("Tavily API Key", type="password", help="Get key from tavily.com")
        
        st.write("**Make.com**")
        make_webhook = st.text_input("Make.com Webhook URL")
        make_key = st.text_input("Make.com API Key", type="password")
    
    with tab4:
        st.subheader("System Configuration")
        
        st.write("**Telegram**")
        telegram_token = st.text_input("Telegram Bot Token", type="password")
        
        st.write("**Application**")
        app_debug = st.checkbox("Debug Mode", value=False)
        log_level = st.selectbox("Log Level", ["DEBUG", "INFO", "WARNING", "ERROR"])
    
    st.divider()
    
    # Save button
    col1, col2 = st.columns([1, 4])
    
    with col1:
        if st.button("💾 Save Settings", use_container_width=True):
            st.success("Settings saved (not persisted yet - requires .env file)")
    
    with col2:
        if st.button("🔄 Load Settings", use_container_width=True):
            st.info("Loading settings from environment...")
    
    # Reset
    st.divider()
    if st.button("🔙 Reset to Defaults", use_container_width=True):
        st.warning("Reset functionality coming soon")


if __name__ == "__main__":
    show()