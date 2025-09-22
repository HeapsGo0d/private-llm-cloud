# GPU Sizing and Cost Optimization Guide

Comprehensive guide to selecting optimal GPUs and managing costs for Private LLM Cloud deployments.

## 🎯 Quick GPU Recommendations

### Budget-Conscious (< $1/hour)
| Model Size | Quantization | GPU | VRAM | Cost/Hour | Provider |
|------------|-------------|-----|------|-----------|----------|
| 7B | Q4_K_M | RTX 3090 | 24GB | $0.20-0.35 | Vast.ai |
| 7B | Q4_K_M | RTX 4090 | 24GB | $0.25-0.40 | Vast.ai |
| 13B | Q3_K_M | RTX 4090 | 24GB | $0.25-0.40 | Vast.ai |

### Performance-Focused (< $3/hour)
| Model Size | Quantization | GPU | VRAM | Cost/Hour | Provider |
|------------|-------------|-----|------|-----------|----------|
| 13B | Q4_K_M | RTX 4090 | 24GB | $0.40-0.60 | RunPod |
| 30B | Q4_K_M | A100-40GB | 40GB | $1.50-2.00 | RunPod |
| 70B | Q3_K_M | A100-40GB | 40GB | $1.50-2.00 | RunPod |

### Maximum Quality (< $5/hour)
| Model Size | Quantization | GPU | VRAM | Cost/Hour | Provider |
|------------|-------------|-----|------|-----------|----------|
| 30B | Q5_K_M | A100-80GB | 80GB | $2.50-3.50 | RunPod |
| 70B | Q4_K_M | A100-80GB | 80GB | $2.50-3.50 | RunPod |
| 70B | Q5_K_M | H100 | 80GB | $4.00-5.00 | RunPod |

## 🧮 VRAM Calculation Method

### Formula Components

The VRAM calculator uses this formula:
```
Total VRAM = Model Size + Context Memory + Overhead + Safety Margin
```

#### 1. Model Size Calculation
```python
def calculate_model_size(parameters, quantization):
    bytes_per_param = {
        'FP32': 4.0,
        'FP16': 2.0,
        'Q8_0': 1.0,
        'Q6_K': 0.75,
        'Q5_K_M': 0.625,
        'Q4_K_M': 0.5,
        'Q3_K_M': 0.375,
        'Q2_K': 0.25
    }
    return (parameters * bytes_per_param[quantization]) / (1024**3)  # GB
```

#### 2. Context Memory
```python
def calculate_context_memory(context_length, hidden_size, batch_size=1):
    # KV cache memory for transformers
    return (context_length * hidden_size * 2 * batch_size * 2) / (1024**3)  # GB
```

#### 3. Overhead Estimation
```python
def calculate_overhead(model_size_gb):
    # CUDA kernels, temporary tensors, etc.
    base_overhead = 2.0  # GB
    proportional_overhead = model_size_gb * 0.15  # 15% of model size
    return max(base_overhead, proportional_overhead)
```

#### 4. Safety Margin
```python
def calculate_safety_margin(total_base_memory):
    return total_base_memory * 0.2  # 20% safety margin
```

### Example Calculations

#### Llama-2-7B with Q4_K_M
```
Parameters: 7,000,000,000
Quantization: Q4_K_M (0.5 bytes/param)
Context: 4096 tokens
Hidden size: 4096

Model size: 7B × 0.5 bytes = 3.5 GB
Context memory: 4096 × 4096 × 2 × 2 / (1024³) = 0.125 GB
Overhead: max(2.0, 3.5 × 0.15) = 2.0 GB
Base total: 3.5 + 0.125 + 2.0 = 5.625 GB
Safety margin: 5.625 × 0.2 = 1.125 GB
Total VRAM needed: 6.75 GB
Recommended GPU: 12GB+ (RTX 3060, RTX 4070, etc.)
```

#### Llama-2-70B with Q4_K_M
```
Parameters: 70,000,000,000
Quantization: Q4_K_M (0.5 bytes/param)
Context: 4096 tokens
Hidden size: 8192

Model size: 70B × 0.5 bytes = 35 GB
Context memory: 4096 × 8192 × 2 × 2 / (1024³) = 0.5 GB
Overhead: max(2.0, 35 × 0.15) = 5.25 GB
Base total: 35 + 0.5 + 5.25 = 40.75 GB
Safety margin: 40.75 × 0.2 = 8.15 GB
Total VRAM needed: 48.9 GB
Recommended GPU: 80GB (A100-80GB, H100)
```

## 💰 Cost Optimization Strategies

### 1. Quantization Optimization

