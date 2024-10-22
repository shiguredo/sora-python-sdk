import httpx


def list_channel_connections_api(url: str, channel_id: str) -> httpx.Response:
    headers = {
        "Content-Type": "application/json",
        "x-sora-target": "Sora_20201013.ListChannelConnections",
    }
    body = {"channel_id": channel_id}
    return httpx.post(url, headers=headers, json=body, follow_redirects=True)


def disconnect_channel_api(url: str, channel_id: str) -> httpx.Response:
    headers = {
        "Content-Type": "application/json",
        "x-sora-target": "Sora_20151104.DisconnectChannel",
    }
    body = {"channel_id": channel_id}
    return httpx.post(url, headers=headers, json=body, follow_redirects=True)


def disconnect_connection_api(url: str, channel_id: str, connection_id: str) -> httpx.Response:
    headers = {
        "Content-Type": "application/json",
        "x-sora-target": "Sora_20151104.DisconnectConnection",
    }
    body = {
        "channel_id": channel_id,
        "connection_id": connection_id,
    }
    return httpx.post(url, headers=headers, json=body, follow_redirects=True)
