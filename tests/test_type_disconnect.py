import sys
import time
import uuid

from client import SoraClient, SoraRole

from sora_sdk import SoraSignalingErrorCode


def test_websocket_signaling_only_disconnect(setup):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    """
    - WebSocket シグナリングのみ
    """
    with SoraClient(
        signaling_urls,
        SoraRole.RECVONLY,
        channel_id,
        audio=True,
        video=True,
        metadata=metadata,
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


def test_hybrid_signaling_disconnect(setup):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    """
    - WebSocket シグナリングと DataChannel シグナリング
    """
    with SoraClient(
        signaling_urls,
        SoraRole.RECVONLY,
        channel_id,
        audio=True,
        video=True,
        metadata=metadata,
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


def test_datachannel_only_type_disconnect(setup):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    """
    - DataChannel シグナリングのみ
    """
    with SoraClient(
        signaling_urls,
        SoraRole.RECVONLY,
        channel_id,
        audio=True,
        video=True,
        metadata=metadata,
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
