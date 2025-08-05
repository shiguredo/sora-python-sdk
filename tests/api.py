import httpx


def disconnect_connection_api(url: str, channel_id: str, connection_id: str) -> httpx.Response:
    # URL の簡易バリデーション
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        raise ValueError(f"Invalid URL: {url}")

    headers = {
        "Content-Type": "application/json",
        "x-sora-target": "Sora_20151104.DisconnectConnection",
    }
    body = {
        "channel_id": channel_id,
        "connection_id": connection_id,
    }
    return httpx.post(url, headers=headers, json=body, follow_redirects=True)


def request_key_frame_api(url: str, channel_id: str, connection_id: str) -> httpx.Response:
    # URL の簡易バリデーション
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        raise ValueError(f"Invalid URL: {url}")

    headers = {
        "Content-Type": "application/json",
        "x-sora-target": "Sora_20241218.RequestKeyFrame",
    }
    body = {
        "channel_id": channel_id,
        "connection_id": connection_id,
    }
    return httpx.post(url, headers=headers, json=body, follow_redirects=True)
