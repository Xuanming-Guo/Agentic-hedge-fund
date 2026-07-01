# Deploy On Alibaba Cloud ECS

```bash
cp .env.example .env
# Qwen Cloud for the final Alibaba demo:
# set DASHSCOPE_API_KEY in .env.
docker compose up --build -d
docker compose ps
curl http://localhost:8000/health
curl http://localhost:8000/api/proof/qwen
```

Keep the ECS security group restricted to the demo ports you intentionally expose.
