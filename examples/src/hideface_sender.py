import json
import math
import os
import platform
from pathlib import Path
from threading import Event
from typing import Any, Optional

import cv2  # type: ignore
import mediapipe as mp  # type: ignore
import numpy as np
from cv2.typing import MatLike  # type: ignore
from dotenv import load_dotenv
from PIL import Image
from sora_sdk import Sora, SoraSignalingErrorCode, SoraVideoSource


class LogoStreamer:
    """顔検出を行い、検出された顔にロゴを重ねて Sora に送信するクラス。"""

    def __init__(
        self,
        signaling_urls: list[str],
        role: str,
        channel_id: str,
        metadata: Optional[dict[str, Any]],
        camera_id: int,
        video_width: Optional[int],
        video_height: Optional[int],
        video_fps: Optional[int],
        video_fourcc: Optional[str],
    ):
        """
        LogoStreamer インスタンスを初期化します。

        このクラスは Sora への接続を設定し、カメラからのビデオフレームを処理し、
        顔検出を行い、検出された顔にロゴを重ねて Sora に送信する機能を提供します。

        :param signaling_urls: Sora シグナリング URL のリスト
        :param role: 接続ロール（"sendonly" など）
        :param channel_id: 接続するチャンネル ID
        :param metadata: 接続のためのオプションのメタデータ
        :param camera_id: 使用するカメラの ID
        :param video_width: ビデオの幅
        :param video_height: ビデオの高さ
        :param video_fps: ビデオのフレームレート
        :param video_fourcc: ビデオの FOURCC コード
        """
        self.mp_face_detection = mp.solutions.face_detection  # type: ignore

        self._sora = Sora(openh264=None)
        self._video_source: SoraVideoSource = self._sora.create_video_source()
        self._connection = self._sora.create_connection(
            signaling_urls=signaling_urls,
            role=role,
            channel_id=channel_id,
            metadata=metadata,
            video_codec_type=None,
            video_bit_rate=500,
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

        # ロゴを読み込む
        self._logo = Image.open(Path(__file__).parent.joinpath("shiguremaru.png"))

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
            timeout=self._default_connection_timeout_s
        ), "接続に失敗しました"

    def disconnect(self) -> None:
        """Sora から切断します。"""
        self._connection.disconnect()

    def _on_disconnect(self, error_code: SoraSignalingErrorCode, message: str) -> None:
        """
        切断イベントを処理します。

        :param error_code: 切断のエラーコード
        :param message: 切断メッセージ
        """
        print(f"Sora から切断されました: error_code='{error_code}' message='{message}'")
        self._connected.clear()
        self._closed = True

    def _on_set_offer(self, raw_message: str) -> None:
        """
        オファー設定イベントを処理します。

        :param raw_message: オファーを含む生のメッセージ
        """
        message = json.loads(raw_message)
        if message["type"] == "offer":
            self._connection_id = message["connection_id"]

    def _on_notify(self, raw_message: str) -> None:
        """
        Sora からの通知イベントを処理します。

        :param raw_message: 生の通知メッセージ
        """
        message = json.loads(raw_message)
        if (
            message["type"] == "notify"
            and message["event_type"] == "connection.created"
            and message["connection_id"] == self._connection_id
        ):
            print("Sora に接続しました")
            self._connected.set()

    def run(self) -> None:
        """ビデオフレームの処理と送信を行うメインループ。"""
        self.connect()
        try:
            # 顔検出を用意する
            with self.mp_face_detection.FaceDetection(
                model_selection=0, min_detection_confidence=0.5
            ) as face_detection:
                angle = 0
                while self._connected.is_set() and self._video_capture.isOpened():
                    # フレームを取得する
                    success, frame = self._video_capture.read()
                    if not success:
                        continue
                    angle = self.run_one_frame(face_detection, angle, frame)
        except KeyboardInterrupt:
            pass
        finally:
            self.disconnect()
            self._video_capture.release()

    def run_one_frame(
        self,
        face_detection: mp.solutions.face_detection.FaceDetection,  # type: ignore
        angle: int,
        frame: MatLike,  # type: ignore
    ) -> int:
        """
        1フレームの処理を行います。

        :param face_detection: 顔検出オブジェクト
        :param angle: ロゴの回転角度
        :param frame: 処理するフレーム
        :return: 更新されたロゴの回転角度
        """
        # 高速化の呪文
        frame.flags.writeable = False
        # mediapipe や PIL で処理できるように色の順序を変える
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # mediapipe で顔を検出する
        results = face_detection.process(frame)

        frame_height, frame_width, _ = frame.shape
        # PIL で処理できるように画像を変換する
        pil_image = Image.fromarray(frame)

        # ロゴを回しておく
        rotated_logo = self._logo.rotate(angle)
        angle += 1
        if angle >= 360:
            angle = 0

        if results.detections:
            for detection in results.detections:
                location = detection.location_data
                if not location.HasField("relative_bounding_box"):
                    continue
                bb = location.relative_bounding_box

                # 正規化されているので逆正規化を行う
                w_px = math.floor(bb.width * frame_width)
                h_px = math.floor(bb.height * frame_height)
                x_px = min(math.floor(bb.xmin * frame_width), frame_width - 1)
                y_px = min(math.floor(bb.ymin * frame_height), frame_height - 1)

                # 検出領域は顔に対して小さいため、顔全体が覆われるように検出領域を大きくする
                fixed_w_px = math.floor(w_px * 1.6)
                fixed_h_px = math.floor(h_px * 1.6)
                # 大きくした分、座標がずれてしまうため顔の中心になるように座標を補正する
                fixed_x_px = max(0, math.floor(x_px - (fixed_w_px - w_px) / 2))
                # 検出領域は顔であり頭が入っていないため、上寄りになるように座標を補正する
                fixed_y_px = max(0, math.floor(y_px - (fixed_h_px - h_px)))

                # ロゴをリサイズする
                resized_logo = rotated_logo.resize((fixed_w_px, fixed_h_px))
                pil_image.paste(resized_logo, (fixed_x_px, fixed_y_px), resized_logo)

        frame.flags.writeable = True
        # PIL から numpy に画像を戻す
        frame = np.array(pil_image)
        # 色の順序をもとに戻す
        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

        # WebRTC に渡す
        self._video_source.on_captured(frame)
        return angle


def hideface_sender() -> None:
    """
    環境変数を使用して LogoStreamer インスタンスを設定し実行します。

    :raises ValueError: 必要な環境変数が設定されていない場合
    """
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

    video_width = int(os.getenv("SORA_VIDEO_WIDTH", "640"))
    video_height = int(os.getenv("SORA_VIDEO_HEIGHT", "360"))
    video_fps = int(os.getenv("SORA_VIDEO_FPS", "30"))
    video_fourcc = os.getenv("SORA_VIDEO_FOURCC", "MJPG")

    camera_id = int(os.getenv("SORA_CAMERA_ID", "1"))

    streamer = LogoStreamer(
        signaling_urls=signaling_urls,
        role="sendonly",
        channel_id=channel_id,
        metadata=metadata,
        camera_id=camera_id,
        video_height=video_height,
        video_width=video_width,
        video_fps=video_fps,
        video_fourcc=video_fourcc,
    )
    streamer.run()


if __name__ == "__main__":
    hideface_sender()
