import signal

import cv2
import sounddevice

from sora_sdk import Sora


class SendOnly:
    def __init__(self, signaling_url, channel_id, access_token,
                 use_hardware_encoder=False, channels=1, samplerate=16000):
        self.running = True
        self.channels = channels
        self.samplerate = samplerate
        self.use_hardware_encoder = use_hardware_encoder

        self.sora = Sora(self.use_hardware_encoder)
        self.audio_source = self.sora.create_audio_source(
            self.channels, self.samplerate)
        self.video_source = self.sora.create_video_source()
        self.connection = self.sora.create_connection(
            signaling_url=signaling_url,
            role="sendonly",
            channel_id=channel_id,
            client_id="sendonly",
            metadata={'access_token': access_token},
            audio_source=self.audio_source,
            video_source=self.video_source
        )

        self.video_capture = cv2.VideoCapture(0)

    def handler(self, signum, frame):
        self.running = False

    def callback(self, indata, frames, time, status):
        self.audio_source.on_data(indata)

    def run(self):
        signal.signal(signal.SIGINT, self.handler)

        with sounddevice.InputStream(samplerate=self.samplerate, channels=self.channels,
                                     dtype='int16', callback=self.callback):
            self.connection.connect()

            while self.running:
                success, frame = self.video_capture.read()
                if not success:
                    continue
                self.video_source.on_captured(frame)

        self.connection.disconnect()
        self.video_capture.release()


if __name__ == '__main__':
    signaling_url = "signaling_url"
    channel_id = "channel_id"
    access_token = "access_token"

    sendonly = SendOnly(signaling_url, channel_id, access_token)
    sendonly.run()
