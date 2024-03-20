import json
import os
import time

from dotenv import load_dotenv

from messaging import Messaging


def recvonly():
    # .env ファイルを読み込む
    load_dotenv()

    # 必須引数
    if not (raw_signaling_urls := os.getenv("SORA_SIGNALING_URLS")):
        raise ValueError("環境変数 SORA_SIGNALING_URLS が設定されていません")
    signaling_urls = raw_signaling_urls.split(",")

    if not (channel_id := os.getenv("SORA_CHANNEL_ID")):
        raise ValueError("環境変数 SORA_CHANNEL_ID が設定されていません")

    if not (messaging_label := os.getenv("SORA_MESSAGING_LABEL")):
        raise ValueError("環境変数 SORA_MESSAGING_LABEL が設定されていません")

    # オプション引数
    metadata = None
    if raw_metadata := os.getenv("SORA_METADATA"):
        metadata = json.loads(raw_metadata)

    data_channels = [{"label": messaging_label, "direction": "recvonly"}]
    messaging_recvonly = Messaging(
        signaling_urls,
        channel_id,
        data_channels,
        metadata,
    )

    # Sora に接続する
    messaging_recvonly.connect()
    try:
        # Ctrl+C が押される or 切断されるまでメッセージ受信を待機
        while not messaging_recvonly.closed:
            time.sleep(0.01)
    except KeyboardInterrupt:
        pass
    finally:
        # Sora から切断する（すでに切断済みの場合には無視される）
        messaging_recvonly.disconnect()


if __name__ == "__main__":
    recvonly()
