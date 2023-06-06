import argparse
import json
import signal
import time

from sora_sdk import Sora, SoraAudioSink, SoraVideoSink


class MessagingRecvonly:
    def __init__(self, signaling_url, channel_id, client_id,
                 labels, data_channel_signaling, ignore_disconnect_websocket,
                 metadata):
        self.sora = Sora()
        self.connection = self.sora.create_connection(
            signaling_url=signaling_url,
            role="recvonly",
            channel_id=channel_id,
            client_id=client_id,
            data_channels=[{"label": label, "direction": "recvonly"}
                           for label in labels],
            data_channel_signaling=data_channel_signaling,
            ignore_disconnect_websocket=ignore_disconnect_websocket,
            metadata=metadata,
        )

        self.disconnected = False
        self.connection.on_message = self.on_message

    def on_disconnect(self, ec, message):
        self.disconnected = True

    def on_message(self, label, data):
        print(f"メッセージを受信しました: label={label}, data={data}")

    def exit_gracefully(self, signal_number, frame):
        print("\nCtrl+Cが押されました。終了します")
        self.connection.disconnect()
        cv2.destroyAllWindows()
        exit(0)

    def run(self):
        # シグナルを登録し、プログラムが終了するときに正常に処理が行われるようにする
        signal.signal(signal.SIGINT, self.exit_gracefully)

        self.connection.connect()

        while True:
            time.sleep(0.01)

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
    parser.add_argument("--client_id",default='',  help="クライアントID")
    parser.add_argument("--metadata", help="メタデータ JSON")
    parser.add_argument("--data-channel-signaling",
                        action="store_true", help="データチャネルを使ったシグナリングを有効にする")
    parser.add_argument("--ignore-disconnect-websocket",
                        action="store_true", help="WebSocket の切断を無視する")
    args = parser.parse_args()

    metadata = None
    if args.metadata:
        metadata = json.loads(args.metadata)

    messaging_recvonly = MessagingRecvonly(args.signaling_url,
                                           args.channel_id,
                                           args.client_id,
                                           args.labels,
                                           args.data_channel_signaling,
                                           args.ignore_disconnect_websocket,
                                           metadata)
    messaging_recvonly.run()
