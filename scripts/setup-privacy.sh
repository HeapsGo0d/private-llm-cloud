#!/bin/bash
set -euo pipefail

# Private LLM Cloud - Privacy Setup Script
# Configures maximum privacy settings for all components

echo "🔐 Setting up privacy controls..."

# Initialize privacy settings
init_privacy_settings() {
    echo "🎯 Initializing privacy settings..."

    # Create privacy configuration directory
    mkdir -p /app/configs/privacy
    chmod 700 /app/configs/privacy

    # Privacy configuration file
    cat > /app/configs/privacy/privacy-config.json << EOF
{
  "privacy_mode": "${PRIVACY_MODE:-maximum}",
  "data_retention_days": ${DATA_RETENTION_DAYS:-7},
  "encrypt_conversations": ${ENCRYPT_STORAGE:-true},
  "disable_logging": ${DISABLE_LOGGING:-true},
  "offline_mode": ${OFFLINE_MODE:-false},
  "purge_on_shutdown": ${PURGE_ON_SHUTDOWN:-false},
  "allowed_ips": "${ALLOWED_IPS:-127.0.0.1}",
  "enable_audit_trail": ${ENABLE_AUDIT_LOG:-true},
  "timestamp": "$(date -Iseconds)"
}
EOF

    chmod 600 /app/configs/privacy/privacy-config.json
    echo "✅ Privacy settings initialized"
}

# Configure Ollama for maximum privacy
configure_ollama_privacy() {
    echo "🦙 Configuring Ollama privacy settings..."

    # Create Ollama configuration
    mkdir -p /app/configs/ollama
    cat > /app/configs/ollama/privacy.json << EOF
{
  "OLLAMA_KEEP_ALIVE": "5m",
  "OLLAMA_MAX_LOADED_MODELS": 1,
  "OLLAMA_NUM_PARALLEL": 1,
  "OLLAMA_FLASH_ATTENTION": true,
  "OLLAMA_NOHISTORY": true,
  "OLLAMA_ORIGINS": "${ALLOWED_IPS:-127.0.0.1}",
  "OLLAMA_HOST": "0.0.0.0:11434"
}
EOF

    # Set environment variables for Ollama
    export OLLAMA_KEEP_ALIVE=5m
    export OLLAMA_MAX_LOADED_MODELS=1
    export OLLAMA_NOHISTORY=true
    export OLLAMA_ORIGINS="${ALLOWED_IPS:-127.0.0.1}"

    echo "✅ Ollama privacy configured"
}

# Setup conversation encryption
setup_conversation_encryption() {
    echo "💬 Setting up conversation encryption..."

    if [ "${ENCRYPT_STORAGE:-true}" = "true" ]; then
        # Create encrypted conversation storage
        mkdir -p /app/data/conversations/encrypted
        chmod 700 /app/data/conversations

        # Generate conversation encryption key
        if [ ! -f /app/data/.conversation_key ]; then
            openssl rand -base64 32 > /app/data/.conversation_key
            chmod 600 /app/data/.conversation_key
        fi

        # Create conversation manager script
        cat > /app/scripts/conversation-manager.py << 'EOF'
#!/usr/bin/env python3
import os
import json
import base64
from cryptography.fernet import Fernet
from datetime import datetime, timedelta
from pathlib import Path

class ConversationManager:
    def __init__(self):
        self.data_dir = Path("/app/data/conversations")
        self.key_file = Path("/app/data/.conversation_key")
        self.cipher = self._load_cipher()

    def _load_cipher(self):
        if self.key_file.exists():
            with open(self.key_file, 'rb') as f:
                key = f.read().strip()
            return Fernet(base64.urlsafe_b64encode(key[:32].ljust(32, b'0')))
        return None

    def encrypt_conversation(self, conversation_data):
        if not self.cipher:
            return conversation_data
        encrypted = self.cipher.encrypt(json.dumps(conversation_data).encode())
        return base64.b64encode(encrypted).decode()

    def decrypt_conversation(self, encrypted_data):
        if not self.cipher:
            return encrypted_data
        try:
            decoded = base64.b64decode(encrypted_data.encode())
            decrypted = self.cipher.decrypt(decoded)
            return json.loads(decrypted.decode())
        except:
            return None

    def cleanup_old_conversations(self, retention_days=7):
        cutoff_date = datetime.now() - timedelta(days=retention_days)
        cleaned = 0

        for conv_file in self.data_dir.glob("*.json"):
            if conv_file.stat().st_mtime < cutoff_date.timestamp():
                conv_file.unlink()
                cleaned += 1

        return cleaned

if __name__ == "__main__":
    manager = ConversationManager()
    cleaned = manager.cleanup_old_conversations(int(os.getenv("DATA_RETENTION_DAYS", "7")))
    print(f"Cleaned {cleaned} old conversations")
EOF

        chmod +x /app/scripts/conversation-manager.py
        echo "✅ Conversation encryption configured"
    else
        echo "⚠️ Conversation encryption disabled"
    fi
}

