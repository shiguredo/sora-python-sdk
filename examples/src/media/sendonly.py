import json
import os
import platform
from threading import Event
from typing import Any, Dict, List, Optional

import cv2
import sounddevice
from dotenv import load_dotenv
from numpy import ndarray
from sora_sdk import Sora, SoraConnection, SoraSignalingErrorCode


class Sendonly:
    def __init__(
        self,
        # python 3.8 まで対応なので list[str] ではなく List[str] にする
        signaling_urls: List[str],
        channel_id: str,
        metadata: Optional[Dict[str, Any]],
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
        self.audio_channels = audio_channels
        self.audio_sample_rate = audio_sample_rate

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
        self._connection_id = ""
        self._connected = Event()
        self._closed = False
        self._default_connection_timeout_s = 10.0

        self._connection.on_set_offer = self._on_set_offer
        self._connection.on_notify = self._on_notify
        self._connection.on_disconnect = self._on_disconnect

        if platform.system() == "Windows":
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

    def connect(self):
        self._connection.connect()

        assert self._connected.wait(
            timeout=self._default_connection_timeout_s
        ), "接続がタイムアウトしました"

    def disconnect(self):
        self._connection.disconnect()

    def _on_notify(self, raw_message: str):
        message: Dict[str, Any] = json.loads(raw_message)
        # "type": "notify" の "connection.created" で通知される connection_id が
        # 自分の connection_id と一致する場合に接続完了とする
        if (
            message["type"] == "notify"
            and message["event_type"] == "connection.created"
            and message["connection_id"] == self._connection_id
        ):
            print("Sora に接続しました")
            self._connected.set()

    def _on_set_offer(self, raw_message: str):
        message: Dict[str, Any] = json.loads(raw_message)
        if message["type"] == "offer":
            # "type": "offer" に入ってくる自分の connection_id を保存する
            self._connection_id = message["connection_id"]

    def _on_disconnect(self, error_code: SoraSignalingErrorCode, message: str):
        print(f"Sora から切断されました: error_code='{error_code}' message='{message}'")
        self._connected.clear()
        self._closed = True

    def _callback(self, indata: ndarray, frames: int, time, status: sounddevice.CallbackFlags):
        self._audio_source.on_data(indata)

    def run(self):
        # 音声デバイスの入力を Sora に送信する設定
        with sounddevice.InputStream(
            samplerate=self.audio_sample_rate,
            channels=self.audio_channels,
            dtype="int16",
            callback=self._callback,
        ):
            self.connect()
            try:
                while self._connected.is_set():
                    # 取得したフレームを Sora に送信する
                    success, frame = self._video_capture.read()
                    if not success:
                        continue
                    self._video_source.on_captured(frame)
            except KeyboardInterrupt:
                pass
            finally:
                self.disconnect()
                self._video_capture.release()


def sendonly():
    # .env ファイルを読み込む
    load_dotenv()

    # 必須引数
    if not (raw_signaling_urls := os.getenv("SORA_SIGNALING_URLS")):
        raise ValueError("環境変数 SORA_SIGNALING_URLS が設定されていません")
    signaling_urls = raw_signaling_urls.split(",")

    if not (channel_id := os.getenv("SORA_CHANNEL_ID")):
        raise ValueError("環境変数 SORA_CHANNEL_ID が設定されていません")

    # オプション引数
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
