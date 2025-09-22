#!/bin/bash
set -euo pipefail

# Private LLM Cloud - Enhanced Startup Script
# Incorporates proven patterns from Ignition project
# Handles privacy setup, security hardening, and service startup

# Color definitions for enhanced logging
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="/app/logs/startup.log"
PID_FILE="/app/data/startup.pid"
PRIVACY_STATE_MANAGER="$SCRIPT_DIR/privacy_state_manager.py"

# Make sure the privacy state manager is executable
if [ -f "$PRIVACY_STATE_MANAGER" ]; then
    chmod +x "$PRIVACY_STATE_MANAGER"
fi

# Exit codes for different failure types
EXIT_SECURITY_FAILED=10
EXIT_PRIVACY_FAILED=11
EXIT_SERVICE_FAILED=12
EXIT_MODEL_FAILED=13
EXIT_NETWORK_FAILED=14

# Ensure log directory exists
mkdir -p "$(dirname "$LOG_FILE")"

# Enhanced logging system with levels
log() {
    local level=$1
    local message=$2
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    case $level in
        "INFO")  echo -e "${GREEN}[INFO]${NC} $message" | tee -a "$LOG_FILE" ;;
        "WARN")  echo -e "${YELLOW}[WARN]${NC} $message" | tee -a "$LOG_FILE" ;;
        "ERROR") echo -e "${RED}[ERROR]${NC} $message" | tee -a "$LOG_FILE" ;;
        "DEBUG") echo -e "${CYAN}[DEBUG]${NC} $message" | tee -a "$LOG_FILE" ;;
        "SUCCESS") echo -e "${GREEN}[SUCCESS]${NC} $message" | tee -a "$LOG_FILE" ;;
    esac
}

# Cleanup function for graceful shutdown
cleanup() {
    log "INFO" "🛑 Shutting down Private LLM Cloud..."

    # Stop privacy monitoring
    if [ -f "$PRIVACY_STATE_MANAGER" ]; then
        python3 "$PRIVACY_STATE_MANAGER" emergency >/dev/null 2>&1 || true
    fi

    # Kill background jobs
    jobs -p | xargs -r kill 2>/dev/null || true

    # Clean up PID file
    rm -f "$PID_FILE"

    log "INFO" "🔒 Cleanup completed"
    exit 0
}

# Set up signal handlers
trap cleanup SIGTERM SIGINT

# Write startup PID
echo $$ > "$PID_FILE"

# Display startup banner with configuration
print_banner() {
    echo -e "${PURPLE}"
    echo "╔══════════════════════════════════════════════════╗"
    echo "║              🔒 PRIVATE LLM CLOUD 🔒            ║"
    echo "║          Maximum Privacy • Zero Telemetry        ║"
    echo "╚══════════════════════════════════════════════════╝"
    echo -e "${NC}"

    log "INFO" "🚀 Private LLM Cloud starting up..."
    log "INFO" "📅 Startup time: $(date)"
    log "INFO" "🏠 Working directory: $(pwd)"
    log "INFO" "👤 Running as: $(whoami)"
}

# Load and validate configuration
load_configuration() {
    log "INFO" "📋 Loading configuration..."

    # Source environment variables with validation
    if [ -f /app/.env ]; then
        set -a  # Mark variables for export
        source /app/.env
        set +a
        log "SUCCESS" "✅ Environment variables loaded"
    else
        log "WARN" "⚠️ No .env file found, using defaults"
    fi

    # Set secure defaults with fallbacks
    export PRIVACY_MODE=${PRIVACY_MODE:-maximum}
    export DISABLE_TELEMETRY=${DISABLE_TELEMETRY:-true}
    export ENCRYPT_STORAGE=${ENCRYPT_STORAGE:-true}
    export OFFLINE_MODE=${OFFLINE_MODE:-false}
    export ENABLE_AUTH=${ENABLE_AUTH:-true}
    export WEB_UI_PORT=${WEB_UI_PORT:-3000}
    export API_PORT=${API_PORT:-11434}
    export OLLAMA_PORT=${OLLAMA_PORT:-11434}
    export MAX_CONCURRENT_REQUESTS=${MAX_CONCURRENT_REQUESTS:-10}
    export AUTO_SHUTDOWN_IDLE_MINUTES=${AUTO_SHUTDOWN_IDLE_MINUTES:-30}

    # Display configuration
    log "INFO" "🔧 Configuration Summary:"
    log "INFO" "  Privacy Mode: $PRIVACY_MODE"
    log "INFO" "  Telemetry Disabled: $DISABLE_TELEMETRY"
    log "INFO" "  Storage Encryption: $ENCRYPT_STORAGE"
    log "INFO" "  Web UI Port: $WEB_UI_PORT"
    log "INFO" "  API Port: $API_PORT"
    log "INFO" "  Offline Mode: $OFFLINE_MODE"
}

