"""
Genesis Protocol v3 - Production Web Application

Complete platform with:
- Authentication system
- Chat interface
- Voice assistant
- Admin dashboard
- Channel isolation
- Production security
"""

import os
import sys
import json
import logging
import sqlite3
import secrets
from datetime import datetime, timedelta
from functools import wraps
from typing import Optional, Dict, Any

# Load environment variables from .env file
from pathlib import Path
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

from flask import Flask, request, jsonify, session, render_template, redirect, url_for, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from flask_session import Session

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask
app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_urlsafe(32))
app.permanent_session_lifetime = timedelta(days=7)

# Flask-Session configuration for persistent sessions
app.config['SESSION_TYPE'] = os.environ.get('SESSION_TYPE', 'filesystem')
app.config['SESSION_FILE_DIR'] = os.environ.get('SESSION_FILE_DIR', '/tmp/flask_session')
app.config['SESSION_PERMANENT'] = True
app.config['SESSION_USE_SIGNER'] = True
Session(app)

DATABASE = os.environ.get('DATABASE_URL', 'genesis.db')


def get_db():
    """Get database connection."""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize all database tables."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Users table
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
            is_verified INTEGER DEFAULT 0,
            usage_count INTEGER DEFAULT 0,
            theme TEXT DEFAULT 'dark',
            language TEXT DEFAULT 'en',
            settings TEXT DEFAULT '{}'
        )
    ''')
    
    # Sessions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            session_token TEXT UNIQUE NOT NULL,
            ip_address TEXT,
            user_agent TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Conversations table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_archived INTEGER DEFAULT 0
        )
    ''')
    
    # Messages table
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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Password resets
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS password_resets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            used INTEGER DEFAULT 0
        )
    ''')
    
    # Login attempts
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS login_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip_address TEXT NOT NULL,
            success INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create default admin
    cursor.execute('SELECT id FROM users WHERE role = "admin"')
    if not cursor.fetchone():
        admin_password = os.environ.get('ADMIN_PASSWORD', secrets.token_urlsafe(16))
        cursor.execute('''
            INSERT INTO users (username, email, password_hash, role, is_verified)
            VALUES (?, ?, ?, ?, ?)
        ''', ('admin', 'admin@genesis.ai', generate_password_hash(admin_password), 'admin', 1))
        logger.info(f"Admin created. Change password in production!")
    
    conn.commit()
    conn.close()
    logger.info("Database initialized")


# ============ Authentication ============

def login_required(f):
    """Decorator for login requirement."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            if request.is_json:
                return jsonify({'error': 'Unauthorized'}), 401
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    """Decorator for admin requirement."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin':
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def rate_limit(max_attempts=5, window_minutes=15):
    """Rate limiting decorator."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            ip = request.remote_addr
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT COUNT(*) FROM login_attempts 
                WHERE ip_address = ? AND success = 0 
                AND created_at > datetime('now', '-' || ? || ' minutes')
            ''', (ip, window_minutes))
            count = cursor.fetchone()[0]
            conn.close()
            
            if count >= max_attempts:
                return jsonify({'error': 'Too many attempts. Try again later.'}), 429
            return f(*args, **kwargs)
        return decorated
    return decorator


# ============ Routes ============

@app.route('/')
def index():
    """Homepage."""
    if 'user_id' in session:
        return redirect(url_for('chat'))
    return render_template('index_v4.html')


