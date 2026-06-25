from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from config.settings import get_settings
from database.db import session_scope
from database.models import EmailLog
from services.report_service import ReportService
from utils.email_utils import validate_email
from utils.logger import get_logger
from utils.time_utils import now_tz

logger = get_logger("email", "email.log")


class EmailService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def send_test_email(self) -> bool:
        subject = f"【股票AI日报】测试邮件 {now_tz().date().isoformat()}"
        html = "<p>这是一封测试邮件。系统仅用于个人研究和辅助决策，不构成投资建议。</p>"
        return self.send_email(subject, html, "测试邮件")

    def send_daily_report(self) -> bool:
        html, path = ReportService().render_daily_html()
        subject = f"【股票AI日报】{now_tz().date().isoformat()} 持仓/自选股分析报告"
        return self.send_email(subject, html, "请查看 HTML 邮件正文。", html_path=path)

    def send_email(self, subject: str, html: str, plain: str = "", html_path: Path | None = None) -> bool:
        s = self.settings
        recipient = s.email_to
        if not s.email_enabled:
            self._log(recipient, subject, "skipped", "EMAIL_ENABLED=false", html_path)
            return False
        if not all([s.email_host, s.email_username, s.email_password, s.email_from, recipient]) or not validate_email(recipient):
            self._log(recipient, subject, "failed", "邮箱配置不完整或收件地址无效", html_path)
            return False
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = s.email_from
            msg["To"] = recipient
            msg.attach(MIMEText(plain or subject, "plain", "utf-8"))
            msg.attach(MIMEText(html, "html", "utf-8"))
            if s.email_use_ssl:
                with smtplib.SMTP_SSL(s.email_host, s.email_port, timeout=30) as smtp:
                    smtp.login(s.email_username, s.email_password)
                    smtp.sendmail(s.email_from, [recipient], msg.as_string())
            else:
                with smtplib.SMTP(s.email_host, s.email_port, timeout=30) as smtp:
                    smtp.starttls()
                    smtp.login(s.email_username, s.email_password)
                    smtp.sendmail(s.email_from, [recipient], msg.as_string())
            self._log(recipient, subject, "success", "", html_path)
            logger.info("email sent: %s", subject)
            return True
        except Exception as exc:
            logger.exception("email failed: %s", exc)
            self._log(recipient, subject, "failed", str(exc), html_path)
            return False

    def _log(self, recipient: str, subject: str, status: str, error: str, html_path: Path | None) -> None:
        with session_scope() as session:
            session.add(
                EmailLog(
                    send_time=now_tz().replace(tzinfo=None),
                    recipient=recipient or "",
                    subject=subject,
                    status=status,
                    error_message=error,
                    html_path=str(html_path or ""),
                )
            )
