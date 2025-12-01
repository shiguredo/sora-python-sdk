import json
import queue
import threading
import time
from enum import Enum
from threading import Event
from typing import Any, Callable, Optional

import numpy
from conftest import Settings

import sora_sdk
from sora_sdk import (
    Sora,
    SoraAudioSink,
    SoraAudioSource,
    SoraConnection,
    SoraDegradationPreference,
    SoraMediaTrack,
    SoraSignalingDirection,
    SoraSignalingErrorCode,
    SoraSignalingType,
    SoraTrackInterface,
    SoraVideoCodecImplementation,
    SoraVideoCodecPreference,
    SoraVideoCodecType,
    SoraVideoFrame,
    SoraVideoSink,
    get_video_codec_capability,
)


class SoraRole(Enum):
    SENDRECV = "sendrecv"
    SENDONLY = "sendonly"
    RECVONLY = "recvonly"


class SoraClient:
    def __init__(
        self,
        settings: Settings,
        role: SoraRole,
        simulcast: Optional[bool] = None,
        spotlight: Optional[bool] = None,
        metadata: dict[str, str] | None = None,
        jwt_private_claims: dict[str, Any] | None = None,
        audio: Optional[bool] = None,
        audio_codec_type: Optional[str] = None,
        audio_opus_params: Optional[dict[str, Any]] = None,
        video: Optional[bool] = None,
        video_codec_type: Optional[str] = None,
        video_bit_rate: Optional[int] = None,
        data_channel_signaling: Optional[bool] = None,
        ignore_disconnect_websocket: Optional[bool] = None,
        data_channels: Optional[list[dict[str, Any]]] = None,
        forwarding_filter: Optional[dict[str, Any]] = None,
        forwarding_filters: Optional[list[dict[str, Any]]] = None,
        client_key: Optional[bytes] = None,
        client_cert: Optional[bytes] = None,
        ca_cert: Optional[bytes] = None,
        degradation_preference: Optional[SoraDegradationPreference] = None,
        user_agent: Optional[str] = None,
        video_codec_preference: Optional[SoraVideoCodecPreference] = None,
        audio_channels: int = 1,
        audio_sample_rate: int = 16000,
        audio_output_channels: int = 1,
        audio_output_frequency: int = 16000,
        video_width: int = 640,
        video_height: int = 480,
        video_frame_rate: int = 30,
        libcamera: bool = False,
        libcamera_controls: Optional[list[tuple[str, str]]] = None,
        native_frame_output: bool = False,
        force_i420_conversion: Optional[bool] = None,
    ):
        self._signaling_urls = settings.signaling_urls
        self._role = role.value
        self._channel_id = settings.channel_id

        if jwt_private_claims is not None:
            access_token = settings.access_token(**jwt_private_claims)
        else:
            access_token = settings.access_token()

        # secret が設定されていない場合は access_token が存在しない
        if access_token is not None:
            if metadata is not None:
                # metadata が設定されている場合は access_token を追加する
                metadata.update({"access_token": access_token})
            else:
                # metadata が設定されていない場合は access_token のみを metadata に設定する
                metadata = {"access_token": access_token}
        self._metadata = metadata

        self._audio = audio
        self._video = video
        self._degradation_preference = degradation_preference

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
        self._video_frame_rate: int = video_frame_rate

        self._libcamera = libcamera

        if settings.libwebrtc_log is not None:
            sora_sdk.enable_libwebrtc_log(settings.libwebrtc_log)

        self._sora: Sora = Sora(
            openh264=settings.openh264_path,
            video_codec_preference=video_codec_preference,
            force_i420_conversion=force_i420_conversion,
        )

        self._fake_audio_thread: Optional[threading.Thread] = None
        self._fake_video_thread: Optional[threading.Thread] = None

        self._audio_source: Optional[SoraAudioSource] = None
        if self._audio:
            self._audio_source = self._sora.create_audio_source(
                self._audio_channels, self._audio_sample_rate
            )

        self._video_source: Optional[SoraTrackInterface] = None
        if libcamera and self._video:
            self._video_source = self._sora.create_libcamera_source(
                width=self._video_width,
                height=self._video_height,
                fps=self._video_frame_rate,
                native_frame_output=native_frame_output,
                controls=libcamera_controls,
            )
        elif self._video:
            self._video_source = self._sora.create_video_source()

        self._audio_sink: Optional[SoraAudioSink] = None
        self._video_sink: Optional[SoraVideoSink] = None

        self._data_channel_ready_events: dict[str, Event] = {}
        self._messaging_recv_queues: dict[str, queue.Queue] = {}
        self._q_out: queue.Queue = queue.Queue()

        self._connection: SoraConnection = self._sora.create_connection(
            signaling_urls=self._signaling_urls,
            role=self._role,
            channel_id=self._channel_id,
            simulcast=simulcast,
            spotlight=spotlight,
            metadata=metadata,
            audio=self._audio,
            audio_codec_type=audio_codec_type,
            audio_opus_params=audio_opus_params,
            video=self._video,
            video_codec_type=video_codec_type,
            video_bit_rate=video_bit_rate,
            data_channel_signaling=self._connect_data_channel_signaling,
            ignore_disconnect_websocket=self._connect_ignore_disconnect_websocket,
            data_channels=self._connect_data_channels,
            forwarding_filter=forwarding_filter,
            forwarding_filters=forwarding_filters,
            audio_source=self._audio_source,
            video_source=self._video_source,
            ca_cert=ca_cert,
            degradation_preference=self._degradation_preference,
            user_agent=user_agent,
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
            return self.connect()

        return self.connect(fake_audio=bool(self._audio), fake_video=bool(self._video))

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        print("__exit__: disconnecting")
        self.disconnect()
        print("__exit__: disconnected")

    def connect(self, fake_audio=False, fake_video=False) -> "SoraClient":
        # スレッドは connect 前に起動する
        if fake_audio:
            self._fake_audio_thread = threading.Thread(target=self._fake_audio_loop, daemon=True)
            self._fake_audio_thread.start()

        if fake_video:
            self._fake_video_thread = threading.Thread(target=self._fake_video_loop, daemon=True)
            self._fake_video_thread.start()

        self._connection.connect()

        try:
            assert self._connected.wait(self._default_connection_timeout_s), (
                "Could not connect to Sora."
            )
        except Exception as e:
            self._connection.disconnect()
            raise e

        return self

    def disconnect(self) -> None:
        print("disconnect: disconnecting")
        self._connection.disconnect()
        print("disconnect: disconnected")

    def send_message(self, label: str, data: bytes, timeout: float = 5):
        # TODO: direction が sendrecv / sendonly の時しか送れず、例外をあげるようにする
        print(f"send: label={label}, data={data!r}")

        # on_data_channel() が呼ばれるまではデータチャネルの準備ができていないので待機
        self._data_channel_ready_events[label].wait(timeout=timeout)
        self._connection.send_data_channel(label, data)

    def recv_message(self, label: str, timeout: float = 5) -> bytes:
        return self._messaging_recv_queues[label].get(block=True, timeout=timeout)

    def get_stats(self):
        raw_stats = self._connection.get_stats()
        return json.loads(raw_stats)

    @property
    def role(self) -> str:
        return self._role

    @property
    def channel_id(self) -> str:
        return self._channel_id

    @property
    def metadata(self) -> dict[str, Any] | None:
        return self._metadata

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
                # self._video_source.on_captured(
                #     numpy.zeros((self._video_height, self._video_width, 3), dtype=numpy.uint8)
                # )

                # お試し randint
                def generate_random_image():
                    random_color = numpy.random.randint(0, 256, size=(3,), dtype=numpy.uint8)
                    return numpy.full(
                        (self._video_height, self._video_width, 3), random_color, dtype=numpy.uint8
                    )

                random_image = generate_random_image()
                self._video_source.on_captured(random_image)

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
                for data_channel in message["data_channels"]:
                    self._data_channel_ready_events[data_channel["label"]] = Event()

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
            print(
                f"Connected Sora: channel_id={self._channel_id}, connection_id={self._connection_id}"
            )
            self._connected.set()

    def _on_message(self, label: str, data: bytes):
        print(f"Received message: label={label}, data={data.decode('utf-8')}")
        self._messaging_recv_queues[label].put(data)

    def _on_data_channel(self, label: str):
        print(f"DataChannel opened: label={label}")
        self._messaging_recv_queues[label] = queue.Queue()
        self._data_channel_ready_events[label].set()

    def _on_disconnect(self, error_code: SoraSignalingErrorCode, message: str) -> None:
        print(f"Disconnected Sora: error_code='{error_code}' message='{message}'")

        self._disconnect_code = error_code.value
        self._disconnect_reason = message

        self._connected.clear()
        self._disconnected.set()

        if self._libcamera or self._video_source is not None:
            self._video_source = None

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


def codec_type_string_to_codec_type(codec_type: str) -> SoraVideoCodecType:
    match codec_type:
        case "VP8":
            return SoraVideoCodecType.VP8
        case "VP9":
            return SoraVideoCodecType.VP9
        case "AV1":
            return SoraVideoCodecType.AV1
        case "H264":
            return SoraVideoCodecType.H264
        case "H265":
            return SoraVideoCodecType.H265
        case _:
            raise ValueError(f"Unknown codec_type: {codec_type}")


# テストしている Intel のチップが指定したコーデックに対応しているかどうかを確認する関数
# decoder / encoder の両方が対応している場合のみ True を返す
def is_codec_supported(codec_type: str, codec_implementation: SoraVideoCodecImplementation) -> bool:
    capability = get_video_codec_capability()
    for e in capability.engines:
        if e.name == codec_implementation:
            for c in e.codecs:
                if c.type == codec_type_string_to_codec_type(codec_type):
                    if c.decoder is True and c.encoder is True:
                        return True
    return False
