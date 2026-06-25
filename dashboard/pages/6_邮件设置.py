from __future__ import annotations

import streamlit as st

from config.settings import get_settings
from database.db import init_db
from services.email_service import EmailService

st.set_page_config(page_title="邮件设置", layout="wide")
init_db()
settings = get_settings()

st.title("邮件设置")
st.caption("当前第一版从 .env 读取邮件配置；页面用于检查配置和发送测试邮件。")

cols = st.columns(2)
cols[0].text_input("SMTP 服务器", value=settings.email_host, disabled=True)
cols[1].text_input("SMTP 端口", value=str(settings.email_port), disabled=True)
cols[0].text_input("发送邮箱", value=settings.email_from, disabled=True)
cols[1].text_input("收件邮箱", value=settings.email_to, disabled=True)
cols[0].text_input("发送时间", value=", ".join(settings.email_send_time_list), disabled=True)
cols[1].text_input("时区", value=settings.email_timezone, disabled=True)

if st.button("发送测试邮件"):
    ok = EmailService().send_test_email()
    st.success("测试邮件已发送。") if ok else st.error("测试邮件未发送，请检查 .env 和 logs/email.log。")

if st.button("立即发送今日报告"):
    ok = EmailService().send_daily_report()
    st.success("日报已发送。") if ok else st.error("日报未发送，请检查邮件配置。")
