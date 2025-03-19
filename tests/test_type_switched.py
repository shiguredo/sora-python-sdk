import sys
import time
import uuid

import pytest
from client import SoraClient, SoraRole


def test_websocket_signaling_only_type_switched(setup):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    """
    - WebSocket シグナリングのみ
    - type: switched 送られてこない
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

        assert conn.switched is False
        assert conn.ws_close_code is None
        assert conn.ws_close_reason is None


def test_hybrid_signaling_type_switched(setup):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    """
    - WebSocket シグナリング + DataChannel シグナリング
    - type: switched 送られてくる
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
        assert conn.ws_close_code is None
        assert conn.ws_close_reason is None


def test_datachannel_signaling_only_type_switched(setup):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    """
    - DataChannel シグナリングのみ
    - type: switched 送られてくる
    - Python SDK は WebSocket を自分で切断する
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
        time.sleep(3)

        assert conn.switched is True
        assert conn.ws_close_code == 1000
        assert conn.ws_close_reason == "SELF-CLOSED"


@pytest.mark.skip(reason="Sora がまだ対応していない")
def test_disconnect_before_switched(setup):
    # switched 前に type: disconnect を送りつける
    # ignore_disconnect_websocket は true
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

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
        conn.disconnect()

        if not conn.switched:
            assert conn.ws_close_code == 1000
            assert conn.ws_close_reason == "TYPE-DISCONNECT"
