import json
import os

from dotenv import load_dotenv

from messaging import Messaging


def sendonly():
    # .env ファイルを読み込む
    load_dotenv()

    # 必須引数
    signaling_urls = os.getenv("SORA_SIGNALING_URLS").split(",")
    channel_id = os.getenv("SORA_CHANNEL_ID")
    messaging_label = os.getenv("SORA_MESSAGING_LABEL", "#example")

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
