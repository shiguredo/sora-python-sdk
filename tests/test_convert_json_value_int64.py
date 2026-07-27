"""
ConvertJsonValue が int32 範囲を超える Python 整数を受け付けることを検証する。

metadata 等の JSON 変換経路で nb::cast<int> だと 2**31 超で例外になる。
"""

from __future__ import annotations

from sora_sdk import Sora


def test_create_connection_accepts_int64_metadata():
    """
    metadata に int32 を超える整数を渡しても create_connection が成功すること。

    前提:
    - ConvertJsonValue が metadata の整数を boost::json::value に変換する

    期待:
    - 2**40 を含む metadata で例外にならない
    """
    sora = Sora()
    connection = sora.create_connection(
        signaling_urls=["wss://example.invalid/signaling"],
        role="recvonly",
        channel_id="convert-json-int64",
        metadata={"exp": 2**40},
        audio=False,
        video=False,
    )
    assert connection is not None


def test_create_connection_keeps_bool_before_int_branch():
    """
    metadata の True / False が create_connection で例外にならないこと。

    前提:
    - Python では bool は int のサブクラス
    - ConvertJsonValue は bool 分岐を int 分岐より先に評価する

    期待:
    - True / False を含む metadata で例外にならない
    """
    sora = Sora()
    connection = sora.create_connection(
        signaling_urls=["wss://example.invalid/signaling"],
        role="recvonly",
        channel_id="convert-json-bool",
        metadata={"enabled": True, "disabled": False},
        audio=False,
        video=False,
    )
    assert connection is not None
