import asyncio
import logging
import smtplib
from email.message import EmailMessage
from typing import Protocol

from app.core.config import Settings

logger = logging.getLogger(__name__)


class EmailSender(Protocol):
    async def send(self, recipient: str, subject: str, text: str) -> None: ...


class GmailSmtpSender:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def send(self, recipient: str, subject: str, text: str) -> None:
        await asyncio.to_thread(self._send_sync, recipient, subject, text)

    def _send_sync(self, recipient: str, subject: str, text: str) -> None:
        message = EmailMessage()
        message["From"] = self.settings.smtp_from_email
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(text)
        password = self.settings.smtp_password.replace(" ", "")
        with smtplib.SMTP(self.settings.smtp_host, self.settings.smtp_port, timeout=15) as smtp:
            if self.settings.smtp_use_tls:
                smtp.starttls()
            smtp.login(self.settings.smtp_username, password)
            smtp.send_message(message)


class DevelopmentLogSender:
    async def send(self, recipient: str, subject: str, text: str) -> None:
        logger.warning("Development email to=%s subject=%s body=%s", recipient, subject, text)


def build_email_sender(settings: Settings) -> EmailSender:
    if settings.smtp_host:
        return GmailSmtpSender(settings)
    return DevelopmentLogSender()


async def send_password_reset_email(sender: EmailSender, email: str, reset_url: str) -> None:
    await sender.send(
        email,
        "Đặt lại mật khẩu RagHub",
        f"Mở liên kết sau để đặt lại mật khẩu: {reset_url}\nLiên kết có hiệu lực trong 15 phút.",
    )
