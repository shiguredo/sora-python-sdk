# 音声の取り扱いをコールバック処理に変更する

- Created: 2026-09-11
- Completed: -
- Branch: feature/change-audio-input-to-callback
- Polished: -
- Reporter: @voluntas

## 目的

音声入力の扱いを、利用者が `SoraAudioSource.on_data()` に音声データを書き込む push 型から、SDK が利用者のコールバックを呼び出す方式 (WebAudio の AudioWorklet のような形) に見直し、利用者のミスでセグフォしうる箇所をなくす。

現状の `on_data()` には `int16_t` の生ポインタを受け取るオーバーロードがあり、誤った値や不正なサイズを渡すとプロセスがクラッシュしうる。また、配列の shape やサンプルレートを利用者が自己責任で合わせる必要があり、扱いを間違えやすい。

## 現状

- `SoraAudioSource.on_data()` は 4 つのオーバーロードを持つ (`src/sora_sdk_ext.cpp`、`src/sora_audio_source.h`)。
  - `(data: int, samples_per_channel: int, timestamp: float)` と `(data: int, samples_per_channel: int)` の生ポインタ版
  - `(ndarray, timestamp: float)` と `(ndarray)` の ndarray 版
- 生ポインタ版は `int16_t*` をそのまま受け取るため、誤った値を渡すとセグフォしうる。
- 利用側は `Sora.create_audio_source(channels, sample_rate)` で作った source に対し、`sounddevice` の入力コールバックなどから自分で `on_data()` を呼ぶ必要がある (examples の sendrecv など)。
- 音声データのサンプルレートとチャンネル数は `create_audio_source()` で固定されるが、`on_data()` に渡す配列の shape がそれと一致しているかは実行時に検証されない。
- 受信側の `SoraAudioSink` には `on_data` / `on_format` コールバックがあり受信はコールバック型だが、入力側は push 型のままで非対称である。

## 設計方針

保留を解除したら、まず WebAudio (AudioWorklet の `process()` など) の音声処理モデルを調査し、次のいずれかの形を選ぶ。

- `SoraAudioSource` にコールバックを登録し、SDK 側のスレッドから一定間隔でコールバックを呼んで音声データを要求する pull 型にする。コールバックは 10 ms ごとに呼ばれるため、Python 側の処理時間と GIL の扱いを考慮する。
- 既存の push 型を残しつつ、生ポインタ版のオーバーロードを非公開または削除し、ndarray 版に shape / dtype / サンプルレートの検証を追加してセグフォしうる経路をなくす。
- `create_audio_source()` にコールバックを渡す形にし、`on_data()` の手動呼び出しを不要にする。

いずれの場合も既存の `on_data()` を削除するか非推奨として残すかを決める。後方互換を壊す場合は `feature/change-` として扱う。

## 完了条件

- 音声入力をコールバック処理で扱える、または生ポインタ版を使わずに音声を送信できる。
- 誤ったデータを渡してもプロセスがクラッシュしない。
- `tests/` に変更後の音声送信を確認するテストがある。
- 利用方法が README または docstring に記載されている。

## pending にした理由

次の点が未確定で実装方針を決められないため保留する。

- WebAudio の音声処理モデルの調査が未完了で、pull 型コールバックを Python SDK にどう落とすかが決まっていない。
- コールバックをどのスレッドからどの間隔で呼ぶか。libwebrtc の音声スレッドから Python を呼ぶ場合の GIL とリアルタイム性の扱いを決める必要がある。
- 既存の `on_data()` のオーバーロードを削除するか残すか、後方互換の扱いを決める必要がある。
- セグフォしうる具体的な経路 (生ポインタ版の誤用、shape 不一致など) の洗い出しが必要。

再開するときは reopened にしてから実装を進める。
