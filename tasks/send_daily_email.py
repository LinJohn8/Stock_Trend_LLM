from __future__ import annotations

from database.db import init_db
from services.email_service import EmailService


def main() -> None:
    init_db()
    ok = EmailService().send_daily_report()
    print("sent" if ok else "not sent")


if __name__ == "__main__":
    main()
