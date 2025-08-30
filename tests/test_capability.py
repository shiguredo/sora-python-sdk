import time

from client import SoraClient, SoraRole

from sora_sdk import (
    SoraVideoCodecImplementation,
    SoraVideoCodecPreference,
    SoraVideoCodecType,
)

# def test_preference_invalid(settings):
#     # opneh264 のパスを設定してないのに H264 エンコーダを使おうとしているので Sora 生成時にエラーになる
#     with pytest.raises(RuntimeError):
#         SoraClient(
#             settings,
#             SoraRole.SENDONLY,
#             audio=False,
#             video=True,
#             video_codec_type="H264",
#             video_codec_preference=SoraVideoCodecPreference(
#                 codecs=[
#                     SoraVideoCodecPreference.Codec(
#                         type=SoraVideoCodecType.H264,
#                         encoder=SoraVideoCodecImplementation.CISCO_OPENH264,
#                     )
#                 ]
#             ),
#         )


def test_preference_vp8(settings):
    sendonly = SoraClient(
        settings,
        SoraRole.SENDONLY,
        audio=False,
        video=True,
        video_codec_type="VP8",
        video_codec_preference=SoraVideoCodecPreference(
            codecs=[
                SoraVideoCodecPreference.Codec(
                    type=SoraVideoCodecType.VP8, encoder=SoraVideoCodecImplementation.INTERNAL
                )
            ]
        ),
    )
    sendonly.connect(fake_video=True)

    time.sleep(5)

    sendonly.disconnect()
