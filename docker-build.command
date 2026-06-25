#!/bin/zsh
set -e
cd "$(dirname "$0")"
if [ ! -f .env ]; then
  cp .env.sample .env
  echo "已从 .env.sample 创建 .env，请按需填写邮箱授权码和 AI Key。"
fi
docker compose build
