# プロトタイプのメモ

sora-rust-sdk ベースへの切り替え可否を判断するための試行記録である。

## 依存先

- リポジトリ: https://github.com/shiguredo/sora-rust-sdk
- クレート: `sora_sdk` (crates.io)
- 利用版: `2026.2.0-canary.2` (試行時点の最新。安定版の最新は `2026.1.0`)
- 同梱解決された主な版 (`Cargo.lock` より):
  - `shiguredo_webrtc` は `0.152.1-canary.3`
  - `pyo3` は `0.29.2`
  - `tokio` は `1.53.1`
- ビルドバックエンド: `maturin==1.14.1` (試行時点の最新)
- ライセンス: Apache-2.0 (sora_sdk、プロトタイプともに)

## 版参照手段

- Python からは `sora_rust_sdk.__version__` でプロトタイプ自体の版を参照する。
- sora_sdk 側に公開の版取得 API はない (`src/version.rs` は `pub(crate)` のみ)。
  そのため依存版は `Cargo.lock` に記録する運用とする。

## モジュール名

- 拡張モジュール名は `sora_rust_sdk` とした。
- 既存パッケージ `sora_sdk` と同名にすると import が衝突するため避けた。
- 全面移行時は `sora_sdk` 名の扱いを別途決める必要がある。

## `gil_used = false` の判定

- `#[pymodule(gil_used = false)]` を付けた。
- 理由: イベントハンドラは空実装で Python に触れず、blocking な接続処理は
  `Python::detach` で GIL を外して実行し、sora_sdk 側コールバックも
  Rust / tokio スレッド内で完結するため。

## sora_sdk の API 対応メモ

- 接続の組み立ては `SoraConnectionContext::new`、
  `SoraConnection::builder`、`build`、`connection.run` の順で行う。
- ロールは `Role::parse` で `"sendonly"` / `"recvonly"` / `"sendrecv"` を受けられる。
- 認証に access_token 概念はなく、JWT は `metadata` の JSON に載せる
  (既存 E2E と同じく `{"access_token": ...}` 形式)。
  JSON 文字列の検証には `JsonString` の `FromStr` を使う。
- イベントハンドラは `SoraConnectionEventHandler` を空実装するだけでよい
  (全メソッドにデフォルト空実装あり。実装型に要求されるのは `Send` のみ)。
- 切断は `SoraConnectionHandle::disconnect` を別タスクから呼ぶ。
  `run` は切断までブロックするため、指定秒数後に切断するタスクを spawn した。
- ランタイムは sora_sdk の利用例と同じ current-thread を使った。

## Python SDK との差分と困り度

### 2. VAD: 本プロトタイプでは対応しない

- `sora_sdk` / `shiguredo_webrtc` のどちらにも VAD のバインディングはない。
- 別クレート利用か自前実装かの判断が要るため、本プロトタイプの対象外とし、
  後続 issue で扱う。利用実態の棚卸しと方式選定が先になる。

### 1. Sink / フレーム受け渡し: 困り度 中 (受信経路は実証済み)

- 音声は `AudioTrackSinkHandler::on_data` で生 PCM が流れることを実証した。
  実マイク構成 (`AdmConfig::UseBuiltIn`) のループバックで 980 フレーム、
  48 kHz mono を受信した。既定構成 (`AdmConfig::NoAudioDevice`) では
  送信側が無音のため何も流れない。ヘッドレス検証には fake ADM が要る。
  (追記: 正確には受信引き抜きの駆動不足が原因で、後述の偽デバイスで解決した。
  詳細は「音声ミキサー駆動」の節を見ること)
- 映像は `VideoSinkHandler::on_frame` で `VideoFrameRef` が流れることを実証した。
  440 フレーム受信し、寸法 320x240 を取得、`to_i420` と `convert_from_i420` で
  ARGB 変換した結果を numpy 配列として開けることをテストで確認した。
- 残作業は現行相当の付加機能 (リサンプル出力周波数、`read` のタイムアウト、
  ndarray 所有権管理) の自前設計と性能検討である。

### 3. Frame transformer: 困り度 中 (encoded 層は実証済み)

- `sender_video_transform` に通過計数ハンドラを付けて 440 フレームの
  `transform` 呼び出しを実証した。ハンドラには `Send + Sync` が要求され、
  エンコーダー / ネットワークスレッド上で呼ばれる。
- デコード済み numpy 加工が要る用途は Sink 経由の自前実装になる。
  送信側への差し戻しは source 側の実装も要る。利用実態の棚卸しが先になる。

### 4. ログ制御: 困り度 低 (到達可能と実証済み)

