#!/bin/bash
set -euo pipefail

# Private LLM Cloud - RunPod Deployment Script
# Automates deployment to RunPod with optimal GPU selection

echo "🚀 Private LLM Cloud - RunPod Deployment"
echo "========================================"

# Configuration
RUNPOD_API_KEY="${RUNPOD_API_KEY:-}"
MODEL_ID="${MODEL_ID:-}"
QUANTIZATION="${QUANTIZATION:-Q4_K_M}"
BUDGET_LIMIT="${BUDGET_LIMIT:-5.00}"
PREFERRED_REGION="${PREFERRED_REGION:-US-CA}"
AUTO_SHUTDOWN_MINUTES="${AUTO_SHUTDOWN_MINUTES:-60}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check dependencies
check_dependencies() {
    log_info "Checking dependencies..."

    if ! command -v curl &> /dev/null; then
        log_error "curl is required but not installed"
        exit 1
    fi

    if ! command -v jq &> /dev/null; then
        log_error "jq is required but not installed"
        exit 1
    fi

    if ! command -v python3 &> /dev/null; then
        log_error "python3 is required but not installed"
        exit 1
    fi

    log_success "Dependencies check passed"
}

# Validate RunPod API key
validate_api_key() {
    log_info "Validating RunPod API key..."

    if [ -z "$RUNPOD_API_KEY" ]; then
        log_error "RUNPOD_API_KEY environment variable is required"
        echo "Get your API key from: https://www.runpod.io/console/user/settings"
        exit 1
    fi

    # Test API key
    local response=$(curl -s -H "Authorization: Bearer $RUNPOD_API_KEY" \
        "https://api.runpod.io/graphql" \
        -H "Content-Type: application/json" \
        -d '{"query": "query { myself { id } }"}')

    if echo "$response" | jq -e '.data.myself.id' > /dev/null; then
        log_success "API key validated"
    else
        log_error "Invalid API key"
        exit 1
    fi
}

# Calculate VRAM requirements for model
calculate_vram_requirements() {
    local model_id="$1"
    local quantization="$2"

    log_info "Calculating VRAM requirements for $model_id ($quantization)..."

    # Use our model manager to calculate requirements
    python3 /app/scripts/model-manager.py recommend \
        --model-id "$model_id" \
        --quantization "$quantization" \
        --budget "$BUDGET_LIMIT" > /tmp/vram_calc.json

    if [ $? -eq 0 ]; then
        log_success "VRAM calculation completed"
        cat /tmp/vram_calc.json
    else
        log_warning "VRAM calculation failed, using defaults"
        echo '{"vram_estimate": {"total_gb": 16}, "recommended_gpu": {"name": "RTX 4090", "vram_gb": 24}}'
    fi
}

# Get available GPU types from RunPod
get_available_gpus() {
    log_info "Fetching available GPU types..."

    local query='query {
        gpuTypes {
            id
            displayName
            memoryInGb
            communityPrice
            lowestPrice {
                minimumBidPrice
            }
        }
    }'

    curl -s -H "Authorization: Bearer $RUNPOD_API_KEY" \
        "https://api.runpod.io/graphql" \
        -H "Content-Type: application/json" \
        -d "{\"query\":\"$query\"}" | jq '.data.gpuTypes'
}

# Select optimal GPU based on requirements
select_optimal_gpu() {
    local required_vram="$1"
    local budget_limit="$2"

    log_info "Selecting optimal GPU (need ${required_vram}GB, budget \$${budget_limit}/hr)..."

    local gpus=$(get_available_gpus)

    # Filter GPUs by VRAM and budget
    local suitable_gpu=$(echo "$gpus" | jq -r --arg vram "$required_vram" --arg budget "$budget_limit" '
        map(select(.memoryInGb >= ($vram | tonumber) and .communityPrice <= ($budget | tonumber)))
        | sort_by(.communityPrice)
        | .[0]
        | .id'
    )

    if [ "$suitable_gpu" = "null" ] || [ -z "$suitable_gpu" ]; then
        log_warning "No suitable GPU found within budget, using RTX 4090"
        echo "NVIDIA GeForce RTX 4090"
    else
        local gpu_name=$(echo "$gpus" | jq -r --arg id "$suitable_gpu" '.[] | select(.id == $id) | .displayName')
        log_success "Selected GPU: $gpu_name"
        echo "$suitable_gpu"
    fi
}

