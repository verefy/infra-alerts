from __future__ import annotations

import httpx

from infra_alerts.models import AlertPayload


class SlackClient:
    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = webhook_url

    async def send(self, payload: AlertPayload) -> bool:
        body_lines = [payload.body]
        if payload.links:
            body_lines.append("\n".join(payload.links))
        text = "\n\n".join(line for line in body_lines if line)
        blocks: list[dict[str, object]] = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": payload.title,
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": text,
                },
            },
        ]
        if payload.tags:
            context_block: dict[str, object] = {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": " ".join(f"`{tag}`" for tag in payload.tags)}],
            }
            blocks.append(context_block)
        request_body: dict[str, object] = {"text": f"{payload.title}\n{text}", "blocks": blocks}
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(self.webhook_url, json=request_body)
        return 200 <= response.status_code < 300
