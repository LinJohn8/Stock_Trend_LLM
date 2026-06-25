#!/bin/zsh
set -e
cd "$(dirname "$0")"
if [ ! -f .env ]; then
  cp .env.sample .env
  echo "已从 .env.sample 创建 .env，请按需填写邮箱授权码和 AI Key。"
fi
if [ ! -d .venv ]; then
  python3 -m venv .venv
  . .venv/bin/activate
  pip install --upgrade pip
  pip install -r requirements.txt
else
  . .venv/bin/activate
fi
python -c "from database.db import init_db; init_db()"
uvicorn main:app --host 0.0.0.0 --port 8000 &
API_PID=$!
trap "kill $API_PID 2>/dev/null || true" EXIT
streamlit run dashboard/streamlit_app.py --server.address=0.0.0.0 --server.port=8501
