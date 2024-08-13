import json
import os
import platform

import cv2
from dotenv import load_dotenv
from media import Sendonly


def get_video_capture(
    camera_id: int,
    video_width: int,
    video_height: int,
    video_fps: int,
    video_fourcc: str,
) -> cv2.VideoCapture:
    """
    ビデオキャプチャの設定を行います。

    :param camera_id: 使用するカメラの ID
    :param video_width: ビデオの幅
    :param video_height: ビデオの高さ
    :param video_fps: ビデオのフレームレート
    :param video_fourcc: ビデオの FOURCC コード
    """

    if platform.system() == "Windows":
        # CAP_DSHOW を設定しないと、カメラの起動がめちゃめちゃ遅くなる
        video_capture = cv2.VideoCapture(camera_id, cv2.CAP_DSHOW)
    else:
        video_capture = cv2.VideoCapture(camera_id)

    if video_width is not None:
        video_capture.set(cv2.CAP_PROP_FRAME_WIDTH, video_width)
    if video_height is not None:
        video_capture.set(cv2.CAP_PROP_FRAME_HEIGHT, video_height)
    if video_fourcc is not None:
        video_capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*video_fourcc))
    if video_fps is not None:
        video_capture.set(cv2.CAP_PROP_FPS, video_fps)

    # Ubuntu → FOURCC を設定すると FPS が初期化される
    # Windows → FPS を設定すると FOURCC が初期化される
    # ので、両方に対応するため２回設定する
    if video_fourcc is not None:
        fourcc = cv2.VideoWriter_fourcc(*video_fourcc)
        target_fourcc = video_capture.get(cv2.CAP_PROP_FOURCC)
        if fourcc != target_fourcc:
            video_capture.set(cv2.CAP_PROP_FOURCC, fourcc)
    if video_fps is not None:
        if video_fps != int(video_capture.get(cv2.CAP_PROP_FPS)):
            video_capture.set(cv2.CAP_PROP_FPS, video_fps)

    return video_capture


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

    video_capture = get_video_capture(
        camera_id=camera_id,
        video_width=video_width,
        video_height=video_height,
        video_fps=video_fps,
        video_fourcc=video_fourcc,
    )

    openh264_path = os.getenv("OPENH264_PATH")

    use_hwa = bool(os.getenv("USE_HWA", "True"))

    sendonly = Sendonly(
        signaling_urls,
        channel_id,
        metadata=metadata,
        video_codec_type=video_codec_type,
        video_bit_rate=video_bit_rate,
        openh264_path=openh264_path,
        use_hwa=use_hwa,
        video_capture=video_capture,
    )
    sendonly.run()


if __name__ == "__main__":
    sendonly()