# Create RunPod instance
create_runpod_instance() {
    local gpu_type_id="$1"
    local container_disk_gb="${2:-50}"
    local volume_gb="${3:-200}"

    log_info "Creating RunPod instance..."

    # Generate secure API key
    local api_key=$(openssl rand -base64 32)

    local mutation='mutation {
        podFindAndDeployOnDemand(
            input: {
                cloudType: ALL
                gpuCount: 1
                volumeInGb: '$volume_gb'
                containerDiskInGb: '$container_disk_gb'
                minVcpuCount: 4
                minMemoryInGb: 16
                gpuTypeId: "'$gpu_type_id'"
                name: "private-llm-'$(date +%s)'"
                imageName: "ghcr.io/private-llm-cloud/private-llm:latest"
                dockerArgs: ""
                ports: "3000:3000/http,11434:11434/http,8000:8000/http"
                volumeMountPath: "/app/models"
                env: [
                    {key: "PRIVACY_MODE", value: "maximum"}
                    {key: "DISABLE_TELEMETRY", value: "true"}
                    {key: "ENCRYPT_STORAGE", value: "true"}
                    {key: "API_KEY", value: "'$api_key'"}
                    {key: "HF_TOKEN", value: "'${HF_TOKEN:-}'"}
                    {key: "ALLOWED_IPS", value: "'${ALLOWED_IPS:-0.0.0.0/0}'"}
                    {key: "DEFAULT_QUANTIZATION", value: "'$QUANTIZATION'"}
                    {key: "AUTO_SHUTDOWN_IDLE_MINUTES", value: "'$AUTO_SHUTDOWN_MINUTES'"}
                    {key: "ENABLE_MONITORING", value: "true"}
                ]
            }
        ) {
            id
            desiredStatus
            imageName
            env
            machineId
            machine {
                podHostId
            }
        }
    }'

    local response=$(curl -s -H "Authorization: Bearer $RUNPOD_API_KEY" \
        "https://api.runpod.io/graphql" \
        -H "Content-Type: application/json" \
        -d "{\"query\":\"$(echo "$mutation" | tr '\n' ' ')\"}")

    local pod_id=$(echo "$response" | jq -r '.data.podFindAndDeployOnDemand.id')

    if [ "$pod_id" = "null" ] || [ -z "$pod_id" ]; then
        log_error "Failed to create instance"
        echo "$response" | jq '.errors'
        exit 1
    fi

    log_success "Instance created with ID: $pod_id"

    # Save deployment info
    cat > deployment-info.json << EOF
{
    "pod_id": "$pod_id",
    "api_key": "$api_key",
    "model_id": "$MODEL_ID",
    "quantization": "$QUANTIZATION",
    "gpu_type": "$gpu_type_id",
    "created_at": "$(date -Iseconds)",
    "budget_limit": "$BUDGET_LIMIT",
    "auto_shutdown_minutes": "$AUTO_SHUTDOWN_MINUTES"
}
EOF

    echo "$pod_id"
}

