"""実 Sora を使ったメディアループバックを確認する。"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import numpy
import pytest
import sora_sdk
from test_connect import load_env_file, make_access_token


def build_metadata(channel_id: str) -> tuple[list[str], str | None]:
    """既存 E2E と同じく JWT を metadata の access_token に載せる。"""
    load_env_file(Path(__file__).resolve().parent.parent / ".env")
    signaling_urls_env = os.getenv("TEST_SIGNALING_URLS", os.getenv("TEST_SIGNALING_URL", ""))
    signaling_urls = [x.strip() for x in signaling_urls_env.split(",") if x.strip()]
    secret = os.getenv("TEST_SECRET_KEY")
    metadata = None
    if secret:
        metadata = json.dumps({"access_token": make_access_token(secret, channel_id)})
    return signaling_urls, metadata


def prepare_channel() -> tuple[list[str], str | None, str]:
    """環境変数を読み込み、接続先とチャネル ID とメタデータを組み立てる。"""
    # 先に .env を読んでからチャネル ID を作る
    load_env_file(Path(__file__).resolve().parent.parent / ".env")
    channel_id = f"{os.getenv('TEST_CHANNEL_ID_PREFIX', '')}_{uuid.uuid4()}"
    return *build_metadata(channel_id), channel_id


def test_loopback_audio_frames() -> None:
    """
    意図・前提・期待値をここに書く
    実マイク送信と PCM 受信のループバックを確認する。
    前提は既存 E2E と同じ環境変数で接続先が指定され、実マイクが使えること。
    PCM フレームを受信できることを期待する。
    """
    signaling_urls, metadata, channel_id = prepare_channel()

    # 接続先の有無を確認する
    if not signaling_urls:
        pytest.fail("接続先が未設定のため確認できない")

    # 音声ループバックを実行する
    print(f"音声ループバック開始: channel_id={channel_id}")
    result = sora_sdk.loopback_audio_frames(
        signaling_urls, channel_id, metadata=metadata, duration_secs=10, microphone=True
    )
    print(f"音声ループバック結果: frames={result['frames']}")

    # PCM フレームを受信できたことを確認する
    assert result["frames"] > 0
    assert result["bytes"] > 0
    assert result["sample_rate"] > 0
    assert result["channels"] > 0
    assert result["unknown_tracks"] == 0


def test_loopback_video_frames() -> None:
    """
    意図・前提・期待値をここに書く
    黒フレーム送信と映像受信・encoded 変換のループバックを確認する。
    前提は既存 E2E と同じ環境変数で接続先が指定されていること。
    受信フレームと変換フレームの計数が進み、ARGB 変換結果を numpy で開けることを期待する。
    """
    signaling_urls, metadata, channel_id = prepare_channel()

    # 接続先の有無を確認する
    if not signaling_urls:
        pytest.fail("接続先が未設定のため確認できない")

    # 映像ループバックを実行する
    print(f"映像ループバック開始: channel_id={channel_id}")
    result = sora_sdk.loopback_video_frames(
        signaling_urls, channel_id, metadata=metadata, duration_secs=15
    )
    print(
        f"映像ループバック結果: received={result['received_frames']}"
        f" transformed={result['transformed_frames']}"
    )

    # 受信と encoded 変換が流れたことを確認する
    assert result["received_frames"] > 0
    assert result["transformed_frames"] > 0
    assert result["unknown_tracks"] == 0

    # ARGB 変換結果を numpy 配列として開けることを確認する
    width = result["width"]
    height = result["height"]
    frame = numpy.frombuffer(result["argb_frame"], dtype=numpy.uint8).reshape(height, width, 4)
    assert frame.shape == (height, width, 4)
