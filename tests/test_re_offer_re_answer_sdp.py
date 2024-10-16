import sys
import uuid

from client import SoraClient, SoraRole


def test_re_offer_re_answer_sdp(setup):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    recvonly = SoraClient(
        signaling_urls,
        SoraRole.RECVONLY,
        channel_id,
        metadata=metadata,
    )
    recvonly.connect()

    sendonly1 = SoraClient(
        signaling_urls,
        SoraRole.SENDONLY,
        channel_id,
        audio=True,
        video=True,
        metadata=metadata,
    )
    sendonly1.connect(fake_audio=True, fake_video=True)
    sendonly1.disconnect()

    sendonly2 = SoraClient(
        signaling_urls,
        SoraRole.SENDONLY,
        channel_id,
        audio=True,
        video=True,
        metadata=metadata,
    )
    sendonly2.connect(fake_audio=True, fake_video=True)

    sendonly3 = SoraClient(
        signaling_urls,
        SoraRole.SENDONLY,
        channel_id,
        audio=True,
        video=True,
        metadata=metadata,
    )
    sendonly3.connect(fake_audio=True, fake_video=True)

    sendonly2.disconnect()
    sendonly3.disconnect()

    recvonly.disconnect()
