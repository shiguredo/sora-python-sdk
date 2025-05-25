from client import SoraClient, SoraRole


def test_re_offer_re_answer_sdp(settings):
    recvonly = SoraClient(
        settings,
        SoraRole.RECVONLY,
    )
    recvonly.connect()

    sendonly1 = SoraClient(
        settings,
        SoraRole.SENDONLY,
        audio=True,
        video=True,
    )
    sendonly1.connect(fake_audio=True, fake_video=True)
    sendonly1.disconnect()

    sendonly2 = SoraClient(
        settings,
        SoraRole.SENDONLY,
        audio=True,
        video=True,
    )
    sendonly2.connect(fake_audio=True, fake_video=True)

    sendonly3 = SoraClient(
        settings,
        SoraRole.SENDONLY,
        audio=True,
        video=True,
    )
    sendonly3.connect(fake_audio=True, fake_video=True)

    sendonly2.disconnect()
    sendonly3.disconnect()

    recvonly.disconnect()
