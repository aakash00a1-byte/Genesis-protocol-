# Gluttony OS Web - Deployment Guide

A full-featured web application for Genesis AI with authentication and chat interface.

## Features

- 🤖 **AI Chat Interface** - ChatGPT-like experience
- 🔐 **User Authentication** - Login/Register system
- 👨‍💼 **Admin Dashboard** - User management, logs, statistics
- 🌐 **Cloud Deployable** - Railway, Render, VPS, Docker
- 📱 **Mobile Responsive** - Works on all devices

## Quick Start

### Local Development

```bash
cd web

# Install dependencies
pip install -r requirements.txt

# Copy environment file
cp .env.example .env

# Edit .env with your API keys
nano .env

# Run the app
python app.py
```

Visit `http://localhost:5000`

### Default Admin Login

- Username: `admin`
- Password: `genesis-admin-2024` (change in production!)

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `SECRET_KEY` | Flask secret key | Yes |
| `FLASK_DEBUG` | Enable debug mode | No |
| `PORT` | Server port | No (default: 5000) |
| `ADMIN_PASSWORD` | Admin account password | No |

### API Keys (from parent .env)

The web app reads API keys from the parent directory's `.env` file:

```
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...
GROQ_API_KEY=...
CLAUDE_API_KEY=...  # Optional
TAVILY_API_KEY=...
```

## Deployment Options

### 1. Railway (Recommended)

1. Create a new Railway project
2. Connect your GitHub repository
3. Add environment variables from `.env.example`
4. Deploy!

**Railway Button:**
[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new)

### 2. Render

1. Create a new Web Service
2. Connect your GitHub repository
3. Set build command: `pip install -r requirements.txt`
4. Set start command: `gunicorn app:app`
5. Add environment variables
6. Deploy!

### 3. VPS (Docker)

```bash
# Build image
docker build -t genesis-web .

# Run container
docker run -d -p 5000:5000 \
  --env-file .env \
  -v $(pwd)/genesis.db:/app/genesis.db \
  genesis-web
```

### 4. VPS (Direct)

```bash
# Install requirements
pip install -r requirements.txt

# Run with gunicorn
gunicorn --bind 0.0.0.0:5000 --workers 4 app:app
```

## API Endpoints

### Authentication
- `POST /login` - User login
- `POST /register` - User registration
- `GET /logout` - User logout

### Chat
- `POST /api/chat` - Send message to AI
- `GET /api/history` - Get chat history

### Admin (requires admin role)
- `GET /api/admin/stats` - System statistics
- `GET /api/admin/users` - List all users
- `POST /api/admin/users/<id>/toggle` - Toggle user status
- `GET /api/admin/logs` - Request logs

## User Roles

### Admin
- Full access to all features
- View system logs
- Manage users
- Access admin dashboard

### User
- Chat with AI
- View own history
- Rate limited to 100 messages/day

## Database

SQLite database `genesis.db` stores:
- User accounts
- Chat history
- Request logs

Data persists in the container volume.

## Security Notes

1. **Change SECRET_KEY** in production
2. **Change ADMIN_PASSWORD** from default
3. Use HTTPS in production
4. Consider rate limiting
5. Regular backups of `genesis.db`

## Project Structure

```
web/
├── app.py              # Main Flask application
├── requirements.txt    # Python dependencies
├── Dockerfile          # Docker configuration
├── .env.example        # Environment template
├── genesis.db          # SQLite database (created on first run)
├── templates/          # HTML templates
│   ├── base.html
│   ├── index.html
│   ├── login.html
│   ├── register.html
│   ├── chat.html
│   ├── admin.html
│   └── error.html
└── static/
    └── css/
        └── style.css   # Styles
```

## Troubleshooting

### Database locked
```bash
rm genesis.db
python app.py  # Recreates database
```

### Import errors
Make sure you're running from the web directory and parent directory is in Python path.

### API errors
Check that your API keys are valid and have sufficient quota.

## License

MIT License - See parent repository