import json
import math
import signal
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from PIL import Image
from sora_sdk import Sora

mp_face_detection = mp.solutions.face_detection

sora = Sora()
video_source = sora.create_video_source()
connection = sora.create_connection(
    signaling_url="signaling_url",
    role="sendonly",
    channel_id="channel_id",
    client_id="sendonly",
    metadata=json.dumps({'access_token': 'access_token'}),
    video_source=video_source
)

video_capture = cv2.VideoCapture(0)
running = True


def handler(signum, frame):
    global running
    running = False


signal.signal(signal.SIGINT, handler)


# ロゴを読み込む
logo = Image.open(Path(__file__).parent.joinpath("shiguremaru.png"))

connection.connect()

# 顔検出を用意する
with mp_face_detection.FaceDetection(
        model_selection=0, min_detection_confidence=0.5) as face_detection:
    angle = 0
    while running and video_capture.isOpened():
        # フレームを取得する
        success, frame = video_capture.read()
        if not success:
            continue

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
        rotated_logo = logo.rotate(angle)
        angle += 1
        if angle >= 360:
            angle = 0
        if results.detections:
            for detection in results.detections:
                location = detection.location_data
                if not location.HasField('relative_bounding_box'):
                    continue
                bb = location.relative_bounding_box

                # 正規化されているので逆正規化を行う
                w_px = math.floor(bb.width * frame_width)
                h_px = math.floor(bb.height * frame_height)
                x_px = min(math.floor(bb.xmin * frame_width), frame_width - 1)
                y_px = min(math.floor(bb.ymin * frame_height),
                           frame_height - 1)

                # 検出領域は顔に対して小さいため、顔全体が覆われるように検出領域を大きくする
                fixed_w_px = math.floor(w_px * 1.6)
                fixed_h_px = math.floor(h_px * 1.6)
                # 大きくした分、座標がずれてしまうため顔の中心になるように座標を補正する
                fixed_x_px = max(0, math.floor(x_px - (fixed_w_px - w_px) / 2))
                # 検出領域は顔であり頭が入っていないため、上寄りになるように座標を補正する
                fixed_y_px = max(0, math.floor(y_px - (fixed_h_px - h_px)))

                # ロゴをリサイズする
                resized_logo = rotated_logo.resize((fixed_w_px, fixed_h_px))
                pil_image.paste(resized_logo, (fixed_x_px,
                                fixed_y_px), resized_logo)

        frame.flags.writeable = True
        # PIL から numpy に画像を戻す
        frame = np.array(pil_image)
        # 色の順序をもとに戻す
        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

        # WebRTC に渡す
        video_source.on_captured(frame)


connection.disconnect()
video_capture.release()
