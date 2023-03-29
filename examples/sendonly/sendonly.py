import signal

import cv2
import sounddevice
from sora_sdk import Sora

use_hardware_encoder = False
channels = 1
samplerate = 16000

sora = Sora(use_hardware_encoder)
audio_source = sora.create_audio_source(channels, samplerate)
video_source = sora.create_video_source()
connection = sora.create_connection(
    signaling_url="signaling_url",
    role="sendonly",
    channel_id="channel_id",
    client_id="sendonly",
    metadata={'access_token': 'access_token'},
    audio_source=audio_source,
    video_source=video_source
)

video_capture = cv2.VideoCapture(0)
running = True


def handler(signum, frame):
    global running
    running = False


signal.signal(signal.SIGINT, handler)


def callback(indata, frames, time, status):
    global audio_source
    audio_source.on_data(indata)


with sounddevice.InputStream(samplerate=samplerate, channels=channels, dtype='int16', callback=callback):
    connection.connect()

    while running:
        success, frame = video_capture.read()
        if not success:
            continue
        video_source.on_captured(frame)

connection.disconnect()
video_capture.release()
