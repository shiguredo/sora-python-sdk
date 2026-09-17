import httpx


def get_stats_connection_api(url: str, channel_id: str, connection_id: str) -> httpx.Response:
    # URL の簡易バリデーション
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        raise ValueError(f"Invalid URL: {url}")

    headers = {
        "Content-Type": "application/json",
        "x-sora-target": "Sora_20170529.GetStatsConnection",
    }
    body = {
        "channel_id": channel_id,
        "connection_id": connection_id,
    }
    return httpx.post(url, headers=headers, json=body, follow_redirects=True)


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


def request_key_frame_api(
    url: str, channel_id: str, connection_id: str, *, rid: str | None = None
) -> httpx.Response:
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
    # rid を指定した場合はその rid の SSRC にのみ PLI が送られ、
    # 指定しない場合は全登録済み rid に PLI が送られる
    if rid is not None:
        body["rid"] = rid
    return httpx.post(url, headers=headers, json=body, follow_redirects=True)
