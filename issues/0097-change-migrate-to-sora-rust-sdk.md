# Sora C++ SDK + nanobind から sora-rust-sdk + PyO3 + maturin へ移行する

- Created: 2026-09-16
- Completed: -
- Branch: feature/change-migrate-to-sora-rust-sdk
- Polished: -

## 目的

現行の Sora C++ SDK + nanobind + 独自ビルドスクリプト構成を、sora-rust-sdk + PyO3 + maturin へ置き換える。移行の可否、Python 公開 API の設計、実現できない箇所の扱いを確定させ、後続の実装 issue に分割できる状態にする。

置き換える理由は 3 つある。

- 現行は C++ 実装 5,897 行に加え、`buildbase.py` / `run.py` / `pypath.py` / `sysroot_builder.py` で 4,066 行のビルド基盤を自前で維持している。sora-rust-sdk が依存する `shiguredo_webrtc` は prebuilt libwebrtc を取得するため、CMake と sysroot 構築が不要になり維持対象が大きく減る。
- Python SDK が Sora C++ SDK と sora-rust-sdk の両方に追従する必要がなくなり、追従先が 1 つになる。
- 現行は `NB_FREE_THREADED` を定義しておらず free-threading 非対応である。Rust 化により free-threading 対応の可否を改めて設計できる。

## 現状

### 現行実装

- バインディングの起点は `src/sora_sdk_ext.cpp` の `NB_MODULE(sora_sdk_ext, m)` で、`src/sora.cpp` / `src/sora_connection.cpp` / `src/sora_audio_sink.cpp` / `src/sora_video_sink.cpp` / `src/sora_audio_source.cpp` / `src/sora_video_source.cpp` / `src/sora_frame_transformer.h` / `src/sora_vad.cpp` などが C++ SDK のラッパーになっている。
- ビルドは `CMakeLists.txt` の `nanobind_add_module(sora_sdk_ext ...)` を入口とし、`setup.py` / `run.py` / `buildbase.py` / `pypath.py` / `sysroot_builder.py` が Sora C++ SDK / WebRTC / Boost / rootfs を取得・生成する。`DEPS` が `SORA_CPP_SDK_VERSION` `2026.3.0-canary.6`、`WEBRTC_BUILD_VERSION` `m154.8037.1.1`、`BOOST_VERSION` `1.92.0` を pin している。
- Python 公開 API の正本はビルド時に生成される `src/sora_sdk/sora_sdk_ext.pyi` である。`Sora.create_connection` は 49 引数あり、`src/sora.h` の宣言・`src/sora.cpp` の定義・`src/sora_sdk_ext.cpp` の `.def("create_connection", ...)` の 3 箇所で同じ引数リストを機械同期している。
- `src/sora_sdk/__init__.py` の `SoraAudioSink` / `SoraAudioStreamSink` / `SoraVideoSink` は、C++ 側で track を `shared_ptr` 保持するとリークするため Python 側で track 参照を持つラッパーになっている。
- CI (`.github/workflows/build.yml`) は 8 プラットフォーム × Python 3.12 / 3.13 / 3.14 の 24 wheel を作る。プラットフォームは ubuntu-26.04 と ubuntu-24.04 の x86_64 / armv8、raspberry-pi-os_armv8、macos-15 と macos-26 の arm64、windows-2025_x86_64 である。
  - armv8 系は x86_64 runner からのクロスコンパイルで、`sysroot_builder.py` が rootfs を生成する。
  - `setup.py` が manylinux tag を手動で設定し、Raspberry Pi 向けのみ `libcamerac.so` を同梱する。
- `src/sora_vad.cpp` の `SoraVAD` は libwebrtc の `webrtc::VoiceActivityDetectorWrapper` (`modules/audio_processing/agc2/vad_wrapper.h`) を利用している。
- free-threading は未対応である。`src/gil.h` と各所の `gil_scoped_acquire` が GIL を前提にしている。

### 試作

0076 で作成した `feature/add-sora-rust-sdk-prototype` の試作を出発点にする。この試作は C++ 実装と CMake / setup 系を削除して Rust へ全面置き換えたものである (Rust 6,063 行、`src/connection.rs` が 1,472 行で最大)。

- `pyproject.toml` を maturin 化し、`module-name = "sora_sdk"` / `python-source = "python"` としている。`Cargo.toml` は `sora_sdk = "2026.2.0-canary.2"` + `pyo3 = "0.29"` + `shiguredo_webrtc = "0.152.1-canary.3"` に依存し、`#[pymodule(gil_used = false)]` を宣言している。
- 実 Sora への recvonly 接続、音声 980 フレーム / 映像 440 フレームのループバック受信、映像 encoded transform の通過、ログ初期化を実証している。
- 音声は `AdmConfig::NoAudioDevice` では再生ループが回らず `AudioTrackSinkHandler::on_data` が発火しないため、`AudioDeviceModuleHandler` を実装した独自の偽オーディオデバイス (`src/fake_audio_device.rs`) で再生と録音を駆動している。
- ただし現行 API の形を合わせるため、実測できない値を合成している箇所がある。
  - `src/connection.rs` の `fire_disconnect` が、実際の close イベントが無いときに WebSocket close code `1000` と理由 `"TYPE-DISCONNECT"` / `"SELF-CLOSED"` を生成して `on_ws_close` を発火する。
  - `on_switched` が切替記録が無いとき、要求値から `{"type":"switched",...}` を合成する。
  - `on_set_offer` と `on_disconnect` も受信記録と終了結果から合成する。
  - `src/vad.rs` の `SoraVAD` は libwebrtc の VAD ではなく、実効値の閾値による簡易判定である。
  - `Sora::new` の `openh264` と `force_i420_conversion` は `let _ = (openh264, force_i420_conversion);` で破棄している。
  - `SoraTrackInterface.state` / `SoraMediaTrack.stream_id` / `SoraFrameTransformer` 基底が公開面から消えている。
