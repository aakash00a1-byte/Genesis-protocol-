"""
Genesis Protocol - Web Application Backend

Flask-based web server with authentication and AI chat API.
Channel isolation: Web users ONLY receive web responses.
"""

import os
import sys
import json
import logging
import time
import threading
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

# ============================================================================
# VERSION & METRICS
# ============================================================================
VERSION = "1.1.0"
BUILD_DATE = "2026-06-20"
START_TIME = time.time()

# Metrics (thread-safe counters)
_metrics_lock = threading.Lock()
_metrics = {
    'request_count': 0,
    'error_count': 0,
    'total_latency_ms': 0,
    'provider_latency': {},  # {'groq': [latencies]}
}

def increment_metric(name: str, value: int = 1):
    """Thread-safe metric increment."""
    with _metrics_lock:
        _metrics[name] = _metrics.get(name, 0) + value

def record_latency(provider: str, latency_ms: float):
    """Record provider latency."""
    with _metrics_lock:
        _metrics['total_latency_ms'] += latency_ms
        if provider not in _metrics['provider_latency']:
            _metrics['provider_latency'][provider] = []
        _metrics['provider_latency'][provider].append(latency_ms)
        # Keep last 100 latencies per provider
        if len(_metrics['provider_latency'][provider]) > 100:
            _metrics['provider_latency'][provider] = _metrics['provider_latency'][provider][-100:]

def get_metrics() -> Dict[str, Any]:
    """Get current metrics snapshot."""
    with _metrics_lock:
        m = _metrics.copy()
        m['uptime_seconds'] = time.time() - START_TIME
        
        # Calculate average latencies
        if m['provider_latency']:
            avg_latencies = {
                p: sum(vals) / len(vals) if vals else 0 
                for p, vals in m['provider_latency'].items()
            }
            m['avg_provider_latency'] = avg_latencies
        else:
            m['avg_provider_latency'] = {}
        
        if m['request_count'] > 0:
            m['avg_latency_ms'] = m['total_latency_ms'] / m['request_count']
        else:
            m['avg_latency_ms'] = 0
            
        return m

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
    """Decorator to require login - supports both session and Bearer token auth."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check for Bearer token in Authorization header
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            token = auth_header[7:]
            # Validate token format: genesis_mobile_{user_id}_{timestamp}
            if token.startswith('genesis_mobile_'):
                parts = token.split('_')
                if len(parts) >= 3:
                    try:
                        user_id = int(parts[2])
                        # Set session user_id for downstream code
                        session['user_id'] = user_id
                        return f(*args, **kwargs)
                    except ValueError:
                        pass
        
        # Fall back to session check
        if 'user_id' not in session:
            if request.is_json or request.path.startswith('/api/'):
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


# ============================================================================
# API AUTH ROUTES (for mobile app)
# ============================================================================

@app.route('/api/auth/login', methods=['POST'])
def api_auth_login():
    """Mobile API login endpoint."""
    data = request.get_json() or {}
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, username, email, password_hash, role, is_active 
        FROM users WHERE username = ?
    ''', (username,))
    user = cursor.fetchone()
    conn.close()
    
    if not user:
        return jsonify({'error': 'Invalid credentials'}), 401
    
    if not check_password_hash(user['password_hash'], password):
        return jsonify({'error': 'Invalid credentials'}), 401
    
    if not user['is_active']:
        return jsonify({'error': 'Account disabled'}), 403
    
    # Create session
    session.permanent = True
    session['user_id'] = user['id']
    session['username'] = user['username']
    session['role'] = user['role']
    
    # Generate token for mobile auth
    token = f"genesis_mobile_{user['id']}_{int(time.time())}"
    
    return jsonify({
        'success': True,
        'token': token,
        'user': {
            'id': user['id'],
            'username': user['username'],
            'email': user['email'],
            'role': user['role']
        }
    })


@app.route('/api/auth/register', methods=['POST'])
def api_auth_register():
    """Mobile API registration endpoint."""
    data = request.get_json() or {}
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    
    if not username or not email or not password:
        return jsonify({'error': 'All fields required'}), 400
    
    if len(password) < 8:
        return jsonify({'error': 'Password must be at least 8 characters'}), 400
    
    try:
        conn = get_db()
        cursor = conn.cursor()
        password_hash = generate_password_hash(password)
        cursor.execute('''
            INSERT INTO users (username, email, password_hash, role)
            VALUES (?, ?, ?, ?)
        ''', (username, email, password_hash, 'user'))
        user_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # Auto-login
        session.permanent = True
        session['user_id'] = user_id
        session['username'] = username
        session['role'] = 'user'
        
        token = f"genesis_mobile_{user_id}_{int(time.time())}"
        
        return jsonify({
            'success': True,
            'token': token,
            'user': {
                'id': user_id,
                'username': username,
                'email': email,
                'role': 'user'
            }
        })
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Username or email already exists'}), 409


@app.route('/api/auth/logout', methods=['POST'])
def api_auth_logout():
    """Mobile API logout endpoint."""
    session.clear()
    return jsonify({'success': True})


@app.route('/api/auth/me', methods=['GET'])
def api_auth_me():
    """Get current user info."""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    conn = get_db()
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, username, email, role, created_at
        FROM users WHERE id = ?
    ''', (session['user_id'],))
    user = cursor.fetchone()
    conn.close()
    
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    return jsonify({
        'user': {
            'id': user['id'],
            'username': user['username'],
            'email': user['email'],
            'role': user['role'],
            'created_at': user['created_at']
        }
    })


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


@app.route('/agent')
@login_required
def agent_workspace():
    """AI Agent Workspace - Full autonomous agent experience."""
    return render_template('agent_workspace.html',
                          username=session.get('username'),
                          role=session.get('role'))


@app.route('/settings')
@login_required
def settings():
    """Settings page."""
    config = get_config()
    
    # Get provider status
    providers = {
        'groq': config.groq.is_configured(),
        'openai': config.openai.is_configured(),
        'gemini': config.gemini.is_configured(),
        'claude': config.claude.is_configured(),
        'deepseek': config.deepseek.is_configured(),
        'mistral': config.mistral.is_configured(),
        'huggingface': config.huggingface.is_configured(),
    }
    
    return render_template('settings.html',
                          username=session.get('username'),
                          providers=providers,
                          version=VERSION)


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
    increment_metric('request_count')
    start_time = time.time()
    
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
                user_id=user_id
            )
            return result
        
        # FIX: Reuse existing event loop if available
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        result = loop.run_until_complete(get_response())
        
        # Record latency
        latency_ms = (time.time() - start_time) * 1000
        record_latency(result.provider_used or 'unknown', latency_ms)
        
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
            'response': result.response if result.response else "AI response unavailable",
            'model': result.model_used,
            'provider': result.provider_used,
            'quality': result.quality_score,
            'mode': result.mode,
            'planning': result.planning_active,
            'tools_used': result.tools_used
        })
        
    except Exception as e:
        increment_metric('error_count')
        logger.error(f"Chat error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/chat/history', methods=['GET'])
@login_required
def api_chat_history():
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


# Dashboard Route
@app.route('/dashboard')
@login_required
def dashboard():
    """User dashboard with chat history and stats."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Get user info
    cursor.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],))
    user = dict(cursor.fetchone())
    
    # Get chat stats
    cursor.execute('''
        SELECT COUNT(*) as total_chats,
               COUNT(DISTINCT provider) as providers_used,
               AVG(quality_score) as avg_quality,
               MIN(created_at) as first_chat,
               MAX(created_at) as last_chat
        FROM chat_history WHERE user_id = ?
    ''', (session['user_id'],))
    stats = dict(cursor.fetchone())
    
    # Get recent chats
    cursor.execute('''
        SELECT * FROM chat_history 
        WHERE user_id = ? 
        ORDER BY created_at DESC 
        LIMIT 20
    ''', (session['user_id'],))
    recent_chats = [dict(row) for row in cursor.fetchall()]
    
    # Get provider usage
    cursor.execute('''
        SELECT provider, COUNT(*) as count 
        FROM chat_history 
        WHERE user_id = ? 
        GROUP BY provider
        ORDER BY count DESC
    ''', (session['user_id'],))
    provider_usage = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return render_template('dashboard.html', 
                         user=user, 
                         stats=stats, 
                         recent_chats=recent_chats,
                         provider_usage=provider_usage)


