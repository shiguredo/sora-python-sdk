import json
import os

from dotenv import load_dotenv
from media import Sendonly


def sendonly() -> None:
    """
    環境変数を使用して Sendonly インスタンスを設定し実行します。

    :raises ValueError: 必要な環境変数が設定されていない場合
    """
    load_dotenv()

    if not (raw_signaling_urls := os.getenv("SORA_SIGNALING_URLS")):
        raise ValueError("環境変数 SORA_SIGNALING_URLS が設定されていません")
    signaling_urls = raw_signaling_urls.split(",")

    if not (channel_id := os.getenv("SORA_CHANNEL_ID")):
        raise ValueError("環境変数 SORA_CHANNEL_ID が設定されていません")

    metadata = None
    if raw_metadata := os.getenv("SORA_METADATA"):
        metadata = json.loads(raw_metadata)

    video_codec_type = os.getenv("SORA_VIDEO_CODEC_TYPE", "VP9")
    video_bit_rate = int(os.getenv("SORA_VIDEO_BIT_RATE", "500"))
    video_width = int(os.getenv("SORA_VIDEO_WIDTH", "640"))
    video_height = int(os.getenv("SORA_VIDEO_HEIGHT", "360"))
    video_fps = int(os.getenv("SORA_VIDEO_FPS", "30"))
    video_fourcc = os.getenv("SORA_VIDEO_FOURCC", "MJPG")

    camera_id = int(os.getenv("SORA_CAMERA_ID", "0"))

    openh264_path = os.getenv("OPENH264_PATH")

    use_hwa = bool(os.getenv("USE_HWA", "True"))

    sendonly = Sendonly(
        signaling_urls,
        channel_id,
        metadata=metadata,
        video_codec_type=video_codec_type,
        video_bit_rate=video_bit_rate,
        video_width=video_width,
        video_height=video_height,
        video_fps=video_fps,
        video_fourcc=video_fourcc,
        openh264_path=openh264_path,
        camera_id=camera_id,
        use_hwa=use_hwa,
    )
    sendonly.run()


if __name__ == "__main__":
    sendonly()
