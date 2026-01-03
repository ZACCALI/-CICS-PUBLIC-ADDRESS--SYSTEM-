#!/bin/bash

# Force Kill EVERYTHING on Port 8000
echo "=========================================="
echo "      CICS PA SYSTEM - FORCE RESTART      "
echo "=========================================="
echo ""
echo "[1/4] Killing old processes..."
PROCESS_MSG=$(fuser -k 8000/tcp 2>&1)
echo "      -> $PROCESS_MSG"
# Double tap
PID=$(lsof -t -i:8000)
if [ -n "$PID" ]; then
  kill -9 $PID
  echo "      -> Killed persistent PID: $PID"
fi

# Kill old tunnels
pkill cloudflared
echo "      -> Killed old tunnels"
sleep 2

# 2. Activate Venv
echo "[2/4] Activating Environment..."
source venv/bin/activate

# 3. Start Backend
echo "[3/4] Starting Backend..."
nohup python app.py > backend.log 2>&1 &
echo "      -> Backend started (Log: backend.log)"

# 4. Wait
echo "      -> Waiting for Port 8000..."
for i in {1..15}; do
    if (echo > /dev/tcp/127.0.0.1/8000) >/dev/null 2>&1; then
        echo "      -> Backend is UP!"
        break
    fi
    sleep 1
done

echo "[4/4] Starting Cloudflare Tunnel..."
echo ""
echo "!!! KEEP THIS WINDOW OPEN !!!"
echo ""

cloudflared tunnel --url http://127.0.0.1:8000