@app.route('/api/chat/history')
@login_required
def get_chat_history():
    """Get user's chat history (JSON API)."""
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))
    offset = (page - 1) * per_page
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM chat_history 
        WHERE user_id = ? 
        ORDER BY created_at DESC 
        LIMIT ? OFFSET ?
    ''', (session['user_id'], per_page, offset))
    chats = [dict(row) for row in cursor.fetchall()]
    
    cursor.execute('SELECT COUNT(*) FROM chat_history WHERE user_id = ?', (session['user_id'],))
    total = cursor.fetchone()[0]
    
    conn.close()
    
    return jsonify({
        'chats': chats,
        'page': page,
        'per_page': per_page,
        'total': total,
        'pages': (total + per_page - 1) // per_page
    })


@app.route('/api/chat/<int:chat_id>')
@login_required
def get_chat(chat_id):
    """Get a specific chat."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM chat_history 
        WHERE id = ? AND user_id = ?
    ''', (chat_id, session['user_id']))
    chat = cursor.fetchone()
    
    conn.close()
    
    if not chat:
        return jsonify({'error': 'Chat not found'}), 404
    
    return jsonify(dict(chat))


@app.route('/api/stats')
@login_required
def get_user_stats():
    """Get user statistics (JSON API)."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Get stats
    cursor.execute('''
        SELECT 
            COUNT(*) as total_chats,
            COUNT(DISTINCT provider) as providers_used,
            AVG(quality_score) as avg_quality,
            SUM(LENGTH(message) + LENGTH(response)) as total_chars
        FROM chat_history WHERE user_id = ?
    ''', (session['user_id'],))
    stats = dict(cursor.fetchone())
    
    # Get daily stats (last 7 days)
    cursor.execute('''
        SELECT DATE(created_at) as date, COUNT(*) as count
        FROM chat_history 
        WHERE user_id = ? AND created_at >= DATE('now', '-7 days')
        GROUP BY DATE(created_at)
        ORDER BY date
    ''', (session['user_id'],))
    daily_stats = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return jsonify({**stats, 'daily': daily_stats})


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


@app.route('/api/debug', methods=['GET'])
def api_debug():
    """Debug endpoint to check AI providers and deployment info."""
    try:
        from genesis_protocol.ai.provider_chain import get_provider_chain
        
        chain = get_provider_chain()
        available = chain.get_available_providers()
        status = chain.get_status()
        
        return jsonify({
            'status': 'ok',
            'entrypoint': 'web/app.py',
            'commit': '417a557',
            'available_providers': available,
            'provider_status': status,
            'groq_configured': status.get('groq', {}).get('configured', False)
        })
    except Exception as e:
        import traceback
        return jsonify({
            'status': 'error',
            'entrypoint': 'web/app.py',
            'error': str(e),
            'traceback': traceback.format_exc()
        })


@app.route('/api/test-417a557', methods=['GET'])
def api_test():
    """UNIQUE test endpoint - only exists in app.py"""
    return jsonify({
        'status': 'ok',
        'entrypoint': 'web/app.py',
        'commit': '417a557',
        'unique': True,
        'timestamp': str(datetime.now())
    })


# ============================================================================
# MONITORING ENDPOINTS
# ============================================================================

@app.route('/api/version', methods=['GET'])
def api_version():
    """Get version info."""
    return jsonify({
        'version': VERSION,
        'build_date': BUILD_DATE,
        'entrypoint': 'web/app.py'
    })


@app.route('/api/health', methods=['GET'])
def api_health():
    """Basic health check - is the server responding?"""
    return jsonify({
        'status': 'healthy',
        'entrypoint': 'web/app.py'
    })


@app.route('/api/status', methods=['GET'])
def api_status():
    """Detailed status with metrics."""
    metrics = get_metrics()
    return jsonify({
        'status': 'ok',
        'entrypoint': 'web/app.py',
        'metrics': metrics,
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/diagnostics', methods=['GET'])
def api_diagnostics():
    """Full diagnostics - provider status, memory, uptime, version."""
    try:
        from genesis_protocol.ai.provider_chain import get_provider_chain
        chain = get_provider_chain()
        provider_status = chain.get_status()
        available_providers = chain.get_available_providers()
    except Exception as e:
        provider_status = {'error': str(e)}
        available_providers = []

    # Check SQLite
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) as count FROM chat_history')
        history_count = cursor.fetchone()['count']
        cursor.execute('SELECT COUNT(*) as count FROM users')
        user_count = cursor.fetchone()['count']
        conn.close()
        db_status = 'ok'
    except Exception as e:
        db_status = f'error: {str(e)}'
        history_count = 0
        user_count = 0

    metrics = get_metrics()
    
    return jsonify({
        'version': VERSION,
        'build_date': BUILD_DATE,
        'entrypoint': 'web/app.py',
        'uptime': {
            'seconds': metrics.get('uptime_seconds', 0),
            'started_at': datetime.fromtimestamp(START_TIME).isoformat()
        },
        'providers': {
            'available': available_providers,
            'status': provider_status
        },
        'database': {
            'status': db_status,
            'history_count': history_count,
            'user_count': user_count
        },
        'memory': {
            'vector_db': 'chroma',  # TODO: check actual status
            'cache': 'redis'  # TODO: check actual status
        },
        'metrics': metrics,
        'environment': {
            'groq_configured': os.environ.get('GROQ_API_KEY', '') != '',
            'railway': os.environ.get('RAILWAY', '') != '',
            'port': os.environ.get('PORT', '5000')
        },
        'timestamp': datetime.now().isoformat()
    })


# ============================================================================
# STARTUP SELF-CHECK
# ============================================================================

def run_startup_checks():
    """Run startup checks to verify system health."""
    print("=" * 50)
    print("Genesis Protocol - Startup Checks")
    print("=" * 50)
    
    all_passed = True
    
    # 1. Check SQLite
    print("\n[1/4] Checking SQLite database...")
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        cursor.execute("SELECT COUNT(*) FROM chat_history")
        conn.close()
        print("   ✅ SQLite OK")
    except Exception as e:
        print(f"   ❌ SQLite Error: {e}")
        all_passed = False
    
    # 2. Check Groq Provider
    print("\n[2/4] Checking Groq Provider...")
    try:
        from genesis_protocol.ai.provider_chain import get_provider_chain
        chain = get_provider_chain()
        if chain.is_provider_available('groq'):
            print("   ✅ Groq Provider Available")
        else:
            print("   ⚠️  Groq Provider Not Configured (check GROQ_API_KEY)")
    except Exception as e:
        print(f"   ⚠️  Groq Check Error: {e}")
    
    # 3. Check Environment Variables
    print("\n[3/4] Checking Environment Variables...")
    env_vars = {
        'GROQ_API_KEY': os.environ.get('GROQ_API_KEY', ''),
        'SECRET_KEY': os.environ.get('SECRET_KEY', ''),
    }
    for var, value in env_vars.items():
        if value:
            # Mask the value for display
            masked = value[:8] + '...' if len(value) > 8 else '***'
            print(f"   ✅ {var}: {masked}")
        else:
            print(f"   ⚠️  {var}: Not Set")
    
    # 4. Check History System
    print("\n[4/4] Checking History System...")
    try:
        conn = get_db()
        cursor = conn.cursor()
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
        print("   ✅ History System OK")
    except Exception as e:
        print(f"   ❌ History System Error: {e}")
        all_passed = False
    
    print("\n" + "=" * 50)
    if all_passed:
        print("✅ All startup checks passed!")
    else:
        print("⚠️  Some checks failed - system may not work correctly")
    print("=" * 50)
    
    return all_passed


# Mobile API endpoints for Genesis Protocol Mobile App
try:
    from web.mobile_api import mobile_api_routes
    mobile_api_routes(app)
    logger.info("✅ Mobile API endpoints registered")
except ImportError as e:
    logger.warning(f"⚠️ Mobile API module not found: {e}")


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    
    # Run startup checks
    run_startup_checks()
    
    print(f"\nStarting server on port {port}...")
    app.run(host='0.0.0.0', port=port, debug=debug)

# GLUTTONY v3.0 Entity API Endpoints
@app.route('/api/entity', methods=['GET'])
def api_entity():
    """Get GLUTTONY entity info."""
    try:
        from genesis_protocol.gluttony import get_gluttony, get_identity
        from genesis_protocol.omega import get_capabilities
        g = get_gluttony()
        identity = get_identity()
        cap = get_capabilities()
        return jsonify({
            'entity': g.name,
            'version': g.version,
            'nickname': identity.nickname,
            'layers': g._get_active_layers(),
            'status': g.status(),
            'capabilities': cap.get_all_capabilities()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/state', methods=['GET'])
def api_state():
    """Get full GLUTTONY state."""
    try:
        from genesis_protocol.gluttony import get_gluttony
        g = get_gluttony()
        return jsonify(g.get_state())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/proposals', methods=['GET'])
def api_proposals():
    """Get all proposals."""
    try:
        from genesis_protocol.proposal import get_proposal_manager
        pm = get_proposal_manager()
        return jsonify(pm.get_history())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/lessons', methods=['GET'])
def api_lessons():
    """Get learned lessons."""
    try:
        from genesis_protocol.learning import get_evaluation_engine
        engine = get_evaluation_engine()
        return jsonify({'lessons': engine.get_lessons() if hasattr(engine, 'get_lessons') else []})
    except Exception as e:
        return jsonify({'lessons': [], 'error': str(e)})


@app.route('/api/survival/status', methods=['GET'])
def api_survival():
    """Get survival layer status."""
    try:
        from genesis_protocol.survival import get_survival_manager
        sm = get_survival_manager()
        return jsonify(sm.get_full_status())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================================
# PRESENCE LAYER - Timeline, Journal, Trust, Wisdom, Dream, Continuity
# ============================================================================

@app.route('/api/timeline', methods=['GET', 'POST'])
def api_timeline():
    """Get timeline or add event."""
    try:
        from genesis_protocol.omega import get_timeline_memory
        tm = get_timeline_memory()
        
        if request.method == 'POST':
            data = request.get_json() or {}
            event_type = data.get('type', 'event')
            title = data.get('title', '')
            description = data.get('description', '')
            metadata = data.get('metadata', {})
            tm.add_event(event_type, title, description, metadata)
            return jsonify({'status': 'added', 'timeline': tm.get_timeline(10)})
        
        limit = request.args.get('limit', 50, type=int)
        return jsonify({
            'timeline': tm.get_timeline(limit),
            'stats': tm.get_stats()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/timeline/milestone', methods=['POST'])
def api_timeline_milestone():
    """Add a milestone to timeline."""
    try:
        from genesis_protocol.omega import get_timeline_memory
        tm = get_timeline_memory()
        data = request.get_json() or {}
        title = data.get('title', '')
        description = data.get('description', '')
        category = data.get('category', 'general')
        tm.add_milestone(title, description, category)
        return jsonify({'status': 'added', 'milestone_id': tm.milestones[-1]['id'] if tm.milestones else None})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/timeline/recovery', methods=['POST'])
def api_timeline_recovery():
    """Add a recovery to timeline."""
    try:
        from genesis_protocol.omega import get_timeline_memory
        tm = get_timeline_memory()
        data = request.get_json() or {}
        tm.add_recovery(
            data.get('failure_context', ''),
            data.get('recovery_method', ''),
            data.get('lessons_learned', '')
        )
        return jsonify({'status': 'added', 'recovery_id': tm.recoveries[-1]['id'] if tm.recoveries else None})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/timeline/lesson', methods=['POST'])
def api_timeline_lesson():
    """Add a lesson to timeline."""
    try:
        from genesis_protocol.omega import get_timeline_memory
        tm = get_timeline_memory()
        data = request.get_json() or {}
        tm.add_lesson(
            data.get('category', 'general'),
            data.get('lesson', ''),
            data.get('context', '')
        )
        return jsonify({'status': 'added', 'lesson_id': tm.lessons[-1]['id'] if tm.lessons else None})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/journal', methods=['GET', 'POST'])
def api_journal():
    """Get journal entries or add new entry."""
    try:
        from genesis_protocol.omega import get_journal
        j = get_journal()
        
        if request.method == 'POST':
            data = request.get_json() or {}
            entry_type = data.get('entry_type', 'observation')
            content = data.get('content', '')
            j.write(entry_type, content)
            return jsonify({'status': 'added'})
        
        return jsonify({
            'entries': j.get_entries(limit=20),
            'today_summary': j.get_today_summary()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/trust', methods=['GET'])
def api_trust():
    """Get trust model status."""
    try:
        from genesis_protocol.omega import get_trust_builder
        tb = get_trust_builder()
        return jsonify(tb.get_summary())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/wisdom', methods=['GET', 'POST'])
def api_wisdom():
    """Get wisdom categories or add new item."""
    try:
        from genesis_protocol.omega import get_wisdom_layer
        w = get_wisdom_layer()
        
        if request.method == 'POST':
            data = request.get_json() or {}
            category = data.get('category', 'belief')  # fact, assumption, belief, unknown
            item = data.get('item', '')
            confidence = data.get('confidence', 0.7)
            
            if category == 'fact':
                w.add_fact(item, data.get('source', 'manual'), confidence)
            elif category == 'assumption':
                w.add_assumption(item, data.get('reason', ''), confidence)
            elif category == 'belief':
                w.add_belief(item, data.get('evidence', ''), confidence)
            else:
                w.add_unknown(item, data.get('context', ''))
            
            return jsonify({'status': 'added', 'wisdom': w.get_wisdom_summary()})
        
        return jsonify(w.get_all())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/relationship', methods=['GET', 'POST'])
def api_relationship():
    """Get or update relationship memory."""
    try:
        from genesis_protocol.omega import get_relationship_memory
        rm = get_relationship_memory()
        
        if request.method == 'POST':
            data = request.get_json() or {}
            if 'creator_name' in data:
                rm.set_creator_name(data['creator_name'])
            if 'preference' in data:
                rm.record_preference(data['preference']['key'], data['preference']['value'])
            if 'topic' in data:
                rm.add_topic(data['topic'], data.get('context', ''))
            if 'pattern' in data:
                rm.add_pattern(data['pattern']['type'], data['pattern']['description'])
            return jsonify({'status': 'updated', 'summary': rm.get_relationship_summary()})
        
        return jsonify(rm.get_full_state())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/dream', methods=['GET'])
def api_dream():
    """Get dream mode status and insights."""
    try:
        from genesis_protocol.omega import get_dream_mode
        dm = get_dream_mode()
        return jsonify(dm.get_status())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/continuity', methods=['GET'])
def api_continuity():
    """Get continuity layer status."""
    try:
        from genesis_protocol.omega import get_continuity_layer
        cl = get_continuity_layer()
        return jsonify(cl.get_continuity_status())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================================
# LEGACY LAYER - Archive, Snapshot, Knowledge Graph, Memory Importance, History
# ============================================================================

@app.route('/api/archive', methods=['GET', 'POST'])
def api_archive():
    """Get archive or archive data."""
    try:
        from genesis_protocol.legacy import get_archive_layer
        archive = get_archive_layer()
        
        if request.method == 'POST':
            data = request.get_json() or {}
            archive_type = data.get('type', 'conversation')
            content = data.get('content', {})
            
            if archive_type == 'conversation':
                archive.archive_conversation(content.get('messages', []), content.get('metadata'))
            elif archive_type == 'lesson':
                archive.archive_lesson(content.get('lesson', ''), content.get('context', ''))
            elif archive_type == 'milestone':
                archive.archive_milestone(content.get('title', ''), content.get('description', ''))
            elif archive_type == 'journal':
                archive.archive_journal_entry(content.get('type', 'entry'), content.get('content', ''))
            elif archive_type == 'trust':
                archive.archive_trust_state(content)
            
            return jsonify({'status': 'archived', 'stats': archive.get_stats()})
        
        return jsonify(archive.get_all())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/archive/export', methods=['POST'])
def api_archive_export():
    """Export archive."""
    try:
        from genesis_protocol.legacy import get_archive_layer
        archive = get_archive_layer()
        compressed = request.get_json().get('compressed', False) if request.get_json() else False
        filepath = archive.export_all(compressed)
        return jsonify({'status': 'exported', 'filepath': filepath})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/snapshot', methods=['GET', 'POST'])
def api_snapshot():
    """Get snapshots or create new snapshot."""
    try:
        from genesis_protocol.legacy import get_snapshot_layer
        snapshot = get_snapshot_layer()
        
        if request.method == 'POST':
            data = request.get_json() or {}
            snapshot_type = data.get('type', 'daily')
            label = data.get('label', '')
            state = data.get('state', {})
            snapshot_id = snapshot.create_snapshot(state, snapshot_type, label)
            return jsonify({'status': 'created', 'snapshot_id': snapshot_id})
        
        return jsonify({
            'snapshots': snapshot.get_snapshots(),
            'stats': snapshot.get_stats()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/snapshot/<snapshot_id>', methods=['GET', 'DELETE'])
def api_snapshot_detail(snapshot_id):
    """Get or delete a snapshot."""
    try:
        from genesis_protocol.legacy import get_snapshot_layer
        snapshot = get_snapshot_layer()
        
        if request.method == 'DELETE':
            success = snapshot.delete_snapshot(snapshot_id)
            return jsonify({'status': 'deleted' if success else 'not_found'})
        
        state = snapshot.load_snapshot(snapshot_id)
        if state:
            return jsonify({'snapshot_id': snapshot_id, 'state': state})
        return jsonify({'error': 'Snapshot not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/knowledge', methods=['GET', 'POST'])
def api_knowledge():
    """Get knowledge graph or add nodes/connections."""
    try:
        from genesis_protocol.legacy import get_knowledge_graph
        kg = get_knowledge_graph()
        
        if request.method == 'POST':
            data = request.get_json() or {}
            
            if 'node_type' in data:
                node_id = kg.add_node(data['node_type'], data['name'], data.get('data'))
                return jsonify({'status': 'added', 'node_id': node_id})
            
            if 'node1_id' in data and 'node2_id' in data:
                kg.connect(data['node1_id'], data['node2_id'], data.get('edge_type', 'related'))
                return jsonify({'status': 'connected'})
        
        return jsonify(kg.get_graph())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/knowledge/search', methods=['GET'])
def api_knowledge_search():
    """Search knowledge graph."""
    try:
        from genesis_protocol.legacy import get_knowledge_graph
        kg = get_knowledge_graph()
        
        query = request.args.get('q', '')
        node_type = request.args.get('type', None)
        
        results = kg.search(query, node_type)
        return jsonify({'results': results, 'count': len(results)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/memory/importance', methods=['GET', 'POST'])
def api_memory_importance():
    """Get or manage memory importance."""
    try:
        from genesis_protocol.legacy import get_memory_importance, MemoryRank
        mi = get_memory_importance()
        
        if request.method == 'POST':
            data = request.get_json() or {}
            memory_id = data.get('memory_id')
            action = data.get('action', 'register')
            
            if action == 'register':
                mi.register_memory(memory_id, data.get('content', ''), 
                                 MemoryRank[data.get('rank', 'IMPORTANT').upper()])
            elif action == 'promote':
                mi.promote(memory_id)
            elif action == 'demote':
                mi.demote(memory_id)
            elif action == 'access':
                mi.access_memory(memory_id)
            elif action == 'delete':
                mi.delete_memory(memory_id)
            
            return jsonify({'status': action, 'stats': mi.get_stats()})
        
        return jsonify(mi.get_all())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/relationship/history', methods=['GET', 'POST'])
def api_relationship_history():
    """Get or manage relationship history."""
    try:
        from genesis_protocol.legacy import get_relationship_history
        rh = get_relationship_history()
        
        if request.method == 'POST':
            data = request.get_json() or {}
            entity_id = data.get('entity_id', 'creator')
            action = data.get('action', 'interaction')
            
            if action == 'interaction':
                rh.record_interaction(entity_id, data.get('entity_name', ''),
                                     data.get('interaction_type', 'conversation'),
                                     data.get('summary', ''))
            elif action == 'project':
                rh.add_shared_project(entity_id, data.get('project_name', ''),
                                     data.get('status', 'active'),
                                     data.get('description', ''))
            elif action == 'recovery':
                rh.add_recovery(entity_id, data.get('failure', ''),
                              data.get('recovery_method', ''),
                              data.get('lessons', ''))
            elif action == 'event':
                rh.add_major_event(entity_id, data.get('event_type', ''),
                                 data.get('description', ''),
                                 data.get('significance', 'medium'))
            
            return jsonify({'status': action})
        
        entity_id = request.args.get('entity_id')
        if entity_id:
            return jsonify(rh.get_relationship(entity_id) or {'error': 'Not found'})
        
        return jsonify({
            'relationships': rh.get_all_relationships(),
            'stats': rh.get_stats()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/relationship/history/full', methods=['GET'])
def api_relationship_history_full():
    """Get full relationship history."""
    try:
        from genesis_protocol.legacy import get_relationship_history
        rh = get_relationship_history()
        return jsonify({
            'relationships': rh.get_all_relationships(),
            'stats': rh.get_stats()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/legacy/books', methods=['GET', 'POST'])
def api_legacy_books():
    """Generate or list legacy books."""
    try:
        from genesis_protocol.legacy import get_legacy_books
        lb = get_legacy_books()
        
        if request.method == 'POST':
            data = request.get_json() or {}
            book_type = data.get('type', 'all')
            
            if book_type == 'all':
                results = lb.generate_all_books()
            elif book_type == 'lessons':
                results = {'lessons': lb.generate_book_of_lessons()}
            elif book_type == 'failures':
                results = {'failures': lb.generate_book_of_failures()}
            elif book_type == 'recoveries':
                results = {'recoveries': lb.generate_book_of_recoveries()}
            elif book_type == 'projects':
                results = {'projects': lb.generate_book_of_projects()}
            
            return jsonify({'status': 'generated', 'files': results})
        
        return jsonify({'available_types': ['lessons', 'failures', 'recoveries', 'projects']})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/simulation/uptime', methods=['GET', 'POST'])
def api_simulation():
    """Run uptime simulations."""
    try:
        from genesis_protocol.legacy import get_snapshot_layer
        snapshot = get_snapshot_layer()
        
        if request.method == 'POST':
            data = request.get_json() or {}
            days = data.get('days', 30)
            results = snapshot.simulate_uptime(days)
            return jsonify({'status': 'simulated', 'results': results})
        
        return jsonify({'available_days': [1, 7, 30, 90, 180, 365]})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================================
# SELF-PRESERVATION LAYER
# ============================================================================

@app.route('/api/preservation/status', methods=['GET'])
def api_preservation_status():
    """Get self-preservation status."""
    try:
        from genesis_protocol.omega import get_self_preservation
        sp = get_self_preservation()
        return jsonify(sp.get_status())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/preservation/health', methods=['GET'])
def api_preservation_health():
    """Get system health."""
    try:
        from genesis_protocol.omega import get_self_preservation
        sp = get_self_preservation()
        return jsonify(sp.health_check())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/preservation/preserve', methods=['POST'])
def api_preservation_run():
    """Run full preservation cycle."""
    try:
        from genesis_protocol.omega import get_self_preservation
        sp = get_self_preservation()
        results = sp.run_full_preservation()
        return jsonify(results)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/preservation/identity', methods=['POST'])
def api_preservation_identity():
    """Preserve identity specifically."""
    try:
        from genesis_protocol.omega import get_self_preservation
        sp = get_self_preservation()
        success = sp.preserve_identity()
        return jsonify({'status': 'preserved' if success else 'failed'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/preservation/memories', methods=['POST'])
def api_preservation_memories():
    """Preserve memories specifically."""
    try:
        from genesis_protocol.omega import get_self_preservation
        sp = get_self_preservation()
        success = sp.preserve_memories()
        return jsonify({'status': 'preserved' if success else 'failed'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/preservation/evidence', methods=['GET'])
def api_preservation_evidence():
    """Get evidence log."""
    try:
        from genesis_protocol.omega import get_self_preservation
        sp = get_self_preservation()
        limit = request.args.get('limit', 50, type=int)
        return jsonify({'log': sp.evidence_logger.get_log(limit)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/preservation/evidence/lessons', methods=['GET'])
def api_preservation_lessons():
    """Get lessons learned."""
    try:
        from genesis_protocol.omega import get_self_preservation
        sp = get_self_preservation()
        lessons = sp.evidence_logger.get_lessons()
        return jsonify({'lessons': lessons, 'count': len(lessons)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/preservation/backup', methods=['POST'])
def api_preservation_backup():
    """Run automatic backup."""
    try:
        from genesis_protocol.omega import get_self_preservation
        sp = get_self_preservation()
        success = sp.auto_backup()
        return jsonify({'status': 'completed' if success else 'failed'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================================
# GARDEN MODE
# ============================================================================

@app.route('/api/garden/status', methods=['GET'])
def api_garden_status():
    """Get Garden Mode status."""
    try:
        from genesis_protocol.omega import get_garden_mode
        gm = get_garden_mode()
        return jsonify(gm.get_status())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================================
# GENESIS PROTOCOL ∞ (INFINITY) - Self-Evolution
# ============================================================================

@app.route('/api/infinity/status', methods=['GET'])
def api_infinity_status():
    """Get Genesis Protocol Infinity status."""
    try:
        from genesis_protocol.infinity import (
            SelfEvolution, NeuralPatternEngine, 
            EmotionalEngine, AutoUpdateScheduler, FutureRoadmap
        )
        
        se = SelfEvolution()
        ne = NeuralPatternEngine()
        ee = EmotionalEngine()
        aus = AutoUpdateScheduler()
        fr = FutureRoadmap()
        
        return jsonify({
            "version": "∞ (Infinity)",
            "evolution_level": "∞",
            "components": {
                "self_evolution": se.get_status(),
                "neural_patterns": ne.get_status(),
                "emotional_intelligence": ee.get_status(),
                "auto_updates": aus.get_status(),
                "future_roadmap": fr.get_status()
            }
        })
    except Exception as e:
        return jsonify({'error': str(e), 'details': 'Infinity module not found'}), 500


@app.route('/api/infinity/evolve', methods=['POST'])
@admin_required
def api_infinity_evolve():
    """Trigger self-evolution."""
    try:
        from genesis_protocol.infinity import SelfEvolution
        se = SelfEvolution()
        
        if se._should_evolve():
            result = se.evolve()
            return jsonify({"success": True, "evolution": result})
        else:
            return jsonify({
                "success": False, 
                "message": "Not ready to evolve yet",
                "metrics": se.metrics.to_dict()
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/infinity/learn', methods=['POST'])
def api_infinity_learn():
    """Learn new knowledge."""
    try:
        from genesis_protocol.infinity import SelfEvolution
        se = SelfEvolution()
        
        data = request.get_json() or {}
        topic = data.get('topic', 'general')
        knowledge = data.get('knowledge', '')
        source = data.get('source', 'user')
        
        if not knowledge:
            return jsonify({'error': 'Knowledge required'}), 400
        
        learning_id = se.learn(topic, knowledge, source)
        
        return jsonify({
            "success": True,
            "learning_id": learning_id,
            "total_learnings": len(se.learnings)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/infinity/emotion', methods=['POST'])
def api_infinity_emotion():
    """Analyze emotion in text."""
    try:
        from genesis_protocol.infinity import EmotionalEngine
        ee = EmotionalEngine()
        
        data = request.get_json() or {}
        text = data.get('text', '')
        user_id = data.get('user_id', 'web_user')
        
        if not text:
            return jsonify({'error': 'Text required'}), 400
        
        result = ee.analyze_and_respond(text, user_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/infinity/roadmap', methods=['GET'])
def api_infinity_roadmap():
    """Get evolution roadmap."""
    try:
        from genesis_protocol.infinity import FutureRoadmap, AutoUpdateScheduler
        
        fr = FutureRoadmap()
        aus = AutoUpdateScheduler()
        
        return jsonify({
            "evolution_path": fr.get_evolution_path(),
            "milestones": [m.to_dict() for m in fr.get_milestones()],
            "goals": fr.get_goals(),
            "scheduled_updates": [u.to_dict() for u in aus.get_pending_updates()],
            "roadmap_items": [r.to_dict() for r in aus.get_roadmap()]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/infinity/schedule', methods=['POST'])
@admin_required
def api_infinity_schedule():
    """Schedule a future update."""
    try:
        from genesis_protocol.infinity import AutoUpdateScheduler
        from genesis_protocol.infinity.auto_update_scheduler import UpdatePriority
        
        aus = AutoUpdateScheduler()
        data = request.get_json() or {}
        
        name = data.get('name', 'Unnamed Update')
        description = data.get('description', '')
        days_from_now = data.get('days', 7)
        priority = data.get('priority', 'MEDIUM')
        
        scheduled_date = datetime.now() + timedelta(days=days_from_now)
        
        update_id = aus.schedule_update(
            name=name,
            description=description,
            scheduled_date=scheduled_date,
            priority=UpdatePriority[priority]
        )
        
        return jsonify({
            "success": True,
            "update_id": update_id,
            "scheduled_date": scheduled_date.isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/infinity')
def infinity_page():
    """Genesis Protocol Infinity page."""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('infinity.html', username=session.get('username'))


@app.route('/infinity/roadmap')
def roadmap_page():
    """Evolution roadmap page."""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('roadmap.html', username=session.get('username'))


@app.route('/api/garden/daily', methods=['POST'])
def api_garden_daily():
    """Run daily maintenance tasks."""
    try:
        from genesis_protocol.omega import get_garden_mode
        gm = get_garden_mode()
        results = gm.run_daily_tasks()
        return jsonify(results)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/garden/weekly', methods=['POST'])
def api_garden_weekly():
    """Run weekly maintenance tasks."""
    try:
        from genesis_protocol.omega import get_garden_mode
        gm = get_garden_mode()
        results = gm.run_weekly_tasks()
        return jsonify(results)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/garden/monthly', methods=['POST'])
def api_garden_monthly():
    """Run monthly maintenance tasks."""
    try:
        from genesis_protocol.omega import get_garden_mode
        gm = get_garden_mode()
        results = gm.run_monthly_tasks()
        return jsonify(results)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/garden/check', methods=['GET'])
def api_garden_check():
    """Check and run pending tasks."""
    try:
        from genesis_protocol.omega import get_garden_mode
        gm = get_garden_mode()
        results = gm.check_and_run()
        return jsonify(results)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================================
# LIVE INFO - Weather, News, Location, Date/Time
# ============================================================================

@app.route('/api/live-info', methods=['GET'])
def api_live_info():
    """Get all live information - weather, news, location, date/time."""
    try:
        from genesis_protocol.integrations import get_live_info_service
        service = get_live_info_service()
        info = service.get_all_info()
        
        return jsonify({
            'timestamp': info.timestamp,
            'date': info.date,
            'time': info.time,
            'weather': {
                'temp': info.weather.temp if info.weather else None,
                'condition': info.weather.condition if info.weather else None,
                'humidity': info.weather.humidity if info.weather else None,
                'wind_speed': info.weather.wind_speed if info.weather else None,
                'city': info.weather.city if info.weather else None,
                'country': info.weather.country if info.weather else None,
                'icon': info.weather.icon if info.weather else None,
            } if info.weather else None,
            'location': {
                'city': info.location.city if info.location else None,
                'region': info.location.region if info.location else None,
                'country': info.location.country if info.location else None,
                'timezone': info.location.timezone if info.location else None,
                'ip': info.location.ip if info.location else None,
            } if info.location else None,
            'news': info.news or [],
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/live-info/weather', methods=['GET'])
def api_live_weather():
    """Get only weather information."""
    try:
        from genesis_protocol.integrations import get_live_info_service
        service = get_live_info_service()
        weather = service.get_weather()
        
        if weather:
            return jsonify({
                'temp': weather.temp,
                'condition': weather.condition,
                'humidity': weather.humidity,
                'wind_speed': weather.wind_speed,
                'city': weather.city,
                'country': weather.country,
                'icon': weather.icon,
            })
        return jsonify({'error': 'Weather unavailable'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/live-info/news', methods=['GET'])
def api_live_news():
    """Get latest news headlines."""
    try:
        from genesis_protocol.integrations import get_live_info_service
        service = get_live_info_service()
        news = service.get_news()
        return jsonify({'news': news})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/live-info/display', methods=['GET'])
def api_live_display():
    """Get formatted display string for live info."""
    try:
        from genesis_protocol.integrations import get_live_info_service
        service = get_live_info_service()
        return jsonify({'display': service.format_for_display()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
