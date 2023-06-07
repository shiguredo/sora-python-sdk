# Sora のデータチャネル機能を使ってメッセージを受信するサンプルスクリプト。
#
# コマンドライン引数で指定されたチャネルおよびラベルに届いたメッセージを標準出力に表示する。
#
# 実行例:
# $ rye run python test/messaging_recvonly.py --signaling-url ws://localhost:5000/signaling --channel-id sora --labels '#foo' '#bar'
import argparse
import json
import signal
import time

from sora_sdk import Sora


class MessagingRecvonly:
    def __init__(self, signaling_url, channel_id, client_id, labels, metadata):
        self.sora = Sora()
        self.connection = self.sora.create_connection(
            signaling_url=signaling_url,
            role="sendrecv",
            channel_id=channel_id,
            client_id=client_id,
            metadata=metadata,
            audio=False,
            video=False,
            data_channels=[{"label": label, "direction": "recvonly"}
                           for label in labels],
            data_channel_signaling=True,
        )

        self.disconnected = False
        self.shutdown = False
        self.connection.on_message = self.on_message
        self.connection.on_disconnect = self.on_disconnect

    def on_disconnect(self, ec, message):
        print(f"Sora から切断されました: message='{message}'")
        self.disconnected = True

    def on_message(self, label, data):
        print(f"メッセージを受信しました: label={label}, data={data}")

    def exit_gracefully(self, signal_number, frame):
        print("\nCtrl+Cが押されました。終了します")
        self.shutdown = True

    def run(self):
        # シグナルを登録し、プログラムが終了するときに正常に処理が行われるようにする
        signal.signal(signal.SIGINT, self.exit_gracefully)

        # Sora に接続する
        self.connection.connect()

        # Ctrl+C が押される or 切断されるまでメッセージ受信を待機
        while not self.shutdown and not self.disconnected:
            time.sleep(0.01)

        # Sora から切断する
        if not self.disconnected:
            self.connection.disconnect()

            # 切断が完了するまで待機
            while not self.disconnected:
                time.sleep(0.01)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    # 必須引数
    parser.add_argument("--signaling-url", required=True, help="シグナリング URL")
    parser.add_argument("--channel-id", required=True, help="チャネルID")
    parser.add_argument("--labels", required=True, nargs='+',
                        help="受信するデータチャネルのラベル名（複数指定可能）")

    # オプション引数
    parser.add_argument("--client_id", default='',  help="クライアントID")
    parser.add_argument("--metadata", help="メタデータ JSON")
    args = parser.parse_args()

    metadata = None
    if args.metadata:
        metadata = json.loads(args.metadata)

    messaging_recvonly = MessagingRecvonly(args.signaling_url,
                                           args.channel_id,
                                           args.client_id,
                                           args.labels,
                                           metadata)
    messaging_recvonly.run()
