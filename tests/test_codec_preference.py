import sys

from sora_sdk import (
    Sora,
    SoraVideoCodecImplementation,
    SoraVideoCodecPreference,
    SoraVideoCodecType,
    get_video_codec_capability,
)


# このテストでは Linux では NVIDIA Video Codec SDK > Intel VPL > OpenH264 の順で優先される
# このテストでは Windows では NVIDIA Video Codec SDK > Intel VPL の順で優先される
# このテストでは macOS では Video Toolbox >OpenH264 の順で優先される
def test_get_codec_capability(setup):
    openh264_path = setup.get("openh264_path")
    capability = get_video_codec_capability(openh264_path)

    intel_vpl_available = False
    cisco_openh264_available = False
    nvidia_video_codec_sdk_available = False

    for e in capability.engines:
        if e.name == SoraVideoCodecImplementation.INTEL_VPL:
            intel_vpl_available = True
        if e.name == SoraVideoCodecImplementation.CISCO_OPENH264:
            cisco_openh264_available = True
        if e.name == SoraVideoCodecImplementation.NVIDIA_VIDEO_CODEC_SDK:
            nvidia_video_codec_sdk_available = True

    match sys.platform:
        case "linux":
            assert openh264_path is not None
            assert cisco_openh264_available is True
        case "darwin":
            assert openh264_path is not None
            assert cisco_openh264_available is True
        case "win32":
            # SDK 的には Windows は非対応だが GitHub Actions の E2E テストの OpenH264 のパスは指定してある
            assert openh264_path is not None
            assert cisco_openh264_available is True

    codecs = []
    for e in capability.engines:
        if sys.platform == "linux":
            # Intel VPL があったら Open H.264 は採用しない
            if intel_vpl_available and e.name == SoraVideoCodecImplementation.CISCO_OPENH264:
                continue

            # NVIDIA Video Codec SDK があったら Intel VPL は採用しない
            if (
                nvidia_video_codec_sdk_available
                and e.name == SoraVideoCodecImplementation.INTEL_VPL
            ):
                continue

            # NVIDIA Video Codec SDK があったら OpenH264 は採用しない
            if (
                nvidia_video_codec_sdk_available
                and e.name == SoraVideoCodecImplementation.CISCO_OPENH264
            ):
                continue

        # macOS では INTERNAL の Video Toolbox が利用されるので OpenH264 は採用しないようにする
        if sys.platform == "darwin":
            if e.name == SoraVideoCodecImplementation.CISCO_OPENH264:
                continue

        for c in e.codecs:
            if c.decoder or c.encoder:
                # encoder/decoder どちらかが true であれば採用する
                if c.decoder or c.encoder:
                    codecs.append(
                        SoraVideoCodecPreference.Codec(
                            type=c.type,
                            decoder=e.name,
                            encoder=e.name,
                        )
                    )

        # print(e.parameters.nvcodec_gpu_device_name)
        # print(e.parameters.openh264_path)
        # print(e.parameters.version)
        # print(e.parameters.vpl_impl)
        # print(e.parameters.vpl_impl_value)

    Sora(
        video_codec_preference=SoraVideoCodecPreference(
            codecs=codecs,
        ),
        openh264=openh264_path,
    )


def test_video_codec_preference(setup):
    openh264_path = setup.get("openh264_path")
    Sora(
        video_codec_preference=SoraVideoCodecPreference(
            codecs=[
                SoraVideoCodecPreference.Codec(
                    type=SoraVideoCodecType.VP8,
                    decoder=SoraVideoCodecImplementation.INTERNAL,
                    encoder=SoraVideoCodecImplementation.INTERNAL,
                ),
                SoraVideoCodecPreference.Codec(
                    type=SoraVideoCodecType.VP9,
                    decoder=SoraVideoCodecImplementation.INTERNAL,
                    encoder=SoraVideoCodecImplementation.INTERNAL,
                ),
                SoraVideoCodecPreference.Codec(
                    type=SoraVideoCodecType.AV1,
                    decoder=SoraVideoCodecImplementation.INTERNAL,
                    encoder=SoraVideoCodecImplementation.INTERNAL,
                ),
                # H.264 だけは OpenH264 を利用するようにする
                SoraVideoCodecPreference.Codec(
                    type=SoraVideoCodecType.H264,
                    decoder=SoraVideoCodecImplementation.CISCO_OPENH264,
                    encoder=SoraVideoCodecImplementation.CISCO_OPENH264,
                ),
            ],
        ),
        openh264=openh264_path,
    )
