import json
import queue
import random
import threading
import time
from threading import Event
from typing import Any, Optional

import numpy

from sora_sdk import (
    Sora,
    SoraAudioSink,
    SoraConnection,
    SoraMediaTrack,
    SoraSignalingDirection,
    SoraSignalingErrorCode,
    SoraSignalingType,
    SoraVideoFrame,
    SoraVideoSink,
)


class Sendonly:
    def __init__(
        self,
        signaling_urls: list[str],
        channel_id: str,
        metadata: Optional[dict[str, Any]] = None,
        audio: Optional[bool] = None,
        video: Optional[bool] = None,
        video_codec_type: Optional[str] = None,
        video_bit_rate: Optional[int] = None,
        data_channel_signaling: Optional[bool] = None,
        openh264_path: Optional[str] = None,
        use_hwa: bool = False,
        audio_channels: int = 1,
        audio_sample_rate: int = 16000,
    ):
        self._signaling_urls: list[str] = signaling_urls
        self._channel_id: str = channel_id

        self._audio_channels: int = audio_channels
        self._audio_sample_rate: int = audio_sample_rate

        self._sora: Sora = Sora(openh264=openh264_path, use_hardware_encoder=use_hwa)

        self._fake_audio_thread: Optional[threading.Thread] = None
        self._fake_video_thread: Optional[threading.Thread] = None

        self._audio_source = self._sora.create_audio_source(
            self._audio_channels, self._audio_sample_rate
        )
        self._video_source = self._sora.create_video_source()

        self._connection: SoraConnection = self._sora.create_connection(
            signaling_urls=signaling_urls,
            role=self.role,
            channel_id=channel_id,
            metadata=metadata,
            audio=audio,
            video=video,
            video_codec_type=video_codec_type,
            video_bit_rate=video_bit_rate,
            data_channel_signaling=data_channel_signaling,
            audio_source=self._audio_source,
            video_source=self._video_source,
        )
        self._connection_id: Optional[str] = None

        self._connected: Event = Event()
        self._switched: bool = False
        self._closed: Event = Event()
        self._default_connection_timeout_s: float = 10.0

        # signaling message
        self._connect_message: Optional[dict[str, Any]] = None
        self._redirect_message: Optional[dict[str, Any]] = None
        self._offer_message: Optional[dict[str, Any]] = None
        self._answer_message: Optional[dict[str, Any]] = None
        self._candidate_messages: list[dict[str, Any]] = []
        self._re_offer_messages: list[dict[str, Any]] = []
        self._re_answer_messages: list[dict[str, Any]] = []

        # callback
        self._connection.on_signaling_message = self._on_signaling_message
        self._connection.on_set_offer = self._on_set_offer
        self._connection.on_switched = self._on_switched
        self._connection.on_notify = self._on_notify
        self._connection.on_disconnect = self._on_disconnect

    def connect(self, fake_audio=False, fake_video=False) -> None:
        self._connection.connect()

        if fake_audio:
            self._fake_audio_thread = threading.Thread(target=self._fake_audio_loop, daemon=True)
            self._fake_audio_thread.start()

        if fake_video:
            self._fake_video_thread = threading.Thread(target=self._fake_video_loop, daemon=True)
            self._fake_video_thread.start()

        assert self._connected.wait(
            self._default_connection_timeout_s
        ), "Could not connect to Sora."

    def disconnect(self) -> None:
        """Sora から切断します。"""
        self._connection.disconnect()

    def get_stats(self):
        raw_stats = self._connection.get_stats()
        return json.loads(raw_stats)

    @property
    def role(self) -> str:
        return "sendonly"

    @property
    def connect_message(self) -> Optional[dict[str, Any]]:
        return self._connect_message

    @property
    def redirect_message(self) -> Optional[dict[str, Any]]:
        return self._redirect_message

    @property
    def offer_message(self) -> Optional[dict[str, Any]]:
        return self._offer_message

    @property
    def answer_message(self) -> Optional[dict[str, Any]]:
        return self._answer_message

    @property
    def candidate_messages(self) -> list[dict[str, Any]]:
        return self._candidate_messages

    @property
    def re_offer_messages(self) -> list[dict[str, Any]]:
        return self._re_offer_messages

    @property
    def re_answer_messages(self) -> list[dict[str, Any]]:
        return self._re_answer_messages

    @property
    def connected(self) -> bool:
        return self._connected.is_set()

    @property
    def switched(self) -> bool:
        return self._switched

    def _fake_audio_loop(self):
        while not self._closed.is_set():
            time.sleep(0.02)
            self._audio_source.on_data(numpy.zeros((320, 1), dtype=numpy.int16))

    def _fake_video_loop(self):
        while not self._closed.is_set():
            time.sleep(1.0 / 30)
            self._video_source.on_captured(numpy.zeros((480, 640, 3), dtype=numpy.uint8))

    def _on_signaling_message(
        self,
        signaling_type: SoraSignalingType,
        signaling_direction: SoraSignalingDirection,
        raw_message: str,
    ):
        print(raw_message)
        message: dict[str, Any] = json.loads(raw_message)
        match message["type"]:
            case "connect":
                assert signaling_type == SoraSignalingType.WEBSOCKET
                assert signaling_direction == SoraSignalingDirection.SENT
                self._connect_message = message
            case "redirect":
                assert signaling_type == SoraSignalingType.WEBSOCKET
                assert signaling_direction == SoraSignalingDirection.RECEIVED
                self._redirect_message = message
            case "offer":
                assert signaling_type == SoraSignalingType.WEBSOCKET
                assert signaling_direction == SoraSignalingDirection.RECEIVED
                self._offer_message = message
            case "answer":
                assert signaling_type == SoraSignalingType.WEBSOCKET
                assert signaling_direction == SoraSignalingDirection.SENT
                self._answer_message = message
            case "candidate":
                self._candidate_messages.append(message)
            case "re-offer":
                assert signaling_direction == SoraSignalingDirection.SENT
                self._re_offer_messages.append(message)
            case "re-answer":
                assert signaling_direction == SoraSignalingDirection.RECEIVED
                self._re_answer_messages.append(message)
            case _:
                NotImplementedError(f"Unknown signaling message type: {message['type']}")

    def _on_set_offer(self, raw_message: str) -> None:
        message: dict[str, Any] = json.loads(raw_message)
        if message["type"] == "offer":
            self._connection_id = message["connection_id"]

    def _on_switched(self, raw_message: str) -> None:
        message = json.loads(raw_message)
        if message["type"] == "switched":
            print(f"Switched to DataChannel Signaling: connection_id={self._connection_id}")
            self._switched = True

    def _on_notify(self, raw_message: str) -> None:
        message: dict[str, Any] = json.loads(raw_message)
        if (
            message["type"] == "notify"
            and message["event_type"] == "connection.created"
            and message["connection_id"] == self._connection_id
        ):
            print(f"Connected Sora: connection_id={self._connection_id}")
            self._connected.set()

    def _on_disconnect(self, error_code: SoraSignalingErrorCode, message: str) -> None:
        print(f"Disconnected Sora: error_code='{error_code}' message='{message}'")
        self._connected.clear()
        self._closed.set()

        if self._fake_audio_thread is not None:
            self._fake_audio_thread.join(timeout=10)

        if self._fake_video_thread is not None:
            self._fake_video_thread.join(timeout=10)


