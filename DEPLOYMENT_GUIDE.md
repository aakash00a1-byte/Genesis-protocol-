# Genesis Protocol - Production Deployment Guide

## 🚀 Quick Deploy to Render (Recommended)

### Step 1: Fork/Clone Repository
```bash
git clone https://github.com/aakash00a1-byte/Genesis-protocol-.git
cd Genesis-protocol-
```

### Step 2: Create Render Account
1. Go to [render.com](https://render.com)
2. Sign up with GitHub
3. Connect your GitHub repository

### Step 3: Deploy via Blueprint
1. Go to Render Dashboard → Blueprints
2. Click "New Blueprint Instance"
3. Connect your GitHub repo
4. Select `render.yaml` file
5. Add Environment Variables (see below)

### Step 4: Required Environment Variables
| Variable | Description | Required |
|----------|-------------|----------|
| `GROQ_API_KEY` | Groq AI API key | ✅ Yes |
| `SECRET_KEY` | Flask secret key (auto-generated) | ✅ Auto |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token | Optional |
| `OPENAI_API_KEY` | OpenAI API key | Optional |
| `ADMIN_PASSWORD` | Admin dashboard password | ✅ Set |

### Step 5: Deploy
Click "Apply Blueprint" and wait for deployment (~3-5 minutes).

---

## 🏗️ Alternative: Deploy to Railway

### Prerequisites
```bash
npm install -g @railway/cli
railway login
railway link <project-id>
```

### Deploy
```bash
cd web
railway up
railway variables set GROQ_API_KEY=your_key
```

---

## ✅ Post-Deployment Checklist

### Health Endpoints
- `/health` - Basic health check
- `/status` - Detailed status with DB stats

### Test All Features
- [ ] Login page loads
- [ ] Registration works
- [ ] Chat functionality works
- [ ] AI responses are generated
- [ ] Admin dashboard accessible

### Verify Auto-Restart
Render provides automatic restart on:
- Crash detection
- Server reboot
- Memory limits

---

## 📊 Production Features Enabled

| Feature | Status | Provider |
|---------|--------|----------|
| Auto-restart on crash | ✅ | Render/Railway |
| Auto-restart on reboot | ✅ | Render/Railway |
| HTTPS | ✅ | Render/Railway |
| Health monitoring | ✅ | `/health` endpoint |
| Process manager | ✅ | Gunicorn |
| Logging | ✅ | Production logs |

---

## 🌐 Expected Output

After successful deployment:
- **URL**: `https://genesis-protocol.onrender.com`
- **Status**: Health check passing
- **Uptime**: 24x7 with auto-restart

---

## 🔧 Troubleshooting

### Build Fails
Check that `web/requirements.txt` has all dependencies.

### Health Check Fails
Verify all required environment variables are set.

### Crashes on Start
Check logs in Render Dashboard → Logs

### Database Error
SQLite works for small scale. For production, migrate to PostgreSQL.