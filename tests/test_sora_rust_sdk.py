"""sora_sdk モジュールの版と引数検証を確認する。"""

from __future__ import annotations

from typing import Any

import pytest
import sora_sdk


def test_version_is_non_empty_string() -> None:
    """
    意図・前提・期待値をここに書く
    モジュール版を参照できることを確認する。前提はパッケージ導入済み。
    __version__ が空でない文字列であることを期待する。
    """
    # 版を取得する
    version = sora_sdk.__version__
    # 空でない文字列であることを確認する
    assert isinstance(version, str)
    assert version != ""


@pytest.mark.parametrize(
    ("kwargs", "pattern"),
    [
        (
            {"signaling_urls": [], "channel_id": "x"},
            "signaling_urls must contain at least 1 URL, got 0",
        ),
        (
            {"signaling_urls": ["wss://example.com/signaling"] * 17, "channel_id": "x"},
            "signaling_urls must contain at least 1 URL and at most 16 URLs, got 17",
        ),
        (
            {
                "signaling_urls": ["wss://example.com/signaling"],
                "channel_id": "x",
                "role": "send",
            },
            'invalid role "send", expected sendonly, recvonly or sendrecv',
        ),
        (
            {"signaling_urls": ["wss://example.com/signaling"], "channel_id": ""},
            "channel_id must not be empty",
        ),
        (
            {
                "signaling_urls": ["wss://example.com/signaling"],
                "channel_id": "x",
                "metadata": "{oops",
            },
            "invalid metadata JSON",
        ),
        (
            {
                "signaling_urls": ["wss://example.com/signaling"],
                "channel_id": "x",
                "metadata": "x" * 16385,
            },
            "metadata must be at most 16384 characters",
        ),
        (
            {
                "signaling_urls": ["wss://example.com/signaling"],
                "channel_id": "x",
                "duration_secs": 0,
            },
            "duration_secs must be within",
        ),
    ],
    ids=[
        "empty-urls",
        "too-many-urls",
        "invalid-role",
        "empty-channel-id",
        "invalid-metadata-json",
        "too-long-metadata",
        "non-positive-duration",
    ],
)
def test_connect_rejects_invalid_arguments(kwargs: dict[str, Any], pattern: str) -> None:
    """
    意図・前提・期待値をここに書く
    不正な引数を Sora 接続前に弾けることを確認する。前提は接続不要。
    ValueError が送出されることを期待する。
    """
    # 不正な引数で接続を試みる
    with pytest.raises(ValueError, match=pattern):
        sora_sdk.connect(**kwargs)