# Wait for instance to be ready
wait_for_instance() {
    local pod_id="$1"

    log_info "Waiting for instance to be ready..."

    local max_attempts=60
    local attempt=0

    while [ $attempt -lt $max_attempts ]; do
        local query='query {
            pod(input: {podId: "'$pod_id'"}) {
                id
                desiredStatus
                runtime {
                    uptimeInSeconds
                    ports {
                        ip
                        privatePort
                        publicPort
                        type
                    }
                }
            }
        }'

        local response=$(curl -s -H "Authorization: Bearer $RUNPOD_API_KEY" \
            "https://api.runpod.io/graphql" \
            -H "Content-Type: application/json" \
            -d "{\"query\":\"$query\"}")

        local status=$(echo "$response" | jq -r '.data.pod.desiredStatus')
        local uptime=$(echo "$response" | jq -r '.data.pod.runtime.uptimeInSeconds // 0')

        if [ "$status" = "RUNNING" ] && [ "$uptime" -gt 30 ]; then
            log_success "Instance is ready!"

            # Extract connection info
            local ip=$(echo "$response" | jq -r '.data.pod.runtime.ports[] | select(.privatePort == 3000) | .ip')
            local web_port=$(echo "$response" | jq -r '.data.pod.runtime.ports[] | select(.privatePort == 3000) | .publicPort')
            local api_port=$(echo "$response" | jq -r '.data.pod.runtime.ports[] | select(.privatePort == 11434) | .publicPort')

            echo ""
            echo "🎉 Deployment Complete!"
            echo "======================="
            echo "Pod ID: $pod_id"
            echo "Web UI: https://$ip:$web_port"
            echo "API: https://$ip:$api_port"
            echo "Privacy Dashboard: https://$ip:$web_port/privacy-dashboard.html"
            echo ""
            echo "API Key: $(cat deployment-info.json | jq -r '.api_key')"
            echo ""
            echo "📱 iOS App Configuration:"
            echo "  Endpoint: https://$ip:$api_port"
            echo "  API Key: [See above]"
            echo ""
            return 0
        fi

        echo -n "."
        sleep 10
        ((attempt++))
    done

    log_error "Instance failed to start within timeout"
    return 1
}

# Download model automatically
auto_download_model() {
    local pod_id="$1"
    local model_id="$2"

    if [ -z "$model_id" ]; then
        log_info "No model specified for auto-download"
        return 0
    fi

    log_info "Triggering automatic model download: $model_id"

    # Get instance connection info
    local query='query {
        pod(input: {podId: "'$pod_id'"}) {
            runtime {
                ports {
                    ip
                    privatePort
                    publicPort
                }
            }
        }
    }'

    local response=$(curl -s -H "Authorization: Bearer $RUNPOD_API_KEY" \
        "https://api.runpod.io/graphql" \
        -H "Content-Type: application/json" \
        -d "{\"query\":\"$query\"}")

    local ip=$(echo "$response" | jq -r '.data.pod.runtime.ports[] | select(.privatePort == 8000) | .ip')
    local port=$(echo "$response" | jq -r '.data.pod.runtime.ports[] | select(.privatePort == 8000) | .publicPort')
    local api_key=$(cat deployment-info.json | jq -r '.api_key')

    if [ "$ip" != "null" ] && [ "$port" != "null" ]; then
        log_info "Triggering model download via API..."

        curl -s -X POST "https://$ip:$port/api/models/download" \
            -H "Authorization: Bearer $api_key" \
            -H "Content-Type: application/json" \
            -d "{\"model_id\":\"$model_id\",\"quantization\":\"$QUANTIZATION\"}" \
            > /dev/null

        log_success "Model download initiated"
    else
        log_warning "Could not trigger automatic download - configure manually via Web UI"
    fi
}

# Cleanup on failure
cleanup_on_failure() {
    local pod_id="$1"

    log_warning "Cleaning up failed deployment..."

    if [ -n "$pod_id" ] && [ "$pod_id" != "null" ]; then
        local mutation='mutation {
            podTerminate(input: {podId: "'$pod_id'"}) {
                id
            }
        }'

        curl -s -H "Authorization: Bearer $RUNPOD_API_KEY" \
            "https://api.runpod.io/graphql" \
            -H "Content-Type: application/json" \
            -d "{\"query\":\"$mutation\"}" > /dev/null

        log_info "Terminated pod $pod_id"
    fi
}

