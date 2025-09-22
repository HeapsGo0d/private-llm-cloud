#!/bin/bash
set -euo pipefail

# Private LLM Cloud - Startup Script
# Handles privacy setup, security hardening, and service startup

echo "🔒 Starting Private LLM Cloud with maximum privacy..."

# Source environment variables
if [ -f /app/.env ]; then
    export $(grep -v '^#' /app/.env | xargs)
fi

# Privacy and security setup
PRIVACY_MODE=${PRIVACY_MODE:-maximum}
DISABLE_TELEMETRY=${DISABLE_TELEMETRY:-true}
ENCRYPT_STORAGE=${ENCRYPT_STORAGE:-true}

# Create necessary directories
mkdir -p /app/models /app/data /app/logs /app/backups

# Set secure permissions
chmod 700 /app/data /app/logs /app/backups
chmod 600 /app/.env 2>/dev/null || true

# Apply security hardening
echo "🛡️ Applying security hardening..."
/app/scripts/security-hardening.sh

# Setup privacy controls
echo "🔐 Setting up privacy controls..."
/app/scripts/setup-privacy.sh

# Initialize model manager
echo "📦 Initializing model manager..."
python3 /app/scripts/model-manager.py status

# Start Ollama in background
echo "🚀 Starting Ollama..."
ollama serve &
OLLAMA_PID=$!

# Wait for Ollama to be ready
echo "⏳ Waiting for Ollama to start..."
for i in {1..30}; do
    if curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
        echo "✅ Ollama is ready!"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "❌ Ollama failed to start within 30 seconds"
        exit 1
    fi
    sleep 1
done

# Start secure API proxy
echo "🔒 Starting secure API proxy..."
python3 /app/api/secure-proxy.py &
PROXY_PID=$!

# Setup signal handlers for graceful shutdown
cleanup() {
    echo "🛑 Shutting down services..."
    kill $OLLAMA_PID $PROXY_PID 2>/dev/null || true
    wait $OLLAMA_PID $PROXY_PID 2>/dev/null || true
    echo "✅ Services stopped"
}

trap cleanup SIGTERM SIGINT

# Keep the container running
echo "🎉 Private LLM Cloud is running!"
echo "📊 Web UI: http://localhost:3000"
echo "🔌 API: http://localhost:11434"
echo "🔒 Privacy Mode: $PRIVACY_MODE"

# Wait for services
wait $OLLAMA_PID $PROXY_PID