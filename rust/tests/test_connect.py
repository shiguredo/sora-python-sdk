"""実 Sora への接続と切断を確認する。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from pathlib import Path

import pytest
import sora_rust_sdk


def load_env_file(env_file: Path) -> None:
    """環境変数ファイルを読み込む。既存の環境変数は上書きしない。"""
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def make_access_token(secret: str, channel_id: str) -> str:
    """テスト用 JWT を作る。"""
    header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).rstrip(b"=")
    payload = base64.urlsafe_b64encode(
        json.dumps({"channel_id": channel_id, "exp": int(time.time()) + 300}).encode()
    ).rstrip(b"=")
    signature = hmac.new(secret.encode(), header + b"." + payload, hashlib.sha256).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).rstrip(b"=")
    return (header + b"." + payload + b"." + encoded_signature).decode()


def test_connect_and_disconnect_recvonly() -> None:
    """
    意図・前提・期待値をここに書く
    実 Sora に recvonly 接続し切断できることを確認する。
    前提は既存 E2E と同じ環境変数で接続先が指定されていること。
    connect が例外なく戻ることを期待する。
    """
    # リポジトリ直下の .env を読む
    load_env_file(Path(__file__).resolve().parent.parent.parent / ".env")

    # 既存 E2E と同じ環境変数から接続先を組み立てる
    signaling_urls_env = os.getenv("TEST_SIGNALING_URLS", os.getenv("TEST_SIGNALING_URL", ""))
    signaling_urls = [x.strip() for x in signaling_urls_env.split(",") if x.strip()]
    channel_id = f"{os.getenv('TEST_CHANNEL_ID_PREFIX', '')}_{uuid.uuid4()}"
    secret = os.getenv("TEST_SECRET_KEY")

    # 接続先の有無を確認する
    if not signaling_urls:
        pytest.fail("接続先が未設定のため確認できない")

    metadata = None
    if secret:
        # 既存 E2E と同じく JWT を metadata の access_token に載せる
        metadata = json.dumps({"access_token": make_access_token(secret, channel_id)})

    # 接続して切断する
    print(f"接続開始: channel_id={channel_id}")
    sora_rust_sdk.connect(
        signaling_urls, channel_id, role="recvonly", metadata=metadata, duration_secs=5
    )
    print("接続と切断を確認した")
