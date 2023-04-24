import os
import signal
import threading
import time

import cv2
import pytest
import sounddevice

from sora_sdk import Sora


class Sendonly:
    def __init__(self):
        self.use_hardware_encoder = False
        self.channels = 1
        self.samplerate = 16000
        self.running = True

    def handler(self, signum, frame):
        self.running = False

    def callback(self, indata, frames, time, status):
        self.audio_source.on_data(indata)

    def stop(self):
        self.running = False

    def run(self):
        sora = Sora(self.use_hardware_encoder)
        self.audio_source = sora.create_audio_source(
            self.channels, self.samplerate)
        video_source = sora.create_video_source()
        connection = sora.create_connection(
            signaling_url=os.environ.get("TEST_SIGNALING_URL"),
            role="sendonly",
            channel_id=os.environ.get("TEST_CHANNEL_ID_PREFIX"),
            client_id="sendonly",
            metadata={'access_token': os.environ.get("TEST_SECRET_KEY")},
            audio_source=self.audio_source,
            video_source=video_source
        )

        video_capture = cv2.VideoCapture(0)

        signal.signal(signal.SIGINT, self.handler)

        with sounddevice.InputStream(samplerate=self.samplerate, channels=self.channels, dtype='int16', callback=self.callback):
            connection.connect()

            while self.running:
                success, frame = video_capture.read()
                if not success:
                    continue
                video_source.on_captured(frame)

        connection.disconnect()
        video_capture.release()


@pytest.mark.timeout(10)
def test_sendonly():
    sendonly = Sendonly()
    sendonly_thread = threading.Thread(target=sendonly.run)
    sendonly_thread.start()
    time.sleep(5)
    sendonly.stop()
    sendonly_thread.join()