- 音声 Sink のリサンプルは、`src/audio_sink.rs` の `resample_pcm` が直線補間で自前実装している。現行が使っている libwebrtc のリサンプラとは出力が異なる。
- 既存テストは `test_encoded_transform.py` / `test_degradation_preference.py` / `test_simulcast.py` / `test_authz_simulcast.py` などが通らない。`build.yml` / `build-debug.yml` は削除されたままで CI は未再構築である。
- 試作専用の検証関数 (`connect` / `loopback_audio_frames` / `loopback_video_frames` / `logging_self_check`) が公開面に混ざっている。

### sora-rust-sdk

- crates.io の最新版は `2026.2.0-canary.6`、安定版は `2026.1.0` である。
- 依存する `shiguredo_webrtc` (`~0.154`) の `build.rs` が prebuilt libwebrtc を `shiguredo/webrtc-rs` の Release から SHA-256 検証付きで取得する。CMake と libclang は不要で、`curl` と `tar` があればビルドできる。`source-build` feature を有効にすると CMake によるソースビルドに切り替わる。
- 対応ターゲットは linux x86_64 / aarch64 (ubuntu-22.04 / 24.04 / 26.04、raspberry-pi-os)、macos aarch64、windows x86_64 である。ターゲットは `CARGO_CFG_TARGET_OS` / `CARGO_CFG_TARGET_ARCH` と `/etc/os-release` から決まり、`WEBRTC_C_TARGET` で明示指定できる。
- `SoraConnectionEventHandler` は `Send` のみを要求し、コールバックは単一タスクから直列に呼ばれる。ブロックさせることは禁止されている (重い処理は自前のタスクへ転送する)。
- `SoraConnection::run(self)` は `async fn` で切断までブロックし、`SoraConnectionHandle` (Clone) で外部から制御する。`SoraConnectionContext::new()` は内部スレッドを 3 本起動するため、プロセスで 1 つに集約して共有する。
- `on_disconnect` / `on_set_offer` / `on_rpc` に対応する受け口が無い。
- encoded transform は映像のみで、`sender_video_transform` / `receiver_video_transform` がある。音声の受け口は無い。
- 受信 Sink は sora-rust-sdk には無く、`shiguredo_webrtc` の `AudioTrackSink` / `VideoSink` を直接使う。`shiguredo_webrtc::MediaStreamTrack` には `state()` が無く、`RtpReceiver` にも `stream_id()` が無い。
- 映像入力は `shiguredo_webrtc` の `AdaptedVideoTrackSource` を使う。音声の任意 PCM 投入には `AdmConfig` に加えて `AudioDeviceModuleHandler` の実装が要る。
- ログ制御は `shiguredo_webrtc::log` (`LoggingConfig` / `Severity` / `LogSink` / `LogSinkHandler` / `initialize_logging` / `print`) で再現できる。
- 転送フィルター、DataChannel メッセージング、JSON-RPC、TLS / TURN-TLS / プロキシ、コーデック capability と preference は公開 API がある。
- `Error` の `Display` は日本語である。Python に渡すエラーメッセージは英語にする必要がある。

## 設計方針

- sora-rust-sdk + PyO3 + maturin へ置き換える。バインディングは PyO3、ビルドバックエンドは maturin とし、モジュール名は `sora_sdk` を維持する。
- **実測できない値を合成して API の形だけを合わせることを禁止する。** 試作が行っている close code や切替記録の捏造、簡易 VAD での代替、直線補間によるリサンプルは採用しない。上流に受け口が無い機能は、上流への追加依頼、実現方式の決定、API 自体の見直しのいずれかで解決する。
- 後方互換は考慮しない (`shiguredo-python` 規約)。`Sora.create_connection` の 49 引数は Rust 化を機に構造体ベースへ変える方向で検討し、引数の機械同期をなくす。
- 試作はまだパッケージ化しない。wheel の公開、PyPI への登録、リリースは本 issue の対象外とし、移行が完了してから別途判断する。
- sora-rust-sdk と shiguredo_webrtc は canary 系列に追従する。安定版が出た時点で切り替える。
- モックとスタブは使わない。E2E は実 Sora に対して行う。
- 対応プラットフォームは現行の 8 種を維持することを目標とするが、クロスコンパイルと Jetson の扱いは実証結果で判断する。
- 本 issue は移行全体を 1 件にまとめたものである。着手時に実装単位へ分割し、分割後の issue で個別に完了させる。

