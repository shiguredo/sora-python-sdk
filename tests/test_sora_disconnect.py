import time

from api import disconnect_connection_api
from client import SoraClient, SoraRole

from sora_sdk import SoraSignalingErrorCode


def test_websocket_signaling_only_disconnect_api(settings):
    with SoraClient(
        settings,
        SoraRole.RECVONLY,
        audio=True,
        video=True,
        data_channel_signaling=False,
        ignore_disconnect_websocket=False,
    ) as conn:
        time.sleep(3)

        if conn.connection_id is None:
            raise ValueError("connection_id is None")
        response = disconnect_connection_api(
            settings.api_url, settings.channel_id, conn.connection_id
        )
        assert response.status_code == 200

        time.sleep(3)

        assert conn.ws_close is True
        assert conn.ws_close_code == 1000
        assert conn.ws_close_reason == "DISCONNECTED-API"

        assert conn.disconnect_code == SoraSignalingErrorCode.CLOSE_SUCCEEDED
        assert conn.disconnect_reason is not None
        assert "DISCONNECTED-API" in conn.disconnect_reason


def test_websocket_signaling_only_lifetime_expired(settings):
    with SoraClient(
        settings,
        SoraRole.RECVONLY,
        audio=True,
        video=True,
        jwt_private_claims={
            "audio": False,
            "video": True,
            "connection_lifetime": 3,
        },
        data_channel_signaling=False,
        ignore_disconnect_websocket=False,
    ) as conn:
        time.sleep(5)

        assert conn.ws_close is True
        assert conn.ws_close_code == 1000
        assert conn.ws_close_reason == "LIFETIME-EXPIRED"


def test_websocket_datachannel_signaling_disconnect_api(settings):
    with SoraClient(
        settings,
        SoraRole.RECVONLY,
        audio=True,
        video=True,
        data_channel_signaling=True,
        ignore_disconnect_websocket=False,
    ) as conn:
        time.sleep(3)

        if conn.connection_id is None:
            raise ValueError("connection_id is None")
        response = disconnect_connection_api(
            settings.api_url, settings.channel_id, conn.connection_id
        )
        assert response.status_code == 200

        time.sleep(3)

        assert conn.ws_close is True
        assert conn.ws_close_code == 1000
        assert conn.ws_close_reason == "DISCONNECTED-API"

        assert conn.disconnect_code == SoraSignalingErrorCode.CLOSE_SUCCEEDED
        assert conn.disconnect_reason is not None
        assert "DISCONNECTED-API" in conn.disconnect_reason


def test_websocket_datachannel_signaling_lifetime_expired(settings):
    with SoraClient(
        settings,
        SoraRole.RECVONLY,
        audio=True,
        video=True,
        jwt_private_claims={
            "audio": True,
            "video": True,
            "connection_lifetime": 3,
        },
        data_channel_signaling=True,
        ignore_disconnect_websocket=False,
    ) as conn:
        time.sleep(5)

        assert conn.ws_close is True
        assert conn.ws_close_code == 1000
        assert conn.ws_close_reason == "LIFETIME-EXPIRED"


def test_datachannel_only_signaling_disconnect_api(settings):
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
        assert conn.ignore_disconnect_websocket is True

        assert conn.ws_close_code == 1000
        assert conn.ws_close_reason == "SELF-CLOSED"

        if conn.connection_id is None:
            raise ValueError("connection_id is None")
        response = disconnect_connection_api(
            settings.api_url, settings.channel_id, conn.connection_id
        )
        assert response.status_code == 200

        time.sleep(3)

        assert conn.close_message is not None
        assert conn.close_message["type"] == "close"
        assert conn.close_message["code"] == 1000
        assert conn.close_message["reason"] == "DISCONNECTED-API"

        assert conn.disconnect_code == SoraSignalingErrorCode.CLOSE_SUCCEEDED
        assert conn.disconnect_reason is not None
        assert "DISCONNECTED-API" in conn.disconnect_reason


def test_datachannel_only_signaling_lifetime_expired(settings):
    with SoraClient(
        settings,
        SoraRole.RECVONLY,
        audio=True,
        video=True,
        jwt_private_claims={
            "audio": True,
            "video": True,
            "connection_lifetime": 3,
        },
        data_channel_signaling=True,
        ignore_disconnect_websocket=True,
    ) as conn:
        time.sleep(5)

        assert conn.close_message is not None
        assert conn.close_message["type"] == "close"
        assert conn.close_message["code"] == 1000
        assert conn.close_message["reason"] == "LIFETIME-EXPIRED"

        assert conn.disconnect_code == SoraSignalingErrorCode.CLOSE_SUCCEEDED
        assert conn.disconnect_reason is not None
        assert "LIFETIME-EXPIRED" in conn.disconnect_reason
