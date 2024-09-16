import json
import os
import queue
from threading import Event
from typing import Any, Optional

import cv2  # type: ignore
import sounddevice  # type: ignore
from dotenv import load_dotenv
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


class Recvonly:
    """Sora からビデオと音声ストリームを受信するためのクラス。"""

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
        self._signaling_urls: list[str] = signaling_urls
        self._channel_id: str = channel_id

        self._output_frequency: int = output_frequency
        self._output_channels: int = output_channels

        self._sora: Sora = Sora(openh264=openh264_path, use_hardware_encoder=use_hwa)
        self._connection: SoraConnection = self._sora.create_connection(
            signaling_urls=signaling_urls,
            role="recvonly",
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

        self._connection.on_set_offer = self._on_set_offer
        self._connection.on_switched = self._on_switched
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
        return json.loads(raw_stats)

    @property
    def connected(self) -> bool:
        return self._connected.is_set()

    @property
    def switched(self) -> bool:
        """データチャネルシグナリングへの切り替えが完了しているかどうかを示すブール値。"""
        return self._switched

    @property
    def closed(self):
        """接続が閉じられているかどうかを示すブール値。"""
        return self._closed.is_set()

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
        self._closed.is_set()

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


def recvonly() -> None:
    """
    環境変数を使用して Recvonly インスタンスを設定し実行します。

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

    openh264_path = os.getenv("OPENH264_PATH")

    use_hwa = bool(os.getenv("USE_HWA", "True"))

    recvonly = Recvonly(
        signaling_urls, channel_id, metadata=metadata, openh264_path=openh264_path, use_hwa=use_hwa
    )
    recvonly.run()


if __name__ == "__main__":
    recvonly()
