#!/bin/zsh
set -e
cd "$(dirname "$0")"
if [ ! -f .env ]; then
  cp .env.sample .env
fi
docker compose up --build stock-ai-api
