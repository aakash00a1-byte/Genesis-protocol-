#!/bin/bash
# ⚡ GENESIS AUTONOMOUS DEPLOY - ONE COMMAND ⚡
# Usage: curl -s https://raw.githubusercontent.com/aakash00a1-byte/Genesis-protocol-/main/scripts/genesis-deploy.sh | bash

set -e

REPO="https://github.com/aakash00a1-byte/Genesis-protocol-.git"
TARGET_DIR="${1:-/tmp/Genesis-protocol}"

echo """
╔═══════════════════════════════════════════════════════════╗
║     ⚡ GENESIS AUTONOMOUS DEPLOYMENT ENGINE ⚡          ║
║     Self-deploying AI Protocol                          ║
╚═══════════════════════════════════════════════════════════╝
"""

# Check requirements
echo "[1/6] Checking requirements..."
command -v git >/dev/null || { echo "❌ Git required"; exit 1; }
command -v python3 >/dev/null || { echo "❌ Python3 required"; exit 1; }
echo "✅ Requirements OK"

# Clone or Update
echo ""
echo "[2/6] Cloning/Updating Genesis..."
if [ -d "$TARGET_DIR" ]; then
    echo "   → Updating existing installation..."
    cd "$TARGET_DIR" && git pull
else
    echo "   → Cloning to $TARGET_DIR..."
    git clone "$REPO" "$TARGET_DIR"
fi
echo "✅ Genesis cloned"

# Setup Virtual Environment
echo ""
echo "[3/6] Setting up Python environment..."
cd "$TARGET_DIR"
python3 -m venv .venv
source .venv/bin/activate
pip install -q flask python-dotenv werkzeug groq httpx requests
echo "✅ Dependencies installed"

# Create .env if not exists
echo ""
echo "[4/6] Configuring environment..."
if [ ! -f .env ]; then
    cat > .env << 'EOF'
# Genesis Protocol - Auto-generated
GROQ_API_KEY=your_groq_key_here
OPENAI_API_KEY=
GEMINI_API_KEY=
ANTHROPIC_API_KEY=
DEEPSEEK_API_KEY=
SECRET_KEY=genesis-$(openssl rand -hex 8)
FLASK_ENV=production
PORT=5000
EOF
    echo "✅ .env created"
else
    echo "   .env exists, skipping"
fi

# Create Railway config
echo ""
echo "[5/6] Creating Railway config..."
cat > railway.json << 'EOF'
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "NIXPACKS",
    "buildCommand": "cd web && pip install -r requirements.txt"
  },
  "deploy": {
    "startCommand": "cd web && python3 app.py",
    "healthCheckPath": "/"
  }
}
EOF
echo "✅ Railway config ready"

# Summary
echo ""
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║              ✅ DEPLOYMENT READY!                       ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo ""
echo "📋 Summary:"
echo "   📁 Location: $TARGET_DIR"
echo "   🌐 Web: $TARGET_DIR/web"
echo "   🚂 Railway: Ready"
echo ""
echo "📌 Next Steps:"
echo "   1. Edit: nano $TARGET_DIR/.env"
echo "   2. Run:  cd $TARGET_DIR && source .venv/bin/activate && cd web && python app.py"
echo "   3. Deploy: https://railway.app/new?template=https://github.com/aakash00a1-byte/Genesis-protocol-"
echo ""
echo "🚀 Start now? (y/n)"
read -r start
if [ "$start" = "y" ]; then
    cd "$TARGET_DIR/web"
    source ../.venv/bin/activate
    python app.py
fi