import json
import os

from dotenv import load_dotenv

from messaging import Messaging


def sendonly():
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

    data_channels = [{"label": messaging_label, "direction": "sendonly"}]
    messaging_sendonly = Messaging(signaling_urls, channel_id, data_channels, metadata)

    # Sora に接続する
    messaging_sendonly.connect()
    try:
        while not messaging_sendonly.closed:
            # input で入力された文字列を utf-8 でエンコードして送信
            message = input("Enter キーを押すと送信します: ")
            messaging_sendonly.send(message.encode("utf-8"))
    except KeyboardInterrupt:
        pass
    finally:
        messaging_sendonly.disconnect()


if __name__ == "__main__":
    sendonly()
