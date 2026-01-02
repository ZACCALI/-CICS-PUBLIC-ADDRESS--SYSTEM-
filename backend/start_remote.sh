#!/bin/bash

# 0. Check for Cloudflared
if ! command -v cloudflared &> /dev/null; then
    echo "Error: 'cloudflared' is not installed or not in PATH."
    echo "Please install it first: curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb && sudo dpkg -i cloudflared.deb"
    exit 1
fi

# 1. Activate Virtual Environment
source venv/bin/activate

# 2. Start Backend in Background (Log to backend.log)
echo "--------------------------------------------------"
echo "Starting FastAPI Backend..."
nohup python app.py > backend.log 2>&1 &
BACKEND_PID=$!
echo "Backend PID: $BACKEND_PID"

# 3. Synchronize: Wait for Port 8000 to be active
echo "Waiting for Backend to listen on port 8000..."
# Attempt to check port with python/bash (fallback to sleep if netstat missing)
for i in {1..15}; do
    if (echo > /dev/tcp/127.0.0.1/8000) >/dev/null 2>&1; then
        echo "Backend is UP!"
        break
    fi
    sleep 1
    if [ $i -eq 15 ]; then
        echo "Warning: Backend taking long to start. Check backend.log."
    fi
done


# 4. Display Access Information
LOCAL_IP=$(hostname -I | cut -d' ' -f1)
echo "--------------------------------------------------"
echo "✅ Backend is UP and RUNNING!"
echo ""
echo "📱 LOCAL ACCESS (Same WiFi):"
echo "   http://$LOCAL_IP:8000"
echo ""
echo "☁️  CLOUD ACCESS (Anywhere):"
echo "   (Copy the trycloudflare.com link below)"
echo "--------------------------------------------------"

echo "Starting Cloudflare Tunnel..."
echo "Press Ctrl+C to stop everything."
echo "--------------------------------------------------"

# 5. Start Cloudflare Tunnel (Foreground)
cloudflared tunnel --url http://127.0.0.1:8000

# Cleanup on exit
kill $BACKEND_PID
echo "Backend Stopped."
