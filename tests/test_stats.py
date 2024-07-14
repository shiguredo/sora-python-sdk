import json
import threading
import time
from threading import Event
from typing import List

import numpy as np
from sora_sdk import Sora, SoraConnection, SoraVideoSource


class GetStats:
    def __init__(self, signaling_urls: List[str], channel_id: str, metadata: dict):
        self._signaling_urls: List[str] = signaling_urls
        self._channel_id: str = channel_id

        self._connection_id: str

        # 接続した
        self._connected: Event = Event()
        # 終了
        self._closed: bool = False

        self._video_height: int = 480
        self._video_width: int = 640

        self._sora: Sora = Sora()
        self._connected = Event()

        self._video_source: SoraVideoSource = self._sora.create_video_source()

        self._connection: SoraConnection = self._sora.create_connection(
            signaling_urls=signaling_urls,
            role="sendonly",
            channel_id=channel_id,
            metadata=metadata,
            audio=False,
            video=True,
            video_source=self._video_source,
        )

        self._connection.on_set_offer = self._on_set_offer
        self._connection.on_notify = self._on_notify
        self._connection.on_disconnect = self._on_disconnect

    def connect(self):
        self._connection.connect()

        self._video_input_thread = threading.Thread(target=self._video_input_loop, daemon=True)
        self._video_input_thread.start()

        # _connected が set されるまで 30 秒待つ
        assert self._connected.wait(30)

        self._stats_thread = threading.Thread(target=self._stats_loop, daemon=True)
        self._stats_thread.start()

        return self

    def _video_input_loop(self):
        while not self._closed:
            time.sleep(1.0 / 30)
            self._video_source.on_captured(
                np.zeros((self._video_height, self._video_width, 3), dtype=np.uint8)
            )

    def _stats_loop(self):
        while not self._closed:
            raw_stats = self._connection.get_stats()
            stats = json.loads(raw_stats)
            # stats が list かつ len が 1 以上である事を確認する
            assert isinstance(stats, list)
            assert len(stats) > 0
            time.sleep(5)

    def _on_set_offer(self, raw_offer):
        offer = json.loads(raw_offer)
        if offer["type"] == "offer":
            self._connection_id = offer["connection_id"]
            print(f"Offer を受信しました: connection_id={self._connection_id}")

    def _on_notify(self, raw_message):
        message = json.loads(raw_message)
        if (
            message["type"] == "notify"
            and message["event_type"] == "connection.created"
            and message["connection_id"] == self._connection_id
        ):
            print(f"Sora に接続しました: connection_id={self._connection_id}")
            self._connected.set()

    def _on_disconnect(self, error_code, message):
        print(f"Sora から切断しました: error_code='{error_code}' message='{message}'")
        self._closed = True
        self._connected.clear()

    def disconnect(self):
        self._connection.disconnect()
        # タイムアウト指定
        self._video_input_thread.join(timeout=10)
        # タイムアウト指定
        self._stats_thread.join(timeout=10)


def test_get_stats(setup):
    signaling_urls = setup.get("signaling_urls")
    channel_id_prefix = setup.get("channel_id_prefix")
    metadata = setup.get("metadata")

    channel_id = f"{channel_id_prefix}_{__name__}"

    client = GetStats(signaling_urls, channel_id, metadata)
    client.connect()

    time.sleep(5)

    client.disconnect()
