import json
import os
import platform
from threading import Event
from typing import Any, Optional

import cv2
import sounddevice
from dotenv import load_dotenv
from numpy import ndarray
from sora_sdk import Sora, SoraConnection, SoraSignalingErrorCode


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
        metadata: Optional[dict[str, Any]],
        camera_id: int,
        video_codec_type: str,
        video_bit_rate: int,
        video_width: Optional[int],
        video_height: Optional[int],
        video_fps: Optional[int],
        video_fourcc: Optional[str],
        openh264: Optional[str],
        audio_channels: int = 1,
        audio_sample_rate: int = 16000,
    ):
        """
        Sendonly インスタンスを初期化します。

        引数:
            signaling_urls (list[str]): Sora シグナリング URL のリスト。
            channel_id (str): 接続するチャンネル ID。
            metadata (Optional[dict[str, Any]]): 接続のためのオプションのメタデータ。
            camera_id (int): 使用するカメラの ID。
            video_codec_type (str): 使用するビデオコーデックの種類。
            video_bit_rate (int): ビデオのビットレート。
            video_width (Optional[int]): ビデオの幅。
            video_height (Optional[int]): ビデオの高さ。
            video_fps (Optional[int]): ビデオのフレームレート。
            video_fourcc (Optional[str]): ビデオの FOURCC コード。
            openh264 (Optional[str]): OpenH264 ライブラリへのパス。
            audio_channels (int): 音声チャンネル数。デフォルトは 1。
            audio_sample_rate (int): 音声サンプリングレート。デフォルトは 16000。
        """
        self.audio_channels: int = audio_channels
        self.audio_sample_rate: int = audio_sample_rate

        self._sora: Sora = Sora(openh264=openh264)

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

        引数:
            camera_id (int): 使用するカメラの ID。
            video_width (Optional[int]): ビデオの幅。
            video_height (Optional[int]): ビデオの高さ。
            video_fps (Optional[int]): ビデオのフレームレート。
            video_fourcc (Optional[str]): ビデオの FOURCC コード。
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

        例外:
            AssertionError: タイムアウト期間内に接続が確立できなかった場合。
        """
        self._connection.connect()

        assert self._connected.wait(
            timeout=self._default_connection_timeout_s
        ), "接続がタイムアウトしました"

    def disconnect(self) -> None:
        """Sora から切断します。"""
        self._connection.disconnect()

    def _on_notify(self, raw_message: str) -> None:
        """
        Sora からの通知イベントを処理します。

        引数:
            raw_message (str): 生の通知メッセージ。
        """
        message: dict[str, Any] = json.loads(raw_message)
        if (
            message["type"] == "notify"
            and message["event_type"] == "connection.created"
            and message["connection_id"] == self._connection_id
        ):
            print("Sora に接続しました")
            self._connected.set()

    def _on_set_offer(self, raw_message: str) -> None:
        """
        オファー設定イベントを処理します。

        引数:
            raw_message (str): オファーを含む生のメッセージ。
        """
        message: dict[str, Any] = json.loads(raw_message)
        if message["type"] == "offer":
            self._connection_id = message["connection_id"]

    def _on_disconnect(self, error_code: SoraSignalingErrorCode, message: str) -> None:
        """
        切断イベントを処理します。

        引数:
            error_code (SoraSignalingErrorCode): 切断のエラーコード。
            message (str): 切断メッセージ。
        """
        print(f"Sora から切断されました: error_code='{error_code}' message='{message}'")
        self._connected.clear()
        self._closed = True

    def _callback(
        self, indata: ndarray, frames: int, time: Any, status: sounddevice.CallbackFlags
    ) -> None:
        """
        音声入力のためのコールバック関数。

        引数:
            indata (ndarray): 入力された音声データ。
            frames (int): 処理するフレーム数。
            time (Any): タイミング情報（未使用）。
            status (sounddevice.CallbackFlags): ステータスフラグ。
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


def sendonly() -> None:
    """
    環境変数を使用して Sendonly インスタンスを設定し実行します。

    例外:
        ValueError: 必要な環境変数が設定されていない場合。
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

    openh264_path = os.getenv("OPENH264_PATH")

    sendonly = Sendonly(
        signaling_urls,
        channel_id,
        metadata,
        camera_id,
        video_codec_type,
        video_bit_rate,
        video_width,
        video_height,
        video_fps,
        video_fourcc,
        openh264_path,
    )
    sendonly.run()


if __name__ == "__main__":
    sendonly()
