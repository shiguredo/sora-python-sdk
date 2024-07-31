import json
import threading
import time
from threading import Event
from typing import Any, Optional

import numpy as np
from sora_sdk import Sora, SoraConnection, SoraMediaTrack, SoraVideoSource


class Sendonly:
    def __init__(
        self,
        signaling_urls: list[str],
        channel_id: str,
        metadata: dict,
        audio: bool = False,
        video: bool = True,
        audio_codec_type: str = "OPUS",
        video_codec_type: str = "VP8",
        data_channel_signaling: bool = True,
        openh264_path: Optional[str] = None,
    ):
        self._signaling_urls: list[str] = signaling_urls
        self._channel_id: str = channel_id

        self._connection_id: str

        # 接続した
        self._connected: Event = Event()
        # DataChannel へ切り替わった
        self._switched: bool = False
        # 終了
        self._closed: bool = False

        self._video_height: int = 480
        self._video_width: int = 640

        self._sora: Sora = Sora(openh264=openh264_path)
        self._connected = Event()

        self._video_source: SoraVideoSource = self._sora.create_video_source()

        self._connection: SoraConnection = self._sora.create_connection(
            signaling_urls=signaling_urls,
            role="sendonly",
            channel_id=channel_id,
            metadata=metadata,
            audio=False,
            video=True,
            video_codec_type=video_codec_type,
            video_source=self._video_source,
            data_channel_signaling=data_channel_signaling,
        )

        self._connection.on_set_offer = self._on_set_offer

        if data_channel_signaling:
            self._connection.on_switched = self._on_switched
        self._connection.on_notify = self._on_notify
        self._connection.on_disconnect = self._on_disconnect

    def connect(self):
        self._connection.connect()

        self._video_input_thread = threading.Thread(target=self._video_input_loop, daemon=True)
        self._video_input_thread.start()

        # _connected が set されるまで 30 秒待つ
        assert self._connected.wait(30)

        return self

    @property
    def connected(self):
        return self._connected.is_set()

    @property
    def switched(self):
        return self._switched

    def _video_input_loop(self):
        while not self._closed:
            time.sleep(1.0 / 30)
            self._video_source.on_captured(
                np.zeros((self._video_height, self._video_width, 3), dtype=np.uint8)
            )

    def _on_set_offer(self, raw_offer):
        offer = json.loads(raw_offer)
        if offer["type"] == "offer":
            self._connection_id = offer["connection_id"]
            print(f"Offer を受信しました: connection_id={self._connection_id}")

    def _on_switched(self, raw_message):
        message = json.loads(raw_message)
        if message["type"] == "switched":
            self._switched = True

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

    def get_stats(self):
        raw_stats = self._connection.get_stats()
        stats = json.loads(raw_stats)
        return stats


class Recvonly:
    def __init__(
        self,
        signaling_urls: list[str],
        channel_id: str,
        metadata: dict[str, Any],
        data_channel_signaling: bool = True,
        openh264_path: Optional[str] = None,
    ):
        self._signaling_urls: list[str] = signaling_urls
        self._channel_id: str = channel_id

        self._connection_id: str

        # 接続した
        self._connected = Event()
        # 終了
        self._closed = False

        self._sora: Sora = Sora()
        self._connection: SoraConnection = self._sora.create_connection(
            signaling_urls=signaling_urls,
            role="sendrecv",
            channel_id=channel_id,
            metadata=metadata,
        )

        self._connection.on_set_offer = self._on_set_offer
        if data_channel_signaling:
            self._connection.on_switched = self._on_switched
        self._connection.on_notify = self._on_notify
        self._connection.on_disconnect = self._on_disconnect

        self._connection.on_track = self._on_track

    def connect(self):
        self._connection.connect()

        # _connected が set されるまで 30 秒待つ
        assert self._connected.wait(30)

        return self

    @property
    def connected(self):
        return self._connected.is_set()

    def _on_track(self, track: SoraMediaTrack):
        if track.kind == "audio":
            pass
        if track.kind == "video":
            pass

    def _on_set_offer(self, raw_offer: str):
        offer = json.loads(raw_offer)
        if offer["type"] == "offer":
            self._connection_id = offer["connection_id"]

    def _on_switched(self, raw_message):
        message = json.loads(raw_message)
        if message["type"] == "switched":
            self._switched = True

    def _on_notify(self, raw_message: str):
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
