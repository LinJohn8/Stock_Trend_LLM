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

IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "本机局域网 IP")
echo "局域网访问时，请使用启动输出里的 Dashboard 端口，例如：http://$IP:<端口>"

python -m tasks.start_app --lan
