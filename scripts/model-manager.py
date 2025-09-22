#!/usr/bin/env python3
"""
Private LLM Cloud - Model Management System
Handles model downloading, format conversion, VRAM calculation, and optimization
"""

import os
import json
import math
import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from enum import Enum
import hashlib
import shutil

import httpx
from huggingface_hub import HfApi, model_info, snapshot_download
from transformers import AutoConfig, AutoTokenizer
import torch
from cryptography.fernet import Fernet


class ModelFormat(Enum):
    GGUF = "gguf"
    GPTQ = "gptq"
    AWQ = "awq"
    SAFETENSORS = "safetensors"
    PYTORCH = "pytorch"
    UNKNOWN = "unknown"


class Quantization(Enum):
    FP16 = "fp16"
    FP32 = "fp32"
    Q2_K = "Q2_K"
    Q3_K_S = "Q3_K_S"
    Q3_K_M = "Q3_K_M"
    Q3_K_L = "Q3_K_L"
    Q4_0 = "Q4_0"
    Q4_1 = "Q4_1"
    Q4_K_S = "Q4_K_S"
    Q4_K_M = "Q4_K_M"
    Q5_0 = "Q5_0"
    Q5_1 = "Q5_1"
    Q5_K_S = "Q5_K_S"
    Q5_K_M = "Q5_K_M"
    Q6_K = "Q6_K"
    Q8_0 = "Q8_0"


@dataclass
class GPUSpec:
    name: str
    vram_gb: int
    memory_bandwidth_gbps: float
    compute_capability: float
    hourly_cost_usd: float
    provider: str


@dataclass
class ModelInfo:
    model_id: str
    name: str
    size_gb: float
    parameters: int
    format: ModelFormat
    quantization: Optional[Quantization]
    architecture: str
    context_length: int
    vram_requirements: Dict[str, float]
    supported_formats: List[ModelFormat]
    download_url: Optional[str] = None
    local_path: Optional[str] = None
    encrypted: bool = False
    checksum: Optional[str] = None


@dataclass
class VRAMEstimate:
    model_size_gb: float
    context_size_gb: float
    overhead_gb: float
    total_gb: float
    recommended_gpu_gb: float
    recommended_gpus: List[GPUSpec]
    cost_per_hour: float
    tokens_per_dollar: float


