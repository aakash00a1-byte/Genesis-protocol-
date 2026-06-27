"""
Genesis Protocol - Mobile API Endpoints

REST API endpoints specifically designed for the Genesis Protocol Mobile App.
These endpoints provide a clean JSON API for mobile clients.
"""

import os
import sys
import json
import time
import sqlite3
from datetime import datetime, timedelta
from functools import wraps
from typing import Optional, Dict, Any

from flask import Flask, request, jsonify, session

# Import the main app and decorators
# Note: This module should be imported after app is created in app.py

# Mobile API configuration
API_VERSION = "v1"
API_PREFIX = f"/api/{API_VERSION}"


def mobile_api_routes(app: Flask):
    """Register mobile API routes with the Flask app."""
    
    # =========================================================================
    # AUTHENTICATION
    # =========================================================================
    
    @app.route(f'{API_PREFIX}/auth/login', methods=['POST'])
    def mobile_api_login():
        """Mobile login endpoint."""
        data = request.get_json() or {}
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            return jsonify({'error': 'Username and password required'}), 400
        
        conn = sqlite3.connect('genesis.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, username, email, password_hash, role, is_active 
            FROM users WHERE username = ?
        ''', (username,))
        user = cursor.fetchone()
        conn.close()
        
        if not user:
            return jsonify({'error': 'Invalid credentials'}), 401
        
        from werkzeug.security import check_password_hash
        if not check_password_hash(user['password_hash'], password):
            return jsonify({'error': 'Invalid credentials'}), 401
        
        if not user['is_active']:
            return jsonify({'error': 'Account disabled'}), 403
        
        # Create session
        session.permanent = True
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['role'] = user['role']
        
        # Generate a simple token for mobile auth
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
    
    @app.route(f'{API_PREFIX}/auth/register', methods=['POST'])
    def mobile_api_register():
        """Mobile registration endpoint."""
        data = request.get_json() or {}
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')
        
        if not username or not email or not password:
            return jsonify({'error': 'All fields required'}), 400
        
        if len(password) < 8:
            return jsonify({'error': 'Password must be at least 8 characters'}), 400
        
        try:
            conn = sqlite3.connect('genesis.db')
            cursor = conn.cursor()
            
            from werkzeug.security import generate_password_hash
            password_hash = generate_password_hash(password)
            
            cursor.execute('''
                INSERT INTO users (username, email, password_hash, role)
                VALUES (?, ?, ?, ?)
            ''', (username, email, password_hash, 'user'))
            
            user_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            # Auto-login after registration
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
    
    @app.route(f'{API_PREFIX}/auth/logout', methods=['POST'])
    def mobile_api_logout():
        """Mobile logout endpoint."""
        session.clear()
        return jsonify({'success': True})
    
    @app.route(f'{API_PREFIX}/auth/me', methods=['GET'])
    def mobile_api_me():
        """Get current user info."""
        if 'user_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        
        conn = sqlite3.connect('genesis.db')
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
    
    # =========================================================================
    # CHAT
    # =========================================================================
    
    @app.route(f'{API_PREFIX}/chat', methods=['POST'])
    def mobile_api_chat():
        """Send a chat message."""
        if 'user_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        
        data = request.get_json() or {}
        message = data.get('message', '')
        
        if not message:
            return jsonify({'error': 'Message required'}), 400
        
        # Process the message through Genesis Protocol AI
        try:
            from genesis_protocol.ai.chain import ProviderChain
            chain = ProviderChain()
            response = chain.process(message)
            
            # Save to history
            conn = sqlite3.connect('genesis.db')
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO chat_history (user_id, message, response, provider)
                VALUES (?, ?, ?, ?)
            ''', (session['user_id'], message, response.get('response', ''), 
                  response.get('provider', 'unknown')))
            chat_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            return jsonify({
                'message': response.get('response', ''),
                'chat_id': chat_id,
                'provider': response.get('provider', 'unknown'),
                'timestamp': int(time.time() * 1000)
            })
        except Exception as e:
            return jsonify({
                'message': f"I apologize, but I encountered an error: {str(e)}",
                'error': True,
                'timestamp': int(time.time() * 1000)
            })
    
    @app.route(f'{API_PREFIX}/chat/history', methods=['GET'])
    def mobile_api_chat_history():
        """Get chat history."""
        if 'user_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        
        limit = request.args.get('limit', 50, type=int)
        
        conn = sqlite3.connect('genesis.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, message, response, provider, created_at
            FROM chat_history
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        ''', (session['user_id'], limit))
        
        messages = []
        for row in cursor.fetchall():
            messages.append({
                'id': str(row['id']),
                'role': 'user',
                'content': row['message'],
                'timestamp': int(datetime.fromisoformat(row['created_at']).timestamp() * 1000)
            })
            if row['response']:
                messages.append({
                    'id': f"{row['id']}_response",
                    'role': 'assistant',
                    'content': row['response'],
                    'timestamp': int(datetime.fromisoformat(row['created_at']).timestamp() * 1000) + 1
                })
        
        conn.close()
        
        return jsonify(list(reversed(messages)))
    
    @app.route(f'{API_PREFIX}/chat/clear', methods=['POST'])
    def mobile_api_chat_clear():
        """Clear chat history."""
        if 'user_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        
        conn = sqlite3.connect('genesis.db')
        cursor = conn.cursor()
        cursor.execute('DELETE FROM chat_history WHERE user_id = ?', (session['user_id'],))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
    
    # =========================================================================
    # SYSTEM STATUS
    # =========================================================================
    
    @app.route(f'{API_PREFIX}/status', methods=['GET'])
    def mobile_api_status():
        """Get system status."""
        # Check if Genesis Protocol services are running
        services = {
            'telegram': False,
            'discord': False,
            'web': True  # This is the web service
        }
        
        # Check Telegram bot status (simplified)
        try:
            import os
            if os.environ.get('TELEGRAM_BOT_TOKEN'):
                services['telegram'] = True
        except:
            pass
        
        # Check Discord bot status (simplified)
        try:
            import os
            if os.environ.get('DISCORD_BOT_TOKEN'):
                services['discord'] = True
        except:
            pass
        
        uptime = int(time.time() - float(getattr(__import__('__main__'), 'START_TIME', time.time())))
        
        return jsonify({
            'status': 'online',
            'uptime': uptime,
            'version': '1.1.0',
            'services': services
        })
    
    @app.route(f'{API_PREFIX}/health', methods=['GET'])
    def mobile_api_health():
        """Health check endpoint."""
        start = time.time()
        
        # Simple latency measurement
        latency_ms = int((time.time() - start) * 1000)
        
        return jsonify({
            'healthy': True,
            'latency': latency_ms,
            'timestamp': int(time.time() * 1000)
        })
    
    # =========================================================================
    # DISCORD
    # =========================================================================
    
    @app.route(f'{API_PREFIX}/discord/status', methods=['GET'])
    def mobile_api_discord_status():
        """Get Discord bot status."""
        try:
            discord_token = os.environ.get('DISCORD_BOT_TOKEN')
            connected = bool(discord_token)
            
            return jsonify({
                'connected': connected,
                'serverName': 'Genesis Board',
                'channelCount': 5 if connected else 0,
                'lastActivity': int(time.time() * 1000)
            })
        except Exception as e:
            return jsonify({
                'connected': False,
                'error': str(e),
                'serverName': 'Unknown',
                'channelCount': 0,
                'lastActivity': int(time.time() * 1000)
            })
    
    @app.route(f'{API_PREFIX}/discord/channels', methods=['GET'])
    def mobile_api_discord_channels():
        """Get Discord channels."""
        # Mock channel data - in production, this would query the Discord API
        channels = ['general', 'commands', 'bot-logs']
        return jsonify(channels)
    
    @app.route(f'{API_PREFIX}/discord/send', methods=['POST'])
    def mobile_api_discord_send():
        """Send message via Discord bot."""
        if 'user_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        
        data = request.get_json() or {}
        channel_id = data.get('channelId')
        message = data.get('message')
        
        if not message:
            return jsonify({'error': 'Message required'}), 400
        
        # In production, this would use the Discord API
        return jsonify({
            'success': True,
            'message': 'Message sent via Discord bot'
        })
    
    # =========================================================================
    # ACTIVITY LOGS
    # =========================================================================
    
    @app.route(f'{API_PREFIX}/activity/logs', methods=['GET'])
    def mobile_api_activity_logs():
        """Get activity logs."""
        if 'user_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        
        limit = request.args.get('limit', 100, type=int)
        
        # Generate mock activity logs
        activities = [
            {
                'id': '1',
                'type': 'chat',
                'description': 'User sent message: "Hello Genesis"',
                'timestamp': int((time.time() - 300) * 1000)
            },
            {
                'id': '2',
                'type': 'system',
                'description': 'System health check passed',
                'timestamp': int((time.time() - 600) * 1000)
            },
            {
                'id': '3',
                'type': 'discord',
                'description': 'Discord bot responded to command',
                'timestamp': int((time.time() - 900) * 1000)
            }
        ]
        
        return jsonify(activities[:limit])
    
    @app.route(f'{API_PREFIX}/activity/recent', methods=['GET'])
    def mobile_api_activity_recent():
        """Get recent activity."""
        return mobile_api_activity_logs()
    
    # =========================================================================
    # NOTIFICATIONS
    # =========================================================================
    
    @app.route(f'{API_PREFIX}/notifications/register', methods=['POST'])
    def mobile_api_notification_register():
        """Register push notification token."""
        if 'user_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        
        data = request.get_json() or {}
        token = data.get('token')
        
        if not token:
            return jsonify({'error': 'Token required'}), 400
        
        # In production, save token to database for push notifications
        return jsonify({'success': True})
    
    @app.route(f'{API_PREFIX}/notifications/preferences', methods=['GET'])
    def mobile_api_notification_preferences():
        """Get notification preferences."""
        if 'user_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        
        return jsonify({
            'chatMessages': True,
            'systemAlerts': True,
            'discordMentions': False,
            'activityUpdates': True
        })
    
    @app.route(f'{API_PREFIX}/notifications/preferences', methods=['PUT'])
    def mobile_api_notification_update_preferences():
        """Update notification preferences."""
        if 'user_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        
        data = request.get_json() or {}
        
        # In production, save preferences to database
        return jsonify({'success': True})
    
    # =========================================================================
    # ADMIN
    # =========================================================================
    
    @app.route(f'{API_PREFIX}/admin/restart', methods=['POST'])
    def mobile_api_admin_restart():
        """Restart a service (admin only)."""
        if 'user_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        
        if session.get('role') != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        
        data = request.get_json() or {}
        service = data.get('service')
        
        # In production, this would restart the specified service
        return jsonify({
            'success': True,
            'message': f'Service {service or "all"} restart initiated'
        })
    
    return app
