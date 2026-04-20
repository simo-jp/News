"""
メール送信スクリプト（任意）
環境変数 EMAIL_FROM, EMAIL_TO, EMAIL_APP_PASSWORD が設定されている場合のみ動作する。
GitHub ActionsのSecretsに登録して利用する想定。
"""

import os
import sys
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


def send_email():
    email_from = os.getenv("EMAIL_FROM")
    email_to = os.getenv("EMAIL_TO")
    app_password = os.getenv("EMAIL_APP_PASSWORD")

    if not all([email_from, email_to, app_password]):
        logger.info("メール設定が未構成のためスキップ")
        return

    html_path = Path("docs/index.html")
    if not html_path.exists():
        logger.error("配信対象のHTMLが存在しません")
        sys.exit(1)

    html_body = html_path.read_text(encoding="utf-8")
    today = datetime.now().strftime("%Y-%m-%d")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"📰 Tech News Daily - {today}"
    msg["From"] = email_from
    msg["To"] = email_to
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    # Gmail SMTPで送信（アプリパスワード必須）
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(email_from, app_password)
        server.send_message(msg)

    logger.info(f"メール送信完了: {email_to}")


if __name__ == "__main__":
    send_email()