## 検討が必要な事項

上流に受け口が無く、現行 API を再現できないもの。

1. `SoraConnection.on_disconnect` — 現行は `SoraSignalingErrorCode` と理由文を返す。切断結果を取得する受け口が無い。
2. `SoraConnection.on_set_offer` — 現行は受信した offer の SDP を返す。SDK 内部の offer を取得する受け口が無い。
3. `SoraConnection.on_rpc` — サーバーからの RPC 要求を受ける受け口が無い。現行は送信のみ `send_rpc_request` として存在する。
4. `SoraConnection.on_switched` の引数 — 現行は切替内容の JSON 文字列を渡すが、上流の `on_switched` は引数を取らない。
5. `SoraTrackInterface.state` と `SoraMediaTrack.stream_id` — `shiguredo_webrtc::MediaStreamTrack` に状態取得が無い。
6. 音声 encoded transform — 上流は映像のみで、`SoraAudioFrameTransformer` を接続できない。
7. 送信設定の一部 — `degradation_preference` / `audio_streaming_language_code` / `spotlight_number` / 送信側 `simulcast_rid` に対応する設定が無い。

方式の選定が必要なもの。

8. VAD — libwebrtc の `VoiceActivityDetectorWrapper` は `shiguredo_webrtc` の C API に露出していない。上流への追加依頼、別クレートの利用、自前実装のいずれかを選ぶ。閾値による簡易判定で代替しない。
9. `force_i420_conversion` — C++ SDK 固有の機能で、Rust 側に対応する概念が無い。同等機能を実装するか、公開 API から削除するかを決める。
10. 音声のリサンプル — 現行は `src/sora_audio_sink.h` と `src/sora_audio_stream_sink.h` で libwebrtc の `webrtc::PushResampler<int16_t>` を利用している。`shiguredo_webrtc` にリサンプラの露出が無いため、上流への追加依頼、別クレートの利用、自前実装のいずれかを選ぶ。自前実装にする場合は現行と同等の出力品質が得られることを検証する。
11. free-threading — `#[pymodule(gil_used = false)]` を付けるか、現行どおり GIL 前提とするかを決める。付ける場合はコールバック中継とフレーム受け渡しを GIL 非依存で設計する必要がある。
12. コールバックの Python 中継方式 — 上流のコールバックはブロック禁止であり、Python callable を直接呼ぶと GIL 取得でブロックする。キュー経由で専用スレッドに渡す方式を設計する。

ビルドと配布。

13. armv8 のクロスコンパイル — 現行は x86_64 runner から armv8 と raspberry-pi-os をビルドしている。上流の CI は native arm runner のみで、クロスコンパイルの実績が無い。`WEBRTC_C_TARGET` と sysroot / リンカ設定で成立するかを実証する。
14. wheel の tag と同梱物 — 現行の手動 manylinux tag 設定と Raspberry Pi 向け `libcamerac.so` 同梱を maturin でどう表現するかを決める。
15. Jetson — `shiguredo_webrtc` に Jetson ターゲットが無いため、移行すると `issues/pending/` の Jetson 対応 (プラットフォーム対応、runtime library 契約、リリース経路、E2E dispatcher) は一旦失われる。移行後に再構築するか、Jetson を切り捨てるかを決める。

## 完了条件

- 移行の可否と Python 公開 API の設計が確定し、実装単位の issue に分割されていること。
- 上流 (sora-rust-sdk / shiguredo_webrtc) へ必要な追加を依頼済みであること、または依頼が不要な代替方式が確定していること。
- 対応プラットフォームと wheel の配布方法が確定していること。
- sora-rust-sdk + PyO3 + maturin でビルドでき、`import sora_sdk` から現行相当の機能が使えること。
- 実測できない値を合成している箇所が 1 つも無いこと。
- 既存テストが移行され、実 Sora に対して通ること。
- CI が maturin ベースで 8 プラットフォーム × Python 3.12 / 3.13 / 3.14 の wheel をビルドできること。
- C++ 実装と独自ビルドスクリプト (`buildbase.py` / `run.py` / `pypath.py` / `sysroot_builder.py` / `CMakeLists.txt`) が削除されていること。
- CHANGES.md の `## develop` にエントリが追記されていること。

## 解決方法

1. 上流に受け口が無い 7 項目について、sora-rust-sdk / shiguredo_webrtc への追加要否を判断し、必要なものを依頼する。
2. VAD、`force_i420_conversion`、音声リサンプル、free-threading、コールバック中継方式の 5 項目を決定する。
3. 決定内容を反映して `Cargo.toml` / `pyproject.toml` / `python/sora_sdk` の構成を確定し、実装単位の issue に分割する。
4. 分割した issue で受信系、送信系、残差 API、ビルド基盤、CI、テスト移行を順に実装する。
5. クロスコンパイルと wheel 配布を実証し、対応プラットフォームを確定する。
6. C++ 実装と独自ビルドスクリプトを削除し、ドキュメントとサンプルを追従させる。
7. CHANGES.md の `## develop` に `[CHANGE]` エントリを追記する。
