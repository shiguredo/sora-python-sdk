import sys
import uuid

from client import SoraClient, SoraRole


def test_re_offer_re_answer_sdp(settings):
    recvonly = SoraClient(
        settings.signaling_urls,
        SoraRole.RECVONLY,
        settings.channel_id,
        metadata=settings.metadata,
    )
    recvonly.connect()

    sendonly1 = SoraClient(
        settings.signaling_urls,
        SoraRole.SENDONLY,
        settings.channel_id,
        audio=True,
        video=True,
        metadata=settings.metadata,
    )
    sendonly1.connect(fake_audio=True, fake_video=True)
    sendonly1.disconnect()

    sendonly2 = SoraClient(
        settings.signaling_urls,
        SoraRole.SENDONLY,
        settings.channel_id,
        audio=True,
        video=True,
        metadata=settings.metadata,
    )
    sendonly2.connect(fake_audio=True, fake_video=True)

    sendonly3 = SoraClient(
        settings.signaling_urls,
        SoraRole.SENDONLY,
        settings.channel_id,
        audio=True,
        video=True,
        metadata=settings.metadata,
    )
    sendonly3.connect(fake_audio=True, fake_video=True)

    sendonly2.disconnect()
    sendonly3.disconnect()

    recvonly.disconnect()
