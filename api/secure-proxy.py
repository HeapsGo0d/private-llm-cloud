#!/usr/bin/env python3
"""
Private LLM Cloud - Secure API Proxy
OpenAI-compatible API with maximum privacy and security
"""

import os
import json
import time
import hmac
import hashlib
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path
from dataclasses import dataclass, asdict

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Depends, Request, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field
from cryptography.fernet import Fernet
import structlog


# Request/Response Models (OpenAI Compatible)
class ChatMessage(BaseModel):
    role: str = Field(..., description="Message role: system, user, or assistant")
    content: str = Field(..., description="Message content")


class ChatCompletionRequest(BaseModel):
    model: str = Field(..., description="Model identifier")
    messages: List[ChatMessage] = Field(..., description="List of messages")
    temperature: Optional[float] = Field(0.7, ge=0, le=2, description="Sampling temperature")
    max_tokens: Optional[int] = Field(None, ge=1, description="Maximum tokens to generate")
    stream: Optional[bool] = Field(False, description="Stream response")
    top_p: Optional[float] = Field(1.0, ge=0, le=1, description="Nucleus sampling parameter")
    frequency_penalty: Optional[float] = Field(0.0, ge=-2, le=2, description="Frequency penalty")
    presence_penalty: Optional[float] = Field(0.0, ge=-2, le=2, description="Presence penalty")
    stop: Optional[List[str]] = Field(None, description="Stop sequences")


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[Dict[str, Any]]
    usage: Dict[str, int]


class ModelsResponse(BaseModel):
    object: str = "list"
    data: List[Dict[str, Any]]


@dataclass
class SecurityConfig:
    api_key: str
    allowed_ips: List[str]
    rate_limit_requests: int
    rate_limit_window: int
    enable_encryption: bool
    max_request_size: int
    enable_audit_log: bool


class RateLimiter:
    """Token bucket rate limiter"""

    def __init__(self, requests_per_window: int, window_seconds: int):
        self.requests_per_window = requests_per_window
        self.window_seconds = window_seconds
        self.requests = {}

    def is_allowed(self, identifier: str) -> bool:
        now = time.time()
        window_start = now - self.window_seconds

        # Clean old entries
        if identifier in self.requests:
            self.requests[identifier] = [
                req_time for req_time in self.requests[identifier]
                if req_time > window_start
            ]
        else:
            self.requests[identifier] = []

        # Check rate limit
        if len(self.requests[identifier]) >= self.requests_per_window:
            return False

        # Add current request
        self.requests[identifier].append(now)
        return True


class SecurityMiddleware:
    """Custom security middleware for privacy-focused API"""

    def __init__(self, config: SecurityConfig):
        self.config = config
        self.rate_limiter = RateLimiter(
            config.rate_limit_requests,
            config.rate_limit_window
        )
        self.cipher = self._init_encryption() if config.enable_encryption else None

    def _init_encryption(self) -> Optional[Fernet]:
        """Initialize encryption for request/response"""
        key_path = Path("/app/data/.api_encryption_key")

        if key_path.exists():
            with open(key_path, "rb") as f:
                key = f.read()
        else:
            key = Fernet.generate_key()
            with open(key_path, "wb") as f:
                f.write(key)
            os.chmod(key_path, 0o600)

        return Fernet(key)

    def verify_ip(self, client_ip: str) -> bool:
        """Verify client IP against allowlist"""
        if not self.config.allowed_ips:
            return True

        for allowed_ip in self.config.allowed_ips:
            if client_ip == allowed_ip or client_ip.startswith(allowed_ip):
                return True

        return False

    def verify_api_key(self, credentials: HTTPAuthorizationCredentials) -> bool:
        """Verify API key using constant-time comparison"""
        if not credentials or not credentials.credentials:
            return False

        provided_key = credentials.credentials
        expected_key = self.config.api_key

        return hmac.compare_digest(provided_key, expected_key)

    def check_rate_limit(self, identifier: str) -> bool:
        """Check rate limiting"""
        return self.rate_limiter.is_allowed(identifier)


