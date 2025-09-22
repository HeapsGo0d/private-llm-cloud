#!/usr/bin/env python3
"""
Private LLM Cloud - Privacy State Management System
Adapted from Ignition ComfyUI proven patterns for LLM use case
"""

import json
import time
import os
import subprocess
import logging
from enum import Enum
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
import psutil

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Status icons for consistent feedback
ICONS = {
    'success': '✅',
    'error': '❌',
    'warning': '⚠️',
    'info': 'ℹ️',
    'privacy': '🔒',
    'monitoring': '👁️',
    'download': '📥',
    'block': '🚫',
    'active': '🟢',
    'inactive': '🔴'
}

class PrivacyState(Enum):
    """
    Privacy states for phased blocking approach
    Based on Ignition's proven state management
    """
    STARTUP = "startup"
    DOWNLOADS_ACTIVE = "downloads_active"
    ACTIVITY_DETECTED = "activity_detected"
    STRICT = "strict"
    EMERGENCY_BLOCK = "emergency_block"
    MONITORING_ONLY = "monitoring_only"

@dataclass
class PrivacyConfig:
    """Configuration for privacy state management"""
    # State file locations
    state_file: str = "/app/data/privacy_state.json"
    log_file: str = "/app/logs/privacy.log"

    # Timeouts and intervals
    startup_grace_period: int = 300  # 5 minutes
    download_timeout: int = 3600     # 1 hour
    activity_timeout: int = 1800     # 30 minutes
    monitoring_interval: int = 5     # 5 seconds

    # Feature availability flags
    iptables_available: bool = True
    activity_detection_available: bool = True
    monitoring_only_mode: bool = False

    # Network controls
    allowed_domains: List[str] = None
    blocked_domains: List[str] = None
    startup_only_domains: List[str] = None

    def __post_init__(self):
        if self.allowed_domains is None:
            self.allowed_domains = [
                "huggingface.co",
                "hf.co",
                "github.com",
                "raw.githubusercontent.com"
            ]

        if self.blocked_domains is None:
            self.blocked_domains = [
                "api.mixpanel.com",
                "api.segment.io",
                "www.google-analytics.com",
                "analytics.google.com",
                "stats.g.doubleclick.net",
                "api.amplitude.com"
            ]

        if self.startup_only_domains is None:
            self.startup_only_domains = [
                "ollama.ai",
                "openwebui.com",
                "docker.io",
                "ghcr.io"
            ]

@dataclass
class StateInfo:
    """Information about current privacy state"""
    state: PrivacyState
    timestamp: float
    details: Dict[str, Any]
    active_downloads: List[str] = None
    activity_detected: bool = False

    def __post_init__(self):
        if self.active_downloads is None:
            self.active_downloads = []

