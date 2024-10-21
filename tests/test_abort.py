import sys
import time
import uuid

from api import disconnect_channel_api
from client import SoraClient, SoraRole


def test_abort(setup):
    """
    abort させるためのテスト
    """
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")
    api_url = setup.get("api_url")
    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    conn1 = SoraClient(
        signaling_urls,
        SoraRole.SENDONLY,
        channel_id,
        audio=True,
        video=True,
        metadata=metadata,
    ).connect(fake_audio=True, fake_video=True)

    conn2 = SoraClient(
        signaling_urls,
        SoraRole.RECVONLY,
        channel_id,
        audio=True,
        video=True,
        metadata=metadata,
    ).connect()

    time.sleep(3)

    response = disconnect_channel_api(api_url, channel_id)
    assert response.status_code == 200, [response.text]

    time.sleep(3)

    assert conn1.disconnected is True
    assert conn2.disconnected is True

    # conn1.disconnect()
    # conn2.disconnect()