@app.route('/login', methods=['GET', 'POST'])
@rate_limit()
def login():
    """User login."""
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            return jsonify({'error': 'Username and password required'}), 400
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, username, password_hash, role, is_active 
            FROM users WHERE username = ?
        ''', (username,))
        user = cursor.fetchone()
        
        # Log attempt
        success = user and check_password_hash(user['password_hash'], password)
        cursor.execute('INSERT INTO login_attempts (ip_address, success) VALUES (?, ?)',
                      (request.remote_addr, 1 if success else 0))
        conn.commit()
        
        if not user or not success:
            conn.close()
            return jsonify({'error': 'Invalid credentials'}), 401
        
        if not user['is_active']:
            conn.close()
            return jsonify({'error': 'Account disabled'}), 403
        
        # Create session
        session_token = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(days=7)
        
        cursor.execute('''
            INSERT INTO sessions (user_id, session_token, ip_address, user_agent, expires_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (user['id'], session_token, request.remote_addr, request.user_agent.string, expires_at))
        cursor.execute('UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?', (user['id'],))
        conn.commit()
        conn.close()
        
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['role'] = user['role']
        session['session_token'] = session_token
        
        logger.info(f"User {username} logged in from {request.remote_addr}")
        
        return jsonify({'success': True, 'redirect': '/chat'})
    
    return render_template('login_v4.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    """User registration."""
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form
        username = data.get('username', '').strip()
        email = data.get('email', '').strip()
        password = data.get('password', '')
        
        # Validation
        if len(username) < 3 or len(username) > 20:
            return jsonify({'error': 'Username must be 3-20 characters'}), 400
        
        if not re.match(r'^[a-zA-Z0-9_]+$', username):
            return jsonify({'error': 'Username can only contain letters, numbers, underscore'}), 400
        
        import re
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            return jsonify({'error': 'Invalid email address'}), 400
        
        if len(password) < 8:
            return jsonify({'error': 'Password must be at least 8 characters'}), 400
        
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO users (username, email, password_hash, is_verified)
                VALUES (?, ?, ?, ?)
            ''', (username, email, generate_password_hash(password), 0))
            user_id = cursor.lastrowid
            conn.commit()
            
            # Create verification token
            token = secrets.token_urlsafe(32)
            expires_at = datetime.utcnow() + timedelta(days=1)
            cursor.execute('INSERT INTO email_verifications (user_id, token, expires_at) VALUES (?, ?, ?)',
                          (user_id, token, expires_at))
            conn.commit()
            
            # Send verification email
            try:
                from web.email_service import get_email_service
                email_service = get_email_service()
                verify_url = f"{request.host_url}verify/{token}"
                email_service.send_verification_email(email, username, verify_url)
                logger.info(f"Verification email sent to {email}")
            except Exception as e:
                logger.warning(f"Email service unavailable: {e}")
            
            conn.close()
            
            logger.info(f"User {username} registered")
            return jsonify({'success': True, 'redirect': '/login', 'message': 'Please check your email to verify your account'})
            
        except sqlite3.IntegrityError:
            return jsonify({'error': 'Username or email already exists'}), 400
    
    return render_template('register_v4.html')


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Request password reset."""
    if request.method == 'POST':
        email = request.get_json().get('email')
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT id, username FROM users WHERE email = ?', (email,))
        user = cursor.fetchone()
        
        if user:
            # Create reset token
            token = secrets.token_urlsafe(32)
            expires_at = datetime.utcnow() + timedelta(hours=1)
            cursor.execute('INSERT INTO password_resets (user_id, token, expires_at) VALUES (?, ?, ?)',
                          (user['id'], token, expires_at))
            conn.commit()
            
            # Send email
            try:
                from web.email_service import get_email_service
                email_service = get_email_service()
                reset_url = f"{request.host_url}reset-password/{token}"
                email_service.send_password_reset_email(email, user['username'], reset_url)
                logger.info(f"Password reset email sent to {email}")
            except Exception as e:
                logger.warning(f"Email service unavailable: {e}")
        
        conn.close()
        
        # Always return success to prevent email enumeration
        return jsonify({'success': True, 'message': 'If email exists, reset instructions sent'})
    
    return render_template('forgot_password.html')


@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Reset password with token."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT user_id FROM password_resets 
        WHERE token = ? AND used = 0 AND expires_at > CURRENT_TIMESTAMP
    ''', (token,))
    reset = cursor.fetchone()
    
    if not reset:
        conn.close()
        return render_template('error.html', error='Invalid or expired reset link'), 400
    
    if request.method == 'POST':
        password = request.get_json().get('password')
        
        if len(password) < 8:
            return jsonify({'error': 'Password must be at least 8 characters'}), 400
        
        cursor.execute('UPDATE users SET password_hash = ? WHERE id = ?',
                      (generate_password_hash(password), reset['user_id']))
        cursor.execute('UPDATE password_resets SET used = 1 WHERE token = ?', (token,))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'redirect': '/login'})
    
    conn.close()
    return render_template('reset_password.html', token=token)