class PrivacyStateManager:
    """
    Manages privacy states with phased blocking approach
    Incorporates Ignition's proven patterns adapted for LLM use case
    """

    def __init__(self, config: Optional[PrivacyConfig] = None):
        self.config = config or PrivacyConfig()
        self.current_state = PrivacyState.STARTUP
        self.state_start_time = time.time()
        self.logger = logging.getLogger(__name__)

        # Initialize feature detection
        self._detect_capabilities()

        # Create necessary directories
        self._ensure_directories()

        # Load previous state if available
        self._load_state()

        logger.info(f"{ICONS['privacy']} Privacy State Manager initialized")
        logger.info(f"{ICONS['info']} Current state: {self.current_state.value}")
        logger.info(f"{ICONS['info']} Monitoring only mode: {self.config.monitoring_only_mode}")

    def _detect_capabilities(self):
        """Detect system capabilities for graceful degradation"""
        try:
            # Test iptables availability
            result = subprocess.run(['iptables', '--version'],
                                  capture_output=True, text=True, timeout=5)
            self.config.iptables_available = result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
            self.config.iptables_available = False
            logger.warning(f"{ICONS['warning']} iptables not available, using monitoring-only mode")

        # If iptables unavailable, force monitoring-only mode
        if not self.config.iptables_available:
            self.config.monitoring_only_mode = True

        # Test for activity detection capabilities
        try:
            # Check if we can monitor processes
            psutil.process_iter()
            self.config.activity_detection_available = True
        except Exception:
            self.config.activity_detection_available = False
            logger.warning(f"{ICONS['warning']} Activity detection limited")

    def _ensure_directories(self):
        """Create necessary directories"""
        try:
            Path(self.config.state_file).parent.mkdir(parents=True, exist_ok=True)
            Path(self.config.log_file).parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.error(f"{ICONS['error']} Failed to create directories: {e}")

    def _load_state(self):
        """Load previous state from file"""
        try:
            if Path(self.config.state_file).exists():
                with open(self.config.state_file, 'r') as f:
                    state_data = json.load(f)

                # Validate state age
                state_age = time.time() - state_data.get('timestamp', 0)
                if state_age < 3600:  # State valid for 1 hour
                    self.current_state = PrivacyState(state_data['state'])
                    self.state_start_time = state_data['timestamp']
                    logger.info(f"{ICONS['success']} Loaded previous state: {self.current_state.value}")
                else:
                    logger.info(f"{ICONS['info']} Previous state expired, starting fresh")
        except Exception as e:
            logger.warning(f"{ICONS['warning']} Could not load previous state: {e}")

    def _save_state(self):
        """Save current state to file"""
        try:
            state_data = {
                'state': self.current_state.value,
                'timestamp': self.state_start_time,
                'monitoring_only': self.config.monitoring_only_mode,
                'capabilities': {
                    'iptables': self.config.iptables_available,
                    'activity_detection': self.config.activity_detection_available
                }
            }

            with open(self.config.state_file, 'w') as f:
                json.dump(state_data, f, indent=2)
        except Exception as e:
            logger.error(f"{ICONS['error']} Failed to save state: {e}")

    def transition_to_state(self, new_state: PrivacyState, reason: str = ""):
        """Transition to a new privacy state"""
        old_state = self.current_state
        self.current_state = new_state
        self.state_start_time = time.time()

        logger.info(f"{ICONS['privacy']} State transition: {old_state.value} → {new_state.value}")
        if reason:
            logger.info(f"{ICONS['info']} Reason: {reason}")

        # Apply state-specific configurations
        self._apply_state_config()

        # Save state
        self._save_state()

    def _apply_state_config(self):
        """Apply configuration based on current state"""
        if self.config.monitoring_only_mode:
            logger.info(f"{ICONS['monitoring']} Monitoring-only mode: logging network activity")
            return

        try:
            if self.current_state == PrivacyState.STARTUP:
                self._configure_startup_mode()
            elif self.current_state == PrivacyState.DOWNLOADS_ACTIVE:
                self._configure_download_mode()
            elif self.current_state == PrivacyState.STRICT:
                self._configure_strict_mode()
            elif self.current_state == PrivacyState.EMERGENCY_BLOCK:
                self._configure_emergency_mode()
        except Exception as e:
            logger.error(f"{ICONS['error']} Failed to apply state config: {e}")

    def _configure_startup_mode(self):
        """Configure network for startup phase"""
        logger.info(f"{ICONS['active']} Configuring startup mode - allowing essential services")

        # Allow startup domains temporarily
        allowed = self.config.allowed_domains + self.config.startup_only_domains
        self._update_network_rules(allowed=allowed, blocked=self.config.blocked_domains)

    def _configure_download_mode(self):
        """Configure network for download phase"""
        logger.info(f"{ICONS['download']} Configuring download mode - allowing model downloads")

        # Allow model download domains
        self._update_network_rules(allowed=self.config.allowed_domains,
                                 blocked=self.config.blocked_domains)

    def _configure_strict_mode(self):
        """Configure network for strict privacy mode"""
        logger.info(f"{ICONS['block']} Configuring strict mode - blocking external connections")

        # Block most external connections, allow only local
        self._update_network_rules(allowed=[], blocked=self.config.blocked_domains, strict=True)

    def _configure_emergency_mode(self):
        """Configure network for emergency privacy mode"""
        logger.info(f"{ICONS['error']} Configuring emergency mode - blocking all external connections")

        # Block everything except localhost
        self._update_network_rules(allowed=[], blocked=["*"], strict=True)

    def _update_network_rules(self, allowed: List[str], blocked: List[str], strict: bool = False):
        """Update network rules based on current state"""
        if not self.config.iptables_available:
            logger.info(f"{ICONS['monitoring']} Would update network rules (monitoring-only mode)")
            return

        try:
            # This would implement actual iptables rules in production
            # For now, we log what would be done
            logger.info(f"{ICONS['privacy']} Network rules update:")
            logger.info(f"  Allowed domains: {allowed}")
            logger.info(f"  Blocked domains: {blocked}")
            logger.info(f"  Strict mode: {strict}")

            # In a real implementation, this would call iptables commands
            # self._apply_iptables_rules(allowed, blocked, strict)

        except Exception as e:
            logger.error(f"{ICONS['error']} Failed to update network rules: {e}")

    def check_download_activity(self) -> bool:
        """Check if downloads are currently active"""
        try:
            # Check for aria2c processes
            aria2_count = 0
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                if 'aria2c' in proc.info['name']:
                    aria2_count += 1

            # Check for HuggingFace download activity
            hf_processes = 0
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                cmdline = ' '.join(proc.info['cmdline'] or [])
                if 'huggingface' in cmdline.lower() or 'snapshot_download' in cmdline:
                    hf_processes += 1

            download_active = aria2_count > 0 or hf_processes > 0

            if download_active:
                logger.info(f"{ICONS['download']} Active downloads detected (aria2c: {aria2_count}, hf: {hf_processes})")

            return download_active

        except Exception as e:
            logger.error(f"{ICONS['error']} Error checking download activity: {e}")
            return False

    def check_system_activity(self) -> bool:
        """Check for general system activity that might indicate ongoing work"""
        try:
            if not self.config.activity_detection_available:
                return False

            # Check CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            high_cpu = cpu_percent > 50

            # Check network activity
            net_io = psutil.net_io_counters()
            # This would need baseline comparison in real implementation

            # Check disk I/O
            disk_io = psutil.disk_io_counters()
            # This would need baseline comparison in real implementation

            activity_detected = high_cpu  # Simplified for now

            if activity_detected:
                logger.info(f"{ICONS['active']} System activity detected (CPU: {cpu_percent:.1f}%)")

            return activity_detected

        except Exception as e:
            logger.error(f"{ICONS['error']} Error checking system activity: {e}")
            return False

    def update_state(self):
        """Update privacy state based on current conditions"""
        try:
            current_time = time.time()
            state_duration = current_time - self.state_start_time

            downloads_active = self.check_download_activity()
            system_activity = self.check_system_activity()

            # State transition logic
            if self.current_state == PrivacyState.STARTUP:
                if downloads_active:
                    self.transition_to_state(PrivacyState.DOWNLOADS_ACTIVE, "Downloads detected")
                elif state_duration > self.config.startup_grace_period:
                    self.transition_to_state(PrivacyState.STRICT, "Startup grace period expired")

            elif self.current_state == PrivacyState.DOWNLOADS_ACTIVE:
                if not downloads_active and not system_activity:
                    self.transition_to_state(PrivacyState.STRICT, "Downloads completed")
                elif state_duration > self.config.download_timeout:
                    self.transition_to_state(PrivacyState.STRICT, "Download timeout exceeded")

            elif self.current_state == PrivacyState.ACTIVITY_DETECTED:
                if not system_activity:
                    self.transition_to_state(PrivacyState.STRICT, "Activity ceased")
                elif state_duration > self.config.activity_timeout:
                    self.transition_to_state(PrivacyState.STRICT, "Activity timeout exceeded")

            elif self.current_state == PrivacyState.STRICT:
                if downloads_active:
                    self.transition_to_state(PrivacyState.DOWNLOADS_ACTIVE, "New downloads started")
                elif system_activity:
                    self.transition_to_state(PrivacyState.ACTIVITY_DETECTED, "System activity detected")

        except Exception as e:
            logger.error(f"{ICONS['error']} Error updating state: {e}")

    def force_emergency_block(self):
        """Force transition to emergency block state"""
        self.transition_to_state(PrivacyState.EMERGENCY_BLOCK, "Emergency block activated")

    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive status information"""
        current_time = time.time()
        state_duration = current_time - self.state_start_time

        status = {
            'current_state': self.current_state.value,
            'state_duration': state_duration,
            'monitoring_only_mode': self.config.monitoring_only_mode,
            'capabilities': {
                'iptables_available': self.config.iptables_available,
                'activity_detection_available': self.config.activity_detection_available
            },
            'activity': {
                'downloads_active': self.check_download_activity(),
                'system_activity': self.check_system_activity()
            },
            'configuration': {
                'allowed_domains': len(self.config.allowed_domains),
                'blocked_domains': len(self.config.blocked_domains),
                'startup_grace_period': self.config.startup_grace_period
            }
        }

        return status

    def get_detailed_status(self) -> str:
        """Get human-readable detailed status"""
        status = self.get_status()

        lines = [
            f"{ICONS['privacy']} Privacy State Manager Status",
            f"{'=' * 40}",
            f"Current State: {status['current_state'].upper()}",
            f"State Duration: {status['state_duration']:.1f}s",
            f"Mode: {'Monitoring Only' if status['monitoring_only_mode'] else 'Active Protection'}",
            "",
            f"{ICONS['info']} Capabilities:",
            f"  iptables: {'✅' if status['capabilities']['iptables_available'] else '❌'}",
            f"  Activity Detection: {'✅' if status['capabilities']['activity_detection_available'] else '❌'}",
            "",
            f"{ICONS['active']} Current Activity:",
            f"  Downloads Active: {'✅' if status['activity']['downloads_active'] else '❌'}",
            f"  System Activity: {'✅' if status['activity']['system_activity'] else '❌'}",
            "",
            f"{ICONS['privacy']} Configuration:",
            f"  Allowed Domains: {status['configuration']['allowed_domains']}",
            f"  Blocked Domains: {status['configuration']['blocked_domains']}",
            f"  Startup Grace: {status['configuration']['startup_grace_period']}s"
        ]

        return "\n".join(lines)

if __name__ == "__main__":
    """CLI interface for testing privacy state manager"""
    import sys

    manager = PrivacyStateManager()

    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "status":
            print(manager.get_detailed_status())
        elif command == "emergency":
            manager.force_emergency_block()
            print(f"{ICONS['error']} Emergency block activated")
        elif command == "update":
            manager.update_state()
            print(f"{ICONS['success']} State updated")
        else:
            print(f"Usage: {sys.argv[0]} [status|emergency|update]")
    else:
        print(manager.get_detailed_status())