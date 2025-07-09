import time

from client import SoraClient, SoraRole

from sora_sdk import SoraSignalingErrorCode


def test_websocket_signaling_only_disconnect(settings):
    """
    - WebSocket シグナリングのみ
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

        conn.disconnect()

        assert conn.ws_close_code == 1000
        assert conn.ws_close_reason == "TYPE-DISCONNECT"

        assert conn.disconnect_code == SoraSignalingErrorCode.CLOSE_SUCCEEDED
        assert (
            conn.disconnect_reason == "Succeeded to close WebSocket (DC signaling is not enabled)"
        )


def test_hybrid_signaling_disconnect(settings):
    """
    - WebSocket シグナリングと DataChannel シグナリング
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

        conn.disconnect()

        assert conn.ws_close_code == 1000
        assert conn.ws_close_reason == "TYPE-DISCONNECT"

        assert conn.disconnect_code == SoraSignalingErrorCode.CLOSE_SUCCEEDED
        assert conn.disconnect_reason == "Succeeded to close Websocket (DC signaling is enabled)"


def test_datachannel_only_type_disconnect(settings):
    """
    - DataChannel シグナリングのみ
    """

    with SoraClient(
        settings,
        SoraRole.RECVONLY,
        audio=True,
        video=True,
        data_channel_signaling=True,
        ignore_disconnect_websocket=True,
    ) as conn:
        time.sleep(5)

        assert conn.switched is True
        assert conn.ws_close_code == 1000
        assert conn.ws_close_reason == "SELF-CLOSED"

        conn.disconnect()

        assert conn.disconnect_code == SoraSignalingErrorCode.CLOSE_SUCCEEDED
        assert conn.disconnect_reason == "Succeeded to close DataChannel"
