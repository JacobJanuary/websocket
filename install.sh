#!/bin/bash
# WebSocket Signal Server Installation Script

set -e

echo "=========================================="
echo "WebSocket Signal Server - Installation"
echo "=========================================="
echo ""

# Check Python version
echo "Checking Python version..."
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
echo "✓ Python $PYTHON_VERSION found"
echo ""

# Create virtual environment
echo "Creating virtual environment..."
if [ -d "venv" ]; then
    echo "⚠ venv already exists, skipping..."
else
    python3 -m venv venv
    echo "✓ Virtual environment created"
fi
echo ""

# Activate and install dependencies
echo "Installing dependencies..."
./venv/bin/pip install --upgrade pip > /dev/null
./venv/bin/pip install -r requirements.txt
echo "✓ Dependencies installed"
echo ""

# Check .env file
echo "Checking configuration..."
if [ ! -f ".env" ]; then
    echo "❌ .env file not found!"
    echo ""
    echo "Please create .env file with the following variables:"
    echo "  DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD"
    echo "  WS_SERVER_HOST, WS_SERVER_PORT, WS_AUTH_PASSWORD"
    echo ""
    exit 1
fi
echo "✓ Configuration file found"
echo ""

# Test database connection
echo "Testing database connection..."
if ./venv/bin/python3 -c "
import os
import asyncio
import asyncpg
from dotenv import load_dotenv

async def test():
    load_dotenv()
    try:
        conn = await asyncpg.connect(
            host=os.getenv('DB_HOST'),
            port=int(os.getenv('DB_PORT', 5432)),
            database=os.getenv('DB_NAME'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD')
        )
        await conn.close()
        return True
    except Exception as e:
        print(f'Error: {e}')
        return False

result = asyncio.run(test())
exit(0 if result else 1)
" 2>&1; then
    echo "✓ Database connection successful"
else
    echo "❌ Database connection failed"
    echo "Please check your .env configuration"
    exit 1
fi
echo ""

# Make scripts executable
echo "Setting permissions..."
chmod +x install_trigger_python.py
chmod +x quick_test.py
chmod +x monitor_simple.py
chmod +x test_hybrid_mode.py
echo "✓ Permissions set"
echo ""

echo "=========================================="
echo "✓ Installation Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Install PostgreSQL trigger (for NOTIFY mode):"
echo "   ./install_trigger_python.py"
echo ""
echo "2. Test the installation:"
echo "   ./test_hybrid_mode.py"
echo ""
echo "3. Start the server:"
echo "   ./venv/bin/python3 signal_websocket_server.py"
echo ""
echo "4. Test connection:"
echo "   ./quick_test.py"
echo ""
echo "5. Monitor in real-time:"
echo "   ./monitor_simple.py"
echo ""
echo "For production deployment:"
echo "   ./install_service.sh"
echo ""
