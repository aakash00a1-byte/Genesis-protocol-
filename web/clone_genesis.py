#!/usr/bin/env python3
"""
⚡ GENESIS PROTOCOL - SELF CLONER ⚡
Clone & Deploy Genesis anywhere with one click!
"""

import os
import sys
import subprocess
from pathlib import Path

# Genesis Clone URL
GENESIS_REPO = "https://github.com/aakash00a1-byte/Genesis-protocol-.git"

def print_banner():
    print("""
    ╔═══════════════════════════════════════════╗
    ║   ⚡ GENESIS PROTOCOL - SELF CLONER ⚡    ║
    ║   Clone & Deploy Genesis anywhere!        ║
    ╚═══════════════════════════════════════════╝
    """)

def check_requirements():
    print("\n🔍 Checking requirements...")
    try:
        version = sys.version_info
        print(f"   ✅ Python {version.major}.{version.minor}")
    except:
        print("   ❌ Python not found!")
        return False
    
    try:
        result = subprocess.run(['git', '--version'], capture_output=True, text=True)
        print(f"   ✅ {result.stdout.strip()}")
    except:
        print("   ❌ Git not found! Run: apt install git")
        return False
    
    print("   ✅ All good!")
    return True

def clone_genesis():
    print("\n📥 Cloning Genesis Protocol...")
    target_dir = Path("Genesis-protocol-clone")
    
    if target_dir.exists():
        print("   ⚠️  Already cloned. Pulling latest...")
        os.chdir(target_dir)
        subprocess.run(['git', 'pull'], capture_output=True)
    else:
        print(f"   Cloning to: {target_dir.absolute()}")
        result = subprocess.run(
            ['git', 'clone', GENESIS_REPO, str(target_dir)],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print(f"   ❌ Failed: {result.stderr}")
            return False
        os.chdir(target_dir)
    
    print("   ✅ Genesis cloned!")
    return True

def setup_env():
    print("\n⚙️  Setting up environment...")
    env_file = Path('.env')
    
    if not env_file.exists():
        api_key = input("\n🔑 Enter Groq API Key (skip to add later): ").strip()
        env_content = f"""# Genesis Protocol
GROQ_API_KEY={api_key or 'your_groq_api_key_here'}
SECRET_KEY=genesis-{os.urandom(8).hex()}
FLASK_ENV=development
PORT=5000
"""
        with open(env_file, 'w') as f:
            f.write(env_content)
        print("   ✅ .env created!")
    else:
        print("   .env exists, skipping...")

def install_deps():
    print("\n🐍 Installing dependencies...")
    venv = Path(".venv")
    
    if not venv.exists():
        print("   Creating virtual environment...")
        subprocess.run([sys.executable, '-m', 'venv', str(venv)], check=True)
    
    pip = venv / 'bin' / 'pip'
    print("   Installing packages (this may take a few minutes)...")
    subprocess.run(
        [str(pip), 'install', '-q', '-r', 'requirements.txt'],
        capture_output=True, timeout=300
    )
    print("   ✅ Dependencies installed!")

def create_railway_config():
    print("\n🚂 Creating Railway config...")
    config = """{
  "$schema": "https://railway.app/railway.schema.json",
  "build": { "builder": "NIXPACKS" },
  "deploy": {
    "startCommand": "cd web && python3 app.py",
    "healthCheckPath": "/"
  }
}
"""
    with open('railway.json', 'w') as f:
        f.write(config)
    print("   ✅ railway.json created!")

def main():
    print_banner()
    
    if not check_requirements():
        sys.exit(1)
    
    if not clone_genesis():
        sys.exit(1)
    
    setup_env()
    create_railway_config()
    install_deps()
    
    print("\n" + "="*50)
    print("✅ Genesis is ready!")
    print("="*50)
    print("""
📋 Next Steps:
   1. Edit .env → add GROQ_API_KEY
   2. Run: python web/app.py
   3. Deploy: https://railway.app/new
   
🌐 Access: http://localhost:5000
    """)
    
    start = input("🚀 Start now? (y/n): ").strip().lower()
    if start == 'y':
        os.chdir('web')
        subprocess.run([sys.executable, 'app.py'])

if __name__ == "__main__":
    main()