@app.route('/verify/<token>')
def verify_email(token):
    """Verify email with token."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT user_id FROM email_verifications 
        WHERE token = ? AND verified = 0 AND expires_at > CURRENT_TIMESTAMP
    ''', (token,))
    verification = cursor.fetchone()
    
    if not verification:
        conn.close()
        return render_template('error.html', error='Invalid or expired verification link'), 400
    
    cursor.execute('UPDATE users SET is_verified = 1 WHERE id = ?', (verification['user_id'],))
    cursor.execute('UPDATE email_verifications SET verified = 1 WHERE token = ?', (token,))
    conn.commit()
    conn.close()
    
    # Send welcome email
    try:
        from web.email_service import get_email_service
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT username, email FROM users WHERE id = ?', (verification['user_id'],))
        user = cursor.fetchone()
        if user:
            email_service = get_email_service()
            email_service.send_welcome_email(user['email'], user['username'])
        conn.close()
    except Exception as e:
        logger.warning(f"Welcome email failed: {e}")
    
    return render_template('verification_success.html')


@app.route('/logout')
def logout():
    """User logout."""
    if 'session_token' in session:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('UPDATE sessions SET is_active = 0 WHERE session_token = ?', (session['session_token'],))
        conn.commit()
        conn.close()
    
    session.clear()
    return redirect(url_for('login'))


@app.route('/chat')
@login_required
def chat():
    """Chat interface."""
    user_id = session.get('user_id')
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Get recent messages for this user - match actual schema
    cursor.execute('''
        SELECT id, message, response, model_used, mode, quality_score, created_at
        FROM chat_history
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT 50
    ''', (user_id,))
    
    messages = []
    for row in cursor.fetchall():
        # Format: each row has both user message and AI response
        if row[1]:  # User message exists
            messages.append({
                'id': row[0],
                'content': row[1],
                'is_user': True,
                'created_at': datetime.fromisoformat(row[6]) if row[6] else None
            })
        if row[2]:  # AI response exists
            messages.append({
                'id': row[0] + 1,
                'content': row[2],
                'is_user': False,
                'model': row[3],
                'mode': row[4],
                'created_at': datetime.fromisoformat(row[6]) if row[6] else None
            })
    
    conn.close()
    
    return render_template('chat_v4.html', 
                          messages=messages[::-1],
                          username=session.get('username'),
                          role=session.get('role'))


@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    """User settings."""
    if request.method == 'POST':
        data = request.get_json()
        theme = data.get('theme', 'dark')
        language = data.get('language', 'en')
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET theme = ?, language = ? WHERE id = ?',
                      (theme, language, session['user_id']))
        conn.commit()
        conn.close()
        
        session['theme'] = theme
        return jsonify({'success': True})
    
    return render_template('settings_v4.html')


@app.route('/admin')
@admin_required
def admin():
    """Admin dashboard."""
    return render_template('admin_v4.html', username=session.get('username'))


# ============ API Endpoints ============

@app.route('/api/conversations', methods=['GET', 'POST'])
@login_required
def api_conversations():
    """Get or create conversations."""
    user_id = session['user_id']
    
    if request.method == 'POST':
        title = request.get_json().get('title', f"Chat {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}")
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('INSERT INTO conversations (user_id, title) VALUES (?, ?)', (user_id, title))
        conversation_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'conversation_id': conversation_id})
    
    # GET - list conversations
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT c.*, (SELECT COUNT(*) FROM messages WHERE conversation_id = c.id) as message_count
        FROM conversations c WHERE c.user_id = ? ORDER BY c.updated_at DESC
    ''', (user_id,))
    conversations = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify({'conversations': conversations})


@app.route('/api/conversations/<int:conv_id>', methods=['GET', 'DELETE'])
@login_required
def api_conversation(conv_id):
    """Get or delete conversation."""
    user_id = session['user_id']
    
    conn = get_db()
    cursor = conn.cursor()
    
    if request.method == 'DELETE':
        cursor.execute('DELETE FROM messages WHERE conversation_id = ?', (conv_id,))
        cursor.execute('DELETE FROM conversations WHERE id = ? AND user_id = ?', (conv_id, user_id))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    
    # GET
    cursor.execute('SELECT * FROM conversations WHERE id = ? AND user_id = ?', (conv_id, user_id))
    conversation = cursor.fetchone()
    
    if not conversation:
        conn.close()
        return jsonify({'error': 'Not found'}), 404
    
    cursor.execute('SELECT * FROM messages WHERE conversation_id = ? ORDER BY created_at ASC', (conv_id,))
    messages = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify({'conversation': dict(conversation), 'messages': messages})


@app.route('/api/chat', methods=['POST'])
@login_required
def api_chat():
    """Chat API endpoint."""
    data = request.get_json()
    message = data.get('message', '')
    conversation_id = data.get('conversation_id')
    
    if not message:
        return jsonify({'error': 'Message required'}), 400
    
    user_id = session['user_id']
    
    # Get or create conversation
    if not conversation_id:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('INSERT INTO conversations (user_id, title) VALUES (?, ?)',
                      (user_id, message[:50] + '...' if len(message) > 50 else message))
        conversation_id = cursor.lastrowid
        conn.commit()
        conn.close()
    
    # Add user message
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO messages (conversation_id, role, content) VALUES (?, 'user', ?)
    ''', (conversation_id, message))
    conn.commit()
    conn.close()
    
    # Generate AI response
    response_text = "Genesis AI response placeholder. Connect to AI backend for real responses."
    
    # Try to use real AI
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from genesis_protocol.ai.agent import get_genesis_agent
        
        import asyncio
        
        # Use a persistent event loop to avoid "bound to different event loop" errors
        if not hasattr(app, '_ai_event_loop') or app._ai_event_loop.is_closed():
            app._ai_event_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(app._ai_event_loop)
        
        async def get_response():
            agent = get_genesis_agent()
            result = await agent.process(message, chat_id=user_id, user_id=user_id)
            return result
        
        result = app._ai_event_loop.run_until_complete(get_response())
        
        if result.success:
            # Extract content from AIResponse object
            if hasattr(result.response, 'content'):
                response_text = result.response.content
            else:
                response_text = str(result.response)
            model = result.model_used
            provider = result.provider_used
            quality = result.quality_score
            mode = result.mode
        else:
            model, provider, quality, mode = "fallback", "none", 0.0, "normal"
            
    except Exception as e:
        logger.warning(f"AI backend unavailable: {e}")
        model, provider, quality, mode = "standalone", "none", 0.0, "normal"
    
    # Add assistant message
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO messages (conversation_id, role, content, model, provider, quality_score, mode)
        VALUES (?, 'assistant', ?, ?, ?, ?, ?)
    ''', (conversation_id, response_text, model, provider, quality, mode))
    cursor.execute('UPDATE users SET usage_count = usage_count + 1 WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True,
        'response': response_text,
        'conversation_id': conversation_id,
        'model': model,
        'provider': provider
    })


@app.route('/api/history')
@login_required
def api_history():
    """Get chat history."""
    user_id = session['user_id']
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT m.* FROM messages m
        JOIN conversations c ON m.conversation_id = c.id
        WHERE c.user_id = ? ORDER BY m.created_at DESC LIMIT 100
    ''', (user_id,))
    history = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify({'history': history})


# ============ Image Upload API ============
@app.route('/api/upload', methods=['POST'])
@login_required
def api_upload():
    """Handle image upload and analysis."""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Validate file type
        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
        ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
        if ext not in allowed_extensions:
            return jsonify({'error': f'File type not allowed. Allowed: {allowed_extensions}'}), 400
        
        # Read file
        image_data = file.read()
        file_size = len(image_data) / (1024 * 1024)  # MB
        
        # Size limit (5MB)
        if file_size > 5:
            return jsonify({'error': 'File too large. Max 5MB allowed'}), 400
        
        # Process image using AI
        try:
            import io
            from genesis_protocol.processors.image_processor import ImageProcessor
            
            processor = ImageProcessor()
            image_stream = io.BytesIO(image_data)
            image_stream.filename = file.filename
            
            # Run async processor synchronously
            import asyncio
            result = asyncio.run(processor.analyze(image_stream))
            
            if result:
                return jsonify({
                    'success': True,
                    'analysis': result.get('description', 'Image analyzed'),
                    'full_result': result
                })
            else:
                return jsonify({
                    'success': True,
                    'analysis': 'Image received but analysis unavailable',
                    'file_size': f'{file_size:.2f}MB'
                })
        except Exception as e:
            logger.error(f"Image processing error: {e}")
            return jsonify({
                'success': True,
                'message': 'Image uploaded successfully',
                'file_size': f'{file_size:.2f}MB'
            })
            
    except Exception as e:
        logger.error(f"Upload error: {e}")
        return jsonify({'error': str(e)}), 500


# ============ Voice Processing API ============
@app.route('/api/voice', methods=['POST'])
@login_required
def api_voice():
    """Handle voice/audio processing (STT)."""
    try:
        if 'audio' not in request.files and (request.get_json(silent=True) or {}).get('audio_data') is None:
            return jsonify({'error': 'No audio provided'}), 400
        
        # Handle file upload
        if 'audio' in request.files:
            audio_file = request.files['audio']
            audio_data = audio_file.read()
        else:
            # Handle base64 audio data
            import base64
            data = request.get_json()
            audio_b64 = data.get('audio_data', '')
            audio_data = base64.b64decode(audio_b64)
        
        # Process audio using voice processor
        try:
            import io
            from genesis_protocol.processors.voice_processor import VoiceProcessor
            
            processor = VoiceProcessor()
            audio_stream = io.BytesIO(audio_data)
            
            # Run async processor synchronously
            import asyncio
            transcript = asyncio.run(processor.transcribe(audio_stream))
            
            if transcript:
                return jsonify({
                    'success': True,
                    'transcript': transcript
                })
            else:
                return jsonify({
                    'success': False,
                    'error': 'Transcription failed'
                }), 500
        except Exception as e:
            logger.error(f"Voice processing error: {e}")
            return jsonify({
                'success': False,
                'error': f'Voice processing unavailable: {str(e)}'
            }), 500
            
    except Exception as e:
        logger.error(f"Voice API error: {e}")
        return jsonify({'error': str(e)}), 500


# Admin APIs
@app.route('/api/admin/stats')
@admin_required
def api_admin_stats():
    """System statistics."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) as total, SUM(usage_count) as usage FROM users')
    users = dict(cursor.fetchone())
    
    cursor.execute('SELECT COUNT(*) as total_conversations FROM conversations')
    convs = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) as total_messages FROM messages')
    msgs = cursor.fetchone()[0]
    
    cursor.execute('''
        SELECT model, COUNT(*) as count FROM messages 
        WHERE model IS NOT NULL GROUP BY model
    ''')
    model_usage = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return jsonify({
        'users': users,
        'conversations': convs,
        'messages': msgs,
        'model_usage': model_usage
    })


