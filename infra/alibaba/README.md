# Alibaba Cloud Deployment Notes

Use a small Alibaba Cloud ECS instance with Docker and Docker Compose installed.

1. Copy the repository to ECS.
2. Create `.env` from `.env.example`.
3. Set `DASHSCOPE_API_KEY` for Qwen Cloud. Without it, the backend uses deterministic mock agents for local/offline checks.
4. Run `docker compose up --build -d`.
5. Show `/health`, `/api/proof/qwen`, and the dashboard in the proof video.

This deployment keeps Postgres local to the Compose stack for hackathon reproducibility.
