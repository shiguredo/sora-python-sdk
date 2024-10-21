import sys
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

    response = disconnect_channel_api(signaling_urls, channel_id)
    assert response.status_code == 200, [response.text]
