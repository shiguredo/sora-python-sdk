import json
import os

from dotenv import load_dotenv
from media import Recvonly


def recvonly() -> None:
    """
    環境変数を使用して Recvonly インスタンスを設定し実行します。

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

    openh264_path = os.getenv("OPENH264_PATH")

    use_hwa = bool(os.getenv("USE_HWA", "True"))

    recvonly = Recvonly(
        signaling_urls, channel_id, metadata=metadata, openh264_path=openh264_path, use_hwa=use_hwa
    )
    recvonly.run()


if __name__ == "__main__":
    recvonly()
