import json
import os
import time

from dotenv import load_dotenv

from messaging import Messaging


def recvonly():
    # .env ファイルを読み込む
    load_dotenv()

    # 必須引数
    signaling_urls = os.getenv("SORA_SIGNALING_URLS").split(",")
    channel_id = os.getenv("SORA_CHANNEL_ID")
    messaging_label = os.getenv("SORA_MESSAGING_LABEL")

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
