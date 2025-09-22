# Private LLM Cloud Inference

A production-ready system for running private LLM inference on cloud GPUs with maximum privacy and security.

## 🔒 Privacy-First Architecture

- **Complete Data Isolation**: No external data transmission after model download
- **Encrypted Storage**: All conversations and models stored with encryption
- **Zero Telemetry**: No logging, tracking, or data collection
- **Network Isolation**: Can run completely airgapped after setup
- **Secure APIs**: Custom authentication and encrypted endpoints

## 🚀 Features

- Support for any HuggingFace model (7B to 120B+)
- Automatic model downloading and format conversion
- GGUF, GPTQ, AWQ, safetensors support
- OpenAI-compatible API for iOS app integration
- Cost optimization through intelligent GPU selection
- Quick spin-up/spin-down capability

## 🏗️ Architecture

- **Primary Stack**: Ollama + Open WebUI (lightweight, fast)
- **Fallback Stack**: Text Generation WebUI (broader format support)
- **Container-based**: Docker/Docker Compose for portability
- **Cloud Platform**: RunPod with template automation
- **CI/CD**: GitHub Actions for automated building

## 📁 Project Structure

```
private-llm-cloud/
├── .github/workflows/     # CI/CD automation
├── docker/               # Container configurations
├── scripts/              # Setup and management scripts
├── configs/              # Service configurations
├── templates/            # Cloud provider templates
├── web/                  # Privacy-focused UI extensions
├── api/                  # Secure API layer
└── docs/                 # Documentation
```

## 🚀 Quick Start

1. **Clone and Setup**
   ```bash
   git clone <repo-url>
   cd private-llm-cloud
   cp .env.example .env
   # Edit .env with your settings
   ```

2. **Local Development**
   ```bash
   docker-compose up -d
   ```

3. **RunPod Deployment**
   ```bash
   ./scripts/deploy-runpod.sh
   ```

## 🛡️ Security Features

- Multi-stage Docker builds with minimal attack surface
- Non-root user execution
- Encrypted volume mounts
- Rate limiting and DDoS protection
- IP allowlisting
- Custom authentication
- Emergency data purge functionality

## 📊 Cost Optimization

- Automatic VRAM calculation and GPU sizing
- Cloud provider cost comparison
- Quantization recommendations
- Auto-shutdown features
- Usage monitoring and alerts

## 🔧 Configuration

See `docs/SETUP.md` for detailed configuration options.

## 📖 Documentation

- [Setup Guide](docs/SETUP.md) - Complete installation and configuration
- [Privacy Guide](docs/PRIVACY-GUIDE.md) - Privacy verification and best practices
- [GPU Sizing](docs/GPU-SIZING.md) - GPU selection and cost optimization

## 📄 License

MIT License - see LICENSE file for details.

---

**⚠️ Privacy Notice**: This system is designed for maximum privacy. Always verify your setup meets your security requirements before processing sensitive data.