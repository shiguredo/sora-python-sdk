# on_captured() / on_data() のタイムスタンプが送信に反映されるか確認する

- Created: 2026-09-11
- Completed: -
- Branch: feature/test-verify-source-timestamp
- Polished: -
- Reporter: @sile

## 目的

`SoraVideoSource.on_captured()` と `SoraAudioSource.on_data()` に指定したタイムスタンプが、実際の送信 (RTP) と録画にどう反映されるかを確認する。

録画の調査で、フレームごとに 1 時間ずつ進むようなイレギュラーなタイムスタンプを指定しても反映されず、FPS 通りの増加幅に見える事象があった。音声でも、指定したタイムスタンプがそのまま使われているとは言い切れない挙動が確認されている。指定方法の誤り、libwebrtc 側の調整、Sora の録画側の処理のどれが原因か切り分けられておらず、`on_captured()` / `on_data()` のタイムスタンプ指定がどこまで効くのかが不明である。

## 現状

- `src/sora_video_source.cpp` の `SoraVideoSource::SendFrame()` は `webrtc::VideoFrame` に `set_timestamp_us(timestamp_us)` と `set_timestamp_rtp(kMsToRtpTimestamp * timestamp_us / 1000)` を設定して `OnCapturedFrame()` に渡す。
- `src/sora_audio_source.cpp` の `SoraAudioSourceInterface::OnData()` は、渡されたタイムスタンプを 10 ms 単位に区切って `Add10MsData()` に渡し、`AudioTrackSinkInterface::OnData()` へ伝える。10 ms ずつ加算する処理と連続性の判定処理がある。
- `src/sora_video_source.h` / `src/sora_audio_source.h` の docstring は、タイムスタンプを「Python の `time.time()` で取得できるエポック秒」と説明している。libwebrtc が要求するのはモノトニッククロックであり、`time.time()` を渡すと遅延が生じるという指摘がある。
- 2024 年に `feature/fix-timestamp` ブランチで「`SoraVideoSource` で RTP Timestamp を設定しないように修正」する PR #101 と、docstring を `time.monotonic()` に直す PR #102 が出されたが、どちらもマージされずに closed になっている。
- `on_captured()` / `on_data()` のタイムスタンプの反映を確認するテストは `tests/` に無い。

## 設計方針

実 Sora を使い、タイムスタンプを変えながら送信して次の点を切り分ける。モックやスタブは使わない。

- `on_captured()` に FPS から大きく外れるタイムスタンプ (フレームごとに大きく進む / 戻る) を指定し、受信側のフレーム到着間隔、`get_stats()` の RTP タイムスタンプ、録画ファイルの時刻がどうなるかを確認する。
- `on_data()` でも、20 ms 間隔で大きく異なるタイムスタンプを指定し、受信側の音声と録画の時刻を確認する。
- 指定値の反映に Python SDK 側で RTP タイムスタンプを設定し続けるべきか、libwebrtc に任せるべきかを判断する。必要なら `feature/fix-timestamp` の変更を再検討する。
- docstring のタイムスタンプの説明を `time.monotonic()` ベースに直すか、`rtc::TimeMicros()` / `rtc::TimeMillis()` 相当のヘルパーを公開するかを決める。

## 完了条件

- `on_captured()` / `on_data()` のタイムスタンプが送信と録画に反映されるかどうかが実 Sora で確認されていること。
- 反映されない場合、どの層 (Python SDK / libwebrtc / Sora 録画) で値が変わっているかが切り分けられていること。
- 指定値の反映に必要な修正方針 (RTP タイムスタンプの設定有無、docstring の単位) が決まっていること。
- 確認結果と手順が issue に記録されていること。
- 再現テストが `tests/` に追加されている、またはテストを追加できない理由が記録されていること。

## 解決方法

1. `tests/client.py` に `on_captured()` / `on_data()` へ任意のタイムスタンプを渡せる口を追加する。
2. 送信側でイレギュラーなタイムスタンプを指定し、受信側の到着時刻と `get_stats()` の RTP タイムスタンプを記録する。
3. 録画ファイルの時刻と比較し、どの層で値が変わっているかを切り分ける。
4. 結果に応じて docstring の修正、RTP タイムスタンプ設定の見直し、再現テストの追加を別 issue に切り出す。

## pending にした理由

次の点が未確定で実装方針を決められないため保留する。

- 指定したタイムスタンプが送信・録画のどこまで反映されるのが正しい挙動なのかが未確定。
- Sora の録画側のタイムスタンプ調整処理の影響範囲が未確認で、Python SDK 側の修正だけで解決するかが分からない。
- RTP タイムスタンプを Python SDK が設定し続けるべきか、libwebrtc に任せるべきかの設計判断が必要 (PR #101 は未マージ)。
- タイムスタンプの種類 (モノトニッククロック) をどう公開するかで API 設計の判断が必要。docstring の修正で済ませるか、`rtc::TimeMicros()` / `rtc::TimeMillis()` 相当のヘルパーを公開するかを決める必要がある。

再開するときは reopened にしてから実装を進める。
