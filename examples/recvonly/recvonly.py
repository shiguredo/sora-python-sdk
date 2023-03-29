import queue
import time

import cv2
import sounddevice
from sora_sdk import Sora, SoraAudioSink, SoraVideoSink

use_hardware_encoder = False
output_frequency = 16000
output_channels = 2

sora = Sora(use_hardware_encoder)
connection = sora.create_connection(
    signaling_url="signaling_url",
    role="recvonly",
    channel_id="channel_id",
    client_id="recvonly",
    metadata={'access_token': 'access_token'}
)

disconnected = False


def on_disconnect(ec, message):
    global disconnected
    disconnected = True
    print(message)


connection.on_disconnect = on_disconnect

audio_sink = None
video_sink = None

q_out = queue.Queue()


def on_frame(frame):
    global q_out
    q_out.put(frame)


def on_track(track):
    global audio_sink, video_sink
    if track.kind == "audio":
        # ここで指定した output_frequency と output_channels に resampling 、 remix されて出力する
        audio_sink = SoraAudioSink(track, output_frequency, output_channels)
    if track.kind == "video":
        video_sink = SoraVideoSink(track)
        video_sink.on_frame = on_frame


def callback(outdata, frames, time, status):
    global audio_sink
    if audio_sink is not None:
        success, data = audio_sink.read(frames)
        if success:
            if data.shape[0] != frames:
                print("AUDIO_DATA_NOT_ENOUGH", data.shape, frames)
            outdata[:] = data
        else:
            print("CAN_NOT_GET_AUDIO_DATA")


connection.on_track = on_track

with sounddevice.OutputStream(channels=output_channels, callback=callback,
                              samplerate=output_frequency, dtype='int16'):
    connection.connect()

    while True:
        # frame を queue から取り出したとき何故か一度変数にしてあげないとクラッシュする
        frame = q_out.get()
        cv2.imshow('frame', frame.data())
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    connection.disconnect()

    while not disconnected:
        time.sleep(0.01)

cv2.destroyAllWindows()
