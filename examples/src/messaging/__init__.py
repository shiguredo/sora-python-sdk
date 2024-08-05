import json
import random
import time
from threading import Event
from typing import Any, Optional

from sora_sdk import Sora, SoraConnection, SoraSignalingErrorCode


class Messaging:
    """Sora を使用してメッセージングを行うクラス。"""

    def __init__(
        self,
        signaling_urls: list[str],
        channel_id: str,
        data_channels: list[dict[str, Any]],
        metadata: Optional[dict[str, Any]],
    ):
        """
        Messaging インスタンスを初期化します。

        このクラスは Sora への接続を設定し、データチャネルを通じてメッセージの
        送受信を行うメソッドを提供します。

        :param signaling_urls: Sora シグナリング URL のリスト
        :param channel_id: 接続するチャンネル ID
        :param data_channels: データチャネルの設定リスト
        :param metadata: 接続のためのオプションのメタデータ
        """
        self._data_channels = data_channels

        self._sora = Sora()
        self._connection: SoraConnection = self._sora.create_connection(
            signaling_urls=signaling_urls,
            role="sendrecv",
            channel_id=channel_id,
            metadata=metadata,
            audio=False,
            video=False,
            data_channels=self._data_channels,
            data_channel_signaling=True,
        )
        self._connection_id: Optional[str] = None

        self._connected = Event()
        self._closed = False
        self._label = data_channels[0]["label"]
        self._sendable_data_channels: set = set()
        self._is_data_channel_ready = False

        self.sender_id = random.randint(1, 10000)

        self._connection.on_set_offer = self._on_set_offer
        self._connection.on_notify = self._on_notify
        self._connection.on_data_channel = self._on_data_channel
        self._connection.on_message = self._on_message
        self._connection.on_disconnect = self._on_disconnect

    @property
    def closed(self):
        """接続が閉じられているかどうかを示すブール値。"""
        return self._closed

    def connect(self):
        """
        Sora への接続を確立します。

        :raises AssertionError: タイムアウト期間内に接続が確立できなかった場合
        """
        self._connection.connect()

        assert self._connected.wait(10), "接続に失敗しました"

    def disconnect(self):
        """Sora から切断します。"""
        self._connection.disconnect()

    def send(self, data: bytes):
        """
        データチャネルを通じてメッセージを送信します。

        :param data: 送信するバイトデータ
        """
        # on_data_channel() が呼ばれるまではデータチャネルの準備ができていないので待機
        while not self._is_data_channel_ready and not self._closed:
            time.sleep(0.01)

        self._connection.send_data_channel(self._label, data)

    def _on_set_offer(self, raw_message: str):
        """
        オファー設定イベントを処理します。

        :param raw_message: オファーを含む生のメッセージ
        """
        message: dict[str, Any] = json.loads(raw_message)
        if message["type"] == "offer":
            # "type": "offer" に入ってくる自分の connection_id を保存する
            self._connection_id = message["connection_id"]

    def _on_notify(self, raw_message: str):
        """
        Sora からの通知イベントを処理します。

        :param raw_message: 生の通知メッセージ
        """
        message: dict[str, Any] = json.loads(raw_message)
        # "type": "notify" の "connection.created" で通知される connection_id が
        # 自分の connection_id と一致する場合に接続完了とする
        if (
            message["type"] == "notify"
            and message["event_type"] == "connection.created"
            and message["connection_id"] == self._connection_id
        ):
            print("Sora に接続しました")
            self._connected.set()

    def _on_disconnect(self, error_code: SoraSignalingErrorCode, message: str):
        """
        切断イベントを処理します。

        :param error_code: 切断のエラーコード
        :param message: 切断メッセージ
        """
        print(f"Sora から切断されました: error_code='{error_code}' message='{message}'")
        self._connected.clear()
        self._closed = True

    def _on_message(self, label: str, data: bytes):
        """
        受信したメッセージを処理します。

        :param label: データチャネルのラベル
        :param data: 受信したバイトデータ
        """
        print(f"メッセージを受信しました: label={label}, data={data.decode('utf-8')}")

    def _on_data_channel(self, label: str):
        """
        新しいデータチャネルイベントを処理します。

        :param label: データチャネルのラベル
        """
        for data_channel in self._data_channels:
            if data_channel["label"] != label:
                continue

            if data_channel["direction"] in ["sendrecv", "sendonly"]:
                self._sendable_data_channels.add(label)
                # データチャネルの準備ができたのでフラグを立てる
                self._is_data_channel_ready = True
                break
