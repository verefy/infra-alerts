from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage

from infra_alerts.models import AlertPayload


class EmailClient:
    def __init__(self, sender: str, app_password: str, recipients: list[str]) -> None:
        self.sender = sender
        self.app_password = app_password
        self.recipients = recipients

    async def send_alert(self, payload: AlertPayload) -> bool:
        subject = f"[Verefy Infra Alert] {payload.level}: {payload.title}"
        body = payload.body
        if payload.links:
            body = f"{body}\n\n" + "\n".join(payload.links)
        message = EmailMessage()
        message["From"] = self.sender
        message["To"] = ", ".join(self.recipients)
        message["Subject"] = subject
        message.set_content(body)
        return await asyncio.to_thread(self._send, message)

    def _send(self, message: EmailMessage) -> bool:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as smtp:
            smtp.login(self.sender, self.app_password)
            smtp.send_message(message)
        return True
