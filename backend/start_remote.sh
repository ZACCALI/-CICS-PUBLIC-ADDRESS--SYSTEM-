#!/bin/bash

# 1. Activate Virtual Environment
source venv/bin/activate

# 2. Start Backend in Background (Log to backend.log)
echo "Starting Backend Server..."
nohup python app.py > backend.log 2>&1 &
BACKEND_PID=$!

# Wait for backend to be ready (dumb wait)
echo "Waiting for Backend to initialize (5s)..."
sleep 5

# 3. Start Cloudflare Tunnel in Foreground
echo "Starting Cloudflare Tunnel..."
echo "Your URL will appear below. Press Ctrl+C to stop everything."
cloudflared tunnel --url http://127.0.0.1:8000

# Cleanup on exit
kill $BACKEND_PID