- 当初の「代替できる」も、その後の「到達できない」も正確ではなかった。
  正しくは `shiguredo_webrtc::log` モジュール (`LoggingConfig` / `Severity` /
  `LogSink` / `LogSinkHandler` / `initialize_logging` / `print`) が
  クレート直下に再 export されており、外部から使える。
  (`mod rtc_base` 自体は非公開だが、`log` モジュールが再 export 対象に含まれる)
- `logging_self_check` で初期化と目印行の取得を実証した。
  初期化は初回だけ有効で、二重呼び出しでは偽が返る仕様も確認した。
- `enable_libwebrtc_log` 相当 (ログレベル設定) と `rtc_log` 相当 (任意文言出力) は
  上記の組み合わせで再現できる。動作必須ではないため困り度は低いまま。

## 音声ミキサー駆動

- 既定構成 (`AdmConfig::NoAudioDevice`) では RTP 到達・映像復号は動くが、
  音声 PCM の引き抜き (`OnData`) が起きないことを実証した。
  原因は再生ループの欠如で、C++ 版が自前 `DummyAudioMixer` を持つ理由と一致する。
- `sora_sdk` / `shiguredo_webrtc` の公開 API にミキサー設定はないため、
  `AudioDeviceModuleHandler` 実装の偽デバイス (`src/fake_audio_device.rs`) で
  10ms 周期の再生要求を出して駆動する。実マイク不要で受信できる。
- 注意点 2 件。再生要求はステレオ 48 kHz で出すこと
  (mono 要求ではエンジン側書き込みで壊れる)。
  時刻ポインタには有効な変数を渡すこと (null で壊れる)。
- 録音側は未対応。送信段階で取り込む。

## 送信系 API

- `Sora.create_audio_source` / `create_video_source` に対応する
  `SoraAudioSource` / `SoraVideoSource` を追加した。
  `Sora` が偽デバイス付きコンテキストを所有し、送信元と接続で共有する
  (既存 C++ 版の factory 構成に対応)。
- 音声は `on_data` で受けた PCM を送信キューに積み、偽デバイスの録音側が
  10ms 周期の取り込み要求 (`RecordedDataIsAvailable`) で送る。
  不足分は無音で埋め、上限 (10 秒分) を超えた古い分は捨てる。
  取り込み形式は送信元の形式で報告する (`get_record_audio_parameters`)。
- 映像は `on_captured` で受けた RGB を ARGB 経由で I420 変換し、
  `AdaptedVideoTrackSource::on_frame` で投入する。
  時刻は整数ならマイクロ秒、実数なら秒として扱う (既存の多重定義に対応)。
- `create_connection` は `audio_source` / `video_source` と
  `audio` / `video` の可否指定を受け付け、送信トラックと送受信設定を組み立てる。
  送信元があるのに可否指定がない場合は有効として扱う。
- 差分: ポインタ直渡しの `on_data` 多重定義は未対応 (ndarray 経由のみ)。
  コーデック指定やビットレート等の送信設定は対象外で後続に切り出す。

## PyO3 0.29 での差分
- `#[pyattr]` は廃止されていたため、関数形式の `#[pymodule]` で
  `m.add("__version__", ...)` する形にした。
- `Python::allow_threads` は廃止されていたため、`Python::detach` を使う。

## 検証結果

- `uv run maturin build` で wheel を生成できる。
- `uv run maturin develop` で venv に導入し、`import sora_rust_sdk` できる。
- 引数検証 (空 URL、不正 role、空 channel_id、不正 JSON、不正 duration) は
  `ValueError` で弾けることを確認した。
- `check_connect.py` で実 Sora に recvonly 接続し、PeerConnection の Connected と
  DataChannel 群の open を経て切断できることを確認した (終了コード 0)。
  接続設定は既存 E2E と同じ環境変数を使った。
- `loopback_audio_frames` で同一チャネルへの送受信ループバックを実証した。
  実マイク構成で PCM 980 フレーム (48 kHz mono) を受信した。
- `loopback_video_frames` で黒フレーム送信のループバックを実証した。
  映像 440 フレーム受信、encoded 変換 440 回通過、ARGB 変換結果の numpy 化を確認した。
- pytest は `uv run pytest` で 19 件が通る
  (版参照 1 件、引数検証 7 件、実接続 1 件、ループバック 2 件、ログ到達 1 件、
  新 API 受信 3 件、新 API 送信 4 件)。

## 後続作業の洗い出し

- イベントコールバックの Python 中継設計 (GIL 取得スレッド、キュー方式の検討)。
- 送信トラック (音声 / 映像) 対応とフレーム受け渡し方式の決定。
- 既存 `sora_sdk` Python API との対応表と移行単位の切り分け。
- ビルド体系の置き換え (CMake / setup.py / run.py の扱いと対応 platform)。
- E2E テストの移行と CI 組み込み。
- wheel 公開名とモジュール名 (`sora_sdk` 衝突) の最終決定。
