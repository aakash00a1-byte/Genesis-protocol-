"""
Genesis Protocol - Web Application Backend

Flask-based web server with authentication and AI chat API.
Channel isolation: Web users ONLY receive web responses.
"""

import os
import sys
import json
import logging
from datetime import datetime, timedelta
from functools import wraps
from typing import Optional, Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, request, jsonify, session, render_template, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3

# Import channel isolation
from genesis_protocol.core.channel import Channel, get_channel_isolation

# Initialize Flask app
app = Flask(__name__, 
            template_folder='templates',
            static_folder='static')
app.secret_key = os.environ.get('SECRET_KEY', 'genesis-secret-key-change-in-production')
app.permanent_session_lifetime = timedelta(days=7)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database setup
DATABASE = 'genesis.db'


def get_db():
    """Get database connection."""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize database tables."""
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
            usage_count INTEGER DEFAULT 0
        )
    ''')
    
    # Chat history table
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
    
    # Request logs table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS request_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            provider TEXT,
            model TEXT,
            intent TEXT,
            status TEXT,
            latency_ms INTEGER,
            error TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Create default admin user if not exists
    cursor.execute('SELECT id FROM users WHERE role = "admin"')
    if not cursor.fetchone():
        admin_hash = generate_password_hash(os.environ.get('ADMIN_PASSWORD', 'genesis-admin-2024'))
        cursor.execute('''
            INSERT INTO users (username, email, password_hash, role)
            VALUES (?, ?, ?, ?)
        ''', ('admin', 'admin@genesis.ai', admin_hash, 'admin'))
        logger.info("Default admin user created")
    
    conn.commit()
    conn.close()
    logger.info("Database initialized")


# Authentication decorators
def login_required(f):
    """Decorator to require login."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.is_json:
                return jsonify({'error': 'Unauthorized', 'login_required': True}), 401
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """Decorator to require admin role."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if request.is_json:
                return jsonify({'error': 'Unauthorized'}), 401
            return redirect(url_for('login'))
        if session.get('role') != 'admin':
            if request.is_json:
                return jsonify({'error': 'Admin access required'}), 403
            return redirect(url_for('chat'))
        return f(*args, **kwargs)
    return decorated_function


# Authentication routes
@app.route('/login', methods=['GET', 'POST'])
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
        conn.close()
        
        if user and check_password_hash(user['password_hash'], password):
            if not user['is_active']:
                return jsonify({'error': 'Account disabled'}), 403
            
            session.permanent = True
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            
            # Update last login
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?', (user['id'],))
            conn.commit()
            conn.close()
            
            logger.info(f"User {username} logged in")
            
            if request.is_json:
                return jsonify({'success': True, 'redirect': '/chat', 'role': user['role']})
            return redirect(url_for('chat'))
        
        if request.is_json:
            return jsonify({'error': 'Invalid credentials'}), 401
        return render_template('login.html', error='Invalid credentials')
    
    if 'user_id' in session:
        return redirect(url_for('chat'))
    
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    """User registration."""
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')
        
        if not username or not email or not password:
            return jsonify({'error': 'All fields required'}), 400
        
        if len(password) < 6:
            return jsonify({'error': 'Password must be at least 6 characters'}), 400
        
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO users (username, email, password_hash, role)
                VALUES (?, ?, ?, ?)
            ''', (username, email, generate_password_hash(password), 'user'))
            conn.commit()
            conn.close()
            
            logger.info(f"User {username} registered")
            
            if request.is_json:
                return jsonify({'success': True, 'redirect': '/login'})
            return redirect(url_for('login'))
            
        except sqlite3.IntegrityError:
            return jsonify({'error': 'Username or email already exists'}), 400
    
    return render_template('register.html')


@app.route('/logout')
def logout():
    """User logout."""
    username = session.get('username')
    session.clear()
    logger.info(f"User {username} logged out")
    return redirect(url_for('login'))


# Main routes
@app.route('/')
def index():
    """Homepage."""
    if 'user_id' in session:
        return redirect(url_for('chat'))
    return render_template('index.html')


@app.route('/chat')
@login_required
def chat():
    """Chat interface."""
    return render_template('chat.html', 
                          username=session.get('username'),
                          role=session.get('role'))


@app.route('/admin')
@admin_required
def admin():
    """Admin dashboard."""
    return render_template('admin.html',
                          username=session.get('username'))


# API Routes
@app.route('/api/chat', methods=['POST'])
@login_required
def api_chat():
    """Chat API endpoint - WEB CHANNEL ONLY."""
<<<<<<< Updated upstream
    data = request.get_json()
    message = data.get('message', '')
=======
    # Support both JSON and FormData
    if request.is_json:
        data = request.get_json()
        message = data.get('message', '')
        provider = data.get('provider', 'groq')
        model = data.get('model', 'llama-3.3-70b-versatile')
    else:
        message = request.form.get('message', '')
        provider = request.form.get('provider', 'groq')
        model = request.form.get('model', 'llama-3.3-70b-versatile')
>>>>>>> Stashed changes
    
    if not message:
        return jsonify({'error': 'Message required'}), 400
    
    user_id = session['user_id']
    
    # Set channel isolation - WEB ONLY
    channel_isolation = get_channel_isolation()
    channel_isolation.set_channel(Channel.WEB)
    channel_isolation.log_channel_activity(Channel.WEB, "chat_request", f"User {user_id} using {provider}/{model}")
    
    # Check rate limit (100 messages per day for non-admin)
    if session.get('role') != 'admin':
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) FROM chat_history 
            WHERE user_id = ? AND created_at > datetime('now', '-1 day')
        ''', (user_id,))
        count = cursor.fetchone()[0]
        conn.close()
        
        if count >= 100:
            return jsonify({'error': 'Rate limit exceeded. Try again tomorrow.'}), 429
    
    try:
        # Import and use Genesis Agent
        import asyncio
        from genesis_protocol.ai.agent import get_genesis_agent
        
        async def get_response():
            agent = get_genesis_agent()
            result = await agent.process(
                message, 
                chat_id=user_id, 
                user_id=user_id,
                provider=provider,
                model=model
            )
            return result
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(get_response())
        loop.close()
        
        # Store in database
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO chat_history (user_id, message, response, model_used, provider, quality_score, mode)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, message, result.response, result.model_used, result.provider_used, 
              result.quality_score, result.mode))
        
        # Increment usage count
        cursor.execute('UPDATE users SET usage_count = usage_count + 1 WHERE id = ?', (user_id,))
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'response': result.response,
            'model': result.model_used,
            'provider': result.provider_used,
            'quality': result.quality_score,
            'mode': result.mode,
            'planning': result.planning_active,
            'tools_used': result.tools_used
        })
        
    except Exception as e:
        logger.error(f"Chat error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/history', methods=['GET'])
@login_required
def api_history():
    """Get chat history - WEB CHANNEL ONLY."""
    user_id = session['user_id']
    limit = request.args.get('limit', 50, type=int)
    
    # Set channel isolation - WEB ONLY
    channel_isolation = get_channel_isolation()
    channel_isolation.set_channel(Channel.WEB)
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT message, response, model_used, created_at, 'web' as channel
        FROM chat_history 
        WHERE user_id = ? 
        ORDER BY created_at DESC 
        LIMIT ?
    ''', (user_id, limit))
    
    history = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify({'history': history, 'channel': 'web'})


@app.route('/api/admin/stats', methods=['GET'])
@admin_required
def api_admin_stats():
    """Get system statistics for admin."""
    conn = get_db()
    cursor = conn.cursor()
    
    # User stats
    cursor.execute('SELECT COUNT(*) as total, SUM(usage_count) as usage FROM users')
    user_stats = dict(cursor.fetchone())
    
    # Request logs
    cursor.execute('''
        SELECT provider, model, COUNT(*) as count, AVG(latency_ms) as avg_latency
        FROM request_logs 
        WHERE created_at > datetime('now', '-24 hours')
        GROUP BY provider, model
    ''')
    model_usage = [dict(row) for row in cursor.fetchall()]
    
    # Recent errors
    cursor.execute('''
        SELECT error, COUNT(*) as count 
        FROM request_logs 
        WHERE status = 'failed' AND created_at > datetime('now', '-24 hours')
        GROUP BY error
        ORDER BY count DESC
        LIMIT 10
    ''')
    recent_errors = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return jsonify({
        'users': user_stats,
        'model_usage': model_usage,
        'recent_errors': recent_errors
    })


@app.route('/api/admin/users', methods=['GET'])
@admin_required
def api_admin_users():
    """Get all users for admin."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, username, email, role, created_at, last_login, usage_count, is_active
        FROM users ORDER BY created_at DESC
    ''')
    users = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({'users': users})


@app.route('/api/admin/users/<int:user_id>/toggle', methods=['POST'])
@admin_required
def api_admin_toggle_user(user_id):
    """Toggle user active status."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET is_active = NOT is_active WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/admin/logs', methods=['GET'])
@admin_required
def api_admin_logs():
    """Get request logs for admin."""
    limit = request.args.get('limit', 100, type=int)
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT r.*, u.username 
        FROM request_logs r 
        LEFT JOIN users u ON r.user_id = u.id
        ORDER BY r.created_at DESC 
        LIMIT ?
    ''', (limit,))
    logs = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify({'logs': logs})


# Error handlers
@app.errorhandler(404)
def not_found(e):
    if request.is_json:
        return jsonify({'error': 'Not found'}), 404
    return render_template('error.html', error='Page not found'), 404


@app.errorhandler(500)
def server_error(e):
    if request.is_json:
        return jsonify({'error': 'Server error'}), 500
    return render_template('error.html', error='Server error'), 500


# Initialize database on startup
init_db()


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug)