FROM node:20-slim

WORKDIR /app

RUN corepack enable && corepack prepare pnpm@9.12.3 --activate
COPY package.json ./
RUN pnpm install
COPY . .

EXPOSE 5173
CMD ["pnpm", "dev", "--host", "0.0.0.0"]
