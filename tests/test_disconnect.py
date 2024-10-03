import sys
import uuid

import httpx
import pytest
from client import SoraClient, SoraRole


def disconnect_connection_api(url: str, channel_id: str, connection_id: str) -> httpx.Response:
    headers = {
        "Content-Type": "application/json",
        "x-sora-target": "Sora_20151104.DisconnectConnection",
    }
    body = {
        "channel_id": channel_id,
        "connection_id": connection_id,
    }
    return httpx.post(url, headers=headers, json=body)


@pytest.mark.xfail(reason="Python SDK がまだ API 経由での切断の ws_close に対応していない")
@pytest.mark.skipif(sys.platform != "linux", reason="linux でのみ実行する")
def test_disconnect_api(setup):
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
    ) as conn:
        if conn.connection_id is None:
            raise ValueError("connection_id is None")
        response = disconnect_connection_api(api_url, channel_id, conn.connection_id)
        assert response.status_code == 200

        assert conn.ws_close_code == 1000
        assert conn.ws_close_reason == "DISCONNECTED-API"

    # TODO: LIFETIME-EXPIRED のテスト


def test_sendonly_disconnect(setup):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    with SoraClient(
        signaling_urls,
        SoraRole.SENDONLY,
        channel_id,
        audio=True,
        video=True,
        metadata=metadata,
        data_channel_signaling=True,
    ):
        with SoraClient(
            signaling_urls,
            SoraRole.SENDONLY,
            channel_id,
            audio=True,
            video=True,
            metadata=metadata,
            data_channel_signaling=True,
        ):
            with SoraClient(
                signaling_urls,
                SoraRole.SENDONLY,
                channel_id,
                audio=True,
                video=True,
                metadata=metadata,
                data_channel_signaling=True,
            ):
                with SoraClient(
                    signaling_urls,
                    SoraRole.SENDONLY,
                    channel_id,
                    audio=True,
                    video=True,
                    metadata=metadata,
                    data_channel_signaling=True,
                ):
                    pass
