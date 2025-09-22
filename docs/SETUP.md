# Private LLM Cloud - Setup Guide

Complete setup guide for deploying your maximum privacy LLM inference system.

## 🚀 Quick Start Options

### Option 1: RunPod Deployment (Recommended)
```bash
# Clone the repository
git clone https://github.com/HeapsGo0d/private-llm-cloud.git
cd private-llm-cloud

# Set your RunPod API key
export RUNPOD_API_KEY="your_runpod_api_key"

# Deploy with automatic GPU selection
./scripts/deploy-runpod.sh --model meta-llama/Llama-2-7b-chat-hf --budget 3.00
```

### Option 2: Vast.ai Deployment
```bash
# Use the Vast.ai template from templates/vast-ai-template.json
# Or deploy manually with their interface
```

### Option 3: Local Development
```bash
git clone https://github.com/HeapsGo0d/private-llm-cloud.git
cd private-llm-cloud
cp .env.example .env
# Edit .env with your settings
docker-compose up -d
```

## 📋 Prerequisites

### Required
- Docker and Docker Compose
- 16GB+ RAM (32GB recommended)
- 50GB+ free disk space
- NVIDIA GPU (for optimal performance)

### Optional
- RunPod or Vast.ai account
- HuggingFace account (for model downloads)

## 🔧 Detailed Setup

### 1. Environment Configuration

Copy and customize the environment file:
```bash
cp .env.example .env
```

Key settings to configure:
```bash
# Privacy Settings (recommended defaults)
PRIVACY_MODE=maximum
DISABLE_TELEMETRY=true
ENCRYPT_STORAGE=true

# Security (IMPORTANT: Change these!)
API_KEY=your_secure_api_key_here
ALLOWED_IPS=your.ip.address.here

# HuggingFace (optional but recommended)
HF_TOKEN=your_huggingface_token

# Performance
GPU_MEMORY_FRACTION=0.9
MAX_CONCURRENT_REQUESTS=10
```

### 2. GPU Configuration

#### For NVIDIA GPUs (Local):
```bash
# Install NVIDIA Container Toolkit
distribution=$(. /etc/os-release;echo $ID$VERSION_ID) \
   && curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg \
   && curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
        sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
        sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker

# Verify GPU access
docker run --rm --gpus all nvidia/cuda:11.8-base-ubuntu20.04 nvidia-smi
```

#### For Cloud GPUs:
GPUs are automatically configured in cloud deployments.

### 3. Model Selection Guide

#### Model Size Recommendations:
| Model Size | VRAM Needed | Recommended GPU | Use Case |
|------------|-------------|-----------------|----------|
| 7B (Q4_K_M) | 4-6GB | RTX 3090, RTX 4090 | General chat, fast responses |
| 13B (Q4_K_M) | 8-12GB | RTX 4090, A100-40GB | Better quality, moderate speed |
| 30B (Q4_K_M) | 18-24GB | A100-40GB, H100 | High quality, slower |
| 70B (Q4_K_M) | 40-48GB | A100-80GB, H100 | Maximum quality |

#### Quantization Options:
- **Q4_K_M**: Best balance (recommended)
- **Q5_K_M**: Higher quality, more VRAM
- **Q3_K_M**: Smaller size, lower quality
- **FP16**: Maximum quality, most VRAM

### 4. Security Configuration

#### IP Allowlisting (Highly Recommended):
```bash
# Set to your specific IP for maximum security
ALLOWED_IPS=your.specific.ip.address

# Or for local development only
ALLOWED_IPS=127.0.0.1,192.168.1.0/24
```

#### API Key Generation:
```bash
# Generate a secure API key
openssl rand -base64 32
```

#### Firewall Setup (Production):
```bash
# Allow only necessary ports
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 3000/tcp  # Web UI
sudo ufw allow 11434/tcp # API
sudo ufw enable
```

## 🌐 Deployment Options

### RunPod Deployment

1. **Get API Key**:
   - Go to RunPod Console → User Settings → API Keys
   - Generate new API key

2. **Deploy with Script**:
   ```bash
   export RUNPOD_API_KEY="your_key"
   ./scripts/deploy-runpod.sh \
     --model microsoft/DialoGPT-medium \
     --quantization Q4_K_M \
     --budget 2.50
   ```

3. **Manual Template**:
   - Use `templates/runpod-template.json`
   - Import in RunPod Console

### Vast.ai Deployment

