import os

# import sys
# import time
# import uuid
import pytest

# from client import SoraClient, SoraRole
#
# from sora_sdk import (
#     SoraVideoCodecImplementation,
#     SoraVideoCodecPreference,
#     SoraVideoCodecType,
#     get_video_codec_capability,
# )


@pytest.mark.skipif(os.environ.get("AMD_AMF") is None, reason="AMD AMF でのみ実行する")
def test_amd_amf_check(setup):
    pass


# @pytest.mark.skipif(os.environ.get("AMD_AMF") is None, reason="AMD AMF でのみ実行する")
# def test_amd_vcn_available(setup):
#     capability = get_video_codec_capability()
#
#     intel_vpl_available = False
#     for e in capability.engines:
#         if e.name == SoraVideoCodecImplementation.AMD_AMF:
#             intel_vpl_available = True
#
#     assert intel_vpl_available is True
#
#     for e in capability.engines:
#         if e.name == SoraVideoCodecImplementation.AMD_AMF:
#             # 対応コーデックは 5 種類
#             assert len(e.codecs) == 5
#
#             for c in e.codecs:
#                 match c.type:
#                     case SoraVideoCodecType.VP8:
#                         assert c.decoder is False
#                         assert c.encoder is False
#                     case SoraVideoCodecType.VP9:
#                         assert c.decoder is True
#                         assert c.encoder is True
#                     case SoraVideoCodecType.AV1:
#                         assert c.decoder is True
#                         assert c.encoder is True
#                     case SoraVideoCodecType.H264:
#                         assert c.decoder is True
#                         assert c.encoder is True
#                     case SoraVideoCodecType.H265:
#                         assert c.decoder is True
#                         assert c.encoder is True
#                     case _:
#                         pytest.fail(f"未実装の codec_type: {c.type}")
#
#
# @pytest.mark.skipif(os.environ.get("AMD_AMF") is None, reason="AMD AMF でのみ実行する")
# @pytest.mark.parametrize(
#     (
#         "video_codec_type",
#         "preference_codec_type",
#         "expected_codec_implementation",
#         "preference_codec_implementation",
#     ),
#     [
#         ("VP9", SoraVideoCodecType.VP9, "amd_amf", SoraVideoCodecImplementation.AMD_AMF),
#         ("AV1", SoraVideoCodecType.AV1, "amd_amf", SoraVideoCodecImplementation.AMD_AMF),
#         ("H264", SoraVideoCodecType.H264, "amd_amf", SoraVideoCodecImplementation.AMD_AMF),
#         ("H265", SoraVideoCodecType.H265, "amd_amf", SoraVideoCodecImplementation.AMD_AMF),
#     ],
# )
# def test_intel_vpl_sendonly(
#     setup,
#     video_codec_type,
#     preference_codec_type,
#     expected_codec_implementation,
#     preference_codec_implementation,
# ):
#     signaling_urls = setup.get("signaling_urls")
#     channel_id_prefix = setup.get("channel_id_prefix")
#     metadata = setup.get("metadata")
#
#     channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"
#
#     sendonly = SoraClient(
#         signaling_urls,
#         SoraRole.SENDONLY,
#         channel_id,
#         audio=False,
#         video=True,
#         video_codec_type=video_codec_type,
#         metadata=metadata,
#         video_codec_preference=SoraVideoCodecPreference(
#             codecs=[
#                 SoraVideoCodecPreference.Codec(
#                     type=preference_codec_type,
#                     encoder=preference_codec_implementation,
#                 ),
#             ]
#         ),
#     )
#     sendonly.connect(fake_video=True)
#
#     time.sleep(5)
#
#     assert sendonly.connect_message is not None
#     assert sendonly.connect_message["channel_id"] == channel_id
#     assert "video" in sendonly.connect_message
#     assert sendonly.connect_message["video"]["codec_type"] == video_codec_type
#
#     # offer の sdp に video_codec_type が含まれているかどうかを確認している
#     assert sendonly.offer_message is not None
#     assert "sdp" in sendonly.offer_message
#     assert video_codec_type in sendonly.offer_message["sdp"]
#
#     # answer の sdp に video_codec_type が含まれているかどうかを確認している
#     assert sendonly.answer_message is not None
#     assert "sdp" in sendonly.answer_message
#     assert video_codec_type in sendonly.answer_message["sdp"]
#
#     sendonly_stats = sendonly.get_stats()
#
#     sendonly.disconnect()
#
#     # codec が無かったら StopIteration 例外が上がる
#     codec_stats = next(s for s in sendonly_stats if s.get("type") == "codec")
#     # H.264 が採用されているかどうか確認する
#     assert codec_stats["mimeType"] == f"video/{video_codec_type}"
#
#     # outbound-rtp が無かったら StopIteration 例外が上がる
#     outbound_rtp_stats = next(s for s in sendonly_stats if s.get("type") == "outbound-rtp")
#     assert outbound_rtp_stats["encoderImplementation"] == expected_codec_implementation
#     assert outbound_rtp_stats["bytesSent"] > 0
#     assert outbound_rtp_stats["packetsSent"] > 0
#