@app.route('/api/admin/users')
@admin_required
def api_admin_users():
    """Get all users."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, username, email, role, created_at, last_login, usage_count, is_active, is_verified
        FROM users ORDER BY created_at DESC
    ''')
    users = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({'users': users})


@app.route('/api/admin/users/<int:user_id>/toggle', methods=['POST'])
@admin_required
def api_admin_toggle_user(user_id):
    """Toggle user status."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET is_active = NOT is_active WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/admin/logs')
@admin_required
def api_admin_logs():
    """Get request logs."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT m.created_at, m.model, m.provider, m.role, c.username
        FROM messages m JOIN conversations c ON m.conversation_id = c.id
        ORDER BY m.created_at DESC LIMIT 100
    ''')
    logs = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({'logs': logs})


# Initialize database
init_db()


# ============ Health Check ============

@app.route('/health')
def health():
    """Health check endpoint for monitoring."""
    import sqlite3
    from datetime import datetime
    
    health_status = {
        'status': 'healthy',
        'version': '3.0.0',
        'timestamp': datetime.utcnow().isoformat(),
        'checks': {}
    }
    
    # Check database
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM users')
        cursor.fetchone()
        conn.close()
        health_status['checks']['database'] = 'ok'
    except Exception as e:
        health_status['checks']['database'] = f'error: {str(e)}'
        health_status['status'] = 'degraded'
    
    # Check AI backend
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from genesis_protocol.ai.agent import get_genesis_agent
        health_status['checks']['ai_backend'] = 'available'
    except Exception as e:
        health_status['checks']['ai_backend'] = 'unavailable'
        health_status['status'] = 'degraded'
    
    status_code = 200 if health_status['status'] == 'healthy' else 503
    return jsonify(health_status), status_code

@app.route('/status')
def status():
    """Detailed status endpoint."""
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM users')
        user_count = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM messages')
        message_count = cursor.fetchone()[0]
        conn.close()
        
        return jsonify({
            'status': 'operational',
            'service': 'Genesis Protocol',
            'version': '3.0.0',
            'database': 'connected',
            'users': user_count,
            'messages': message_count,
            'timestamp': datetime.utcnow().isoformat()
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'service': 'Genesis Protocol',
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)