class Recvonly:
    def __init__(
        self,
        signaling_urls: list[str],
        channel_id: str,
        metadata: Optional[dict[str, Any]] = None,
        data_channel_signaling: Optional[bool] = None,
        openh264_path: Optional[str] = None,
        use_hwa: Optional[bool] = False,
        output_frequency: int = 16000,
        output_channels: int = 1,
    ):
        self._signaling_urls: list[str] = signaling_urls
        self._channel_id: str = channel_id

        self._output_frequency: int = output_frequency
        self._output_channels: int = output_channels

        self._sora: Sora = Sora(openh264=openh264_path, use_hardware_encoder=use_hwa)
        self._connection: SoraConnection = self._sora.create_connection(
            signaling_urls=signaling_urls,
            role=self.role,
            channel_id=channel_id,
            metadata=metadata,
            data_channel_signaling=data_channel_signaling,
        )
        self._connection_id: Optional[str] = None

        self._connected: Event = Event()
        self._switched: bool = False
        self._closed: Event = Event()
        self._default_connection_timeout_s: float = 10.0

        self._audio_sink: Optional[SoraAudioSink] = None
        self._video_sink: Optional[SoraVideoSink] = None

        self._q_out: queue.Queue = queue.Queue()

        # signaling message
        self._connect_message: Optional[dict[str, Any]] = None
        self._redirect_message: Optional[dict[str, Any]] = None
        self._offer_message: Optional[dict[str, Any]] = None
        self._answer_message: Optional[dict[str, Any]] = None
        self._candidate_messages: list[dict[str, Any]] = []
        self._re_offer_messages: list[dict[str, Any]] = []
        self._re_answer_messages: list[dict[str, Any]] = []

        # callback
        self._connection.on_signaling_message = self._on_signaling_message
        self._connection.on_set_offer = self._on_set_offer
        self._connection.on_switched = self._on_switched
        self._connection.on_notify = self._on_notify
        self._connection.on_disconnect = self._on_disconnect
        self._connection.on_track = self._on_track

    def connect(self) -> None:
        self._connection.connect()

        assert self._connected.wait(
            self._default_connection_timeout_s
        ), "Could not connect to Sora."

    def disconnect(self) -> None:
        self._connection.disconnect()

    def get_stats(self):
        raw_stats = self._connection.get_stats()
        return json.loads(raw_stats)

    @property
    def role(self) -> str:
        return "recvonly"

    @property
    def connect_message(self) -> Optional[dict[str, Any]]:
        return self._connect_message

    @property
    def redirect_message(self) -> Optional[dict[str, Any]]:
        return self._redirect_message

    @property
    def offer_message(self) -> Optional[dict[str, Any]]:
        return self._offer_message

    @property
    def answer_message(self) -> Optional[dict[str, Any]]:
        return self._answer_message

    @property
    def candidate_messages(self) -> list[dict[str, Any]]:
        return self._candidate_messages

    @property
    def re_offer_messages(self) -> list[dict[str, Any]]:
        return self._re_offer_messages

    @property
    def re_answer_messages(self) -> list[dict[str, Any]]:
        return self._re_answer_messages

    @property
    def connected(self) -> bool:
        return self._connected.is_set()

    @property
    def switched(self) -> bool:
        return self._switched

    @property
    def closed(self):
        return self._closed.is_set()

    def _on_signaling_message(
        self,
        signaling_type: SoraSignalingType,
        signaling_direction: SoraSignalingDirection,
        raw_message: str,
    ):
        print(raw_message)
        message: dict[str, Any] = json.loads(raw_message)
        match message["type"]:
            case "connect":
                assert signaling_type == SoraSignalingType.WEBSOCKET
                assert signaling_direction == SoraSignalingDirection.SENT
                self._connect_message = message
            case "redirect":
                assert signaling_type == SoraSignalingType.WEBSOCKET
                assert signaling_direction == SoraSignalingDirection.RECEIVED
                self._redirect_message = message
            case "offer":
                assert signaling_type == SoraSignalingType.WEBSOCKET
                assert signaling_direction == SoraSignalingDirection.RECEIVED
                self._offer_message = message
            case "answer":
                assert signaling_type == SoraSignalingType.WEBSOCKET
                assert signaling_direction == SoraSignalingDirection.SENT
                self._answer_message = message
            case "candidate":
                self._candidate_messages.append(message)
            case "re-offer":
                assert signaling_direction == SoraSignalingDirection.RECEIVED
                self._re_offer_messages.append(message)
            case "re-answer":
                assert signaling_direction == SoraSignalingDirection.SENT
                self._re_answer_messages.append(message)
            case _:
                NotImplementedError(f"Unknown signaling message type: {message['type']}")

    def _on_set_offer(self, raw_message: str) -> None:
        message: dict[str, Any] = json.loads(raw_message)
        if message["type"] == "offer":
            self._connection_id = message["connection_id"]

    def _on_switched(self, raw_message: str) -> None:
        message = json.loads(raw_message)
        if message["type"] == "switched":
            print(f"Switched to DataChannel Signaling: connection_id={self._connection_id}")
            self._switched = True

    def _on_notify(self, raw_message: str) -> None:
        message: dict[str, Any] = json.loads(raw_message)
        if (
            message["type"] == "notify"
            and message["event_type"] == "connection.created"
            and message["connection_id"] == self._connection_id
        ):
            print(f"Connected Sora: connection_id={self._connection_id}")
            self._connected.set()

    def _on_disconnect(self, error_code: SoraSignalingErrorCode, message: str) -> None:
        print(f"Disconnected Sora: error_code='{error_code}' message='{message}'")
        self._connected.clear()
        self._closed.is_set()

    def _on_video_frame(self, frame: SoraVideoFrame) -> None:
        self._q_out.put(frame)

    def _on_track(self, track: SoraMediaTrack) -> None:
        if track.kind == "audio":
            self._audio_sink = SoraAudioSink(track, self._output_frequency, self._output_channels)
        if track.kind == "video":
            self._video_sink = SoraVideoSink(track)
            self._video_sink.on_frame = self._on_video_frame