class AuditLogger:
    """Privacy-focused audit logger (local only)"""

    def __init__(self, config: SecurityConfig):
        self.enabled = config.enable_audit_log
        self.log_file = Path("/app/logs/api-audit.jsonl")
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

        # Setup structured logging
        structlog.configure(
            processors=[
                structlog.processors.TimeStamper(fmt="ISO"),
                structlog.processors.add_log_level,
                structlog.processors.JSONRenderer()
            ],
            wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
            logger_factory=structlog.PrintLoggerFactory(),
            cache_logger_on_first_use=True,
        )
        self.logger = structlog.get_logger()

    def log_request(self, request: Request, response_status: int, processing_time: float):
        """Log API request for audit purposes"""
        if not self.enabled:
            return

        # Extract minimal information for privacy
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "method": request.method,
            "path": request.url.path,
            "status": response_status,
            "processing_time_ms": round(processing_time * 1000, 2),
            "client_ip": request.client.host if request.client else "unknown",
            "user_agent": request.headers.get("user-agent", "unknown")[:100],  # Truncated
            "content_length": request.headers.get("content-length", 0)
        }

        # Write to local log file only
        with open(self.log_file, "a") as f:
            f.write(json.dumps(log_entry) + "\n")


class PrivateLLMAPI:
    """Privacy-focused OpenAI-compatible API"""

    def __init__(self):
        self.app = FastAPI(
            title="Private LLM API",
            description="Privacy-focused OpenAI-compatible API",
            version="1.0.0",
            docs_url="/docs" if os.getenv("DEBUG_MODE") == "true" else None,
            redoc_url=None
        )

        # Load configuration
        self.config = self._load_config()
        self.security = SecurityMiddleware(self.config)
        self.audit_logger = AuditLogger(self.config)

        # Setup middleware
        self._setup_middleware()

        # Setup routes
        self._setup_routes()

        # Ollama client
        self.ollama_client = httpx.AsyncClient(
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            timeout=300.0
        )

    def _load_config(self) -> SecurityConfig:
        """Load security configuration"""
        return SecurityConfig(
            api_key=os.getenv("API_KEY", ""),
            allowed_ips=os.getenv("ALLOWED_IPS", "127.0.0.1").split(","),
            rate_limit_requests=int(os.getenv("RATE_LIMIT_REQUESTS", "100")),
            rate_limit_window=int(os.getenv("RATE_LIMIT_WINDOW", "3600")),
            enable_encryption=os.getenv("ENABLE_ENCRYPTION", "false") == "true",
            max_request_size=int(os.getenv("MAX_REQUEST_SIZE", "10485760")),  # 10MB
            enable_audit_log=os.getenv("ENABLE_AUDIT_LOG", "true") == "true"
        )

    def _setup_middleware(self):
        """Setup security middleware"""

        # Trusted host middleware
        if self.config.allowed_ips:
            self.app.add_middleware(
                TrustedHostMiddleware,
                allowed_hosts=self.config.allowed_ips + ["localhost", "127.0.0.1"]
            )

        # CORS middleware (restrictive)
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:3000"],  # Only Web UI
            allow_credentials=True,
            allow_methods=["GET", "POST"],
            allow_headers=["Authorization", "Content-Type"],
            max_age=600
        )

        # Custom security middleware
        @self.app.middleware("http")
        async def security_middleware(request: Request, call_next):
            start_time = time.time()

            # Check IP allowlist
            client_ip = request.client.host if request.client else "unknown"
            if not self.security.verify_ip(client_ip):
                raise HTTPException(status_code=403, detail="IP not allowed")

            # Check rate limiting
            if not self.security.check_rate_limit(client_ip):
                raise HTTPException(status_code=429, detail="Rate limit exceeded")

            # Check request size
            content_length = request.headers.get("content-length")
            if content_length and int(content_length) > self.config.max_request_size:
                raise HTTPException(status_code=413, detail="Request too large")

            # Process request
            response = await call_next(request)

            # Log request for audit
            processing_time = time.time() - start_time
            self.audit_logger.log_request(request, response.status_code, processing_time)

            return response

    def _setup_routes(self):
        """Setup API routes"""

        security = HTTPBearer()

        async def verify_auth(credentials: HTTPAuthorizationCredentials = Depends(security)):
            if not self.security.verify_api_key(credentials):
                raise HTTPException(status_code=401, detail="Invalid API key")
            return credentials

        @self.app.get("/")
        async def root():
            return {"status": "Private LLM API", "privacy_mode": "maximum"}

        @self.app.get("/v1/models", response_model=ModelsResponse)
        async def list_models(auth: HTTPAuthorizationCredentials = Depends(verify_auth)):
            """List available models"""
            try:
                response = await self.ollama_client.get("/api/tags")
                ollama_models = response.json()

                models = []
                for model in ollama_models.get("models", []):
                    models.append({
                        "id": model["name"],
                        "object": "model",
                        "created": int(time.time()),
                        "owned_by": "private-llm",
                        "permission": [],
                        "root": model["name"],
                        "parent": None
                    })

                return ModelsResponse(data=models)

            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to list models: {str(e)}")

        @self.app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
        async def chat_completions(
            request: ChatCompletionRequest,
            auth: HTTPAuthorizationCredentials = Depends(verify_auth)
        ):
            """OpenAI-compatible chat completions endpoint"""
            try:
                # Convert OpenAI format to Ollama format
                ollama_request = {
                    "model": request.model,
                    "messages": [{"role": msg.role, "content": msg.content} for msg in request.messages],
                    "stream": request.stream,
                    "options": {}
                }

                # Map OpenAI parameters to Ollama options
                if request.temperature is not None:
                    ollama_request["options"]["temperature"] = request.temperature

                if request.max_tokens is not None:
                    ollama_request["options"]["num_predict"] = request.max_tokens

                if request.top_p is not None:
                    ollama_request["options"]["top_p"] = request.top_p

                if request.stop:
                    ollama_request["options"]["stop"] = request.stop

                # Send request to Ollama
                response = await self.ollama_client.post("/api/chat", json=ollama_request)

                if response.status_code != 200:
                    raise HTTPException(status_code=response.status_code, detail="Ollama request failed")

                ollama_response = response.json()

                # Convert Ollama response to OpenAI format
                openai_response = ChatCompletionResponse(
                    id=f"chatcmpl-{int(time.time())}",
                    created=int(time.time()),
                    model=request.model,
                    choices=[{
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": ollama_response.get("message", {}).get("content", "")
                        },
                        "finish_reason": "stop"
                    }],
                    usage={
                        "prompt_tokens": ollama_response.get("prompt_eval_count", 0),
                        "completion_tokens": ollama_response.get("eval_count", 0),
                        "total_tokens": ollama_response.get("prompt_eval_count", 0) + ollama_response.get("eval_count", 0)
                    }
                )

                return openai_response

            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Chat completion failed: {str(e)}")

        @self.app.post("/v1/completions")
        async def completions(
            request: dict,
            auth: HTTPAuthorizationCredentials = Depends(verify_auth)
        ):
            """Legacy completions endpoint"""
            # Convert to chat format and redirect
            chat_request = ChatCompletionRequest(
                model=request.get("model"),
                messages=[ChatMessage(role="user", content=request.get("prompt", ""))],
                temperature=request.get("temperature", 0.7),
                max_tokens=request.get("max_tokens"),
                stream=request.get("stream", False)
            )

            response = await chat_completions(chat_request, auth)

            # Convert back to completions format
            return {
                "id": response.id,
                "object": "text_completion",
                "created": response.created,
                "model": response.model,
                "choices": [{
                    "text": response.choices[0]["message"]["content"],
                    "index": 0,
                    "finish_reason": "stop"
                }],
                "usage": response.usage
            }

        @self.app.get("/health")
        async def health_check():
            """Health check endpoint"""
            try:
                # Check Ollama connection
                response = await self.ollama_client.get("/api/tags", timeout=5.0)
                ollama_status = "healthy" if response.status_code == 200 else "unhealthy"

                return {
                    "status": "healthy",
                    "timestamp": datetime.utcnow().isoformat(),
                    "services": {
                        "ollama": ollama_status,
                        "api": "healthy"
                    },
                    "privacy_mode": os.getenv("PRIVACY_MODE", "unknown")
                }

            except Exception as e:
                raise HTTPException(status_code=503, detail=f"Service unhealthy: {str(e)}")

        @self.app.post("/privacy/purge")
        async def emergency_purge(auth: HTTPAuthorizationCredentials = Depends(verify_auth)):
            """Emergency data purge endpoint"""
            try:
                # This would trigger the emergency purge script
                import subprocess
                result = subprocess.run(
                    ["/app/scripts/emergency-purge.sh"],
                    input="PURGE_ALL_DATA\n",
                    text=True,
                    capture_output=True
                )

                if result.returncode == 0:
                    return {"status": "success", "message": "Emergency purge completed"}
                else:
                    raise HTTPException(status_code=500, detail="Purge failed")

            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Emergency purge failed: {str(e)}")

    async def shutdown(self):
        """Cleanup on shutdown"""
        await self.ollama_client.aclose()


# Application factory
def create_app() -> FastAPI:
    """Create and configure the FastAPI application"""
    api = PrivateLLMAPI()
    return api.app


# CLI interface
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Private LLM Secure API")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    parser.add_argument("--workers", type=int, default=1, help="Number of workers")
    parser.add_argument("--log-level", default="info", choices=["debug", "info", "warning", "error"])

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Create application
    app = create_app()

    # Run server
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        workers=args.workers,
        log_level=args.log_level,
        access_log=False,  # Disable access logs for privacy
        server_header=False,  # Hide server header
        date_header=False  # Hide date header
    )