#!/usr/bin/env python3
"""
Private LLM Cloud - Authentication Middleware
Advanced authentication and authorization for maximum security
"""

import os
import jwt
import time
import hmac
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, Request
from cryptography.fernet import Fernet
from passlib.context import CryptContext
from passlib.hash import bcrypt


@dataclass
class User:
    username: str
    password_hash: str
    api_keys: List[str]
    permissions: List[str]
    created_at: datetime
    last_login: Optional[datetime]
    is_active: bool
    rate_limit: int


@dataclass
class Session:
    session_id: str
    user_id: str
    created_at: datetime
    expires_at: datetime
    ip_address: str
    user_agent: str
    is_active: bool


class AuthenticationManager:
    """Secure authentication manager with privacy focus"""

    def __init__(self):
        self.data_dir = Path("/app/data/auth")
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Initialize encryption
        self.cipher = self._init_encryption()

        # Password hashing
        self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

        # JWT settings
        self.jwt_secret = self._get_jwt_secret()
        self.jwt_algorithm = "HS256"
        self.jwt_expiry = timedelta(hours=24)

        # User database (in production, use encrypted file or secure database)
        self.users_file = self.data_dir / "users.enc"
        self.sessions_file = self.data_dir / "sessions.enc"

        # Rate limiting
        self.rate_limits = {}
        self.failed_attempts = {}

        # Load existing data
        self.users = self._load_users()
        self.sessions = self._load_sessions()

        # Create default admin user if none exists
        if not self.users:
            self._create_default_admin()

    def _init_encryption(self) -> Fernet:
        """Initialize encryption for user data"""
        key_path = self.data_dir / ".auth_key"

        if key_path.exists():
            with open(key_path, "rb") as f:
                key = f.read()
        else:
            key = Fernet.generate_key()
            with open(key_path, "wb") as f:
                f.write(key)
            os.chmod(key_path, 0o600)

        return Fernet(key)

    def _get_jwt_secret(self) -> str:
        """Get or generate JWT secret"""
        secret_path = self.data_dir / ".jwt_secret"

        if secret_path.exists():
            with open(secret_path, "r") as f:
                return f.read().strip()
        else:
            secret = secrets.token_urlsafe(32)
            with open(secret_path, "w") as f:
                f.write(secret)
            os.chmod(secret_path, 0o600)
            return secret

    def _create_default_admin(self):
        """Create default admin user"""
        admin_password = os.getenv("ADMIN_PASSWORD", secrets.token_urlsafe(16))

        admin_user = User(
            username="admin",
            password_hash=self.pwd_context.hash(admin_password),
            api_keys=[self._generate_api_key()],
            permissions=["admin", "chat", "models"],
            created_at=datetime.utcnow(),
            last_login=None,
            is_active=True,
            rate_limit=1000
        )

        self.users["admin"] = admin_user
        self._save_users()

        # Log admin credentials (in production, use secure method)
        print(f"🔑 Default admin created - Username: admin, Password: {admin_password}")

    def _generate_api_key(self) -> str:
        """Generate secure API key"""
        return f"pllm_{secrets.token_urlsafe(32)}"

    def _load_users(self) -> Dict[str, User]:
        """Load encrypted users from file"""
        if not self.users_file.exists():
            return {}

        try:
            with open(self.users_file, "rb") as f:
                encrypted_data = f.read()

            decrypted_data = self.cipher.decrypt(encrypted_data)
            users_data = json.loads(decrypted_data.decode())

            users = {}
            for username, user_data in users_data.items():
                users[username] = User(**user_data)

            return users

        except Exception as e:
            print(f"Failed to load users: {e}")
            return {}

    def _save_users(self):
        """Save encrypted users to file"""
        try:
            users_data = {}
            for username, user in self.users.items():
                users_data[username] = {
                    "username": user.username,
                    "password_hash": user.password_hash,
                    "api_keys": user.api_keys,
                    "permissions": user.permissions,
                    "created_at": user.created_at.isoformat(),
                    "last_login": user.last_login.isoformat() if user.last_login else None,
                    "is_active": user.is_active,
                    "rate_limit": user.rate_limit
                }

            data_str = json.dumps(users_data)
            encrypted_data = self.cipher.encrypt(data_str.encode())

            with open(self.users_file, "wb") as f:
                f.write(encrypted_data)

            os.chmod(self.users_file, 0o600)

        except Exception as e:
            print(f"Failed to save users: {e}")

    def _load_sessions(self) -> Dict[str, Session]:
        """Load encrypted sessions from file"""
        if not self.sessions_file.exists():
            return {}

        try:
            with open(self.sessions_file, "rb") as f:
                encrypted_data = f.read()

            decrypted_data = self.cipher.decrypt(encrypted_data)
            sessions_data = json.loads(decrypted_data.decode())

            sessions = {}
            for session_id, session_data in sessions_data.items():
                sessions[session_id] = Session(
                    session_id=session_data["session_id"],
                    user_id=session_data["user_id"],
                    created_at=datetime.fromisoformat(session_data["created_at"]),
                    expires_at=datetime.fromisoformat(session_data["expires_at"]),
                    ip_address=session_data["ip_address"],
                    user_agent=session_data["user_agent"],
                    is_active=session_data["is_active"]
                )

            return sessions

        except Exception as e:
            print(f"Failed to load sessions: {e}")
            return {}

    def _save_sessions(self):
        """Save encrypted sessions to file"""
        try:
            sessions_data = {}
            for session_id, session in self.sessions.items():
                sessions_data[session_id] = {
                    "session_id": session.session_id,
                    "user_id": session.user_id,
                    "created_at": session.created_at.isoformat(),
                    "expires_at": session.expires_at.isoformat(),
                    "ip_address": session.ip_address,
                    "user_agent": session.user_agent,
                    "is_active": session.is_active
                }

            data_str = json.dumps(sessions_data)
            encrypted_data = self.cipher.encrypt(data_str.encode())

            with open(self.sessions_file, "wb") as f:
                f.write(encrypted_data)

            os.chmod(self.sessions_file, 0o600)

        except Exception as e:
            print(f"Failed to save sessions: {e}")

    def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """Authenticate user with username and password"""
        user = self.users.get(username)

        if not user or not user.is_active:
            return None

        if not self.pwd_context.verify(password, user.password_hash):
            self._record_failed_attempt(username)
            return None

        # Update last login
        user.last_login = datetime.utcnow()
        self._save_users()

        return user

    def authenticate_api_key(self, api_key: str) -> Optional[User]:
        """Authenticate using API key"""
        for user in self.users.values():
            if api_key in user.api_keys and user.is_active:
                return user

        return None

    def authenticate_jwt(self, token: str) -> Optional[User]:
        """Authenticate using JWT token"""
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=[self.jwt_algorithm])
            username = payload.get("sub")

            if not username:
                return None

            user = self.users.get(username)
            if not user or not user.is_active:
                return None

            return user

        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

    def generate_jwt_token(self, user: User) -> str:
        """Generate JWT token for user"""
        payload = {
            "sub": user.username,
            "iat": datetime.utcnow(),
            "exp": datetime.utcnow() + self.jwt_expiry,
            "permissions": user.permissions
        }

        return jwt.encode(payload, self.jwt_secret, algorithm=self.jwt_algorithm)

    def create_session(self, user: User, ip_address: str, user_agent: str) -> Session:
        """Create new session for user"""
        session_id = secrets.token_urlsafe(32)
        session = Session(
            session_id=session_id,
            user_id=user.username,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=24),
            ip_address=ip_address,
            user_agent=user_agent[:200],  # Truncate user agent
            is_active=True
        )

        self.sessions[session_id] = session
        self._save_sessions()

        return session

    def validate_session(self, session_id: str, ip_address: str) -> Optional[Session]:
        """Validate session"""
        session = self.sessions.get(session_id)

        if not session or not session.is_active:
            return None

        if datetime.utcnow() > session.expires_at:
            session.is_active = False
            self._save_sessions()
            return None

        # Verify IP address (optional strict mode)
        if os.getenv("STRICT_SESSION_IP", "false") == "true":
            if session.ip_address != ip_address:
                return None

        return session

    def revoke_session(self, session_id: str):
        """Revoke session"""
        if session_id in self.sessions:
            self.sessions[session_id].is_active = False
            self._save_sessions()

    def _record_failed_attempt(self, identifier: str):
        """Record failed authentication attempt"""
        now = time.time()
        if identifier not in self.failed_attempts:
            self.failed_attempts[identifier] = []

        # Clean old attempts (older than 1 hour)
        self.failed_attempts[identifier] = [
            attempt for attempt in self.failed_attempts[identifier]
            if now - attempt < 3600
        ]

        self.failed_attempts[identifier].append(now)

    def is_blocked(self, identifier: str) -> bool:
        """Check if identifier is blocked due to failed attempts"""
        if identifier not in self.failed_attempts:
            return False

        # Block after 5 failed attempts in 1 hour
        return len(self.failed_attempts[identifier]) >= 5

    def check_rate_limit(self, user: User, endpoint: str) -> bool:
        """Check rate limiting for user"""
        now = time.time()
        key = f"{user.username}:{endpoint}"

        if key not in self.rate_limits:
            self.rate_limits[key] = []

        # Clean old requests (older than 1 hour)
        self.rate_limits[key] = [
            req_time for req_time in self.rate_limits[key]
            if now - req_time < 3600
        ]

        # Check limit
        if len(self.rate_limits[key]) >= user.rate_limit:
            return False

        self.rate_limits[key].append(now)
        return True

    def create_user(self, username: str, password: str, permissions: List[str]) -> User:
        """Create new user"""
        if username in self.users:
            raise ValueError("User already exists")

        user = User(
            username=username,
            password_hash=self.pwd_context.hash(password),
            api_keys=[self._generate_api_key()],
            permissions=permissions,
            created_at=datetime.utcnow(),
            last_login=None,
            is_active=True,
            rate_limit=100
        )

        self.users[username] = user
        self._save_users()

        return user

    def delete_user(self, username: str):
        """Delete user"""
        if username in self.users:
            del self.users[username]
            self._save_users()

            # Revoke all sessions for user
            for session in self.sessions.values():
                if session.user_id == username:
                    session.is_active = False

            self._save_sessions()

    def generate_new_api_key(self, username: str) -> str:
        """Generate new API key for user"""
        user = self.users.get(username)
        if not user:
            raise ValueError("User not found")

        new_key = self._generate_api_key()
        user.api_keys.append(new_key)
        self._save_users()

        return new_key

    def revoke_api_key(self, username: str, api_key: str):
        """Revoke specific API key"""
        user = self.users.get(username)
        if not user:
            return

        if api_key in user.api_keys:
            user.api_keys.remove(api_key)
            self._save_users()

    def cleanup_expired_sessions(self):
        """Clean up expired sessions"""
        now = datetime.utcnow()
        expired_sessions = [
            session_id for session_id, session in self.sessions.items()
            if session.expires_at < now
        ]

        for session_id in expired_sessions:
            del self.sessions[session_id]

        if expired_sessions:
            self._save_sessions()

        return len(expired_sessions)

    def get_user_info(self, username: str) -> Optional[Dict]:
        """Get user information (sanitized)"""
        user = self.users.get(username)
        if not user:
            return None

        return {
            "username": user.username,
            "permissions": user.permissions,
            "created_at": user.created_at.isoformat(),
            "last_login": user.last_login.isoformat() if user.last_login else None,
            "is_active": user.is_active,
            "api_key_count": len(user.api_keys),
            "rate_limit": user.rate_limit
        }

    def get_active_sessions(self, username: str) -> List[Dict]:
        """Get active sessions for user"""
        sessions = []
        for session in self.sessions.values():
            if session.user_id == username and session.is_active:
                sessions.append({
                    "session_id": session.session_id[:8] + "...",  # Partial ID for security
                    "created_at": session.created_at.isoformat(),
                    "expires_at": session.expires_at.isoformat(),
                    "ip_address": session.ip_address,
                    "user_agent": session.user_agent[:50] + "..." if len(session.user_agent) > 50 else session.user_agent
                })

        return sessions