# Check system requirements
check_system_requirements() {
    log "INFO" "🔍 Checking system requirements..."

    local requirements_met=true

    # Check Python availability
    if command -v python3 >/dev/null 2>&1; then
        log "SUCCESS" "✅ Python 3 available: $(python3 --version)"
    else
        log "ERROR" "❌ Python 3 not found"
        requirements_met=false
    fi

    # Check aria2c availability (nice to have)
    if command -v aria2c >/dev/null 2>&1; then
        log "SUCCESS" "✅ aria2c available for robust downloads"
    else
        log "WARN" "⚠️ aria2c not found, will use fallback downloads"
    fi

    # Check disk space
    local available_space=$(df /app 2>/dev/null | awk 'NR==2 {print $4}' || echo "0")
    if [ "$available_space" -gt 1048576 ]; then  # 1GB in KB
        log "SUCCESS" "✅ Sufficient disk space: ${available_space}KB available"
    else
        log "WARN" "⚠️ Low disk space: ${available_space}KB available"
    fi

    # Check memory
    local available_memory=$(free -m | awk 'NR==2{printf "%.0f", $7}' 2>/dev/null || echo "0")
    if [ "$available_memory" -gt 512 ]; then
        log "SUCCESS" "✅ Sufficient memory: ${available_memory}MB available"
    else
        log "WARN" "⚠️ Low memory: ${available_memory}MB available"
    fi

    if [ "$requirements_met" = false ]; then
        log "ERROR" "❌ System requirements not met"
        exit $EXIT_SECURITY_FAILED
    fi
}

# Create and secure directories
setup_storage() {
    log "INFO" "📁 Setting up storage directories..."

    # Create necessary directories with proper structure
    local directories=(
        "/app/models"
        "/app/data"
        "/app/data/encrypted"
        "/app/logs"
        "/app/backups"
        "/app/tmp"
        "/app/cache"
    )

    for dir in "${directories[@]}"; do
        mkdir -p "$dir"
        chmod 700 "$dir"
        log "DEBUG" "Created directory: $dir"
    done

    # Set secure permissions on sensitive files
    if [ -f /app/.env ]; then
        chmod 600 /app/.env
        log "DEBUG" "Secured .env file permissions"
    fi

    log "SUCCESS" "✅ Storage setup completed"
}

# Apply security hardening with error handling
apply_security_hardening() {
    log "INFO" "🛡️ Applying security hardening..."

    if [ -f "$SCRIPT_DIR/security-hardening.sh" ]; then
        if "$SCRIPT_DIR/security-hardening.sh"; then
            log "SUCCESS" "✅ Security hardening completed"
        else
            log "WARN" "⚠️ Security hardening had issues, continuing with reduced security"
        fi
    else
        log "WARN" "⚠️ Security hardening script not found, skipping"
    fi
}

# Initialize privacy protection
initialize_privacy() {
    log "INFO" "🔐 Initializing privacy protection..."

    # Setup privacy controls if available
    if [ -f "$SCRIPT_DIR/setup-privacy.sh" ]; then
        if "$SCRIPT_DIR/setup-privacy.sh"; then
            log "SUCCESS" "✅ Privacy controls configured"
        else
            log "WARN" "⚠️ Privacy setup had issues, continuing with basic protection"
        fi
    fi

    # Initialize privacy state manager
    if [ -f "$PRIVACY_STATE_MANAGER" ]; then
        if python3 "$PRIVACY_STATE_MANAGER" update; then
            log "SUCCESS" "✅ Privacy state manager initialized"
        else
            log "WARN" "⚠️ Privacy state manager initialization failed"
        fi
    else
        log "WARN" "⚠️ Privacy state manager not found"
    fi
}