# Configure Web UI privacy settings
configure_webui_privacy() {
    echo "🌐 Configuring Web UI privacy settings..."

    # Create Web UI privacy configuration
    mkdir -p /app/configs/webui
    cat > /app/configs/webui/privacy.json << EOF
{
  "ENABLE_SIGNUP": false,
  "ENABLE_LOGIN_FORM": true,
  "DEFAULT_USER_ROLE": "user",
  "ENABLE_COMMUNITY_SHARING": false,
  "ENABLE_MESSAGE_RATING": false,
  "ENABLE_MODEL_FILTER": true,
  "SHOW_ADMIN_DETAILS": false,
  "ENABLE_API_KEY": true,
  "ENABLE_WEBSOCKET_SUPPORT": false,
  "SAFE_MODE": true,
  "WEBUI_SESSION_COOKIE_SECURE": true,
  "WEBUI_SESSION_COOKIE_SAME_SITE": "Strict"
}
EOF

    # Additional privacy environment variables for Web UI
    export ENABLE_SIGNUP=false
    export ENABLE_COMMUNITY_SHARING=false
    export ENABLE_MESSAGE_RATING=false
    export SAFE_MODE=true

    echo "✅ Web UI privacy configured"
}

# Setup data isolation
setup_data_isolation() {
    echo "🏝️ Setting up data isolation..."

    # Create isolated data directories
    mkdir -p /app/data/{models,conversations,logs,temp,cache}
    chmod 700 /app/data/*

    # Create data isolation script
    cat > /app/scripts/data-isolation.sh << 'EOF'
#!/bin/bash
# Data isolation enforcement

# Clear system caches
clear_caches() {
    echo "🧹 Clearing system caches..."

    # Clear Python cache
    find /app -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
    find /app -name "*.pyc" -delete 2>/dev/null || true

    # Clear HuggingFace cache if not in privacy mode
    if [ "${PRIVACY_MODE:-}" != "maximum" ]; then
        rm -rf ~/.cache/huggingface/* 2>/dev/null || true
    fi

    # Clear temp files
    find /app/data/temp -type f -mtime +1 -delete 2>/dev/null || true
}

# Secure file permissions
secure_permissions() {
    echo "🔒 Securing file permissions..."

    # Secure data directories
    find /app/data -type d -exec chmod 700 {} \;
    find /app/data -type f -exec chmod 600 {} \;

    # Secure configuration files
    find /app/configs -name "*.json" -exec chmod 600 {} \;
    find /app/configs -name "*.key" -exec chmod 600 {} \;
}

# Network isolation check
check_network_isolation() {
    echo "📡 Checking network isolation..."

    if [ "${OFFLINE_MODE:-false}" = "true" ]; then
        # In offline mode, verify no external connections
        if command -v netstat >/dev/null; then
            external_connections=$(netstat -tn 2>/dev/null | grep -v "127.0.0.1\|::1" | grep ESTABLISHED | wc -l)
            if [ "$external_connections" -gt 0 ]; then
                echo "⚠️ Warning: $external_connections external connections detected in offline mode"
            fi
        fi
    fi
}

# Main isolation routine
main() {
    clear_caches
    secure_permissions
    check_network_isolation
    echo "✅ Data isolation enforced"
}

main "$@"
EOF

    chmod +x /app/scripts/data-isolation.sh
    echo "✅ Data isolation configured"
}

# Create emergency purge functionality
create_emergency_purge() {
    echo "🚨 Setting up emergency purge functionality..."

    cat > /app/scripts/emergency-purge.sh << 'EOF'
#!/bin/bash
set -euo pipefail

# Emergency data purge script
# WARNING: This will permanently delete ALL data

echo "🚨 EMERGENCY DATA PURGE INITIATED"
echo "This will permanently delete ALL conversations, models, and logs!"
read -p "Type 'PURGE_ALL_DATA' to confirm: " confirmation

if [ "$confirmation" != "PURGE_ALL_DATA" ]; then
    echo "❌ Purge cancelled"
    exit 1
fi

echo "🔥 Purging all data..."

# Secure deletion of sensitive data
secure_delete() {
    local target="$1"
    if [ -f "$target" ]; then
        # Overwrite file multiple times
        shred -vfz -n 3 "$target" 2>/dev/null || rm -f "$target"
    elif [ -d "$target" ]; then
        # Secure delete directory contents
        find "$target" -type f -exec shred -vfz -n 3 {} \; 2>/dev/null || true
        rm -rf "$target"
    fi
}

# Stop services
echo "🛑 Stopping services..."
pkill -f ollama || true
pkill -f python || true

# Purge data directories
echo "🗑️ Purging data directories..."
secure_delete "/app/data/conversations"
secure_delete "/app/data/models"
secure_delete "/app/data/logs"
secure_delete "/app/data/cache"
secure_delete "/app/data/temp"

# Purge configuration files with secrets
echo "🔑 Purging secrets..."
secure_delete "/app/data/.encryption_key"
secure_delete "/app/data/.conversation_key"
secure_delete "/app/.env"

# Clear system logs
echo "📝 Clearing logs..."
find /var/log -type f -exec truncate -s 0 {} \; 2>/dev/null || true

# Clear shell history
echo "🐚 Clearing shell history..."
history -c 2>/dev/null || true
cat /dev/null > ~/.bash_history 2>/dev/null || true

echo "✅ Emergency purge completed"
echo "🔄 Container restart recommended"
EOF

    chmod +x /app/scripts/emergency-purge.sh
    echo "✅ Emergency purge functionality created"
}

# Setup privacy monitoring
setup_privacy_monitoring() {
    echo "👁️ Setting up privacy monitoring..."

    cat > /app/scripts/privacy-check.py << 'EOF'
#!/usr/bin/env python3
import os
import json
import socket
import psutil
import subprocess
from pathlib import Path
from datetime import datetime

class PrivacyChecker:
    def __init__(self):
        self.privacy_config = self._load_privacy_config()

    def _load_privacy_config(self):
        config_path = Path("/app/configs/privacy/privacy-config.json")
        if config_path.exists():
            with open(config_path) as f:
                return json.load(f)
        return {}

    def check_network_connections(self):
        """Check for unauthorized external connections"""
        connections = []
        for conn in psutil.net_connections(kind='inet'):
            if conn.status == 'ESTABLISHED' and conn.raddr:
                # Check if connection is to external IP
                if not (conn.raddr.ip.startswith('127.') or
                       conn.raddr.ip.startswith('10.') or
                       conn.raddr.ip.startswith('172.') or
                       conn.raddr.ip.startswith('192.168.')):
                    connections.append({
                        'local': f"{conn.laddr.ip}:{conn.laddr.port}",
                        'remote': f"{conn.raddr.ip}:{conn.raddr.port}",
                        'pid': conn.pid
                    })
        return connections

    def check_file_permissions(self):
        """Verify secure file permissions"""
        issues = []
        sensitive_paths = [
            "/app/data/.encryption_key",
            "/app/data/.conversation_key",
            "/app/configs/privacy/privacy-config.json"
        ]

        for path in sensitive_paths:
            if Path(path).exists():
                stat = Path(path).stat()
                perms = oct(stat.st_mode)[-3:]
                if perms != '600':
                    issues.append(f"{path}: {perms} (should be 600)")

        return issues

    def check_telemetry_status(self):
        """Verify telemetry is disabled"""
        telemetry_vars = {
            'HF_HUB_DISABLE_TELEMETRY': '1',
            'PYTHONDONTWRITEBYTECODE': '1',
            'DISABLE_TELEMETRY': 'true'
        }

        issues = []
        for var, expected in telemetry_vars.items():
            if os.getenv(var) != expected:
                issues.append(f"{var} not set to {expected}")

        return issues

    def generate_privacy_report(self):
        """Generate comprehensive privacy status report"""
        report = {
            'timestamp': datetime.now().isoformat(),
            'privacy_mode': os.getenv('PRIVACY_MODE', 'unknown'),
            'external_connections': self.check_network_connections(),
            'permission_issues': self.check_file_permissions(),
            'telemetry_issues': self.check_telemetry_status(),
            'offline_mode': os.getenv('OFFLINE_MODE', 'false') == 'true'
        }

        # Calculate privacy score
        issues_count = (len(report['external_connections']) +
                       len(report['permission_issues']) +
                       len(report['telemetry_issues']))

        if issues_count == 0:
            report['privacy_score'] = 'EXCELLENT'
        elif issues_count <= 2:
            report['privacy_score'] = 'GOOD'
        elif issues_count <= 5:
            report['privacy_score'] = 'FAIR'
        else:
            report['privacy_score'] = 'POOR'

        return report

if __name__ == "__main__":
    checker = PrivacyChecker()
    report = checker.generate_privacy_report()

    print(f"🔒 Privacy Status Report - {report['timestamp']}")
    print(f"📊 Privacy Score: {report['privacy_score']}")
    print(f"🎯 Privacy Mode: {report['privacy_mode']}")
    print(f"📡 Offline Mode: {report['offline_mode']}")

    if report['external_connections']:
        print(f"⚠️ External Connections: {len(report['external_connections'])}")
        for conn in report['external_connections']:
            print(f"  - {conn['local']} -> {conn['remote']} (PID: {conn['pid']})")

    if report['permission_issues']:
        print(f"🔓 Permission Issues: {len(report['permission_issues'])}")
        for issue in report['permission_issues']:
            print(f"  - {issue}")

    if report['telemetry_issues']:
        print(f"📡 Telemetry Issues: {len(report['telemetry_issues'])}")
        for issue in report['telemetry_issues']:
            print(f"  - {issue}")

    # Save report
    with open('/app/logs/privacy-report.json', 'w') as f:
        json.dump(report, f, indent=2)
EOF

    chmod +x /app/scripts/privacy-check.py
    echo "✅ Privacy monitoring configured"
}

# Main execution
main() {
    echo "Starting privacy setup process..."

    init_privacy_settings
    configure_ollama_privacy
    setup_conversation_encryption
    configure_webui_privacy
    setup_data_isolation
    create_emergency_purge
    setup_privacy_monitoring

    # Run data isolation script
    /app/scripts/data-isolation.sh

    # Create privacy setup completion marker
    touch /app/.privacy_configured
    chmod 600 /app/.privacy_configured

    echo "🎉 Privacy setup completed successfully!"

    # Generate initial privacy report
    if [ -x /app/scripts/privacy-check.py ]; then
        echo "📊 Generating initial privacy report..."
        python3 /app/scripts/privacy-check.py
    fi
}

# Run main function
main "$@"