"""F33 mailers. Console: logs the mail and keeps an outbox (dev / demo / tests). SMTP: STARTTLS, in a thread."""
import asyncio
import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

log = logging.getLogger(__name__)


@dataclass(slots=True)
class Mail:
    to: str
    subject: str
    text: str


class ConsoleMailer:
    name = "console"

    def __init__(self):
        self.outbox: list[Mail] = []

    async def send(self, to: str, subject: str, text: str) -> None:
        self.outbox.append(Mail(to, subject, text))
        del self.outbox[:-50]  # keep the last 50
        log.warning("MAILER=console → mail to %s: %s\n%s", to, subject, text)


class SmtpMailer:
    name = "smtp"

    def __init__(self, host: str, port: int, user: str, password: str, sender: str, timeout_s: float = 15.0):
        self.host, self.port, self.user, self.password, self.sender = host, port, user, password, sender
        self.timeout_s = timeout_s

    async def send(self, to: str, subject: str, text: str) -> None:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = self.sender, to, subject
        msg.set_content(text)
        await asyncio.to_thread(self._send, msg)

    def _send(self, msg: EmailMessage) -> None:
        with smtplib.SMTP(self.host, self.port, timeout=self.timeout_s) as smtp:
            smtp.starttls()
            if self.user:
                smtp.login(self.user, self.password)
            smtp.send_message(msg)