# Request authentication decorators and utilities
class AuthenticationRequired:
    """Authentication decorator class"""

    def __init__(self, auth_manager: AuthenticationManager):
        self.auth_manager = auth_manager

    def __call__(self, permissions: List[str] = None):
        """Authentication decorator with optional permissions check"""

        def decorator(func):
            async def wrapper(request: Request, *args, **kwargs):
                # Extract authentication information
                auth_header = request.headers.get("Authorization")
                session_cookie = request.cookies.get("session_id")

                user = None

                # Try API key authentication
                if auth_header and auth_header.startswith("Bearer "):
                    token = auth_header[7:]

                    # Try JWT first
                    user = self.auth_manager.authenticate_jwt(token)

                    # If JWT fails, try API key
                    if not user:
                        user = self.auth_manager.authenticate_api_key(token)

                # Try session authentication
                elif session_cookie:
                    client_ip = request.client.host if request.client else "unknown"
                    session = self.auth_manager.validate_session(session_cookie, client_ip)

                    if session:
                        user = self.auth_manager.users.get(session.user_id)

                if not user:
                    raise HTTPException(status_code=401, detail="Authentication required")

                # Check permissions
                if permissions:
                    if not any(perm in user.permissions for perm in permissions):
                        raise HTTPException(status_code=403, detail="Insufficient permissions")

                # Check rate limiting
                if not self.auth_manager.check_rate_limit(user, request.url.path):
                    raise HTTPException(status_code=429, detail="Rate limit exceeded")

                # Add user to request state
                request.state.user = user

                return await func(request, *args, **kwargs)

            return wrapper

        return decorator


# Initialize global authentication manager
auth_manager = AuthenticationManager()
require_auth = AuthenticationRequired(auth_manager)