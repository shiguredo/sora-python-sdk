---
name: sora-python-sdk
description: WebRTC SFU Sora の Python クライアントライブラリ sora_sdk の利用方法リファレンス。Sora への接続 (sendonly / recvonly / sendrecv)、numpy 連携による音声・映像の送受信、データチャネルメッセージング、VAD、Encoded Transform、ビデオコーデック設定とハードウェアアクセラレーター、統計情報の取得を網羅する。sora_sdk を使ったアプリケーションを書く・レビューするときに使用する。
---

# sora-python-sdk スキル

[WebRTC SFU Sora](https://sora.shiguredo.jp/) の Python クライアントアプリケーションを開発するためのライブラリ `sora_sdk` の利用方法リファレンス。SDK 利用者（アプリケーション開発者）向け。

- リポジトリ: <https://github.com/shiguredo/sora-python-sdk>
- ドキュメント: <https://sora-python-sdk.shiguredo.jp/>
- サンプル集: <https://github.com/shiguredo/sora-python-sdk-examples>

## 概要

- [Sora C++ SDK](https://github.com/shiguredo/sora-cpp-sdk) ベースの nanobind バインディング
- 音声・映像デバイスの処理を SDK から独立させているため、sounddevice や opencv-python など任意のライブラリと組み合わせられる
- 音声・映像データは numpy の ndarray でやり取りする
- コールバック駆動。コールバックは SDK 内部のスレッドから呼ばれる
- Python は直近 3 バージョン、Sora は直近 2 バージョンをサポートする（具体的なバージョンは README を参照）

## インストール

```bash
# 通常のプラットフォーム (Ubuntu / macOS / Windows)
uv add sora_sdk

# Raspberry Pi OS 向け (libcamera 対応の create_libcamera_source が使える)
uv add sora_sdk_rpi
```

NVIDIA Jetson 向けは PyPI からインストールできない。GitHub Releases で配布されるパッケージバイナリを利用する。

## クラス構成

| クラス | 役割 |
| --- | --- |
| `Sora` | ファクトリー。ここから接続やソースを生成する |
| `SoraConnection` | Sora との接続。`connect()` / `disconnect()` / コールバック設定 |
| `SoraAudioSource` / `SoraVideoSource` | 送信用トラック。ndarray を渡して送信する |
| `SoraAudioSink` / `SoraAudioStreamSink` / `SoraVideoSink` | 受信用シンク。受信トラックから ndarray を取り出す |
| `SoraMediaTrack` | `on_track` で渡される受信トラック |
| `SoraVAD` | 発話区間検出 |
| `SoraAudioFrameTransformer` / `SoraVideoFrameTransformer` | Encoded Transform |

## 接続の基本フロー

1. `Sora()` を生成する
2. 送信するなら `create_audio_source()` / `create_video_source()` でソースを生成する
3. `create_connection()` で `SoraConnection` を生成する
4. コールバックを設定する
5. `connect()` を呼ぶ
6. 接続完了を待つ（`on_notify` の `connection.created` で判定するのが定石）
7. 終了時は必ず `disconnect()` を呼ぶ

`connect()` は非同期でシグナリングを開始するだけで、完了を待たない。接続完了の判定は `threading.Event` と `on_notify` を組み合わせる。

```python
import json
from threading import Event

from sora_sdk import Sora

sora = Sora()

connection = sora.create_connection(
    signaling_urls=["wss://sora.example.com/signaling"],
    role="recvonly",
    channel_id="sora",
    metadata={"access_token": "..."},
    audio=True,
    video=True,
)

connected = Event()
connection_id = None


def on_set_offer(raw_message: str) -> None:
    global connection_id
    message = json.loads(raw_message)
    if message["type"] == "offer":
        # 自身の connection_id は offer から取得する
        connection_id = message["connection_id"]


def on_notify(raw_message: str) -> None:
    message = json.loads(raw_message)
    # 自身の connection.created で接続完了と判定する
    if (
        message["type"] == "notify"
        and message["event_type"] == "connection.created"
        and message["connection_id"] == connection_id
    ):
        connected.set()


connection.on_set_offer = on_set_offer
connection.on_notify = on_notify

connection.connect()
assert connected.wait(30), "Sora に接続できなかった"

# ... 処理 ...

connection.disconnect()
```

## create_connection の主要パラメータ

`Sora.create_connection()` は Sora のシグナリング `"type": "connect"` のパラメータをキーワード引数で受け取る。主要なもの:

- `signaling_urls: list[str]`: シグナリング URL（必須）
- `role: str`: `"sendonly"` / `"recvonly"` / `"sendrecv"`（必須）
- `channel_id: str`: チャネル ID（必須）
- `client_id` / `bundle_id`: 任意の識別子
- `metadata: dict`: 認証用メタデータ。アクセストークンは `{"access_token": token}` のように渡す
- `audio: bool` / `video: bool`: 音声・映像の有効化
- `audio_source` / `video_source`: 送信用ソース（送信する場合は必須）
- `audio_codec_type: str`: `"OPUS"` など
- `video_codec_type: str`: `"VP8"` / `"VP9"` / `"AV1"` / `"H264"` / `"H265"`
- `video_bit_rate: int` / `audio_bit_rate: int`
- `video_vp9_params` / `video_av1_params` / `video_h264_params` / `video_h265_params` / `audio_opus_params`: コーデック固有パラメータ (dict)
- `simulcast: bool` / `simulcast_rid: str`: サイマルキャスト
- `spotlight: bool` / `spotlight_number: int`: スポットライト
- `forwarding_filters: list[dict]`: 転送フィルター
- `data_channels: list[dict]`: メッセージング用データチャネル定義
- `data_channel_signaling: bool` / `ignore_disconnect_websocket: bool`: データチャネルシグナリング
- `audio_frame_transformer` / `video_frame_transformer`: Encoded Transform
- `degradation_preference: SoraDegradationPreference`: `DISABLED` / `BALANCED` / `MAINTAIN_FRAMERATE` / `MAINTAIN_RESOLUTION`
- `client_cert` / `client_key` / `ca_cert`: mTLS / 独自 CA 証明書 (bytes)
- `proxy_url` / `proxy_username` / `proxy_password`: プロキシ

## SoraConnection のコールバック

コールバックはプロパティへの代入で設定する。`connect()` の前に設定すること。

| コールバック | シグネチャ | 発火タイミング |
| --- | --- | --- |
| `on_set_offer` | `(raw_message: str)` | offer 受信時。connection_id の取得に使う |
| `on_notify` | `(raw_message: str)` | Sora からの notify 受信時 |
| `on_push` | `(raw_message: str)` | Sora からの push 受信時 |
| `on_track` | `(track: SoraMediaTrack)` | 受信トラック追加時 |
| `on_data_channel` | `(label: str)` | データチャネル準備完了時 |
| `on_message` | `(label: str, data: bytes)` | データチャネルメッセージ受信時 |
| `on_disconnect` | `(error_code: SoraSignalingErrorCode, message: str)` | 切断時 |
| `on_switched` | `(raw_message: str)` | データチャネルシグナリングへの切り替え完了時 |
| `on_ws_close` | `(code: int, reason: str)` | WebSocket クローズ時 |
| `on_signaling_message` | `(type: SoraSignalingType, direction: SoraSignalingDirection, raw_message: str)` | シグナリングメッセージ送受信の観測 |
| `on_rpc` | `(data: bytes)` | RPC メッセージ受信時 |

raw_message はいずれも JSON 文字列なので `json.loads()` して使う。

## 音声の送信

`create_audio_source(channels, sample_rate)` でソースを作り、`on_data()` に `numpy.int16` の ndarray を渡す。shape は `(サンプル数, チャネル数)`。

```python
import numpy

# 1 チャネル 16kHz の音声ソース
audio_source = sora.create_audio_source(channels=1, sample_rate=16000)

connection = sora.create_connection(
    ...,
    role="sendonly",
    audio=True,
    audio_source=audio_source,
)

# 16kHz の 20ms 分 (320 サンプル) を送信する
samples = numpy.zeros((320, 1), dtype=numpy.int16)
audio_source.on_data(samples)
```

タイムスタンプを自分で管理する場合は `on_data(ndarray, timestamp)` を使う。

## 映像の送信

`create_video_source()` でソースを作り、`on_captured()` に `numpy.uint8` の ndarray を渡す。shape は `(高さ, 幅, 3)` で色順は BGR（opencv-python と同じ）。

```python
video_source = sora.create_video_source()

connection = sora.create_connection(
    ...,
    role="sendonly",
    video=True,
    video_source=video_source,
)

# 480x640 のフレームを送信する
frame = numpy.zeros((480, 640, 3), dtype=numpy.uint8)
video_source.on_captured(frame)
```

タイムスタンプを自分で管理する場合は `on_captured(ndarray, timestamp)`（float 秒）または `on_captured(ndarray, timestamp_us)`（int マイクロ秒）を使う。

### Raspberry Pi の libcamera ソース

`sora_sdk_rpi` パッケージでは libcamera からの直接キャプチャーが使える。

```python
video_source = sora.create_libcamera_source(
    width=640,
    height=480,
    fps=30,
    # True にするとハードウェアエンコーダーへゼロコピーでフレームを渡す
    native_frame_output=False,
)
```

## 音声・映像の受信

受信トラックは `on_track` コールバックで渡される。`track.kind` (`"audio"` / `"video"`) で判別し、シンクを生成する。

```python
from sora_sdk import SoraAudioSink, SoraMediaTrack, SoraVideoFrame, SoraVideoSink

audio_sink = None
video_sink = None


def on_video_frame(frame: SoraVideoFrame) -> None:
    # data() は (高さ, 幅, 3) の numpy.uint8 (BGR)
    ndarray = frame.data()
    ...


def on_track(track: SoraMediaTrack) -> None:
    global audio_sink, video_sink
    # シンクはコールバックを抜けても参照が残るよう外側で保持する
    if track.kind == "audio":
        audio_sink = SoraAudioSink(track, output_frequency=16000, output_channels=1)
    if track.kind == "video":
        video_sink = SoraVideoSink(track)
        video_sink.on_frame = on_video_frame


connection.on_track = on_track
```

### SoraAudioSink: pull 型の音声受信

`read()` で内部バッファーから読み出す。戻り値は `(成功したか, ndarray または None)` のタプル。

```python
# 1024 フレーム貯まるまで最大 1 秒待って読み出す
success, ndarray = audio_sink.read(frames=1024, timeout=1.0)
if success:
    # ndarray は (フレーム数, チャネル数) の numpy.int16
    ...

# frames=0 (デフォルト) なら貯まっている分を全部読み出す
success, ndarray = audio_sink.read()
```

`read()` は待機中に GIL を解放するため、他の Python スレッドの実行を妨げない。

### SoraAudioStreamSink: push 型の音声受信

フレームが届くたびに `on_frame(SoraAudioFrame)` が呼ばれる。`SoraAudioFrame` は `data()` (ndarray) のほか `sample_rate_hz` / `num_channels` / `samples_per_channel` / `absolute_capture_timestamp_ms` を持つ。VAD と組み合わせる場合はこちらを使う。

### SoraVideoSink: 映像受信

フレームが届くたびに `on_frame(SoraVideoFrame)` が呼ばれる。`SoraVideoFrame.data()` で ndarray を取り出す。

## データチャネルメッセージング

`data_channels` にラベルと方向を指定して接続する。ラベルは `#` から始める。direction は自分から見た方向 (`"sendonly"` / `"recvonly"` / `"sendrecv"`)。

```python
connection = sora.create_connection(
    ...,
    data_channels=[{"label": "#chat", "direction": "sendrecv"}],
)


def on_data_channel(label: str) -> None:
    # このラベルのデータチャネルが送信可能になった
    ...


def on_message(label: str, data: bytes) -> None:
    # メッセージを受信した
    ...


connection.on_data_channel = on_data_channel
connection.on_message = on_message
```

送信は `send_data_channel()`。対象ラベルの `on_data_channel` が発火する前に呼ぶと失敗するため、`threading.Event` などで準備完了を待ってから送る。

```python
connection.send_data_channel("#chat", b"hello")
```

メッセージングのみの利用（音声・映像なし）は `audio=False, video=False` と `role="sendonly"` で接続する。

## VAD (発話区間検出)

`SoraAudioStreamSink` と組み合わせて使う。`analyze()` は音声である確率 (0.0 - 1.0) を返す。

```python
from sora_sdk import SoraAudioFrame, SoraVAD

vad = SoraVAD()


def on_frame(frame: SoraAudioFrame) -> None:
    voice_probability = vad.analyze(frame)
    if voice_probability > 0.95:  # 0.95 は libwebrtc の判定値
        # 発話中
        ...
```

## Encoded Transform

エンコード済みフレームを送受信の途中で加工できる。トランスフォーマーを生成して `on_transform` を設定し、`create_connection()` に渡す。

```python
import numpy

from sora_sdk import SoraTransformableVideoFrame, SoraVideoFrameTransformer

video_transformer = SoraVideoFrameTransformer()


def on_transform(frame: SoraTransformableVideoFrame) -> None:
    # エンコード済みデータの取得と書き換え
    data = numpy.copy(frame.get_data())
    ...  # data を加工する
    frame.set_data(data)
    # 処理し終えたフレームは必ず enqueue でパイプラインに戻す
    video_transformer.enqueue(frame)


video_transformer.on_transform = on_transform

connection = sora.create_connection(
    ...,
    video_frame_transformer=video_transformer,
)
```

- 音声は `SoraAudioFrameTransformer` と `SoraTransformableAudioFrame` を使う
- `on_transform` に渡されたフレームを `enqueue()` しないとメディアが流れない
- 以後の変換が不要になったら `start_short_circuiting()` を呼ぶとトランスフォーマーをバイパスできる
- フレームには `payload_type` / `ssrc` / `rtp_timestamp` / `mime_type` などのメタデータがあり、映像は `is_key_frame` / `width` / `height` / `spatial_index` / `temporal_index` も参照できる

## ビデオコーデックとハードウェアアクセラレーター

### 利用可能なコーデックの確認

```python
from sora_sdk import get_video_codec_capability

capability = get_video_codec_capability()
for engine in capability.engines:
    # engine.name は SoraVideoCodecImplementation
    for codec in engine.codecs:
        # codec.type / codec.encoder / codec.decoder で対応状況が分かる
        print(engine.name, codec.type, codec.encoder, codec.decoder)
```

`SoraVideoCodecImplementation` は `INTERNAL` (libwebrtc ソフトウェア) / `CISCO_OPENH264` / `INTEL_VPL` / `NVIDIA_VIDEO_CODEC_SDK` / `AMD_AMF` / `RASPI_V4L2M2M`。

### 利用するコーデック実装の指定

```python
from sora_sdk import (
    Sora,
    SoraVideoCodecImplementation,
    SoraVideoCodecPreference,
    SoraVideoCodecType,
)

# H.264 のエンコード・デコードに NVIDIA Video Codec SDK を使う
preference = SoraVideoCodecPreference(
    codecs=[
        SoraVideoCodecPreference.Codec(
            type=SoraVideoCodecType.H264,
            encoder=SoraVideoCodecImplementation.NVIDIA_VIDEO_CODEC_SDK,
            decoder=SoraVideoCodecImplementation.NVIDIA_VIDEO_CODEC_SDK,
        )
    ]
)
sora = Sora(video_codec_preference=preference)
```

特定実装に寄せた preference は `create_video_codec_preference_from_implementation(capability, implementation)` でも生成できる。

### OpenH264

H.264 のソフトウェアエンコード・デコードには OpenH264 の共有ライブラリを指定する。

```python
sora = Sora(openh264="/path/to/libopenh264.so")
```

## 統計情報

`get_stats()` は [WebRTC 統計情報](https://www.w3.org/TR/webrtc-stats/) の JSON 文字列を返す。

```python
import json

stats = json.loads(connection.get_stats())
outbound_rtp = [s for s in stats if s.get("type") == "outbound-rtp"]
```

## ログ

libwebrtc のログを標準エラー出力に出せる。デバッグ時のみ有効化する。

```python
from sora_sdk import SoraLoggingSeverity, enable_libwebrtc_log

enable_libwebrtc_log(SoraLoggingSeverity.INFO)
```

## 注意点・よくある間違い

- **参照を保持し続けること**: `Sora` / `SoraConnection` / ソース / シンクは接続中ずっと参照を保持する。特に `on_track` 内で作ったシンクをローカル変数にすると GC されて受信が止まる
- **コールバックは SDK 内部スレッドから呼ばれる**: コールバック内でブロッキングや重い処理をしない。`queue.Queue` や `threading.Event` でアプリケーション側のスレッドに渡すのが定石
- **`connect()` は完了を待たない**: 接続完了は `on_notify` の `connection.created`（自身の connection_id と一致するもの）で判定する
- **`send_data_channel()` は準備完了後に呼ぶ**: 対象ラベルの `on_data_channel` 発火を待ってから送信する
- **`disconnect()` を必ず呼ぶ**: 例外時も含めて確実に切断する。`try` / `finally` やコンテキストマネージャーで管理する
- **ndarray の形式を守る**: 音声は `numpy.int16` の `(サンプル数, チャネル数)`、映像は `numpy.uint8` の `(高さ, 幅, 3)` (BGR) で C 連続 (order='C') であること
- **1 つの `Sora` から複数接続を作れる**: 複数チャネルへの同時接続は `create_connection()` を複数回呼ぶ
