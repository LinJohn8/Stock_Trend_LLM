#!/bin/zsh
set -e
cd "$(dirname "$0")"
if [ ! -f .env ]; then
  cp .env.sample .env
fi
if ! docker image inspect stock-trend-llm:latest >/dev/null 2>&1; then
  echo "未找到本地镜像 stock-trend-llm:latest，请先运行：./docker-build.command"
  exit 1
fi
docker compose up stock-ai-api