#### Quality vs. Cost Trade-offs
| Quantization | Quality Loss | VRAM Savings | Speed Gain | Recommended For |
|-------------|-------------|--------------|------------|-----------------|
| FP16 | 0% (baseline) | 0% | 1x | Maximum quality needed |
| Q8_0 | <1% | 50% | 1.2x | High quality, some savings |
| Q6_K | 1-2% | 62.5% | 1.4x | Good balance |
| Q5_K_M | 2-3% | 68.75% | 1.6x | Recommended balance |
| Q4_K_M | 3-5% | 75% | 1.8x | **Best overall choice** |
| Q3_K_M | 5-8% | 81.25% | 2.0x | Budget-focused |
| Q2_K | 8-15% | 87.5% | 2.2x | Extreme budget |

#### Smart Quantization Selection
```python
def recommend_quantization(model_size_params, budget_per_hour):
    if budget_per_hour > 3.0:
        return "Q5_K_M"  # High quality
    elif budget_per_hour > 1.5:
        return "Q4_K_M"  # Balanced
    elif model_size_params > 30e9:
        return "Q3_K_M"  # Large model, aggressive quantization
    else:
        return "Q4_K_M"  # Default recommendation
```

### 2. Cloud Provider Comparison

#### RunPod (Generally higher reliability)
```
RTX 4090:     $0.40-0.60/hour
A100-40GB:    $1.50-2.00/hour
A100-80GB:    $2.50-3.50/hour
H100:         $4.00-5.00/hour

Pros: Reliable, good support, template marketplace
Cons: Higher cost, limited availability
```

#### Vast.ai (Generally lower cost)
```
RTX 4090:     $0.20-0.40/hour
A100-40GB:    $0.80-1.50/hour
A100-80GB:    $1.20-2.50/hour

Pros: Lower cost, more GPU options
Cons: Variable reliability, requires more setup
```

### 3. Auto-Shutdown Configuration

#### Smart Shutdown Rules
```bash
# Conservative (30 min idle)
AUTO_SHUTDOWN_IDLE_MINUTES=30

# Aggressive (10 min idle)
AUTO_SHUTDOWN_IDLE_MINUTES=10

# Development (disabled)
AUTO_SHUTDOWN_IDLE_MINUTES=0
```

#### Cost Monitoring
```python
# Built-in cost tracking
ENABLE_MONITORING=true
COST_ALERT_THRESHOLD=5.00  # Alert at $5/hour
DAILY_BUDGET_LIMIT=50.00   # Stop at $50/day
```

## 🎮 GPU Performance Comparison

### Gaming GPUs (Budget-Friendly)

#### RTX 4090 (24GB VRAM)
```
Price: $0.25-0.60/hour
Sweet spot: 7B-13B models with Q4_K_M
Max model: 30B with Q3_K_M
Pros: Excellent price/performance, widely available
Cons: Limited VRAM for largest models
Best for: Most users, development, testing
```

#### RTX 3090 (24GB VRAM)
```
Price: $0.20-0.50/hour
Sweet spot: 7B models with Q4_K_M/Q5_K_M
Max model: 13B with Q4_K_M
Pros: Lower cost than 4090
Cons: Slower inference than 4090
Best for: Budget-conscious users
```

#### RTX 4080 (16GB VRAM)
```
Price: $0.15-0.40/hour
Sweet spot: 7B models with Q4_K_M
Max model: 7B with Q5_K_M
Pros: Good for smaller models
Cons: Limited VRAM for larger models
Best for: 7B model deployments only
```

### Professional GPUs (High Performance)

#### A100-40GB
```
Price: $0.80-2.00/hour
Sweet spot: 13B-30B models with Q4_K_M/Q5_K_M
Max model: 70B with Q3_K_M
Pros: High memory bandwidth, excellent for inference
Cons: Higher cost than gaming GPUs
Best for: Production deployments, larger models
```

#### A100-80GB
```
Price: $1.20-3.50/hour
Sweet spot: 30B-70B models with Q4_K_M/Q5_K_M
Max model: 70B with Q6_K
Pros: Largest practical VRAM, handles any model
Cons: Most expensive option
Best for: Largest models, maximum quality
```

#### H100 (80GB VRAM)
```
Price: $3.00-5.00/hour
Sweet spot: 70B+ models with highest quality
Max model: 120B+ with appropriate quantization
Pros: Fastest inference, latest architecture
Cons: Very expensive, limited availability
Best for: Maximum performance requirements
```

## 📊 Performance Benchmarks

### Tokens per Second by GPU and Model Size

#### 7B Models (Q4_K_M)
```
RTX 3090:  ~50-60 tokens/sec
RTX 4090:  ~80-100 tokens/sec
A100-40GB: ~120-150 tokens/sec
H100:      ~200-250 tokens/sec
```

#### 13B Models (Q4_K_M)
```
RTX 4090:  ~40-50 tokens/sec
A100-40GB: ~80-100 tokens/sec
A100-80GB: ~100-120 tokens/sec
H100:      ~150-180 tokens/sec
```

#### 30B Models (Q4_K_M)
```
A100-40GB: ~30-40 tokens/sec
A100-80GB: ~50-60 tokens/sec
H100:      ~80-100 tokens/sec
```

