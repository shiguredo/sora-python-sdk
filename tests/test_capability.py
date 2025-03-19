import sys
import time
import uuid

import pytest
from client import SoraClient, SoraRole

from sora_sdk import (
    SoraVideoCodecImplementation,
    SoraVideoCodecPreference,
    SoraVideoCodecType,
    create_video_codec_preference_from_implementation,
    get_video_codec_capability,
)


def test_capability(setup):
    openh264_path = setup.get("openh264_path")
    capability = get_video_codec_capability(openh264=openh264_path)
    has_internal = False
    has_openh264 = False
    for engine in capability.engines:
        if engine.name == SoraVideoCodecImplementation.INTERNAL:
            has_internal = True
        if engine.name == SoraVideoCodecImplementation.CISCO_OPENH264:
            has_openh264 = True
    assert has_internal and has_openh264


def test_preference(setup):
    openh264_path = setup.get("openh264_path")
    capability = get_video_codec_capability(openh264=openh264_path)
    preference = create_video_codec_preference_from_implementation(
        capability, SoraVideoCodecImplementation.CISCO_OPENH264
    )
    assert preference.has_implementation(SoraVideoCodecImplementation.CISCO_OPENH264)


def test_preference_invalid(setup):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    # opneh264 のパスを設定してないのに H264 エンコーダを使おうとしているので Sora 生成時にエラーになる
    with pytest.raises(RuntimeError):
        SoraClient(
            signaling_urls,
            SoraRole.SENDONLY,
            channel_id,
            metadata=metadata,
            audio=False,
            video=True,
            video_codec_type="H264",
            video_codec_preference=SoraVideoCodecPreference(
                codecs=[
                    SoraVideoCodecPreference.Codec(
                        type=SoraVideoCodecType.H264,
                        encoder=SoraVideoCodecImplementation.CISCO_OPENH264,
                    )
                ]
            ),
        )


def test_preference_vp8(setup):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    channel_id = f"{channel_id_prefix}_{__name__}_{sys._getframe().f_code.co_name}_{uuid.uuid4()}"

    sendonly = SoraClient(
        signaling_urls,
        SoraRole.SENDONLY,
        channel_id,
        metadata=metadata,
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
