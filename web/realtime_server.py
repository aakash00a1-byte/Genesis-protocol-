"""
Genesis Protocol - Real-time WebSocket Server
For live chat with streaming responses
"""
import os
import sys
import json
import sqlite3
from datetime import timedelta
from functools import wraps

from flask import Flask, request, jsonify, session, render_template, redirect, url_for
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.security import generate_password_hash, check_password_hash

# Initialize Flask + SocketIO
app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = os.environ.get('SECRET_KEY', 'genesis-secret-key-2024')
app.config['SECRET_KEY'] = app.secret_key

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# Database
DATABASE = 'genesis.db'

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    # Ensure tables exist
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'user',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP,
            is_active INTEGER DEFAULT 1,
            usage_count INTEGER DEFAULT 0
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            response TEXT,
            model_used TEXT,
            provider TEXT,
            quality_score REAL,
            mode TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    conn.commit()
    conn.close()

# Auth decorator
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated

# Routes
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('chat'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json() or request.form
        username = data.get('username')
        password = data.get('password')
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT id, username, password_hash FROM users WHERE username = ?', (username,))
        user = cursor.fetchone()
        conn.close()
        
        if user and check_password_hash(user['password_hash'], password):
            session.permanent = True
            session['user_id'] = user['id']
            session['username'] = user['username']
            return jsonify({'success': True})
        
        return jsonify({'error': 'Invalid credentials'}), 401
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = request.get_json() or request.form
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')
        
        if not all([username, email, password]):
            return jsonify({'error': 'All fields required'}), 400
        
        password_hash = generate_password_hash(password)
        
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)',
                (username, email, password_hash)
            )
            conn.commit()
            conn.close()
            return jsonify({'success': True})
        except:
            return jsonify({'error': 'Username/email exists'}), 400
    
    return render_template('register.html')

@app.route('/chat')
def chat():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('realtime_chat.html')

@app.route('/api/chat/history')
@login_required
def get_history():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM chat_history WHERE user_id = ? ORDER BY created_at DESC LIMIT 50', (session['user_id'],))
    chats = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({'chats': chats})

# WebSocket Events
@socketio.on('connect')
def on_connect():
    if 'user_id' in session:
        join_room(f"user_{session['user_id']}")
        emit('connected', {'status': 'connected', 'username': session.get('username')})

@socketio.on('disconnect')
def on_disconnect():
    if 'user_id' in session:
        leave_room(f"user_{session['user_id']}")

@socketio.on('chat_message')
def handle_message(data):
    """Handle incoming chat message with streaming response."""
    if 'user_id' not in session:
        emit('error', {'error': 'Not authenticated'})
        return
    
    message = data.get('message', '')
    mode = data.get('mode', 'NORMAL')
    
    if not message:
        emit('error', {'error': 'Empty message'})
        return
    
    # Emit "typing" status
    emit('status', {'status': 'thinking', 'message': 'AI is thinking...'})
    
    try:
        from genesis_protocol.ai.provider_chain import get_provider_chain
        from genesis_protocol.core.channel import get_channel_isolation
        
        ai = get_provider_chain()
        channel = get_channel_isolation()
        channel.set_channel('web')
        
        full_response = ""
        
        # Stream response chunks
        for chunk in ai.call_stream(messages=[
            {"role": "system", "content": "You are a helpful AI assistant. Be concise and friendly."},
            {"role": "user", "content": message}
        ], user_input=message):
            if chunk:
                full_response += chunk
                emit('stream', {'chunk': chunk})
        
        # Save to database
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO chat_history (user_id, message, response, provider, mode) VALUES (?, ?, ?, ?, ?)',
            (session['user_id'], message, full_response, 'groq', mode)
        )
        conn.commit()
        conn.close()
        
        emit('status', {'status': 'done', 'message': 'Response complete'})
        
    except Exception as e:
        emit('error', {'error': str(e)})

@socketio.on('share_chat')
def handle_share(data):
    """Generate shareable link for a chat."""
    if 'user_id' not in session:
        emit('error', {'error': 'Not authenticated'})
        return
    
    chat_id = data.get('chat_id')
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM chat_history WHERE id = ? AND user_id = ?', (chat_id, session['user_id']))
    chat = cursor.fetchone()
    conn.close()
    
    if not chat:
        emit('error', {'error': 'Chat not found'})
        return
    
    # Generate simple share ID (in production, use UUID + encryption)
    import hashlib
    share_id = hashlib.md5(f"{chat_id}_{session['user_id']}".encode()).hexdigest()[:8]
    
    emit('share_link', {'share_id': share_id, 'chat_id': chat_id})

# Initialize
init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=True)