class Messaging:
    def __init__(
        self,
        signaling_urls: list[str],
        channel_id: str,
        data_channels: list[dict[str, Any]],
        metadata: Optional[dict[str, Any]] = None,
    ):
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
        self._switched: bool = False
        self._closed = Event()
        self._default_connection_timeout_s: float = 10.0

        self._label = data_channels[0]["label"]
        self._sendable_data_channels: set = set()
        self._is_data_channel_ready = False

        self.sender_id = random.randint(1, 10000)

        # signaling message
        self._connect_message: Optional[dict[str, Any]] = None
        self._redirect_message: Optional[dict[str, Any]] = None
        self._offer_message: Optional[dict[str, Any]] = None
        self._answer_message: Optional[dict[str, Any]] = None
        self._candidate_messages: list[dict[str, Any]] = []
        self._re_offer_messages: list[dict[str, Any]] = []
        self._re_answer_messages: list[dict[str, Any]] = []

        # callback
        self._connection.on_signaling_message = self._on_signaling_message
        self._connection.on_set_offer = self._on_set_offer
        self._connection.on_switched = self._on_switched
        self._connection.on_notify = self._on_notify
        self._connection.on_data_channel = self._on_data_channel
        self._connection.on_message = self._on_message
        self._connection.on_disconnect = self._on_disconnect

    @property
    def closed(self):
        return self._closed.is_set()

    def connect(self):
        self._connection.connect()

        assert self._connected.wait(
            self._default_connection_timeout_s
        ), "Could not connect to Sora."

    def disconnect(self):
        self._connection.disconnect()

    def get_stats(self):
        raw_stats = self._connection.get_stats()
        stats = json.loads(raw_stats)
        return stats

    @property
    def connect_message(self) -> Optional[dict[str, Any]]:
        return self._connect_message

    @property
    def redirect_message(self) -> Optional[dict[str, Any]]:
        return self._redirect_message

    @property
    def offer_message(self) -> Optional[dict[str, Any]]:
        return self._offer_message

    @property
    def answer_message(self) -> Optional[dict[str, Any]]:
        return self._answer_message

    @property
    def candidate_messages(self) -> list[dict[str, Any]]:
        return self._candidate_messages

    @property
    def re_offer_messages(self) -> list[dict[str, Any]]:
        return self._re_offer_messages

    @property
    def re_answer_messages(self) -> list[dict[str, Any]]:
        return self._re_answer_messages

    @property
    def connected(self) -> bool:
        return self._connected.is_set()

    @property
    def switched(self) -> bool:
        return self._switched

    def send(self, data: bytes):
        # on_data_channel() が呼ばれるまではデータチャネルの準備ができていないので待機
        while not self._is_data_channel_ready and not self._closed.is_set():
            time.sleep(0.01)

        self._connection.send_data_channel(self._label, data)

    def _on_signaling_message(
        self,
        signaling_type: SoraSignalingType,
        signaling_direction: SoraSignalingDirection,
        raw_message: str,
    ):
        print(raw_message)
        message: dict[str, Any] = json.loads(raw_message)
        match message["type"]:
            case "connect":
                assert signaling_type == SoraSignalingType.WEBSOCKET
                assert signaling_direction == SoraSignalingDirection.SENT
                self._connect_message = message
            case "redirect":
                assert signaling_type == SoraSignalingType.WEBSOCKET
                assert signaling_direction == SoraSignalingDirection.RECEIVED
                self._redirect_message = message
            case "offer":
                assert signaling_type == SoraSignalingType.WEBSOCKET
                assert signaling_direction == SoraSignalingDirection.RECEIVED
                self._offer_message = message
            case "answer":
                assert signaling_type == SoraSignalingType.WEBSOCKET
                assert signaling_direction == SoraSignalingDirection.SENT
                self._answer_message = message
            case "candidate":
                self._candidate_messages.append(message)
            case "re-offer":
                self._re_offer_messages.append(message)
            case "re-answer":
                self._re_answer_messages.append(message)
            case _:
                NotImplementedError(f"Unknown signaling message type: {message['type']}")

    def _on_set_offer(self, raw_message: str):
        message: dict[str, Any] = json.loads(raw_message)
        if message["type"] == "offer":
            # "type": "offer" に入ってくる自分の connection_id を保存する
            self._connection_id = message["connection_id"]

    def _on_switched(self, raw_message: str):
        message: dict[str, Any] = json.loads(raw_message)
        if message["type"] == "switched":
            self._switched = True

    def _on_notify(self, raw_message: str):
        message: dict[str, Any] = json.loads(raw_message)
        # "type": "notify" の "connection.created" で通知される connection_id が
        # 自分の connection_id と一致する場合に接続完了とする
        if (
            message["type"] == "notify"
            and message["event_type"] == "connection.created"
            and message["connection_id"] == self._connection_id
        ):
            print(f"Connected Sora: connection_id={self._connection_id}")
            self._connected.set()

    def _on_disconnect(self, error_code: SoraSignalingErrorCode, message: str):
        print(f"Disconnected Sora: error_code='{error_code}' message='{message}'")
        self._connected.clear()
        self._closed.set()

    def _on_message(self, label: str, data: bytes):
        print(f"Received message: label={label}, data={data.decode('utf-8')}")

    def _on_data_channel(self, label: str):
        for data_channel in self._data_channels:
            if data_channel["label"] != label:
                continue

            if data_channel["direction"] in ["sendrecv", "sendonly"]:
                self._sendable_data_channels.add(label)
                # データチャネルの準備ができたのでフラグを立てる
                self._is_data_channel_ready = True
                break
