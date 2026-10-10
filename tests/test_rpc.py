"""
Sora の RPC 機能 (JSON-RPC 2.0 over DataChannel) の E2E テスト。

SoraConnection.send_rpc() が rpc ラベルへ JSON-RPC 2.0 のリクエストを送信し、
応答が on_rpc に届くことを確認する。rpc ラベルは Sora の RPC 機能が有効な場合に
だけ offer に含まれるため、rpc ラベルを必要とするテストは含まれない環境では
送信できないことを確認して skip する。
"""

from __future__ import annotations

from queue import Empty
from typing import Any

import pytest
from client import SoraClient, SoraRole

NOT_EXIST_METHOD = "9999.0.0/not_exist"


def _create_rpc_client(settings) -> SoraClient:
    """
    RPC のテストで使うクライアントを生成する (Sora への接続は with 文で行う)。

    rpc ラベルは DataChannel 経由のシグナリングでのみ使うため data_channel_signaling を
    有効にする。RPC は音声・映像とは独立して使えるため両方無効にするが、この構成では
    ユーザー定義の DataChannel が 1 つも無いと Sora が接続メッセージを 4490
    INVALID-MESSAGE で拒否するため、ダミーの #test ラベルを 1 つ用意する。
    """
    return SoraClient(
        settings,
        SoraRole.SENDONLY,
        data_channel_signaling=True,
        audio=False,
        video=False,
        data_channels=[{"label": "#test", "direction": "sendonly"}],
    )


def test_send_rpc_request_and_response(settings):
    """
    send_rpc() で送信した JSON-RPC 2.0 のリクエストに応答が返ることを確認する。

    前提:
    - RPC が有効な Sora に data_channel_signaling を有効にして接続する
    - 払い出される rpc_methods に依存しないよう、存在しないメソッドを指定する

    期待:
    - send_rpc() が True を返す
    - 応答が on_rpc に届き、送信した id と一致する
    - 存在しないメソッドなので error を含む応答になる
    - params に None / Array を指定した場合と、params を省略した場合も送信できる
    """
    with _create_rpc_client(settings) as client:
        if not client.wait_rpc_ready(timeout=5):
            # rpc ラベルが使えない環境では送信されず False が返る
            assert client.send_rpc(1, NOT_EXIST_METHOD, {"key": "value"}) is False
            pytest.skip("rpc ラベルが使えない環境のため送信できない")

        # 送信した id がそのまま応答に含まれることを確認する (0 と 2^64-1 は境界値)
        for request_id in [0, 1, 2**64 - 1]:
            assert client.send_rpc(request_id, NOT_EXIST_METHOD, {"key": "value"})

            response = client.recv_rpc(timeout=5)
            assert response["id"] == request_id
            assert "error" in response

        # params に None を指定した場合は params を含めずに送信する
        assert client.send_rpc(2, NOT_EXIST_METHOD, None)

        response = client.recv_rpc(timeout=5)
        assert response["id"] == 2

        # params には Object だけでなく Array も指定できる
        assert client.send_rpc(3, NOT_EXIST_METHOD, [])

        response = client.recv_rpc(timeout=5)
        assert response["id"] == 3

        # params を省略した 2 引数呼び出しではバインディングの既定値 (None) が使われる。
        # ヘルパは常に params を渡すため、ここでは SDK を直接呼ぶ
        assert client._connection.send_rpc(4, NOT_EXIST_METHOD)

        response = client.recv_rpc(timeout=5)
        assert response["id"] == 4


def test_send_rpc_notification_has_no_response(settings):
    """
    id に None を指定した Notification には Sora が応答を返さないことを確認する。

    前提:
    - RPC が有効な Sora に接続する
    - id に None を指定してリクエストを送る

    期待:
    - send_rpc() が True を返す
    - 応答が返らないため recv_rpc() が Empty でタイムアウトする
    """
    with _create_rpc_client(settings) as client:
        if not client.wait_rpc_ready(timeout=5):
            pytest.skip("rpc ラベルが使えない環境のため送信できない")

        assert client.send_rpc(None, NOT_EXIST_METHOD, {"key": "value"})

        # Notification には Sora が応答を返さない
        with pytest.raises(Empty):
            client.recv_rpc(timeout=3)