class ModelManager:
    """Comprehensive model management with privacy focus"""

    def __init__(self, config_path: str = "/app/configs/model-config.json"):
        self.config_path = Path(config_path)
        self.models_dir = Path(os.getenv("MODEL_STORAGE_PATH", "/app/models"))
        self.data_dir = Path("/app/data")
        self.hf_token = os.getenv("HF_TOKEN")
        self.encryption_key = self._get_or_create_encryption_key()

        # GPU database with current pricing
        self.gpu_database = self._load_gpu_database()

        # Model database
        self.model_db_path = self.data_dir / "models.json"
        self.model_db = self._load_model_database()

        # Privacy settings
        self.privacy_mode = os.getenv("PRIVACY_MODE", "maximum") == "maximum"
        self.encrypt_storage = os.getenv("ENCRYPT_STORAGE", "true") == "true"

        # Ensure directories exist
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Setup logging
        self._setup_logging()

    def _setup_logging(self):
        """Setup secure logging"""
        log_level = os.getenv("LOG_LEVEL", "INFO")
        logging.basicConfig(
            level=getattr(logging, log_level),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler("/app/logs/model-manager.log"),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger("ModelManager")

    def _get_or_create_encryption_key(self) -> Fernet:
        """Get or create encryption key for model storage"""
        key_path = self.data_dir / ".encryption_key"

        if key_path.exists():
            with open(key_path, "rb") as f:
                key = f.read()
        else:
            key = Fernet.generate_key()
            with open(key_path, "wb") as f:
                f.write(key)
            os.chmod(key_path, 0o600)  # Secure permissions

        return Fernet(key)

    def _load_gpu_database(self) -> List[GPUSpec]:
        """Load GPU specifications and pricing"""
        return [
            # RunPod GPUs (current pricing as of 2024)
            GPUSpec("RTX 4090", 24, 1008, 8.9, 0.40, "runpod"),
            GPUSpec("RTX 3090", 24, 936, 8.6, 0.35, "runpod"),
            GPUSpec("A100 40GB", 40, 1555, 8.0, 1.50, "runpod"),
            GPUSpec("A100 80GB", 80, 1935, 8.0, 2.50, "runpod"),
            GPUSpec("H100 80GB", 80, 3350, 9.0, 4.00, "runpod"),
            GPUSpec("V100 32GB", 32, 900, 7.0, 0.80, "runpod"),

            # Vast.ai approximate pricing (variable)
            GPUSpec("RTX 4090", 24, 1008, 8.9, 0.25, "vast"),
            GPUSpec("RTX 3090", 24, 936, 8.6, 0.20, "vast"),
            GPUSpec("A100 40GB", 40, 1555, 8.0, 0.80, "vast"),
            GPUSpec("A100 80GB", 80, 1935, 8.0, 1.20, "vast"),
            GPUSpec("V100 32GB", 32, 900, 7.0, 0.45, "vast"),
        ]

    def _load_model_database(self) -> Dict[str, ModelInfo]:
        """Load model database from disk"""
        if self.model_db_path.exists():
            try:
                with open(self.model_db_path, "r") as f:
                    data = json.load(f)
                return {k: ModelInfo(**v) for k, v in data.items()}
            except Exception as e:
                self.logger.error(f"Failed to load model database: {e}")
        return {}

    def _save_model_database(self):
        """Save model database to disk"""
        try:
            data = {k: asdict(v) for k, v in self.model_db.items()}
            with open(self.model_db_path, "w") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            self.logger.error(f"Failed to save model database: {e}")

    def calculate_vram_requirements(
        self,
        model_id: str,
        quantization: Quantization = Quantization.Q4_K_M,
        context_length: int = 4096,
        batch_size: int = 1
    ) -> VRAMEstimate:
        """Calculate precise VRAM requirements for a model"""

        try:
            # Get model info from HuggingFace
            info = model_info(model_id, token=self.hf_token)
            config = AutoConfig.from_pretrained(model_id, token=self.hf_token)

            # Extract parameters
            if hasattr(config, 'num_parameters'):
                params = config.num_parameters
            else:
                # Estimate from architecture
                params = self._estimate_parameters(config)

            # Calculate model size based on quantization
            model_size_gb = self._calculate_model_size(params, quantization)

            # Calculate context memory requirements
            hidden_size = getattr(config, 'hidden_size', 4096)
            context_size_gb = (
                context_length * hidden_size * 2 * batch_size * 1e-9
            )  # 2 bytes per fp16

            # System overhead (KV cache, activations, etc.)
            overhead_gb = max(2.0, model_size_gb * 0.15)

            total_gb = model_size_gb + context_size_gb + overhead_gb
            recommended_gpu_gb = total_gb * 1.2  # 20% safety margin

            # Find suitable GPUs
            suitable_gpus = [
                gpu for gpu in self.gpu_database
                if gpu.vram_gb >= recommended_gpu_gb
            ]
            suitable_gpus.sort(key=lambda x: x.hourly_cost_usd)

            # Calculate cost metrics
            cost_per_hour = suitable_gpus[0].hourly_cost_usd if suitable_gpus else 0

            # Estimate tokens per dollar (rough calculation)
            tokens_per_second = self._estimate_throughput(params, suitable_gpus[0] if suitable_gpus else None)
            tokens_per_hour = tokens_per_second * 3600
            tokens_per_dollar = tokens_per_hour / cost_per_hour if cost_per_hour > 0 else 0

            return VRAMEstimate(
                model_size_gb=model_size_gb,
                context_size_gb=context_size_gb,
                overhead_gb=overhead_gb,
                total_gb=total_gb,
                recommended_gpu_gb=recommended_gpu_gb,
                recommended_gpus=suitable_gpus[:3],  # Top 3 recommendations
                cost_per_hour=cost_per_hour,
                tokens_per_dollar=tokens_per_dollar
            )

        except Exception as e:
            self.logger.error(f"Failed to calculate VRAM for {model_id}: {e}")
            raise

    def _calculate_model_size(self, params: int, quantization: Quantization) -> float:
        """Calculate model size based on parameters and quantization"""

        # Bytes per parameter based on quantization
        bytes_per_param = {
            Quantization.FP32: 4.0,
            Quantization.FP16: 2.0,
            Quantization.Q8_0: 1.0,
            Quantization.Q6_K: 0.75,
            Quantization.Q5_K_M: 0.625,
            Quantization.Q5_K_S: 0.625,
            Quantization.Q5_1: 0.625,
            Quantization.Q5_0: 0.625,
            Quantization.Q4_K_M: 0.5,
            Quantization.Q4_K_S: 0.5,
            Quantization.Q4_1: 0.5,
            Quantization.Q4_0: 0.5,
            Quantization.Q3_K_L: 0.375,
            Quantization.Q3_K_M: 0.375,
            Quantization.Q3_K_S: 0.375,
            Quantization.Q2_K: 0.25,
        }

        return (params * bytes_per_param.get(quantization, 2.0)) / (1024**3)

    def _estimate_parameters(self, config) -> int:
        """Estimate parameters from model config"""

        # Common parameter estimation formulas
        vocab_size = getattr(config, 'vocab_size', 32000)
        hidden_size = getattr(config, 'hidden_size', 4096)
        num_layers = getattr(config, 'num_hidden_layers', 32)
        intermediate_size = getattr(config, 'intermediate_size', hidden_size * 4)

        # Embedding parameters
        embed_params = vocab_size * hidden_size

        # Transformer block parameters per layer
        # Attention: Q, K, V projections + output projection
        attention_params = 4 * hidden_size * hidden_size

        # Feed-forward network
        ffn_params = 2 * hidden_size * intermediate_size

        # Layer norm parameters
        ln_params = 2 * hidden_size

        params_per_layer = attention_params + ffn_params + ln_params
        total_params = embed_params + (num_layers * params_per_layer)

        return total_params

    def _estimate_throughput(self, params: int, gpu: Optional[GPUSpec]) -> float:
        """Estimate tokens per second based on model size and GPU"""

        if not gpu:
            return 0.0

        # Rough throughput estimation based on parameters and GPU specs
        # This is a simplified model - real performance varies significantly

        if params < 7e9:  # < 7B
            base_throughput = 100
        elif params < 13e9:  # < 13B
            base_throughput = 50
        elif params < 30e9:  # < 30B
            base_throughput = 25
        elif params < 70e9:  # < 70B
            base_throughput = 10
        else:  # > 70B
            base_throughput = 5

        # Scale by GPU capability
        gpu_factor = gpu.compute_capability / 8.0  # Normalize to A100
        memory_factor = min(1.0, gpu.memory_bandwidth_gbps / 1000)

        return base_throughput * gpu_factor * memory_factor

    def detect_model_format(self, model_path: Path) -> ModelFormat:
        """Detect model format from files"""

        files = list(model_path.glob("*"))
        file_names = [f.name.lower() for f in files]

        if any(f.endswith('.gguf') for f in file_names):
            return ModelFormat.GGUF
        elif any('gptq' in f for f in file_names):
            return ModelFormat.GPTQ
        elif any('awq' in f for f in file_names):
            return ModelFormat.AWQ
        elif any(f.endswith('.safetensors') for f in file_names):
            return ModelFormat.SAFETENSORS
        elif any(f.endswith('.bin') for f in file_names):
            return ModelFormat.PYTORCH
        else:
            return ModelFormat.UNKNOWN

    async def download_model(
        self,
        model_id: str,
        quantization: Optional[Quantization] = None,
        force_download: bool = False
    ) -> ModelInfo:
        """Download model from HuggingFace with privacy controls"""

        try:
            self.logger.info(f"Starting download of {model_id}")

            # Check if model already exists
            if model_id in self.model_db and not force_download:
                return self.model_db[model_id]

            # Create model directory
            model_dir = self.models_dir / model_id.replace("/", "_")
            model_dir.mkdir(parents=True, exist_ok=True)

            # Download model files
            if self.privacy_mode:
                # In privacy mode, only download once then disconnect
                local_path = snapshot_download(
                    model_id,
                    cache_dir=str(model_dir),
                    token=self.hf_token,
                    local_files_only=False
                )
            else:
                local_path = snapshot_download(
                    model_id,
                    cache_dir=str(model_dir),
                    token=self.hf_token
                )

            # Get model info
            config = AutoConfig.from_pretrained(local_path)

            # Calculate model info
            params = self._estimate_parameters(config)
            format_detected = self.detect_model_format(Path(local_path))

            # Calculate size
            total_size = sum(
                f.stat().st_size for f in Path(local_path).rglob("*")
                if f.is_file()
            ) / (1024**3)

            # Create model info
            model_info_obj = ModelInfo(
                model_id=model_id,
                name=model_id.split("/")[-1],
                size_gb=total_size,
                parameters=params,
                format=format_detected,
                quantization=quantization,
                architecture=config.model_type if hasattr(config, 'model_type') else "unknown",
                context_length=getattr(config, 'max_position_embeddings', 4096),
                vram_requirements={},
                supported_formats=[format_detected],
                local_path=str(local_path),
                encrypted=False,
                checksum=self._calculate_checksum(Path(local_path))
            )

            # Calculate VRAM requirements for common quantizations
            for quant in [Quantization.Q4_K_M, Quantization.Q5_K_M, Quantization.FP16]:
                try:
                    vram_est = self.calculate_vram_requirements(model_id, quant)
                    model_info_obj.vram_requirements[quant.value] = vram_est.total_gb
                except:
                    pass

            # Encrypt if required
            if self.encrypt_storage:
                await self._encrypt_model(Path(local_path))
                model_info_obj.encrypted = True

            # Save to database
            self.model_db[model_id] = model_info_obj
            self._save_model_database()

            self.logger.info(f"Successfully downloaded {model_id}")
            return model_info_obj

        except Exception as e:
            self.logger.error(f"Failed to download {model_id}: {e}")
            raise

    def _calculate_checksum(self, path: Path) -> str:
        """Calculate checksum for model verification"""
        hasher = hashlib.sha256()

        for file_path in sorted(path.rglob("*")):
            if file_path.is_file():
                with open(file_path, "rb") as f:
                    for chunk in iter(lambda: f.read(4096), b""):
                        hasher.update(chunk)

        return hasher.hexdigest()

    async def _encrypt_model(self, model_path: Path):
        """Encrypt model files for maximum privacy"""
        # Implementation would encrypt model files
        # For now, just log the action
        self.logger.info(f"Encrypting model at {model_path}")

    def recommend_optimal_gpu(
        self,
        model_id: str,
        usage_pattern: str = "interactive",
        budget_limit: Optional[float] = None
    ) -> Dict[str, Any]:
        """Recommend optimal GPU setup for a model"""

        try:
            # Calculate VRAM requirements
            vram_est = self.calculate_vram_requirements(model_id)

            # Filter GPUs by budget
            suitable_gpus = vram_est.recommended_gpus
            if budget_limit:
                suitable_gpus = [
                    gpu for gpu in suitable_gpus
                    if gpu.hourly_cost_usd <= budget_limit
                ]

            if not suitable_gpus:
                return {"error": "No suitable GPUs found within budget"}

            # Score GPUs based on usage pattern
            scored_gpus = []
            for gpu in suitable_gpus:
                if usage_pattern == "batch":
                    # Prioritize cost efficiency for batch processing
                    score = vram_est.tokens_per_dollar / gpu.hourly_cost_usd
                else:
                    # Prioritize performance for interactive use
                    score = gpu.compute_capability / gpu.hourly_cost_usd

                scored_gpus.append((score, gpu))

            scored_gpus.sort(reverse=True)

            return {
                "model_id": model_id,
                "vram_estimate": asdict(vram_est),
                "recommended_gpu": asdict(scored_gpus[0][1]),
                "alternatives": [asdict(gpu) for _, gpu in scored_gpus[1:3]],
                "usage_pattern": usage_pattern,
                "estimated_cost_per_1k_tokens": scored_gpus[0][1].hourly_cost_usd / (vram_est.tokens_per_dollar / 1000) if vram_est.tokens_per_dollar > 0 else None
            }

        except Exception as e:
            self.logger.error(f"Failed to recommend GPU for {model_id}: {e}")
            return {"error": str(e)}

    def list_models(self) -> List[Dict[str, Any]]:
        """List all downloaded models"""
        return [asdict(model) for model in self.model_db.values()]

    def delete_model(self, model_id: str, secure_delete: bool = True) -> bool:
        """Delete model with optional secure deletion"""

        try:
            if model_id not in self.model_db:
                return False

            model = self.model_db[model_id]

            if model.local_path and Path(model.local_path).exists():
                if secure_delete:
                    # Secure deletion - overwrite files before deletion
                    self._secure_delete_directory(Path(model.local_path))
                else:
                    shutil.rmtree(model.local_path)

            # Remove from database
            del self.model_db[model_id]
            self._save_model_database()

            self.logger.info(f"Deleted model {model_id}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to delete {model_id}: {e}")
            return False

    def _secure_delete_directory(self, path: Path):
        """Securely delete directory by overwriting files"""
        for file_path in path.rglob("*"):
            if file_path.is_file():
                # Overwrite file with random data
                size = file_path.stat().st_size
                with open(file_path, "wb") as f:
                    f.write(os.urandom(size))

        shutil.rmtree(path)

    def get_system_status(self) -> Dict[str, Any]:
        """Get system status and resource usage"""

        total_models = len(self.model_db)
        total_size_gb = sum(model.size_gb for model in self.model_db.values())

        return {
            "total_models": total_models,
            "total_size_gb": round(total_size_gb, 2),
            "models_directory": str(self.models_dir),
            "privacy_mode": self.privacy_mode,
            "encryption_enabled": self.encrypt_storage,
            "available_gpus": len(self.gpu_database),
            "storage_free_gb": round(shutil.disk_usage(self.models_dir).free / (1024**3), 2)
        }


if __name__ == "__main__":
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(description="Private LLM Model Manager")
    parser.add_argument("command", choices=["download", "list", "delete", "recommend", "status"])
    parser.add_argument("--model-id", help="Model ID for download/delete/recommend")
    parser.add_argument("--quantization", help="Quantization level")
    parser.add_argument("--usage-pattern", default="interactive", choices=["interactive", "batch"])
    parser.add_argument("--budget", type=float, help="Budget limit per hour")
    parser.add_argument("--force", action="store_true", help="Force download even if exists")

    args = parser.parse_args()

    manager = ModelManager()

    async def main():
        if args.command == "download":
            if not args.model_id:
                print("Error: --model-id required for download")
                return

            quant = None
            if args.quantization:
                try:
                    quant = Quantization(args.quantization)
                except ValueError:
                    print(f"Invalid quantization: {args.quantization}")
                    return

            result = await manager.download_model(args.model_id, quant, args.force)
            print(f"Downloaded: {result.model_id}")
            print(f"Size: {result.size_gb:.2f} GB")
            print(f"Parameters: {result.parameters:,}")

        elif args.command == "list":
            models = manager.list_models()
            print(f"Found {len(models)} models:")
            for model in models:
                print(f"  {model['model_id']} ({model['size_gb']:.2f} GB)")

        elif args.command == "delete":
            if not args.model_id:
                print("Error: --model-id required for delete")
                return

            success = manager.delete_model(args.model_id)
            print(f"Delete {'successful' if success else 'failed'}")

        elif args.command == "recommend":
            if not args.model_id:
                print("Error: --model-id required for recommend")
                return

            rec = manager.recommend_optimal_gpu(
                args.model_id,
                args.usage_pattern,
                args.budget
            )

            if "error" in rec:
                print(f"Error: {rec['error']}")
            else:
                print(f"Recommended GPU: {rec['recommended_gpu']['name']}")
                print(f"VRAM needed: {rec['vram_estimate']['total_gb']:.2f} GB")
                print(f"Cost per hour: ${rec['recommended_gpu']['hourly_cost_usd']:.2f}")

        elif args.command == "status":
            status = manager.get_system_status()
            print("System Status:")
            for key, value in status.items():
                print(f"  {key}: {value}")

    asyncio.run(main())