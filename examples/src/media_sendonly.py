import json
import os
import platform
import threading
import time
from threading import Event
from typing import Any, Optional

import cv2  # type: ignore
import numpy
import sounddevice  # type: ignore
from dotenv import load_dotenv
from numpy import ndarray
from sora_sdk import (
    Sora,
    SoraConnection,
    SoraSignalingDirection,
    SoraSignalingErrorCode,
    SoraSignalingType,
)


class Sendonly:
    """
    Sora にビデオと音声ストリームを送信するためのクラス。

    このクラスは Sora への接続を設定し、カメラからのビデオと
    マイクからの音声を Sora に送信するメソッドを提供します。
    """

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
        video_capture: Optional[cv2.VideoCapture] = None,
    ):
        """
        Sendonly インスタンスを初期化します。

        :param signaling_urls: Sora シグナリング URL のリスト
        :param channel_id: 接続するチャンネル ID
        :param metadata: 接続のためのオプションのメタデータ
        :param audio: 音声ストリームを送信するかどうか
        :param video: ビデオストリームを送信するかどうか
        :param video_codec_type: 使用するビデオコーデックの種類
        :param video_bit_rate: ビデオのビットレート
        :param openh264_path: OpenH264 ライブラリへのパス
        :param audio_channels: 音声チャンネル数（デフォルト: 1）
        :param audio_sample_rate: 音声サンプリングレート（デフォルト: 16000）
        :param video_capture: カメラからのビデオキャプチャ
        """
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
            role="sendonly",
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

        # メッセージ
        self._connect_message: Optional[dict[str, Any]] = None
        self._redirect_message: Optional[dict[str, Any]] = None
        self._offer_message: Optional[dict[str, Any]] = None
        self._answer_message: Optional[dict[str, Any]] = None
        self._candidate_messages: list[dict[str, Any]] = []
        self._re_offer_messages: list[dict[str, Any]] = []
        self._re_answer_messages: list[dict[str, Any]] = []

        self._connection.on_signaling_message = self._on_signaling_message
        self._connection.on_set_offer = self._on_set_offer
        self._connection.on_switched = self._on_switched
        self._connection.on_notify = self._on_notify
        self._connection.on_disconnect = self._on_disconnect

        if video_capture is not None:
            self._video_capture = video_capture

    def connect(self, fake_audio=False, fake_video=False) -> None:
        """
        Sora への接続を確立します。

        :raises AssertionError: タイムアウト期間内に接続が確立できなかった場合
        """
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
                self._re_offer_messages.append(message)
            case "re-answer":
                self._re_answer_messages.append(message)
            case _:
                NotImplementedError(f"Unknown signaling message type: {message['type']}")

    def _on_set_offer(self, raw_message: str) -> None:
        """
        オファー設定イベントを処理します。

        :param raw_message: オファーを含む生のメッセージ
        """
        message: dict[str, Any] = json.loads(raw_message)
        if message["type"] == "offer":
            self._connection_id = message["connection_id"]

    def _on_switched(self, raw_message: str) -> None:
        message = json.loads(raw_message)
        if message["type"] == "switched":
            print(f"Switched to DataChannel Signaling: connection_id={self._connection_id}")
            self._switched = True

    def _on_notify(self, raw_message: str) -> None:
        """
        Sora からの通知イベントを処理します。

        :param raw_message: 生の通知メッセージ
        """
        message: dict[str, Any] = json.loads(raw_message)
        if (
            message["type"] == "notify"
            and message["event_type"] == "connection.created"
            and message["connection_id"] == self._connection_id
        ):
            print(f"Connected Sora: connection_id={self._connection_id}")
            self._connected.set()

    def _on_disconnect(self, error_code: SoraSignalingErrorCode, message: str) -> None:
        """
        切断イベントを処理します。

        :param error_code: 切断のエラーコード
        :param message: 切断メッセージ
        """
        print(f"Disconnected Sora: error_code='{error_code}' message='{message}'")
        self._connected.clear()
        self._closed.set()

        if self._fake_audio_thread is not None:
            self._fake_audio_thread.join(timeout=10)

        if self._fake_video_thread is not None:
            self._fake_video_thread.join(timeout=10)

    def _sounddevice_input_stream_callback(
        self, indata: ndarray, frames: int, time: Any, status: sounddevice.CallbackFlags
    ) -> None:
        """
        音声入力のためのコールバック関数。

        :param indata: 入力された音声データ
        :param frames: 処理するフレーム数
        :param time: タイミング情報（未使用）
        :param status: ステータスフラグ
        """
        self._audio_source.on_data(indata)

    def run(self) -> None:
        """
        ビデオフレームの送信と音声の送信を行うメインループ。
        """
        with sounddevice.InputStream(
            samplerate=self._audio_sample_rate,
            channels=self._audio_channels,
            dtype="int16",
            callback=self._sounddevice_input_stream_callback,
        ):
            self.connect()
            try:
                while self._connected.is_set():
                    success, frame = self._video_capture.read()
                    if not success:
                        continue
                    self._video_source.on_captured(frame)
            except KeyboardInterrupt:
                pass
            finally:
                self.disconnect()
                self._video_capture.release()


