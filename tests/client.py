import json
import queue
import threading
import time
from enum import Enum
from threading import Event
from typing import Any, Callable, Optional

import numpy

from sora_sdk import (
    Sora,
    SoraAudioSink,
    SoraAudioSource,
    SoraConnection,
    SoraMediaTrack,
    SoraSignalingDirection,
    SoraSignalingErrorCode,
    SoraSignalingType,
    SoraVideoFrame,
    SoraVideoSink,
    SoraVideoSource,
)


class SoraRole(Enum):
    SENDRECV = "sendrecv"
    SENDONLY = "sendonly"
    RECVONLY = "recvonly"


class SoraClient:
    def __init__(
        self,
        signaling_urls: list[str],
        role: SoraRole,
        channel_id: str,
        simulcast: Optional[bool] = None,
        spotlight: Optional[bool] = None,
        metadata: Optional[dict[str, Any]] = None,
        audio: Optional[bool] = None,
        video: Optional[bool] = None,
        video_codec_type: Optional[str] = None,
        video_bit_rate: Optional[int] = None,
        data_channel_signaling: Optional[bool] = None,
        ignore_disconnect_websocket: Optional[bool] = None,
        data_channels: Optional[list[dict[str, Any]]] = None,
        openh264_path: Optional[str] = None,
        client_key: Optional[bytes] = None,
        client_cert: Optional[bytes] = None,
        ca_cert: Optional[bytes] = None,
        use_hwa: bool = False,
        audio_channels: int = 1,
        audio_sample_rate: int = 16000,
        audio_output_channels: int = 1,
        audio_output_frequency: int = 16000,
        video_width: int = 640,
        video_height: int = 480,
    ):
        self._signaling_urls = signaling_urls
        self._role = role.value
        self._channel_id = channel_id

        self._audio = audio
        self._video = video

        # "type": "connect" のパラメータ
        self._connect_data_channel_signaling = data_channel_signaling
        self._connect_ignore_disconnect_websocket = ignore_disconnect_websocket
        self._connect_data_channels = data_channels

        self._audio_channels = audio_channels
        self._audio_sample_rate = audio_sample_rate

        self._audio_output_channels = audio_output_channels
        self._audio_output_frequency = audio_output_frequency

        self._video_width: int = video_width
        self._video_height: int = video_height

        self._sora: Sora = Sora(openh264=openh264_path, use_hardware_encoder=use_hwa)

        self._fake_audio_thread: Optional[threading.Thread] = None
        self._fake_video_thread: Optional[threading.Thread] = None

        self._audio_source: Optional[SoraAudioSource] = None
        if self._audio:
            self._audio_source = self._sora.create_audio_source(
                self._audio_channels, self._audio_sample_rate
            )

        self._video_source: Optional[SoraVideoSource] = None
        if self._video:
            self._video_source = self._sora.create_video_source()

        self._audio_sink: Optional[SoraAudioSink] = None
        self._video_sink: Optional[SoraVideoSink] = None

        self._is_data_channel_ready = False
        self._sendable_data_channels: set[str] = set()
        self._q_out: queue.Queue = queue.Queue()

        self._connection: SoraConnection = self._sora.create_connection(
            signaling_urls=self._signaling_urls,
            role=self._role,
            channel_id=channel_id,
            simulcast=simulcast,
            spotlight=spotlight,
            metadata=metadata,
            audio=self._audio,
            video=self._video,
            video_codec_type=video_codec_type,
            video_bit_rate=video_bit_rate,
            data_channel_signaling=self._connect_data_channel_signaling,
            ignore_disconnect_websocket=self._connect_ignore_disconnect_websocket,
            data_channels=self._connect_data_channels,
            audio_source=self._audio_source,
            video_source=self._video_source,
            ca_cert=ca_cert,
        )

        # "type": "offer" のパラメータ
        self._offer_data_channel_signaling: Optional[bool] = None
        self._offer_data_channels: Optional[list[dict[str, Any]]] = None

        # "type": "switched" のパラメータ
        self._ignore_disconnect_websocket: Optional[bool] = None

        self._connection_id: Optional[str] = None

        # state
        self._connected: Event = Event()
        self._switched: bool = False
        self._ws_close: bool = False
        self._ws_close_code: Optional[int] = None
        self._ws_close_reason: Optional[str] = None
        self._disconnected: Event = Event()

        self._notify_queue: queue.Queue = queue.Queue()

        self._disconnect_error_code: Optional[int] = None
        self._disconnect_error_message: Optional[str] = None

        self._default_connection_timeout_s: float = 10.0

        # signaling message
        self._connect_message: Optional[dict[str, Any]] = None
        self._redirect_message: Optional[dict[str, Any]] = None
        self._offer_message: Optional[dict[str, Any]] = None
        self._answer_message: Optional[dict[str, Any]] = None
        self._candidate_messages: list[dict[str, Any]] = []
        self._re_offer_messages: list[dict[str, Any]] = []
        self._re_answer_messages: list[dict[str, Any]] = []
        self._disconnect_message: Optional[dict[str, Any]] = None
        self._close_message: Optional[dict[str, Any]] = None

        # callback
        self._connection.on_signaling_message = self._on_signaling_message
        self._connection.on_set_offer = self._on_set_offer
        self._connection.on_switched = self._on_switched
        self._connection.on_ws_close = self._on_ws_close
        self._connection.on_notify = self._on_notify
        self._connection.on_track = self._on_track
        self._connection.on_data_channel = self._on_data_channel
        self._connection.on_message = self._on_message
        self._connection.on_disconnect = self._on_disconnect

    def __enter__(self) -> "SoraClient":
        if self._role == SoraRole.RECVONLY:
            self.connect()
            return self

        self.connect(fake_audio=bool(self._audio), fake_video=bool(self._video))

        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.disconnect()

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
        self._connection.disconnect()

    def send(self, label: str, data: bytes):
        print(f"send: label={label}, data={data!r}")
        # on_data_channel() が呼ばれるまではデータチャネルの準備ができていないので待機
        if not self._is_data_channel_ready:
            while not self._is_data_channel_ready and not self._disconnected.is_set():
                time.sleep(0.01)

        self._connection.send_data_channel(label, data)

    def get_stats(self):
        raw_stats = self._connection.get_stats()
        return json.loads(raw_stats)

    @property
    def role(self) -> str:
        return self._role

    @property
    def connection_id(self) -> Optional[str]:
        return self._connection_id

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
    def disconnect_message(self) -> Optional[dict[str, Any]]:
        return self._disconnect_message

    @property
    def close_message(self) -> Optional[dict[str, Any]]:
        return self._close_message

    @property
    def connected(self) -> bool:
        return self._connected.is_set()

    @property
    def switched(self) -> bool:
        return self._switched

    @property
    def ignore_disconnect_websocket(self) -> Optional[bool]:
        return self._ignore_disconnect_websocket

    @property
    def ws_close(self) -> bool:
        return self._ws_close

    @property
    def ws_close_code(self) -> Optional[int]:
        return self._ws_close_code

    @property
    def ws_close_reason(self) -> Optional[str]:
        return self._ws_close_reason

    @property
    def disconnect_code(self) -> Optional[int]:
        return self._disconnect_code

    @property
    def disconnect_reason(self) -> Optional[str]:
        return self._disconnect_reason

    def _fake_audio_loop(self):
        while not self._disconnected.is_set():
            time.sleep(0.02)
            if self._audio_source is not None:
                self._audio_source.on_data(numpy.zeros((320, 1), dtype=numpy.int16))

    def _fake_video_loop(self):
        while not self._disconnected.is_set():
            time.sleep(1.0 / 30)
            if self._video_source is not None:
                self._video_source.on_captured(
                    numpy.zeros((self._video_height, self._video_width, 3), dtype=numpy.uint8)
                )

    def _on_signaling_message(
        self,
        signaling_type: SoraSignalingType,
        signaling_direction: SoraSignalingDirection,
        raw_message: str,
    ):
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
            case "disconnect":
                assert signaling_direction == SoraSignalingDirection.SENT
                self._disconnect_message = message
            case "close":
                print(f"type: close: {message}")
                assert signaling_type == SoraSignalingType.DATACHANNEL
                assert signaling_direction == SoraSignalingDirection.RECEIVED
                self._close_message = message
            case _:
                NotImplementedError(f"Unknown signaling message type: {message['type']}")

    def _on_set_offer(self, raw_message: str) -> None:
        message: dict[str, Any] = json.loads(raw_message)
        if message["type"] == "offer":
            self._connection_id = message["connection_id"]
            if "data_channel_signaling" in message:
                self._offer_data_channel_signaling = message["data_channel_signaling"]
            if "ignore_disconnect_websocket" in message:
                self._offer_ignore_disconnect_websocket = message["ignore_disconnect_websocket"]
            if "data_channels" in message:
                self._offer_data_channels = message["data_channels"]

    def _on_switched(self, raw_message: str) -> None:
        message = json.loads(raw_message)
        if message["type"] == "switched":
            print(f"Switched to DataChannel Signaling: connection_id={self._connection_id}")
            self._switched = True
            self._ignore_disconnect_websocket = message["ignore_disconnect_websocket"]

    def _on_notify(self, raw_message: str) -> None:
        message: dict[str, Any] = json.loads(raw_message)
        self._notify_queue.put(message)
        if (
            message["type"] == "notify"
            and message["event_type"] == "connection.created"
            and message["connection_id"] == self._connection_id
        ):
            print(f"Connected Sora: connection_id={self._connection_id}")
            self._connected.set()

    def _on_message(self, label: str, data: bytes):
        print(f"Received message: label={label}, data={data.decode('utf-8')}")

    def _on_data_channel(self, label: str):
        print(f"DataChannel opened: label={label}")
        if self._offer_data_channels:
            for data_channel in self._offer_data_channels:
                if data_channel["label"] != label:
                    continue

                if data_channel["direction"] in ["sendrecv", "sendonly"]:
                    self._sendable_data_channels.add(label)
                    # メッセージングで利用するチャネルが利用可能になったのでフラグを立てる
                    self._is_data_channel_ready = True
                    break

    def _on_disconnect(self, error_code: SoraSignalingErrorCode, message: str) -> None:
        print(f"Disconnected Sora: error_code='{error_code}' message='{message}'")

        self._disconnect_code = error_code.value
        self._disconnect_reason = message

        self._connected.clear()
        self._disconnected.set()

        if self._fake_audio_thread is not None:
            self._fake_audio_thread.join(timeout=10)

        if self._fake_video_thread is not None:
            self._fake_video_thread.join(timeout=10)

    def _on_ws_close(self, code: int, reason: str) -> None:
        print(f"WebSocket closed: code={code} reason={reason}")
        self._ws_close = True
        self._ws_close_code = code
        self._ws_close_reason = reason

    def _on_video_frame(self, frame: SoraVideoFrame) -> None:
        self._q_out.put(frame)

    def _on_track(self, track: SoraMediaTrack) -> None:
        if track.kind == "audio":
            self._audio_sink = SoraAudioSink(
                track, self._audio_output_frequency, self._audio_output_channels
            )
        if track.kind == "video":
            self._video_sink = SoraVideoSink(track)
            self._video_sink.on_frame = self._on_video_frame

    def wait_notify(self, pred: Callable[[dict], bool], timeout: Optional[int] = 5):
        while True:
            notify = self._notify_queue.get(block=True, timeout=timeout)
            if pred(notify):
                return notify
