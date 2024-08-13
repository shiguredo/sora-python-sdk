import json
import platform
import queue
from threading import Event
from typing import Any, Optional

import cv2
import sounddevice
from numpy import ndarray
from sora_sdk import (
    Sora,
    SoraAudioSink,
    SoraConnection,
    SoraMediaTrack,
    SoraSignalingErrorCode,
    SoraVideoFrame,
    SoraVideoSink,
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
        video_codec_type: Optional[str] = None,
        video_bit_rate: Optional[int] = None,
        video_width: Optional[int] = None,
        video_height: Optional[int] = None,
        video_fps: Optional[int] = None,
        openh264_path: Optional[str] = None,
        use_hwa: bool = False,
        video_fourcc: str = "MJPG",
        camera_id: int = 0,
        audio_channels: int = 1,
        audio_sample_rate: int = 16000,
    ):
        """
        Sendonly インスタンスを初期化します。

        :param signaling_urls: Sora シグナリング URL のリスト
        :param channel_id: 接続するチャンネル ID
        :param metadata: 接続のためのオプションのメタデータ
        :param camera_id: 使用するカメラの ID
        :param video_codec_type: 使用するビデオコーデックの種類
        :param video_bit_rate: ビデオのビットレート
        :param video_width: ビデオの幅
        :param video_height: ビデオの高さ
        :param video_fps: ビデオのフレームレート
        :param video_fourcc: ビデオの FOURCC コード
        :param openh264_path: OpenH264 ライブラリへのパス
        :param audio_channels: 音声チャンネル数（デフォルト: 1）
        :param audio_sample_rate: 音声サンプリングレート（デフォルト: 16000）
        """
        self.audio_channels: int = audio_channels
        self.audio_sample_rate: int = audio_sample_rate

        self._sora: Sora = Sora(openh264=openh264_path, use_hardware_encoder=use_hwa)

        self._audio_source = self._sora.create_audio_source(
            self.audio_channels, self.audio_sample_rate
        )
        self._video_source = self._sora.create_video_source()

        self._connection: SoraConnection = self._sora.create_connection(
            signaling_urls=signaling_urls,
            role="sendonly",
            channel_id=channel_id,
            metadata=metadata,
            video_codec_type=video_codec_type,
            video_bit_rate=video_bit_rate,
            audio_source=self._audio_source,
            video_source=self._video_source,
        )
        self._connection_id: Optional[str] = None

        self._connected: Event = Event()
        self._closed: bool = False
        self._default_connection_timeout_s: float = 10.0

        self._connection.on_set_offer = self._on_set_offer
        self._connection.on_notify = self._on_notify
        self._connection.on_disconnect = self._on_disconnect

        self._setup_video_capture(camera_id, video_width, video_height, video_fps, video_fourcc)

    def _setup_video_capture(
        self,
        camera_id: int,
        video_width: Optional[int],
        video_height: Optional[int],
        video_fps: Optional[int],
        video_fourcc: Optional[str],
    ) -> None:
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
            self._video_capture = cv2.VideoCapture(camera_id, cv2.CAP_DSHOW)
        else:
            self._video_capture = cv2.VideoCapture(camera_id)

        if video_width is not None:
            self._video_capture.set(cv2.CAP_PROP_FRAME_WIDTH, video_width)
        if video_height is not None:
            self._video_capture.set(cv2.CAP_PROP_FRAME_HEIGHT, video_height)
        if video_fourcc is not None:
            self._video_capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*video_fourcc))
        if video_fps is not None:
            self._video_capture.set(cv2.CAP_PROP_FPS, video_fps)

        # Ubuntu → FOURCC を設定すると FPS が初期化される
        # Windows → FPS を設定すると FOURCC が初期化される
        # ので、両方に対応するため２回設定する
        if video_fourcc is not None:
            fourcc = cv2.VideoWriter_fourcc(*video_fourcc)
            target_fourcc = self._video_capture.get(cv2.CAP_PROP_FOURCC)
            if fourcc != target_fourcc:
                self._video_capture.set(cv2.CAP_PROP_FOURCC, fourcc)
        if video_fps is not None:
            if video_fps != int(self._video_capture.get(cv2.CAP_PROP_FPS)):
                self._video_capture.set(cv2.CAP_PROP_FPS, video_fps)

    def connect(self) -> None:
        """
        Sora への接続を確立します。

        :raises AssertionError: タイムアウト期間内に接続が確立できなかった場合
        """
        self._connection.connect()

        assert self._connected.wait(
            self._default_connection_timeout_s
        ), "Could not connect to Sora."

    def disconnect(self) -> None:
        """Sora から切断します。"""
        self._connection.disconnect()

    def get_stats(self):
        raw_stats = self._connection.get_stats()
        stats = json.loads(raw_stats)
        return stats

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

    def _on_set_offer(self, raw_message: str) -> None:
        """
        オファー設定イベントを処理します。

        :param raw_message: オファーを含む生のメッセージ
        """
        message: dict[str, Any] = json.loads(raw_message)
        if message["type"] == "offer":
            self._connection_id = message["connection_id"]

    def _on_disconnect(self, error_code: SoraSignalingErrorCode, message: str) -> None:
        """
        切断イベントを処理します。

        :param error_code: 切断のエラーコード
        :param message: 切断メッセージ
        """
        print(f"Disconnected Sora: error_code='{error_code}' message='{message}'")
        self._connected.clear()
        self._closed = True

    def _callback(
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
            samplerate=self.audio_sample_rate,
            channels=self.audio_channels,
            dtype="int16",
            callback=self._callback,
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


class Recvonly:
    """Sora からビデオと音声ストリームを受信するためのクラス。"""

    def __init__(
        self,
        signaling_urls: list[str],
        channel_id: str,
        metadata: Optional[dict[str, Any]] = None,
        openh264_path: Optional[str] = None,
        use_hwa: Optional[bool] = False,
        output_frequency: int = 16000,
        output_channels: int = 1,
    ):
        """
        Recvonly インスタンスを初期化します。

        このクラスは Sora への接続を設定し、音声とビデオトラックを受信し、
        ビデオフレームの表示と音声の再生を行うメソッドを提供します。

        :param signaling_urls: Sora シグナリング URL のリスト
        :param channel_id: 接続するチャンネル ID
        :param metadata: 接続のためのオプションのメタデータ
        :param openh264: OpenH264 ライブラリへのパス
        :param output_frequency: 音声出力周波数（Hz）、デフォルトは 16000
        :param output_channels: 音声出力チャンネル数、デフォルトは 1
        """
        self._output_frequency: int = output_frequency
        self._output_channels: int = output_channels

        self._sora: Sora = Sora(openh264=openh264_path, use_hardware_encoder=use_hwa)
        self._connection: SoraConnection = self._sora.create_connection(
            signaling_urls=signaling_urls,
            role="recvonly",
            channel_id=channel_id,
            metadata=metadata,
        )
        self._connection_id: Optional[str] = None

        self._connected: Event = Event()
        self._closed: bool = False
        self._default_connection_timeout_s: float = 10.0

        self._audio_sink: Optional[SoraAudioSink] = None
        self._video_sink: Optional[SoraVideoSink] = None

        self._q_out: queue.Queue = queue.Queue()

        self._connection.on_set_offer = self._on_set_offer
        self._connection.on_notify = self._on_notify
        self._connection.on_disconnect = self._on_disconnect
        self._connection.on_track = self._on_track

    def connect(self) -> None:
        """
        Sora への接続を確立します。

        :raises AssertionError: タイムアウト期間内に接続が確立できなかった場合
        """
        self._connection.connect()

        assert self._connected.wait(
            self._default_connection_timeout_s
        ), "Could not connect to Sora."

    def disconnect(self) -> None:
        """Sora から切断します。"""
        self._connection.disconnect()

    def get_stats(self):
        raw_stats = self._connection.get_stats()
        stats = json.loads(raw_stats)
        return stats

    def _on_set_offer(self, raw_message: str) -> None:
        """
        オファー設定イベントを処理します。

        :param raw_message: オファーを含む生のメッセージ
        """
        message: dict[str, Any] = json.loads(raw_message)
        if message["type"] == "offer":
            self._connection_id = message["connection_id"]

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
        self._closed = True

    def _on_video_frame(self, frame: SoraVideoFrame) -> None:
        """
        受信したビデオフレームを処理します。

        :param frame: 受信したビデオフレーム
        """
        self._q_out.put(frame)

    def _on_track(self, track: SoraMediaTrack) -> None:
        """
        新しいメディアトラックを処理します。

        :param track: 新しいメディアトラック
        """
        if track.kind == "audio":
            self._audio_sink = SoraAudioSink(track, self._output_frequency, self._output_channels)
        if track.kind == "video":
            self._video_sink = SoraVideoSink(track)
            self._video_sink.on_frame = self._on_video_frame

    def _callback(
        self, outdata: ndarray, frames: int, time: Any, status: sounddevice.CallbackFlags
    ) -> None:
        """
        音声出力のためのコールバック関数。

        :param outdata: 音声データを格納する出力バッファ
        :param frames: 処理するフレーム数
        :param time: タイミング情報（未使用）
        :param status: ストリームのステータス
        """
        if self._audio_sink is not None:
            success, data = self._audio_sink.read(frames)
            if success:
                if data.shape[0] != frames:
                    print("Audio data is insufficient: ", data.shape, frames)
                outdata[:] = data
            else:
                print("Unable to obtain audio data")

    def run(self) -> None:
        """ビデオフレームの受信と表示、および音声の再生を行うメインループ。"""
        with sounddevice.OutputStream(
            channels=self._output_channels,
            callback=self._callback,
            samplerate=self._output_frequency,
            dtype="int16",
        ):
            self.connect()
            try:
                while self._connected.is_set():
                    try:
                        frame = self._q_out.get(timeout=1)
                    except queue.Empty:
                        continue
                    cv2.imshow("frame", frame.data())
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break
            except KeyboardInterrupt:
                pass
            finally:
                self.disconnect()
                cv2.destroyAllWindows()
