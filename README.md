```bash
docker run --rm \
  --runtime nvidia \
  --name "Ministral-3-3B-Instruct-2512" \
  --gpus all \
  --ipc=host \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  -p 8000:8000 \
  vllm/vllm-openai:v0.15.1 \
  --model "mistralai/Ministral-3-3B-Instruct-2512" \
  --dtype bfloat16 \
  --tensor-parallel-size 1 \
  --max-model-len 5000 \
  --gpu-memory-utilization 0.9
```