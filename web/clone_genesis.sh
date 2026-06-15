#!/bin/bash
# ⚡ Genesis Protocol - One Command Deploy
# Run: curl -s https://raw.githubusercontent.com/aakash00a1-byte/Genesis-protocol-/main/web/clone_genesis.sh | bash

set -e

echo """
╔═══════════════════════════════════════════╗
║   ⚡ GENESIS PROTOCOL - QUICK DEPLOY ⚡   ║
╚═══════════════════════════════════════════╝
"""

# Check requirements
command -v git >/dev/null 2>&1 || { echo "❌ Git required. Run: apt install git"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "❌ Python3 required."; exit 1; }

# Clone
echo "📥 Cloning Genesis..."
if [ -d "Genesis-protocol-" ]; then
    echo "   ⚠️  Already exists, pulling latest..."
    cd Genesis-protocol- && git pull
else
    git clone https://github.com/aakash00a1-byte/Genesis-protocol-.git
    cd Genesis-protocol-
fi

# Setup venv
echo "🐍 Setting up Python..."
python3 -m venv venv
source venv/bin/activate
pip install -q flask python-dotenv werkzeug groq httpx

# Create .env if not exists
if [ ! -f .env ]; then
    echo "⚙️  Creating .env..."
    echo "GROQ_API_KEY=your_key_here" > .env
    echo "SECRET_KEY=genesis-$(openssl rand -hex 8)" >> .env
fi

# Start
echo """
✅ Done!
📋 Add GROQ_API_KEY to .env file
🚀 Run: source venv/bin/activate && cd web && python app.py
🌐 Access: http://localhost:5000
"""