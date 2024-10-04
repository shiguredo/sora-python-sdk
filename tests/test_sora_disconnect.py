import sys
import time
import uuid

import pytest
from api import disconnect_connection_api
from client import SoraClient, SoraRole


@pytest.mark.skipif(sys.platform != "linux", reason="linux でのみ実行する")
def test_websocket_signaling_only_disconnect_api(setup):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")
    api_url = setup.get("api_url")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

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

        if conn.connection_id is None:
            raise ValueError("connection_id is None")
        response = disconnect_connection_api(api_url, channel_id, conn.connection_id)
        assert response.status_code == 200

        assert conn.ws_close is True
        assert conn.ws_close_code == 1000
        assert conn.ws_close_reason == "DISCONNECTED-API"

    # TODO: LIFETIME-EXPIRED のテスト


@pytest.mark.skipif(sys.platform != "linux", reason="linux でのみ実行する")
def test_websocket_datachannel_signaling_disconnect_api(setup):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")
    api_url = setup.get("api_url")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

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

        if conn.connection_id is None:
            raise ValueError("connection_id is None")
        response = disconnect_connection_api(api_url, channel_id, conn.connection_id)
        assert response.status_code == 200

        assert conn.ws_close is True
        assert conn.ws_close_code == 1000
        assert conn.ws_close_reason == "DISCONNECTED-API"

    # TODO: LIFETIME-EXPIRED のテスト


@pytest.mark.skipif(sys.platform != "linux", reason="linux でのみ実行する")
def test_datachannel_only_signaling_disconnect_api(setup):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")
    api_url = setup.get("api_url")

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
        time.sleep(3)

        assert conn.switched is True
        assert conn.ignore_disconnect_websocket is True

        assert conn.ws_close_code == 1000
        assert conn.ws_close_reason == "SELF-CLOSED"

        if conn.connection_id is None:
            raise ValueError("connection_id is None")
        response = disconnect_connection_api(api_url, channel_id, conn.connection_id)
        assert response.status_code == 200

        time.sleep(3)

        assert conn.close_message is not None
        assert conn.close_message["type"] == "close"
        assert conn.close_message["code"] == 1000
        assert conn.close_message["reason"] == "DISCONNECTED-API"

    # TODO: LIFETIME-EXPIRED のテスト
