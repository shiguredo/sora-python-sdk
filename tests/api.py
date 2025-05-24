import httpx
from pydantic import HttpUrl


def disconnect_connection_api(url: HttpUrl, channel_id: str, connection_id: str) -> httpx.Response:
    headers = {
        "Content-Type": "application/json",
        "x-sora-target": "Sora_20151104.DisconnectConnection",
    }
    body = {
        "channel_id": channel_id,
        "connection_id": connection_id,
    }
    return httpx.post(str(url), headers=headers, json=body, follow_redirects=True)