# Download models if specified
download_models() {
    log "INFO" "📦 Checking model requirements..."

    # Initialize model manager
    if [ -f "$SCRIPT_DIR/model-manager.py" ]; then
        if python3 "$SCRIPT_DIR/model-manager.py" status; then
            log "SUCCESS" "✅ Model manager initialized"
        else
            log "WARN" "⚠️ Model manager initialization failed"
        fi
    fi

    # Download default model if specified
    if [ -n "${DEFAULT_MODEL:-}" ] && [ "$DEFAULT_MODEL" != "none" ]; then
        log "INFO" "📥 Downloading default model: $DEFAULT_MODEL"
        if python3 "$SCRIPT_DIR/model-manager.py" download "$DEFAULT_MODEL"; then
            log "SUCCESS" "✅ Default model downloaded successfully"
        else
            log "WARN" "⚠️ Default model download failed, continuing without it"
        fi
    fi
}

# Start services with improved error handling and health checks
start_ollama() {
    log "INFO" "🚀 Starting Ollama service..."

    # Start Ollama in background
    ollama serve &
    OLLAMA_PID=$!

    # Enhanced health check with configurable timeout
    local timeout=${OLLAMA_STARTUP_TIMEOUT:-60}
    local interval=2

    log "INFO" "⏳ Waiting for Ollama to start (timeout: ${timeout}s)..."

    for ((i=1; i<=timeout/interval; i++)); do
        if curl -s http://localhost:${OLLAMA_PORT}/api/tags >/dev/null 2>&1; then
            log "SUCCESS" "✅ Ollama is ready! (took $((i*interval))s)"
            return 0
        fi

        if ! kill -0 $OLLAMA_PID 2>/dev/null; then
            log "ERROR" "❌ Ollama process died"
            return $EXIT_SERVICE_FAILED
        fi

        if [ $i -eq $((timeout/interval)) ]; then
            log "ERROR" "❌ Ollama failed to start within ${timeout} seconds"
            return $EXIT_SERVICE_FAILED
        fi

        log "DEBUG" "Waiting for Ollama... (attempt $i/$((timeout/interval)))"
        sleep $interval
    done
}

# Start secure API proxy
start_api_proxy() {
    log "INFO" "🔒 Starting secure API proxy..."

    if [ -f "/app/api/secure-proxy.py" ]; then
        python3 /app/api/secure-proxy.py &
        PROXY_PID=$!

        # Brief health check for proxy
        sleep 3
        if kill -0 $PROXY_PID 2>/dev/null; then
            log "SUCCESS" "✅ Secure API proxy started"
            return 0
        else
            log "ERROR" "❌ Secure API proxy failed to start"
            return $EXIT_SERVICE_FAILED
        fi
    else
        log "WARN" "⚠️ Secure API proxy not found, skipping"
        return 0
    fi
}

# Main startup sequence
main() {
    # Display banner
    print_banner

    # Systematic startup sequence
    load_configuration
    check_system_requirements
    setup_storage
    apply_security_hardening
    initialize_privacy
    download_models

    # Start services
    if start_ollama; then
        log "SUCCESS" "✅ Ollama service started successfully"
    else
        log "ERROR" "❌ Failed to start Ollama"
        exit $EXIT_SERVICE_FAILED
    fi

    if start_api_proxy; then
        log "SUCCESS" "✅ API proxy started successfully"
    else
        log "ERROR" "❌ Failed to start API proxy"
        exit $EXIT_SERVICE_FAILED
    fi

    log "SUCCESS" "🎉 Private LLM Cloud startup completed successfully!"
    log "INFO" "🌐 Web UI available on port: $WEB_UI_PORT"
    log "INFO" "🔌 API available on port: $API_PORT"
    log "INFO" "🔒 Privacy state: $(python3 "$PRIVACY_STATE_MANAGER" status 2>/dev/null | head -1 || echo "Unknown")"

    # Keep container running
    log "INFO" "✨ Private LLM Cloud is ready for use!"

    # Main service loop with health monitoring
    while true; do
        # Check if services are still running
        if [ -n "${OLLAMA_PID:-}" ] && ! kill -0 $OLLAMA_PID 2>/dev/null; then
            log "ERROR" "❌ Ollama process died, restarting..."
            start_ollama || exit $EXIT_SERVICE_FAILED
        fi

        if [ -n "${PROXY_PID:-}" ] && ! kill -0 $PROXY_PID 2>/dev/null; then
            log "ERROR" "❌ API proxy died, restarting..."
            start_api_proxy || exit $EXIT_SERVICE_FAILED
        fi

        # Update privacy state
        if [ -f "$PRIVACY_STATE_MANAGER" ]; then
            python3 "$PRIVACY_STATE_MANAGER" update >/dev/null 2>&1 || true
        fi

        sleep 30
    done
}

# Run main function
main