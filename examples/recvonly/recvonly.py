import queue
import signal
import time

import cv2
import sounddevice

from sora_sdk import Sora, SoraAudioSink, SoraVideoSink


class Recvonly:
    def __init__(self, signaling_url, channel_id, client_id,
                 metadata, use_hardware_encoder=False,
                 output_frequency=16000, output_channels=1):
        self.use_hardware_encoder = use_hardware_encoder
        self.output_frequency = output_frequency
        self.output_channels = output_channels

        self.sora = Sora(self.use_hardware_encoder)
        self.connection = self.sora.create_connection(
            signaling_url=signaling_url,
            role="recvonly",
            channel_id=channel_id,
            client_id=client_id,
            metadata=metadata
        )

        self.disconnected = False
        self.connection.on_disconnect = self.on_disconnect

        self.audio_sink = None
        self.video_sink = None
        self.q_out = queue.Queue()

        self.connection.on_track = self.on_track

    def on_disconnect(self, ec, message):
        self.disconnected = True
        print(message)

    def on_frame(self, frame):
        self.q_out.put(frame)

    def on_track(self, track):
        if track.kind == "audio":
            self.audio_sink = SoraAudioSink(
                track, self.output_frequency, self.output_channels)
        if track.kind == "video":
            self.video_sink = SoraVideoSink(track)
            self.video_sink.on_frame = self.on_frame

    def callback(self, outdata, frames, time, status):
        if self.audio_sink is not None:
            success, data = self.audio_sink.read(frames)
            if success:
                if data.shape[0] != frames:
                    print("AUDIO_DATA_NOT_ENOUGH", data.shape, frames)
                outdata[:] = data
            else:
                print("CAN_NOT_GET_AUDIO_DATA")

    def exit_gracefully(self, signal_number, frame):
        print("\nCtrl+Cが押されました。終了します。")
        self.connection.disconnect()
        cv2.destroyAllWindows()
        exit(0)

    def run(self):
        signal.signal(signal.SIGINT, self.exit_gracefully)
        with sounddevice.OutputStream(channels=self.output_channels, callback=self.callback,
                                      samplerate=self.output_frequency, dtype='int16'):
            self.connection.connect()

            while True:
                frame = self.q_out.get()
                cv2.imshow('frame', frame.data())
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

            self.connection.disconnect()

            while not self.disconnected:
                time.sleep(0.01)

        cv2.destroyAllWindows()


if __name__ == '__main__':
    signaling_url = "signaling_url"
    channel_id = "channel_id"
    client_id = "recvonly"
    access_token = "access_token"
    metadata = {'access_token': access_token}

    recvonly = Recvonly(signaling_url, channel_id, client_id, metadata)
    recvonly.run()
