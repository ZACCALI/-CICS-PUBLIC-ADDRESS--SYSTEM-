#!/bin/bash

# Cloudflare Tunnel Setup Script for Raspberry Pi 5 (ARM64)
# Usage: ./setup_remote_access.sh

echo "=========================================="
echo "   CICS Public Address - Remote Access"
echo "=========================================="
echo "This script will install Cloudflare Tunnel to allow"
echo "remote access via Mobile Data / Internet."
echo ""

# 1. Check if cloudflared is already installed
if command -v cloudflared &> /dev/null; then
    echo "[OK] Cloudflare Tunnel is already installed."
else
    echo "[...] Downloading Cloudflare Tunnel for Raspberry Pi 5 (ARM64)..."
    # Download ARM64 deb package
    curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb
    
    echo "[...] Installing..."
    sudo dpkg -i cloudflared.deb
    
    # Cleanup
    rm cloudflared.deb
    echo "[SUCCESS] Installation Complete!"
fi

echo ""
echo "=========================================="
echo "   NEXT STEPS (READ CAREFULLY)"
echo "=========================================="
echo "1. Run this command to start the tunnel:"
echo "   cloudflared tunnel --url http://127.0.0.1:8000"
echo ""
echo "2. Pass the 'Manage' logic?"
echo "   It will print a link (https://...trycloudflare.com)"
echo "   Copy that link and use it on your phone."
echo ""
echo "   (Press Ctrl+C to stop the tunnel when done)"
echo "=========================================="
