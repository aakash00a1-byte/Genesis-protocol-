"""
Genesis Protocol - Enhanced Chat Interface

Features:
- ChatGPT-style UI
- Dark/Light themes
- Chat history
- Conversation search
- Typing indicators
- Markdown rendering
- Code highlighting
- Voice assistant
"""

from datetime import datetime
from typing import List, Dict, Optional
import json
import sqlite3


class ChatManager:
    """Manage chat conversations and history."""
    
    def __init__(self, db_path: str = 'genesis.db'):
        self.db_path = db_path
        self._init_tables()
    
    def _get_db(self):
        """Get database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _init_tables(self):
        """Initialize chat tables."""
        conn = self._get_db()
        cursor = conn.cursor()
        
        # Conversations table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_archived INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Messages table (enhanced)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                model TEXT,
                provider TEXT,
                quality_score REAL,
                mode TEXT,
                tokens_used INTEGER,
                latency_ms INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id) REFERENCES conversations (id)
            )
        ''')
        
        # Create indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at)')
        
        conn.commit()
        conn.close()
    
    def create_conversation(self, user_id: int, title: str = None) -> int:
        """Create new conversation."""
        if not title:
            title = f"Chat {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        
        conn = self._get_db()
        cursor = conn.cursor()
        cursor.execute('INSERT INTO conversations (user_id, title) VALUES (?, ?)', (user_id, title))
        conversation_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return conversation_id
    
    def get_conversations(self, user_id: int, limit: int = 50, archived: bool = False) -> List[Dict]:
        """Get user's conversations."""
        conn = self._get_db()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT c.*, 
                   (SELECT COUNT(*) FROM messages WHERE conversation_id = c.id) as message_count
            FROM conversations c
            WHERE c.user_id = ? AND c.is_archived = ?
            ORDER BY c.updated_at DESC LIMIT ?
        ''', (user_id, 1 if archived else 0, limit))
        conversations = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return conversations
    
    def get_conversation(self, conversation_id: int, user_id: int) -> Optional[Dict]:
        """Get single conversation with messages."""
        conn = self._get_db()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM conversations WHERE id = ? AND user_id = ?', (conversation_id, user_id))
        conversation = cursor.fetchone()
        
        if not conversation:
            conn.close()
            return None
        
        cursor.execute('SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC', (conversation_id,))
        messages = [dict(row) for row in cursor.fetchall()]
        
        conn.close()
        
        return {'conversation': dict(conversation), 'messages': messages}
    
    def add_message(self, conversation_id: int, role: str, content: str,
                   model: str = None, provider: str = None,
                   quality_score: float = None, mode: str = None,
                   tokens_used: int = None, latency_ms: int = None) -> int:
        """Add message to conversation."""
        conn = self._get_db()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO messages (conversation_id, role, content, model, provider,
                                 quality_score, mode, tokens_used, latency_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (conversation_id, role, content, model, provider,
              quality_score, mode, tokens_used, latency_ms))
        
        message_id = cursor.lastrowid
        cursor.execute('UPDATE conversations SET updated_at = CURRENT_TIMESTAMP WHERE id = ?', (conversation_id,))
        
        conn.commit()
        conn.close()
        return message_id
    
    def export_conversation(self, conversation_id: int, user_id: int, format: str = 'json') -> Optional[str]:
        """Export conversation to JSON or markdown."""
        data = self.get_conversation(conversation_id, user_id)
        if not data:
            return None
        
        if format == 'json':
            return json.dumps(data, indent=2, default=str)
        
        elif format == 'markdown':
            md = f"# {data['conversation']['title']}\n\n"
            for msg in data['messages']:
                md += f"## {msg['role'].upper()}\n\n{msg['content']}\n\n"
            return md
        
        return None
    
    def get_chat_stats(self, user_id: int) -> Dict:
        """Get chat statistics for user."""
        conn = self._get_db()
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM conversations WHERE user_id = ?', (user_id,))
        total_conversations = cursor.fetchone()[0]
        
        cursor.execute('''
            SELECT COUNT(*) FROM messages m
            JOIN conversations c ON m.conversation_id = c.id
            WHERE c.user_id = ?
        ''', (user_id,))
        total_messages = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'total_conversations': total_conversations,
            'total_messages': total_messages
        }


_chat_manager: Optional[ChatManager] = None

def get_chat_manager() -> ChatManager:
    """Get chat manager singleton."""
    global _chat_manager
    if _chat_manager is None:
        _chat_manager = ChatManager()
    return _chat_manager