def get_video_capture(
    camera_id: int,
    video_width: int,
    video_height: int,
    video_fps: int,
    video_fourcc: str,
) -> cv2.VideoCapture:
    """
    ビデオキャプチャの設定を行います。

    :param camera_id: 使用するカメラの ID
    :param video_width: ビデオの幅
    :param video_height: ビデオの高さ
    :param video_fps: ビデオのフレームレート
    :param video_fourcc: ビデオの FOURCC コード
    """

    if platform.system() == "Windows":
        # CAP_DSHOW を設定しないと、カメラの起動がめちゃめちゃ遅くなる
        video_capture = cv2.VideoCapture(camera_id, cv2.CAP_DSHOW)
    else:
        video_capture = cv2.VideoCapture(camera_id)

    if video_width is not None:
        video_capture.set(cv2.CAP_PROP_FRAME_WIDTH, video_width)
    if video_height is not None:
        video_capture.set(cv2.CAP_PROP_FRAME_HEIGHT, video_height)
    if video_fourcc is not None:
        video_capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*video_fourcc))
    if video_fps is not None:
        video_capture.set(cv2.CAP_PROP_FPS, video_fps)

    # Ubuntu → FOURCC を設定すると FPS が初期化される
    # Windows → FPS を設定すると FOURCC が初期化される
    # ので、両方に対応するため２回設定する
    if video_fourcc is not None:
        fourcc = cv2.VideoWriter_fourcc(*video_fourcc)
        target_fourcc = video_capture.get(cv2.CAP_PROP_FOURCC)
        if fourcc != target_fourcc:
            video_capture.set(cv2.CAP_PROP_FOURCC, fourcc)
    if video_fps is not None:
        if video_fps != int(video_capture.get(cv2.CAP_PROP_FPS)):
            video_capture.set(cv2.CAP_PROP_FPS, video_fps)

    return video_capture


def sendonly() -> None:
    """
    環境変数を使用して Sendonly インスタンスを設定し実行します。

    :raises ValueError: 必要な環境変数が設定されていない場合
    """
    load_dotenv()

    if not (raw_signaling_urls := os.getenv("SORA_SIGNALING_URLS")):
        raise ValueError("環境変数 SORA_SIGNALING_URLS が設定されていません")
    signaling_urls = raw_signaling_urls.split(",")

    if not (channel_id := os.getenv("SORA_CHANNEL_ID")):
        raise ValueError("環境変数 SORA_CHANNEL_ID が設定されていません")

    metadata = None
    if raw_metadata := os.getenv("SORA_METADATA"):
        metadata = json.loads(raw_metadata)

    video_codec_type = os.getenv("SORA_VIDEO_CODEC_TYPE", "VP9")
    video_bit_rate = int(os.getenv("SORA_VIDEO_BIT_RATE", "500"))
    video_width = int(os.getenv("SORA_VIDEO_WIDTH", "640"))
    video_height = int(os.getenv("SORA_VIDEO_HEIGHT", "360"))
    video_fps = int(os.getenv("SORA_VIDEO_FPS", "30"))
    video_fourcc = os.getenv("SORA_VIDEO_FOURCC", "MJPG")

    camera_id = int(os.getenv("SORA_CAMERA_ID", "0"))

    # OpenCV を利用したビデオキャプチャの設定
    video_capture = get_video_capture(
        camera_id=camera_id,
        video_width=video_width,
        video_height=video_height,
        video_fps=video_fps,
        video_fourcc=video_fourcc,
    )

    openh264_path = os.getenv("OPENH264_PATH")

    use_hwa = bool(os.getenv("USE_HWA", "True"))

    sendonly = Sendonly(
        signaling_urls,
        channel_id,
        metadata=metadata,
        video_codec_type=video_codec_type,
        video_bit_rate=video_bit_rate,
        openh264_path=openh264_path,
        use_hwa=use_hwa,
        video_capture=video_capture,
    )
    sendonly.run()


if __name__ == "__main__":
    sendonly()
