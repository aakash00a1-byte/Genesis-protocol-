"""Genesis Protocol - Conversation History Page"""

import streamlit as st


def show():
    """Display conversation history page."""
    st.header("💬 Conversation History")
    
    # Chat selector
    st.subheader("Select Conversation")
    
    chat_options = ["No conversations yet"]
    selected_chat = st.selectbox("Choose a chat", chat_options)
    
    if selected_chat == "No conversations yet":
        st.info("No conversations available. Start chatting with the bot to see history here.")
    else:
        st.subheader(f"Chat with {selected_chat}")
        
        # Message display area
        st.write("Messages will appear here...")
        
        # Message input
        message = st.text_input("Send a test message")
        if st.button("Send"):
            st.info("Test messages coming soon - connect to live bot for full functionality")
    
    # Search conversations
    st.divider()
    st.subheader("🔍 Search Conversations")
    
    search_query = st.text_input("Search in conversations")
    if search_query:
        st.write(f"Searching for: {search_query}")
        st.info("Search functionality coming soon")


if __name__ == "__main__":
    show()