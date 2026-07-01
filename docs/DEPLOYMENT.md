# Deployment

## Local Docker

```bash
cp .env.example .env
docker compose up --build
```

Services:

- Postgres on port 5432.
- FastAPI on port 8000.
- React/Vite dashboard on port 5173.

## Qwen Cloud

Set `DASHSCOPE_API_KEY` in `.env` to use Qwen Cloud. With no Qwen key, the backend uses deterministic mock agents for local/offline tests.

API keys are used only by the backend. The frontend receives proof metadata, not secrets.

## Troubleshooting

- Use `/health` for API status.
- Use `/api/proof/qwen` for Qwen proof.
- Use `/api/mcp/status` for local MCP smoke status.
- Use `/metrics` for local Prometheus metrics.
- If a Docker build fails at `COPY . .`, confirm each service build context has its own `.dockerignore`.
