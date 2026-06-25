#!/bin/zsh
set -e
cd "$(dirname "$0")"
if [ ! -f .env ]; then
  cp .env.sample .env
  echo "已从 .env.sample 创建 .env，请按需填写邮箱授权码和 AI Key。"
fi
if ! docker image inspect stock-trend-llm:latest >/dev/null 2>&1; then
  echo "未找到本地镜像 stock-trend-llm:latest。"
  echo "首次使用或 Dockerfile/requirements.txt 变更后，请先运行：./docker-build.command"
  echo "如果 Docker Hub 网络超时，可先用：./start_local.command 本地启动。"
  exit 1
fi
docker compose up
