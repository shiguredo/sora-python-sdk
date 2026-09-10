"""新 API での通知と伝送路通信を確認する。"""

from __future__ import annotations

import json
import threading
import time

import pytest
import sora_sdk
from test_loopback import prepare_channel


def test_signaling_error_code_values() -> None:
    """
    誤り符号の値が既存 API と一致することを確認する。
    前提は特にない。
    0 から 8 の連番であることを期待する。
    """
    codes = sora_sdk.SoraSignalingErrorCode
    assert int(codes.CLOSE_SUCCEEDED) == 0
    assert int(codes.CLOSE_FAILED) == 1
    assert int(codes.INTERNAL_ERROR) == 2
    assert int(codes.INVALID_PARAMETER) == 3
    assert int(codes.WEBSOCKET_HANDSHAKE_FAILED) == 4
    assert int(codes.WEBSOCKET_ONCLOSE) == 5
    assert int(codes.WEBSOCKET_ONERROR) == 6
    assert int(codes.PEER_CONNECTION_STATE_FAILED) == 7
    assert int(codes.ICE_FAILED) == 8


def test_set_offer_and_disconnect_callbacks() -> None:
    """
    offer 設定通知と切断通知が飛ぶことを確認する。
    前提は既存 E2E と同じ環境変数で接続先が指定されていること。
    offer 記録の受信と正常切断の符号を受け取れることを期待する。
    """
    signaling_urls, metadata, channel_id = prepare_channel()

    # 接続先の有無を確認する
    if not signaling_urls:
        pytest.fail("接続先が未設定のため確認できない")

    offers: list = []
    disconnects: list = []

    print(f"接続開始: channel_id={channel_id}")
    connection = sora_sdk.Sora().create_connection(
        signaling_urls, "recvonly", channel_id, metadata=metadata
    )
    connection.on_set_offer = offers.append
    connection.on_disconnect = lambda code, message: disconnects.append((code, message))
    connection.connect()
    try:
        # offer 設定通知を待つ
        deadline = time.time() + 15
        while time.time() < deadline and not offers:
            time.sleep(0.5)
        assert offers, "offer 設定通知を受け取れなかった"
        assert json.loads(offers[0])["type"] == "offer"
        print("offer 設定通知を確認した")
    finally:
        connection.disconnect()

    # 正常切断の通知を確認する
    assert disconnects, "切断通知を受け取れなかった"
    assert int(disconnects[0][0]) == 0
    print(f"切断通知を確認した: code={disconnects[0][0]}")


def test_opus_params_reach_signaling() -> None:
    """
    Opus 詳細設定が接続記録に載ることを確認する。
    前提は既存 E2E と同じ環境変数で接続先が指定されていること。
    送信した connect 記録に opus 項目が含まれることを期待する。
    """
    signaling_urls, metadata, channel_id = prepare_channel()

    # 接続先の有無を確認する
    if not signaling_urls:
        pytest.fail("接続先が未設定のため確認できない")

    sent: list = []

    def on_signaling_message(kind: int, direction: int, text: str) -> None:
        # 送信記録だけ集める
        if direction == 0:
            sent.append(text)

    connection = sora_sdk.Sora().create_connection(
        signaling_urls,
        "sendonly",
        channel_id,
        metadata=metadata,
        audio=True,
        audio_codec_type="OPUS",
        audio_opus_params={"maxplaybackrate": 16000, "stereo": False},
        video=False,
    )
    connection.on_signaling_message = on_signaling_message
    connection.connect()
    try:
        # connect 記録を探す
        connects = [json.loads(text) for text in sent if json.loads(text).get("type") == "connect"]
        assert connects, "connect 記録を送れなかった"
        audio = connects[0].get("audio", {})
        assert audio.get("opus_params", {}).get("maxplaybackrate") == 16000
        assert audio.get("opus_params", {}).get("stereo") is False
        print("Opus 設定の到達を確認した")
    finally:
        connection.disconnect()


def test_send_data_channel_messaging() -> None:
    """
    札付き路で送受信できることを確認する。
    前提は既存 E2E と同じ環境変数で接続先が指定されていること。
    送信側の送達と受信側の到達を期待する。
    """
    signaling_urls, metadata, channel_id = prepare_channel()

    # 接続先の有無を確認する
    if not signaling_urls:
        pytest.fail("接続先が未設定のため確認できない")

    channels = [{"label": "#rust-messaging", "direction": "sendrecv"}]
    received: list = []
    receiver_opened = threading.Event()
    sender_opened = threading.Event()

    def on_message(label: str, data: bytes) -> None:
        received.append((label, data))

    def on_receiver_channel(label: str) -> None:
        if label == "#rust-messaging":
            receiver_opened.set()

    def on_sender_channel(label: str) -> None:
        if label == "#rust-messaging":
            sender_opened.set()

    # 受信側を接続する
    receiver = sora_sdk.Sora().create_connection(
        signaling_urls, "sendrecv", channel_id, metadata=metadata, data_channels=channels
    )
    receiver.on_message = on_message
    receiver.on_data_channel = on_receiver_channel
    receiver.connect()
    try:
        # 送信側を接続する
        sender = sora_sdk.Sora().create_connection(
            signaling_urls, "sendrecv", channel_id, metadata=metadata, data_channels=channels
        )
        sender.on_data_channel = on_sender_channel
        sender.connect()
        try:
            # 両側の路開通を待つ
            assert receiver_opened.wait(timeout=20), "受信側の伝送路が開かなかった"
            assert sender_opened.wait(timeout=20), "送信側の伝送路が開かなかった"

            # 未接続では送れないことを確認する (別接続で検証済みのため到達のみ見る)
            assert sender.send_data_channel("#rust-messaging", b"hello") is True
            print("送信を確認した")

            # 到達を待つ
            deadline = time.time() + 15
            while time.time() < deadline and not received:
                time.sleep(0.5)
            assert received, "伝送路通信を受け取れなかった"
            assert received[0][0] == "#rust-messaging"
            assert received[0][1] == b"hello"
            print(f"受信を確認した: label={received[0][0]}")
        finally:
            sender.disconnect()
    finally:
        receiver.disconnect()


def test_send_data_channel_rejects_disconnected() -> None:
    """
    未接続の送信が誤りになることを確認する。
    前提は特にない。
    未接続での送信で RuntimeError になることを期待する。
    """
    connection = sora_sdk.Sora().create_connection(["wss://127.0.0.1:1/signaling"], "sendrecv", "x")

    # 未接続の送信を確認する
    with pytest.raises(RuntimeError, match="Already disconnected"):
        connection.send_data_channel("#rust-messaging", b"hello")
