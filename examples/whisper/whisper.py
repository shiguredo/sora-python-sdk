import math
import signal
import time

import numpy as np
import whispercpp as whisper

from sora_sdk import Sora, SoraAudioSink


class RealTimeRecognition:
    def __init__(
        self,
        signaling_url,
        channel_id,
        access_token,
        number_of_process=8,
        step_ms=5000,
        length_ms=10000,
        keep_ms=10000,
    ):
        # スレッド数を指定します
        # 実コア数 - 2 をお勧めします
        self.number_of_process = number_of_process

        # おおよそ何ミリ秒ごとに認識を行うかを指定します
        # この値を大きくすると処理の頻度が増えますが、次の認識に間に合わなくなる可能性があります
        # 認識にかかる時間よりも小さくしてください、この時間の倍の時間認識にかかると音が破棄されます
        self.step_ms = step_ms

        # 認識する音の長さをミリ秒で指定します
        # 先に認識をかけた音のうち次の認識でも使う長さをミリ秒で指定します
        # この値を大きくすると認識結果の重複は多くなりますが精度が向上します
        self.length_ms = length_ms

        # 先に認識をかけた音のうち次の認識でも使う長さをミリ秒で指定します
        self.keep_ms = keep_ms

        # 変更しないでください
        self.sample_rate = 16000
        self.n_samples_step = math.floor(
            self.sample_rate * self.step_ms / 1000)
        self.n_samples_length = math.floor(
            self.sample_rate * self.length_ms / 1000)
        self.n_samples_keep = math.floor(
            self.sample_rate * self.keep_ms / 1000)

        self.signaling_url = signaling_url
        self.channel_id = channel_id
        self.access_token = access_token

        self.running = True
        self.disconnected = False
        self.audio_sink = None

    def initialize_whisper(self):
        print("### 初期化中...(初回の場合は時間がかかります) ###")
        params = (
            whisper.api.Params.from_enum(whisper.api.SAMPLING_GREEDY)
            .with_print_progress(False)
            .with_print_realtime(False)
            .with_language("ja")
            .with_num_threads(self.number_of_process)
            .build()
        )
        # M2 MacBook Air の場合は small までいけました
        # Coffee Lake の Core i7 では base が限界でした
        self.w = whisper.Whisper.from_params("small", params=params)

    def initialize_sora(self):
        self.sora = Sora(False)
        self.connection = self.sora.create_connection(
            signaling_url=self.signaling_url,
            role="recvonly",
            channel_id=self.channel_id,
            client_id="recvonly",
            metadata={'access_token': self.access_token}
        )

        signal.signal(signal.SIGINT, self.handler)

        self.connection.on_disconnect = self.on_disconnect
        self.connection.on_track = self.on_track

    def handler(self, signum, frame):
        self.running = False

    def on_disconnect(self, ec, message):
        self.disconnected = True
        print(message)

    def on_track(self, track):
        if track.kind == "audio":
            self.audio_sink = SoraAudioSink(track, self.sample_rate, 1)
            print("### 認識開始 ###")

    def run(self):
        self.initialize_whisper()
        self.initialize_sora()

        print("### 接続中... ###")
        self.connection.connect()

        # 以下を参考に実装した
        # https://github.com/ggerganov/whisper.cpp/blob/478289a4b393904b91df06e0b1ec7552ba25a338/examples/stream/stream.cpp

        new_data = None
        keep_data = None
        while self.running and not self.disconnected:
            if self.audio_sink is None:
                time.sleep(0.01)
                continue
            success, input_data = self.audio_sink.read()
            if not success:
                time.sleep(0.01)
                continue
            if new_data is None:
                new_data = input_data
            else:
                new_data = np.concatenate([new_data, input_data])

            if not self.running or self.disconnected:
                break
            if new_data.shape[0] < self.n_samples_step:
                time.sleep(0.01)
                continue
            if new_data.shape[0] > 2 * self.n_samples_step:
                print("リアルタイムで処理できる性能が無いため処理ができませんでした")
                new_data = None
                keep_data = None
                continue

        n_samples_new = new_data.shape[0]
        new_data_transformed = new_data.flatten().astype(np.float32) / 32768.0

        if keep_data is not None:
            n_samples_take = min([keep_data.shape[0], max(
                [0, self.n_samples_keep + self.n_samples_length - n_samples_new])])
            new_data_transformed = np.concatenate(
                [keep_data[0 - n_samples_take:], new_data_transformed])
        text = self.w.transcribe(new_data_transformed)
        print("認識結果:", text)
        keep_data = new_data_transformed[0 - self.n_samples_keep:].copy()
        new_data = None

        self.connection.disconnect()

        while not self.disconnected:
            time.sleep(0.01)


if __name__ == "main":
    real_time_recognition = RealTimeRecognition(
        signaling_url="signaling_url",
        channel_id="channel_id",
        access_token="access_token"
    )
    real_time_recognition.run()
