import time

import pytest
from client import SoraClient, SoraRole


def test_websocket_signaling_only_type_switched(settings):
    """
    - WebSocket シグナリングのみ
    - type: switched 送られてこない
    """

    with SoraClient(
        settings,
        SoraRole.RECVONLY,
        audio=True,
        video=True,
        data_channel_signaling=False,
        ignore_disconnect_websocket=False,
    ) as conn:
        time.sleep(3)

        assert conn.switched is False
        assert conn.ws_close_code is None
        assert conn.ws_close_reason is None


def test_hybrid_signaling_type_switched(settings):
    """
    - WebSocket シグナリング + DataChannel シグナリング
    - type: switched 送られてくる
    """
    with SoraClient(
        settings,
        SoraRole.RECVONLY,
        audio=True,
        video=True,
        data_channel_signaling=True,
        ignore_disconnect_websocket=False,
    ) as conn:
        time.sleep(3)

        assert conn.switched is True
        assert conn.ws_close_code is None
        assert conn.ws_close_reason is None


def test_datachannel_signaling_only_type_switched(settings):
    """
    - DataChannel シグナリングのみ
    - type: switched 送られてくる
    - Python SDK は WebSocket を自分で切断する
    """
    with SoraClient(
        settings,
        SoraRole.RECVONLY,
        audio=True,
        video=True,
        data_channel_signaling=True,
        ignore_disconnect_websocket=True,
    ) as conn:
        time.sleep(3)

        assert conn.switched is True
        assert conn.ws_close_code == 1000
        assert conn.ws_close_reason == "SELF-CLOSED"


@pytest.mark.skip(reason="Sora がまだ対応していない")
def test_disconnect_before_switched(settings):
    # switched 前に type: disconnect を送りつける
    # ignore_disconnect_websocket は true

    with SoraClient(
        settings,
        SoraRole.RECVONLY,
        audio=True,
        video=True,
        data_channel_signaling=True,
        ignore_disconnect_websocket=True,
    ) as conn:
        conn.disconnect()

        if not conn.switched:
            assert conn.ws_close_code == 1000
            assert conn.ws_close_reason == "TYPE-DISCONNECT"
