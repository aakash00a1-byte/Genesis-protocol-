"""
Genesis Protocol - Standalone Web Server
For direct deployment to Railway/Render/VPS

This is a simplified standalone version that can be deployed
without complex dependencies.
"""

import os
import sys
import sqlite3
import logging
import time
import threading
import json
import requests
from datetime import datetime, timedelta
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, request, jsonify, session, render_template, redirect, url_for, Response

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Groq API Configuration
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

def get_groq_response(message, chat_history=None):
    """Get response from Groq API."""
    api_key = os.environ.get('GROQ_API_KEY')
    
    if not api_key:
        return None, "GROQ_API_KEY not configured", "none", 0.0
    
    # Get available models
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # Try llama-3.1-8b-instant first (fastest, cheapest)
    model = "llama-3.1-8b-instant"
    
    # Build messages
    messages = []
    
    # System prompt
    system_prompt = """You are Genesis AI, a helpful AI assistant. You are knowledgeable, friendly, and helpful.
Provide accurate and concise responses. If you don't know something, say so honestly."""
    
    if chat_history:
        # Include last 10 messages for context
        for msg in chat_history[-10:]:
            messages.append({"role": "user", "content": msg.get('message', '')})
            messages.append({"role": "assistant", "content": msg.get('response', '')})
    
    messages.insert(0, {"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": message})
    
    data = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 2048
    }
    
    try:
        response = requests.post(GROQ_API_URL, headers=headers, json=data, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            return result['choices'][0]['message']['content'], model, "groq", 1.0
        elif response.status_code == 401:
            return None, "Invalid Groq API key", "groq", 0.0
        elif response.status_code == 429:
            return None, "Groq rate limit exceeded", "groq", 0.0
        else:
            return None, f"Groq API error: {response.status_code}", "groq", 0.0
    except requests.exceptions.Timeout:
        return None, "Groq API timeout", "groq", 0.0
    except Exception as e:
        return None, f"Groq error: {str(e)}", "groq", 0.0

# ============================================================================
# VERSION & METRICS
# ============================================================================
VERSION = "1.2.0"
BUILD_DATE = "2026-06-18"
START_TIME = time.time()

# Metrics (thread-safe counters)
_metrics_lock = threading.Lock()
_metrics = {
    'request_count': 0,
    'error_count': 0,
    'total_latency_ms': 0,
    'provider_latency': {},
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
        if len(_metrics['provider_latency'][provider]) > 100:
            _metrics['provider_latency'][provider] = _metrics['provider_latency'][provider][-100:]

def get_metrics() -> dict:
    """Get current metrics snapshot."""
    with _metrics_lock:
        m = _metrics.copy()
        m['uptime_seconds'] = time.time() - START_TIME
        if m['provider_latency']:
            m['avg_provider_latency'] = {p: sum(v)/len(v) if v else 0 for p, v in m['provider_latency'].items()}
        else:
            m['avg_provider_latency'] = {}
        m['avg_latency_ms'] = m['total_latency_ms'] / m['request_count'] if m['request_count'] > 0 else 0
        return m

# Initialize Flask app
app = Flask(__name__, 
            template_folder='templates',
            static_folder='static')
app.secret_key = os.environ.get('SECRET_KEY', 'genesis-secret-key-2024')
app.permanent_session_lifetime = timedelta(days=7)

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
            return redirect(url_for('login'))
        if session.get('role') != 'admin':
            return redirect(url_for('chat'))
        return f(*args, **kwargs)
    return decorated_function


# Routes
@app.route('/')
def index():
    """Homepage."""
    if 'user_id' in session:
        return redirect(url_for('chat'))
    return render_template('index.html')


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
        cursor.execute('SELECT id, username, password_hash, role, is_active FROM users WHERE username = ?', (username,))
        user = cursor.fetchone()
        conn.close()
        
        if user and check_password_hash(user['password_hash'], password):
            if not user['is_active']:
                return jsonify({'error': 'Account disabled'}), 403
            
            session.permanent = True
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            
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
            cursor.execute('INSERT INTO users (username, email, password_hash, role) VALUES (?, ?, ?, ?)',
                         (username, email, generate_password_hash(password), 'user'))
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
    session.clear()
    return redirect(url_for('login'))


@app.route('/chat')
@login_required
def chat():
    """Chat interface."""
    return render_template('chat.html', 
                          username=session.get('username'),
                          role=session.get('role'))


@app.route('/settings')
@login_required
def settings():
    """Settings page."""
    return render_template('settings.html',
                          username=session.get('username'),
                          version=VERSION)


@app.route('/admin')
@admin_required
def admin():
    """Admin dashboard with real data."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Get system stats
    cursor.execute('SELECT COUNT(*) as total_users, SUM(usage_count) as total_usage FROM users')
    user_stats = dict(cursor.fetchone())
    
    cursor.execute('SELECT COUNT(*) as total_chats, AVG(quality_score) as avg_quality FROM chat_history')
    chat_stats = dict(cursor.fetchone())
    
    cursor.execute('SELECT provider, model, COUNT(*) as count FROM chat_history WHERE created_at > datetime("now", "-24 hours") GROUP BY provider, model')
    model_usage = [dict(row) for row in cursor.fetchall()]
    
    cursor.execute('SELECT id, username, email, role, created_at, last_login, usage_count, is_active FROM users ORDER BY created_at DESC')
    users = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return render_template('admin.html', 
                          username=session.get('username'),
                          user_stats=user_stats,
                          chat_stats=chat_stats,
                          model_usage=model_usage,
                          users=users)


# API Routes
@app.route('/api/chat', methods=['POST'])
@login_required
def api_chat():
    """Chat API endpoint."""
    data = request.get_json()
    message = data.get('message', '')
    
    if not message:
        return jsonify({'error': 'Message required'}), 400
    
    user_id = session['user_id']
    
    # Check rate limit
    if session.get('role') != 'admin':
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''SELECT COUNT(*) FROM chat_history WHERE user_id = ? AND created_at > datetime('now', '-1 day')''', (user_id,))
        count = cursor.fetchone()[0]
        conn.close()
        
        if count >= 100:
            return jsonify({'error': 'Rate limit exceeded. Try again tomorrow.'}), 429
    
    # Chat with Groq AI
    
    # Get chat history for context
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT message, response FROM chat_history WHERE user_id = ? ORDER BY created_at DESC LIMIT 10',
                 (user_id,))
    history = [dict(row) for row in cursor.fetchall()]
    conn.close()

    # Get response from Groq
    response_text, model_used, provider, quality = get_groq_response(message, history)
    mode = "normal"

    if response_text is None:
        response_text = "I apologize, but I am having trouble connecting to the AI service right now. Please try again in a few moments."
        model_used = "error"

    # Store in database
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO chat_history (user_id, message, response, model_used, provider, quality_score, mode)
                      VALUES (?, ?, ?, ?, ?, ?, ?)''',
                  (user_id, message, response_text, model_used, provider, quality, mode))
    cursor.execute('UPDATE users SET usage_count = usage_count + 1 WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    
    return jsonify({
        'success': True,
        'response': response_text,
        'model': model_used,
        'provider': provider,
        'quality': quality,
        'mode': mode
    })


@app.route('/api/history', methods=['GET'])
@login_required
def api_history():
    """Get chat history."""
    user_id = session['user_id']
    limit = request.args.get('limit', 50, type=int)
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT message, response, model_used, created_at FROM chat_history WHERE user_id = ? ORDER BY created_at DESC LIMIT ?',
                 (user_id, limit))
    history = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify({'history': history})


@app.route('/api/admin/stats', methods=['GET'])
@admin_required
def api_admin_stats():
    """Get system statistics."""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) as total, SUM(usage_count) as usage FROM users')
    user_stats = dict(cursor.fetchone())
    
    cursor.execute('SELECT provider, model, COUNT(*) as count FROM chat_history WHERE created_at > datetime("now", "-24 hours") GROUP BY provider, model')
    model_usage = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return jsonify({
        'users': user_stats,
        'model_usage': model_usage
    })


@app.route('/api/admin/users', methods=['GET'])
@admin_required
def api_admin_users():
    """Get all users."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT id, username, email, role, created_at, last_login, usage_count, is_active FROM users ORDER BY created_at DESC')
    users = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({'users': users})


@app.route('/dashboard')
@login_required
def dashboard():
    """User dashboard."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],))
    user = dict(cursor.fetchone())
    cursor.execute('''SELECT COUNT(*) as total, COUNT(DISTINCT provider) as providers,
                      AVG(quality_score) as avg_quality FROM chat_history WHERE user_id = ?''', (session['user_id'],))
    stats = dict(cursor.fetchone())
    cursor.execute('SELECT * FROM chat_history WHERE user_id = ? ORDER BY created_at DESC LIMIT 20', (session['user_id'],))
    recent = [dict(row) for row in cursor.fetchall()]
    cursor.execute('SELECT provider, COUNT(*) as count FROM chat_history WHERE user_id = ? GROUP BY provider', (session['user_id'],))
    providers = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return render_template('dashboard.html', user=user, stats=stats, recent_chats=recent, provider_usage=providers)


@app.route('/api/chat/history')
@login_required
def get_chat_history():
    """Get chat history."""
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 20))
    offset = (page - 1) * per_page
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM chat_history WHERE user_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?', (session['user_id'], per_page, offset))
    chats = [dict(row) for row in cursor.fetchall()]
    cursor.execute('SELECT COUNT(*) FROM chat_history WHERE user_id = ?', (session['user_id'],))
    total = cursor.fetchone()[0]
    conn.close()
    return jsonify({'chats': chats, 'page': page, 'total': total})


@app.route('/api/chat/<int:chat_id>')
@login_required
def get_chat(chat_id):
    """Get specific chat."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM chat_history WHERE id = ? AND user_id = ?', (chat_id, session['user_id']))
    chat = cursor.fetchone()
    conn.close()
    if not chat:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(dict(chat))


@app.route('/api/stats')
@login_required
def get_user_stats():
    """Get user stats."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) as total, AVG(quality_score) as avg_quality FROM chat_history WHERE user_id = ?', (session['user_id'],))
    stats = dict(cursor.fetchone())
    cursor.execute("SELECT DATE(created_at) as date, COUNT(*) as count FROM chat_history WHERE user_id = ? AND created_at >= DATE('now', '-7 days') GROUP BY DATE(created_at)", (session['user_id'],))
    daily = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify({**stats, 'daily': daily})


@app.route('/api/chat/stream')
@login_required
def chat_stream():
    """Streaming chat API endpoint."""
    from genesis_protocol.ai.provider_chain import get_provider_chain
    from genesis_protocol.core.channel import get_channel_isolation
    
    message = request.args.get('message', '')
    mode = request.args.get('mode', 'NORMAL')
    system = request.args.get('system', 'You are a helpful AI assistant.')
    
    if not message:
        return jsonify({'error': 'Message required'}), 400
    
    def generate():
        try:
            ai = get_provider_chain()
            channel = get_channel_isolation()
            channel.set_channel('web')
            
            # Yield streaming response
            for chunk in ai.call_stream(messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": message}
            ], user_input=message):
                if chunk:
                    yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            
            yield "data: [DONE]\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return Response(generate(), mimetype='text/event-stream')


@app.route('/api/export/chats')
@login_required
def export_chats():
    """Export chat history as JSON/CSV."""
    format_type = request.args.get('format', 'json')
    limit = int(request.args.get('limit', 100))
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT message, response, provider, model_used, quality_score, created_at
        FROM chat_history WHERE user_id = ? ORDER BY created_at DESC LIMIT ?
    ''', (session['user_id'], limit))
    chats = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    if format_type == 'csv':
        import csv
        from io import StringIO
        
        output = StringIO()
        if chats:
            writer = csv.DictWriter(output, fieldnames=chats[0].keys())
            writer.writeheader()
            writer.writerows(chats)
        
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename=chat_history.csv'}
        )
    
    return jsonify({'chats': chats, 'total': len(chats)})


@app.route('/api/export/stats')
@login_required
def export_stats():
    """Export analytics as JSON."""
    conn = get_db()
    cursor = conn.cursor()
    
    # Overall stats
    cursor.execute('''
        SELECT 
            COUNT(*) as total_chats,
            COUNT(DISTINCT provider) as providers_used,
            AVG(quality_score) as avg_quality,
            SUM(LENGTH(message) + LENGTH(response)) as total_chars,
            MIN(created_at) as first_chat,
            MAX(created_at) as last_chat
        FROM chat_history WHERE user_id = ?
    ''', (session['user_id'],))
    overall = dict(cursor.fetchone())
    
    # Provider breakdown
    cursor.execute('''
        SELECT provider, COUNT(*) as count, AVG(quality_score) as avg_quality
        FROM chat_history WHERE user_id = ? GROUP BY provider
    ''', (session['user_id'],))
    providers = [dict(row) for row in cursor.fetchall()]
    
    # Daily breakdown (last 30 days)
    cursor.execute('''
        SELECT DATE(created_at) as date, COUNT(*) as count
        FROM chat_history 
        WHERE user_id = ? AND created_at >= DATE('now', '-30 days')
        GROUP BY DATE(created_at) ORDER BY date
    ''', (session['user_id'],))
    daily = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return jsonify({
        'overall': overall,
        'providers': providers,
        'daily': daily,
        'exported_at': datetime.now().isoformat()
    })


@app.route('/api/analytics')
@login_required
def analytics():
    """Analytics dashboard data."""
    days = int(request.args.get('days', 7))
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute(f'''
        SELECT DATE(created_at) as date, 
               COUNT(*) as chats,
               AVG(quality_score) as avg_quality,
               provider
        FROM chat_history 
        WHERE user_id = ? AND created_at >= DATE('now', '-{days} days')
        GROUP BY DATE(created_at), provider
        ORDER BY date
    ''', (session['user_id'],))
    data = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    return jsonify({'analytics': data, 'days': days})


# Initialize database on startup
init_db()


# DEBUG ENDPOINT
@app.route('/api/debug', methods=['GET'])
def api_debug():
    """Debug endpoint to check AI providers."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from genesis_protocol.ai.provider_chain import get_provider_chain
        
        chain = get_provider_chain()
        available = chain.get_available_providers()
        status = chain.get_status()
        
        return jsonify({
            'available_providers': available,
            'provider_status': status,
            'groq_configured': status.get('groq', {}).get('configured', False)
        })
    except Exception as e:
        return jsonify({'error': str(e)})


# ============================================================================
# MONITORING ENDPOINTS
# ============================================================================

@app.route('/api/version', methods=['GET'])
def api_version():
    """Get version info."""
    return jsonify({
        'version': VERSION,
        'build_date': BUILD_DATE,
        'entrypoint': 'web/server_simple.py'
    })


@app.route('/api/health', methods=['GET'])
def api_health():
    """Basic health check."""
    return jsonify({
        'status': 'healthy',
        'entrypoint': 'web/server_simple.py'
    })


@app.route('/api/status', methods=['GET'])
def api_status():
    """Detailed status with metrics."""
    return jsonify({
        'status': 'ok',
        'entrypoint': 'web/server_simple.py',
        'metrics': get_metrics(),
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/modules', methods=['GET'])
def api_modules():
    """Get status of all v1.2 modules."""
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from genesis_protocol.integration import get_integration
        
        integration = get_integration()
        module_status = integration.get_module_status()
        detailed = integration.get_detailed_status()
        
        return jsonify({
            **module_status,
            'detailed': detailed,
            'version': VERSION
        })
    except Exception as e:
        logger.error(f"Module status error: {e}")
        return jsonify({
            'personality': False,
            'voice': False,
            'vision': False,
            'tasks': False,
            'memory': False,
            'error': str(e)
        }), 500


@app.route('/api/diagnostics', methods=['GET'])
def api_diagnostics():
    """Full diagnostics - provider status, memory, uptime, version."""
    # Check providers
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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
        cursor.execute('SELECT COUNT(*) FROM chat_history')
        history_count = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM users')
        user_count = cursor.fetchone()[0]
        conn.close()
        db_status = 'ok'
    except Exception as e:
        db_status = f'error: {str(e)}'
        history_count = 0
        user_count = 0

    return jsonify({
        'version': VERSION,
        'build_date': BUILD_DATE,
        'entrypoint': 'web/server_simple.py',
        'uptime': {
            'seconds': get_metrics().get('uptime_seconds', 0),
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
            'vector_db': 'chroma',
            'cache': 'redis'
        },
        'metrics': get_metrics(),
        'environment': {
            'groq_configured': os.environ.get('GROQ_API_KEY', '') != '',
            'railway': os.environ.get('RAILWAY', '') != '',
            'port': os.environ.get('PORT', '5000')
        },
        'timestamp': datetime.now().isoformat()
    })


# ============================================================================
# STARTUP BANNER
# ============================================================================

def print_startup_banner():
    """Print startup banner with system info."""
    import subprocess
    
    # Get commit hash
    try:
        commit = subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD'], 
                                        stderr=subprocess.DEVNULL).decode().strip()
    except:
        commit = 'unknown'
    
    # Get provider status
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from genesis_protocol.ai.provider_chain import get_provider_chain
        chain = get_provider_chain()
        available = chain.get_available_providers()
        groq_ok = chain.is_provider_available('groq')
    except:
        available = []
        groq_ok = False
    
    # Get memory status
    chroma_ok = os.environ.get('CHROMA_DB_PATH', '') != ''
    redis_ok = os.environ.get('REDIS_HOST', '') != ''
    
    banner = f"""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   ██████╗ ███████╗███████╗██╗   ██╗███████╗ █████╗ ██╗     ║
║   ██╔══██╗██╔════╝██╔════╝██║   ██║██╔════╝██╔══██╗██║     ║
║   ██║  ██║█████╗  ███████╗██║   ██║█████╗  ███████║██║     ║
║   ██║  ██║██╔══╝  ╚════██║██║   ██║██╔══╝  ██╔══██║██║     ║
║   ██████╔╝███████╗███████║╚██████╔╝███████╗██║  ██║███████╗
║   ╚═════╝ ╚══════╝╚══════╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝╚══════╝
║                                                              ║
║                    Protocol v{VERSION:<25}                 ║
║                    Commit: {commit:<31}    ║
║                    Build:  {BUILD_DATE:<31}    ║
║                                                              ║
╠══════════════════════════════════════════════════════════════╣
║  PROVIDERS                                                   ║
║  ├─ Groq:        {'✅ Available' if groq_ok else '⚠️  Not configured':<20}       ║
║  └─ Available:   {', '.join(available) or 'None':<20}       ║
║                                                              ║
║  MEMORY                                                      ║
║  ├─ ChromaDB:    {'✅ Configured' if chroma_ok else '⚠️  Using fallback':<20}    ║
║  └─ Redis:       {'✅ Connected' if redis_ok else '⚠️  Using fallback':<20}       ║
║                                                              ║
║  UPTIME: {int(time.time() - START_TIME)}s                                               ║
╚══════════════════════════════════════════════════════════════╝
"""
    print(banner)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    
    # Print startup banner
    print_startup_banner()
    
    logger.info(f"Starting Genesis Web on port {port}")
    app.run(host='0.0.0.0', port=port, debug=debug)