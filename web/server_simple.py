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
from datetime import timedelta
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, request, jsonify, session, render_template, redirect, url_for, Response

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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


@app.route('/admin')
@admin_required
def admin():
    """Admin dashboard."""
    return render_template('admin.html', username=session.get('username'))


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
    
    # Try to use Genesis AI if available
    response_text = "Genesis AI is running in standalone mode. AI responses will be available when connected to the full AI backend."
    
    # Check if we have a real AI backend
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from genesis_protocol.ai.agent import get_genesis_agent
        
        import asyncio
        async def get_response():
            agent = get_genesis_agent()
            result = await agent.process(message, chat_id=user_id, user_id=user_id)
            return result
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(get_response())
        loop.close()
        
        if result.success and result.response:
            response_text = result.response
            model_used = result.model_used
            provider = result.provider_used
            quality = result.quality_score
            mode = result.mode
        else:
            model_used = "fallback"
            provider = "none"
            quality = 0.0
            mode = "normal"
            
    except Exception as e:
        logger.warning(f"AI backend error: {e}")
        model_used = "standalone"
        provider = "none"
        quality = 0.0
        mode = "normal"
        # Still return the response_text which has the fallback message
    
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


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    logger.info(f"Starting Genesis Web on port {port}")
    app.run(host='0.0.0.0', port=port, debug=debug)