#### 70B Models (Q4_K_M)
```
A100-80GB: ~15-25 tokens/sec
H100:      ~40-60 tokens/sec
```

### Cost per 1K Tokens

#### Budget Tier
```
RTX 3090 + 7B Q4_K_M:  ~$0.001-0.002 per 1K tokens
RTX 4090 + 7B Q4_K_M:  ~$0.001-0.003 per 1K tokens
```

#### Performance Tier
```
A100-40GB + 13B Q4_K_M: ~$0.003-0.005 per 1K tokens
A100-40GB + 30B Q4_K_M: ~$0.005-0.008 per 1K tokens
```

#### Premium Tier
```
A100-80GB + 70B Q4_K_M: ~$0.010-0.015 per 1K tokens
H100 + 70B Q5_K_M:      ~$0.008-0.012 per 1K tokens
```

## 🛠️ Using the Built-in Calculator

### Web Interface
Visit `http://your-instance:3000/model-loader.html` and use the VRAM calculator:

1. Enter model ID (e.g., `meta-llama/Llama-2-7b-chat-hf`)
2. Select quantization level
3. View GPU recommendations and cost estimates

### Command Line
```bash
# Calculate VRAM for specific model
python3 scripts/model-manager.py recommend \
  --model-id meta-llama/Llama-2-7b-chat-hf \
  --quantization Q4_K_M \
  --budget 2.00

# Get detailed breakdown
python3 scripts/model-manager.py calculate-vram \
  --model-id microsoft/DialoGPT-medium \
  --quantization Q4_K_M \
  --context-length 4096
```

### API Endpoint
```bash
curl -X POST "http://your-instance:8000/api/models/calculate-vram" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model_id": "meta-llama/Llama-2-7b-chat-hf",
    "quantization": "Q4_K_M",
    "context_length": 4096
  }'
```

## 🎯 Optimization Workflows

### New Deployment Workflow
1. **Identify Model**: Choose target model size and quality
2. **Calculate VRAM**: Use built-in calculator
3. **Set Budget**: Determine acceptable cost per hour
4. **Select GPU**: Filter options by VRAM and budget
5. **Choose Quantization**: Balance quality vs. cost
6. **Deploy & Test**: Start with conservative settings
7. **Optimize**: Adjust based on actual performance

### Cost Optimization Workflow
1. **Monitor Usage**: Track actual token consumption
2. **Analyze Patterns**: Identify peak vs. idle times
3. **Adjust Auto-shutdown**: Reduce idle time costs
4. **Test Quantization**: Try more aggressive quantization
5. **Consider Spot Instances**: Use preemptible instances when available
6. **Schedule Deployments**: Use cheaper off-peak hours

### Performance Optimization Workflow
1. **Baseline Performance**: Measure current tokens/sec
2. **GPU Utilization**: Check if GPU is fully utilized
3. **Memory Usage**: Verify VRAM isn't limiting factor
4. **Context Length**: Reduce if not needed
5. **Batch Size**: Increase for throughput workloads
6. **Model Format**: Try different quantization methods

## 📈 Future-Proofing Considerations

### Model Size Trends
- **Current Sweet Spot**: 7B-13B models for most use cases
- **Trending Up**: 30B-70B models becoming more common
- **Future**: 100B+ models will require multi-GPU setups

### GPU Evolution
- **Current**: RTX 4090 best price/performance
- **Near Future**: RTX 5000 series expected in 2024
- **Long Term**: More specialized AI chips entering market

### Cost Trends
- **Gaming GPUs**: Becoming more available and affordable
- **Professional GPUs**: Costs decreasing as supply increases
- **Cloud Competition**: More providers entering market

## 💡 Expert Tips

### Choosing the Right GPU
1. **Start Small**: Begin with 7B models to learn the system
2. **Quality Matters**: Q4_K_M is the sweet spot for most users
3. **Budget 20% Extra**: Always have VRAM headroom
4. **Monitor Utilization**: Ensure you're using full GPU capacity
5. **Consider Alternatives**: Vast.ai often has better prices

### Cost Management
1. **Set Alerts**: Configure budget alerts and auto-shutdown
2. **Use Spot Instances**: When available for batch processing
3. **Schedule Wisely**: Deploy during off-peak hours when possible
4. **Monitor Continuously**: Check costs daily, especially when starting
5. **Optimize Gradually**: Don't over-optimize too early

### Performance Tuning
1. **Start Conservative**: Use recommended settings first
2. **One Change at a Time**: Isolate performance impacts
3. **Measure Everything**: Use built-in monitoring tools
4. **Document Changes**: Keep track of what works
5. **Community Feedback**: Share findings with other users

---

**Remember**: The best GPU setup balances your quality requirements, performance needs, and budget constraints. Start with our recommendations and optimize based on your actual usage patterns.