# Show usage information
show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Deploy Private LLM Cloud to RunPod with optimal GPU selection"
    echo ""
    echo "Environment Variables:"
    echo "  RUNPOD_API_KEY               RunPod API key (required)"
    echo "  MODEL_ID                     HuggingFace model to download (optional)"
    echo "  QUANTIZATION                 Model quantization (default: Q4_K_M)"
    echo "  BUDGET_LIMIT                 Max hourly cost in USD (default: 5.00)"
    echo "  PREFERRED_REGION             Preferred region (default: US-CA)"
    echo "  AUTO_SHUTDOWN_MINUTES        Auto-shutdown timer (default: 60)"
    echo "  HF_TOKEN                     HuggingFace token (optional)"
    echo "  ALLOWED_IPS                  IP allowlist (default: 0.0.0.0/0)"
    echo ""
    echo "Options:"
    echo "  -h, --help                   Show this help message"
    echo "  -m, --model MODEL_ID         Model to download"
    echo "  -q, --quantization QUANT     Quantization level"
    echo "  -b, --budget AMOUNT          Budget limit per hour"
    echo "  --no-auto-download           Skip automatic model download"
    echo ""
    echo "Examples:"
    echo "  $0 -m microsoft/DialoGPT-medium -q Q4_K_M -b 3.00"
    echo "  RUNPOD_API_KEY=xxx $0 --model meta-llama/Llama-2-7b-chat-hf"
}

# Parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_usage
                exit 0
                ;;
            -m|--model)
                MODEL_ID="$2"
                shift 2
                ;;
            -q|--quantization)
                QUANTIZATION="$2"
                shift 2
                ;;
            -b|--budget)
                BUDGET_LIMIT="$2"
                shift 2
                ;;
            --no-auto-download)
                AUTO_DOWNLOAD=false
                shift
                ;;
            *)
                log_error "Unknown option: $1"
                show_usage
                exit 1
                ;;
        esac
    done
}

# Main deployment function
main() {
    log_info "Starting deployment process..."

    # Parse arguments
    parse_args "$@"

    # Check dependencies and validate setup
    check_dependencies
    validate_api_key

    # Calculate requirements if model specified
    local required_vram=16
    if [ -n "$MODEL_ID" ]; then
        local vram_calc=$(calculate_vram_requirements "$MODEL_ID" "$QUANTIZATION")
        required_vram=$(echo "$vram_calc" | jq -r '.vram_estimate.total_gb // 16')
    fi

    # Select optimal GPU
    local gpu_type_id=$(select_optimal_gpu "$required_vram" "$BUDGET_LIMIT")

    # Create instance
    local pod_id=$(create_runpod_instance "$gpu_type_id")

    # Set up cleanup on failure
    trap "cleanup_on_failure $pod_id" ERR

    # Wait for instance to be ready
    if wait_for_instance "$pod_id"; then
        # Auto-download model if specified
        if [ -n "$MODEL_ID" ] && [ "${AUTO_DOWNLOAD:-true}" = "true" ]; then
            auto_download_model "$pod_id" "$MODEL_ID"
        fi

        log_success "Deployment completed successfully!"
        log_info "Deployment info saved to: deployment-info.json"

        # Show next steps
        echo ""
        echo "🚀 Next Steps:"
        echo "1. Visit the Web UI to download and manage models"
        echo "2. Check the Privacy Dashboard for security status"
        echo "3. Configure your iOS app with the API endpoint"
        echo "4. Start chatting with maximum privacy!"
        echo ""
        echo "📖 For help: https://github.com/private-llm-cloud/docs"
    else
        cleanup_on_failure "$pod_id"
        exit 1
    fi
}

# Run main function with all arguments
main "$@"