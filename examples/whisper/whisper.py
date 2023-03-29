import math
import signal
import time

import numpy as np
import whispercpp as whisper

from sora_sdk import Sora, SoraAudioSink

# whispercpp の設定

# スレッド数を指定します
# 実コア数 - 2 をお勧めします
number_of_process = 8

# おおよそ何ミリ秒ごとに認識を行うかを指定します
# この値を大きくすると処理の頻度が増えますが、次の認識に間に合わなくなる可能性があります
# 認識にかかる時間よりも小さくしてください、この時間の倍の時間認識にかかると音が破棄されます
step_ms = 5000

# 認識する音の長さをミリ秒で指定します
# この値を大きくすると処理時間もかかりますが精度が向上します
# length_ms - step_ms 分を keep_ms から使うため
# この値だけでなく step_ms や keep_ms も長くしてください
length_ms = 10000

# 先に認識をかけた音のうち次の認識でも使う長さをミリ秒で指定します
# この値を大きくすると認識結果の重複は多くなりますが精度が向上します
keep_ms = 10000


keep_ms = min(keep_ms, step_ms)
length_ms = max(length_ms, step_ms)

# 変更しないでください
sample_rate = 16000

n_samples_step = math.floor(sample_rate * step_ms / 1000)
n_samples_length = math.floor(sample_rate * length_ms / 1000)
n_samples_keep = math.floor(sample_rate * keep_ms / 1000)

print("### 初期化中...(初回の場合は時間がかかります) ###")
params = (
    whisper.api.Params.from_enum(whisper.api.SAMPLING_GREEDY)
    .with_print_progress(False)
    .with_print_realtime(False)
    .with_language("ja")
    .with_num_threads(number_of_process)
    .build()
)

# M2 MacBook Air の場合は small までいけました
# Coffee Lake の Core i7 では base が限界でした
w = whisper.Whisper.from_params("small", params=params)

# Sora の設定

use_hardware_encoder = False

sora = Sora(use_hardware_encoder)
connection = sora.create_connection(
    signaling_url="signaling_url",
    role="recvonly",
    channel_id="channel_id",
    client_id="recvonly",
    metadata={'access_token': 'access_token'}
)


running = True


def handler(signum, frame):
    global running
    running = False


signal.signal(signal.SIGINT, handler)


disconnected = False


def on_disconnect(ec, message):
    global disconnected
    disconnected = True
    print(message)


connection.on_disconnect = on_disconnect

audio_sink = None


def on_track(track):
    global audio_sink
    if track.kind == "audio":
        audio_sink = SoraAudioSink(track, sample_rate, 1)
        print("### 認識開始 ###")


connection.on_track = on_track

print("### 接続中... ###")
connection.connect()

# 以下を参考に実装した
# https://github.com/ggerganov/whisper.cpp/blob/478289a4b393904b91df06e0b1ec7552ba25a338/examples/stream/stream.cpp

new_data = None
keep_data = None
while running and not disconnected:
    if audio_sink is None:
        time.sleep(0.01)
        continue
    success, input_data = audio_sink.read()
    if not success:
        time.sleep(0.01)
        continue
    if new_data is None:
        new_data = input_data
    else:
        new_data = np.concatenate([new_data, input_data])
    if not running or disconnected:
        break
    if new_data.shape[0] < n_samples_step:
        time.sleep(0.01)
        continue
    if new_data.shape[0] > 2*n_samples_step:
        print("リアルタイムで処理できる性能が無いため処理ができませんでした")
        new_data = None
        keep_data = None
        continue
    n_samples_new = new_data.shape[0]

    new_data_transformed = new_data.flatten().astype(np.float32) / 32768.0

    if keep_data is not None:
        n_samples_take = min([keep_data.shape[0], max(
            [0, n_samples_keep + n_samples_length - n_samples_new])])
        new_data_transformed = np.concatenate(
            [keep_data[0-n_samples_take:], new_data_transformed])
    text = w.transcribe(new_data_transformed)
    print("認識結果:", text)
    keep_data = new_data_transformed[0-n_samples_keep:].copy()
    new_data = None

connection.disconnect()

while not disconnected:
    time.sleep(0.01)