1. **Create Account** at [vast.ai](https://vast.ai)

2. **Search Instances**:
   - Filter by GPU (RTX 4090 recommended)
   - 16GB+ VRAM
   - Good connectivity scores

3. **Deploy Template**:
   - Use `templates/vast-ai-template.json`
   - Or use Docker image: `ghcr.io/heapsgo0d/private-llm-cloud:latest`

### Local Deployment

```bash
# Standard deployment
docker-compose up -d

# With GPU support
docker-compose -f docker-compose.yml -f docker-compose.gpu.yml up -d

# Production mode
docker-compose -f docker-compose.production.yml up -d
```

## 🔗 Accessing Your System

### Web Interfaces
- **Main Web UI**: `http://your-ip:3000`
- **Model Manager**: `http://your-ip:3000/model-loader.html`
- **Privacy Dashboard**: `http://your-ip:3000/privacy-dashboard.html`

### API Endpoints
- **OpenAI Compatible**: `http://your-ip:11434/v1/chat/completions`
- **Ollama Native**: `http://your-ip:11434/api/chat`
- **Health Check**: `http://your-ip:11434/health`

### Authentication
All endpoints require API key authentication:
```bash
curl -H "Authorization: Bearer YOUR_API_KEY" \
     http://your-ip:11434/v1/models
```

## 📱 iOS App Integration

### Supported Apps
- **Pal Chat**: Full OpenAI compatibility
- **ChatBot**: Works with custom endpoints
- **OpenCat**: Supports custom APIs

### Configuration
1. **API Endpoint**: `https://your-instance:11434`
2. **API Key**: Your configured API_KEY
3. **Model**: Download model first via Web UI

### Example (Pal Chat):
1. Open Pal Chat settings
2. Add new API provider
3. Enter your endpoint and API key
4. Select model from dropdown

## 🛠️ Management Tasks

### Download Models
```bash
# Via Web UI (recommended)
# Visit http://your-ip:3000/model-loader.html

# Via API
curl -X POST "http://your-ip:8000/api/models/download" \
     -H "Authorization: Bearer YOUR_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"model_id": "microsoft/DialoGPT-medium", "quantization": "Q4_K_M"}'

# Via CLI
python3 scripts/model-manager.py download --model-id microsoft/DialoGPT-medium
```

### Monitor System
```bash
# Check status
curl http://your-ip:11434/health

# View logs
docker-compose logs -f ollama

# Privacy check
python3 scripts/privacy-check.py
```

### Update System
```bash
# Pull latest images
docker-compose pull

# Restart services
docker-compose down && docker-compose up -d
```

## ⚠️ Troubleshooting

### Common Issues

#### 1. Container Won't Start
```bash
# Check logs
docker-compose logs ollama

# Common causes:
# - Insufficient GPU memory
# - Missing NVIDIA drivers
# - Port conflicts
```

#### 2. Model Download Fails
```bash
# Check HuggingFace token
echo $HF_TOKEN

# Check disk space
df -h

# Check network connectivity
curl -I https://huggingface.co
```

#### 3. API Authentication Errors
```bash
# Verify API key format
echo $API_KEY | wc -c  # Should be 32+ characters

# Check IP allowlist
grep ALLOWED_IPS .env
```

#### 4. Performance Issues
```bash
# Check GPU utilization
nvidia-smi

# Check memory usage
docker stats

# Optimize quantization
# Try Q3_K_M for less VRAM usage
```

### Getting Help

1. **Check Logs**: Always start with container logs
2. **Privacy Dashboard**: Monitor system status
3. **GitHub Issues**: Report bugs or ask questions
4. **Community**: Join discussions in GitHub

## 🔒 Security Best Practices

### Production Deployment
1. **Use specific IP allowlists**
2. **Enable SSL/TLS certificates**
3. **Regular security updates**
4. **Monitor privacy dashboard**
5. **Regular data purges**

### Privacy Verification
```bash
# Generate privacy report
python3 scripts/privacy-check.py

# Check network connections
netstat -tuln | grep :11434

# Verify encryption
ls -la /app/data/.encryption_key
```

## 📈 Performance Optimization

### GPU Memory Optimization
```bash
# Adjust GPU memory fraction
GPU_MEMORY_FRACTION=0.8  # Use 80% of GPU memory

# Enable memory growth
CUDA_MEMORY_GROWTH=true
```

### Model Optimization
```bash
# Use appropriate quantization
Q4_K_M   # Best balance
Q3_K_M   # Smaller, faster
Q5_K_M   # Higher quality
```

### Cost Optimization
```bash
# Enable auto-shutdown
AUTO_SHUTDOWN_IDLE_MINUTES=30

# Monitor usage
ENABLE_MONITORING=true
COST_ALERT_THRESHOLD=5.00
```

---

**Next Steps**: Once deployed, visit the Privacy Dashboard to verify your system's security status and start downloading models!