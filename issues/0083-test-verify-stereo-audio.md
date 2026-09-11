# ステレオ音声の送受信ができるかどうかを確認する

- Created: 2026-09-11
- Completed: -
- Branch: feature/test-verify-stereo-audio
- Polished: -
- Reporter: @voluntas

## 目的

Sora Python SDK でステレオ音声を送信・受信できるかどうかを実 Sora で確認する。ステレオ対応の可否を裏付ける一次資料が無く、現状のテストはすべてモノラル固定のため、実際に動くかどうかが不明である。動く / 動かないを確定させ、動く場合はその手順をテストとして残す。

## 現状

- 送信側は `Sora.create_audio_source(channels, sample_rate)` でチャンネル数を指定できる。`tests/client.py` の `SoraClient` は `audio_channels` を `create_audio_source()` に渡すが、既定値は 1 で、`_fake_audio_loop()` は `numpy.zeros((320, 1))` のモノラルしか `on_data()` していない。
- 受信側は `SoraAudioSink(track, output_frequency, output_channels)` で出力チャンネル数を指定できる。`tests/test_audio_sink_callbacks.py` は `output_channels=1` で `on_format` が `(16000, 1)` を報告することだけを確認している。`output_channels=2` を検証したテストはない。
- `audio_opus_params` で `stereo` / `sprop_stereo` を指定できる。`tests/test_opus.py` は両方 `False` にしたときの SDP (`stereo=0` / `sprop-stereo=0`) を確認しているだけで、`True` を指定したときの送受信は確認していない。
- ステレオ音声を送受信するテストは存在しない。

## 設計方針

検証のみを目的とし、現状のコードでステレオが成立するかを実 Sora で確かめる。モックやスタブは使わない。

- 送信の確認: `audio_channels=2` で `SoraAudioSource` を作り、`numpy.zeros((320, 2))` を `on_data()` する。`audio_opus_params` に `sprop_stereo: True` を指定し、offer SDP に `sprop-stereo=1` が含まれることと `outbound-rtp` の `bytesSent` / `packetsSent` が増えることを確認する。
- 受信の確認: `audio_output_channels=2` で `SoraAudioSink` を作り、`on_format(sample_rate, number_of_channels)` が 2 を報告すること、`on_data()` に渡る ndarray の shape の第 2 次元が 2 であることを確認する。
- 送受信の確認: sendrecv で接続し、入力 `(320, 2)` に対して受信側が 2 チャンネルとして受け取ることを確認する。
- 動いた場合は再現手順をテストとして追加する。動かなかった場合は、どの段階でどのような形で失敗したかを記録し、対処を別 issue に切り出す。
- `audio_channels` / `audio_output_channels` の既定値は変更しない。既存テストはモノラルのまま維持する。

## 完了条件

- ステレオの送信・受信・送受信それぞれについて、動作するかどうかが実 Sora への接続で確認されていること。
- 確認に使ったコードと手順、結果 (動いた / 動かなかった) が issue に記録されていること。
- 動いた場合は、同じ手順を再現するテストが `tests/` に追加され、実 Sora で通ること。
- 動かなかった場合は、失敗する段階と原因の切り分け結果が記録され、対処を別 issue として起票していること。
- CHANGES.md の `## develop` にエントリが追記されていること (テスト追加または対応方針が確定した場合)。

## 解決方法

1. `tests/client.py` の `audio_channels` / `audio_output_channels` を 2 にした `SoraClient` を作れる状態にし、`_fake_audio_loop()` がチャンネル数に応じた shape の ndarray を `on_data()` するようにする。
2. 送信側で `audio_channels=2` と `audio_opus_params={"sprop_stereo": True}` を指定し、offer SDP と `outbound-rtp` を確認する。
3. 受信側で `audio_output_channels=2` を指定し、`on_format` の `number_of_channels` と `on_data` の shape を確認する。
4. sendrecv で同時に確認し、結果をこの issue に記録する。
5. 結果に応じて再現テストを追加するか、対処を別 issue に切り出す。
