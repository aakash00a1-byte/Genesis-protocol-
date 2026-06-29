#!/bin/bash
# Genesis Protocol - Termux Setup Script

echo "⚡ Genesis Protocol Termux Installer"
echo "=================================="

# Update packages
echo "[1/5] Updating packages..."
pkg update && pkg upgrade -y

# Install dependencies
echo "[2/5] Installing dependencies..."
pkg install python git -y

# Clone repo (if not exists)
if [ ! -d "Genesis-protocol-" ]; then
    echo "[3/5] Cloning Genesis Protocol..."
    git clone https://github.com/aakash00a1-byte/Genesis-protocol-.git
fi

cd Genesis-protocol-

# Install Python packages
echo "[4/5] Installing Python packages..."
pip install -r requirements.txt

# Run
echo "[5/5] Starting Genesis Protocol..."
echo ""
echo "⚡ Genesis Protocol loading..."
python app.py