def test_send_rpc_invalid_params(settings):
    """
    params に送信できない値を指定したときの挙動を確認する。

    JSON-RPC 2.0 の params は Object か Array でなければならないため、それ以外の値に
    変換される場合は送信せず False が返る。JSON の値として扱えない型の場合は既存の
    Sora::ConvertJsonValue() と同じく TypeError、int64 の範囲を超える整数とキーが
    文字列でない dict は同じく RuntimeError になる。TypeError と RuntimeError は引数の
    変換時に発生するため rpc ラベルの有無に依存しない。False はラベルが無い場合も
    Object / Array 以外の場合も返る。
    """
    with _create_rpc_client(settings) as client:
        # 文字列・整数・浮動小数点数・真偽値は JSON の値には変換できるが params の要件を満たさない
        for params in ["not-structured", 1, 1.5, True]:
            assert client.send_rpc(1, NOT_EXIST_METHOD, params) is False

        # JSON の値として扱えない型は TypeError になる
        # 0.1 は float32 で厳密に表現できないため (Sora::ConvertJsonValue() の既知の制限)
        for invalid_params in [
            {"key": set()},
            {"key": (1, 2)},
            {"key": b"bytes"},
            {"key": 0.1},
        ]:
            with pytest.raises(TypeError, match="Invalid JSON value in params"):
                client.send_rpc(1, NOT_EXIST_METHOD, invalid_params)

        # int64 の範囲を超える整数は nb::cast_error 由来の RuntimeError になる
        with pytest.raises(RuntimeError):
            client.send_rpc(1, NOT_EXIST_METHOD, {"key": 2**70})

        # キーが文字列でない dict も nb::cast_error 由来の RuntimeError になる
        with pytest.raises(RuntimeError):
            client.send_rpc(1, NOT_EXIST_METHOD, {1: "value"})


def test_send_rpc_invalid_id(settings):
    """
    id に None でも 0 以上 2^64-1 以下の整数でもない値を指定すると TypeError になることを確認する。

    C++ SDK の SendRpc() の id は std::optional<uint64_t> のため、文字列・負の整数・
    2^64 以上の整数は指定できない。
    """
    with _create_rpc_client(settings) as client:
        # 型注釈 (int | None) では通せない値も実行時に渡すため、Any のリストを経由する
        invalid_ids: list[Any] = ["id", -1, 2**64]
        for invalid_id in invalid_ids:
            with pytest.raises(TypeError):
                client.send_rpc(invalid_id, NOT_EXIST_METHOD, {"key": "value"})


def test_send_rpc_without_rpc_label_returns_false(settings):
    """
    rpc ラベルが使えない接続では send_rpc() が送信せず False を返すことを確認する。

    前提:
    - DataChannel 経由のシグナリングを使わずに接続する (offer の data_channels に
      rpc ラベルが含まれない)

    期待:
    - send_rpc() が送信せず False を返す
    - Sora の RPC 機能の有効無効に依存せず検証できる
    """
    with SoraClient(
        settings,
        SoraRole.RECVONLY,
        audio=True,
        video=True,
        data_channel_signaling=False,
        ignore_disconnect_websocket=False,
    ) as client:
        assert client.send_rpc(1, NOT_EXIST_METHOD, {"key": "value"}) is False


def test_send_rpc_after_disconnect_raises_runtime_error(settings):
    """
    disconnect() 後の send_rpc() が SEGV ではなく RuntimeError になることを確認する。

    前提:
    - Sora に接続してから disconnect() する
    - disconnect() 後の SoraConnection インスタンスをそのまま使う

    期待:
    - RuntimeError が発生する (メッセージに Already disconnected を含む)
    - プロセスが SEGV で落ちない
    """
    with _create_rpc_client(settings) as client:
        connection = client._connection
        client.disconnect()

        with pytest.raises(RuntimeError, match="Already disconnected"):
            connection.send_rpc(1, NOT_EXIST_METHOD, {"key": "value"})
