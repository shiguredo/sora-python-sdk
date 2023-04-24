import os
import signal

import cv2
import sounddevice

# Sora が見たらないといわれてる
from sora_sdk import Sora

use_hardware_encoder = False
channels = 1
samplerate = 16000


def test_sendonly():
    def handler(signum, frame):
        global running
        running = False

    def callback(indata, frames, time, status):
        global audio_source
        # audio_sourceが見当たらないといわれる
        audio_source.on_data(indata)

    # ここで ffmpeg で仮想カメラを作成する

    sora = Sora(use_hardware_encoder)
    audio_source = sora.create_audio_source(channels, samplerate)
    video_source = sora.create_video_source()

    signaling_url = os.environ.get('TEST_SIGNALING_URL')
    access_token = os.environ.get('TEST_ACCESS_TOKEN')
    channel_id_prefix = os.environ.get('TEST_CHANNEL_ID_PREFIX')

    connection = sora.create_connection(
        signaling_url=signaling_url,
        role="sendonly",
        channel_id=f'{channel_id_prefix}_sendonly',
        client_id="sendonly",
        metadata={'access_token': access_token},
        audio_source=audio_source,
        video_source=video_source
    )
    video_capture = cv2.VideoCapture(0)
    running = True

    signal.signal(signal.SIGINT, handler)

    with sounddevice.InputStream(samplerate=samplerate, channels=channels, dtype='int16', callback=callback):
        # ここがそもそも非同期なのがわかりやすくあってほしいかも
        # await とか付いてると嬉しそう
        connection.connect()

        while running:
            success, frame = video_capture.read()
            if not success:
                continue
            video_source.on_captured(frame)

            # キーボードで抜ける仕組み
            # expect: KeyboardInterrupt

    connection.disconnect()
    video_capture.release()
