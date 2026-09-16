# Sora C++ SDK + nanobind から sora-rust-sdk + PyO3 + maturin へ移行する

- Created: 2026-09-16
- Completed: -
- Branch: feature/change-migrate-to-sora-rust-sdk
- Polished: 2026-09-16

## 目的

現行の Sora C++ SDK + nanobind + 独自ビルドスクリプト構成を、sora-rust-sdk + PyO3 + maturin へ置き換える。

本 issue は移行全体を扱う親 issue であり、移行が完了するまで closed にしない。第 1 段で方針と API 設計を確定して実装単位の issue に分割し、第 2 段を分割した issue で実装する。

置き換える理由は 4 つある。

- 現行は C++ 実装 5,897 行に加え、`buildbase.py` / `run.py` / `pypath.py` / `sysroot_builder.py` で 4,066 行のビルド基盤を自前で維持している。sora-rust-sdk が依存する `shiguredo_webrtc` は prebuilt libwebrtc を取得するため、CMake と sysroot 構築が不要になり維持対象が大きく減る。
- 追従先を Sora C++ SDK から sora-rust-sdk の 1 つにできる。
- 現行の `pyproject.toml` はビルドバックエンドに setuptools を指定しており、`shiguredo-python` 規約が定める C++ binding の scikit-build-core + nanobind 経路とは異なる。移行により maturin + PyO3 規約に揃う。
- 現行は `NB_FREE_THREADED` を定義しておらず free-threading 非対応である。Rust 化により free-threading 対応を規約どおり宣言できる。

## 現状

### 現行実装

- バインディングの起点は `src/sora_sdk_ext.cpp` の `NB_MODULE(sora_sdk_ext, m)` で、`src/sora.cpp` / `src/sora_connection.cpp` / `src/sora_audio_sink.cpp` / `src/sora_video_sink.cpp` / `src/sora_audio_source.cpp` / `src/sora_video_source.cpp` / `src/sora_frame_transformer.h` / `src/sora_vad.cpp` などが C++ SDK のラッパーになっている。
- ビルドは `CMakeLists.txt` の `nanobind_add_module(sora_sdk_ext ...)` を入口とし、`setup.py` / `run.py` / `buildbase.py` / `pypath.py` / `sysroot_builder.py` が Sora C++ SDK / WebRTC / Boost / rootfs を取得・生成する。`DEPS` が `SORA_CPP_SDK_VERSION` `2026.3.0-canary.6`、`WEBRTC_BUILD_VERSION` `m154.8037.1.1`、`BOOST_VERSION` `1.92.0` を pin している。
- Python 公開 API の正本はビルド時に生成される `src/sora_sdk/sora_sdk_ext.pyi` である。`Sora.create_connection` は 49 引数あり、`src/sora.h` の宣言・`src/sora.cpp` の定義・`src/sora_sdk_ext.cpp` の `.def("create_connection", ...)` の 3 箇所で同じ引数リストを機械同期している。
- `src/sora_sdk/__init__.py` の `SoraAudioSink` / `SoraAudioStreamSink` / `SoraVideoSink` は、C++ 側で track を `shared_ptr` 保持するとリークするため Python 側で track 参照を持つラッパーになっている。
- 受信音声の駆動は `src/sora_factory.cpp` が `context_config.configure_dependencies` で `dependencies.audio_mixer` に自前の `DummyAudioMixer` (`src/dummy_audio_mixer.cpp`) を差し込んで行う。`use_audio_device` を false にすると通常の AudioMixer では音声ループが止まり、`SoraAudioSinkImpl` (`src/sora_audio_sink.h`) が実装する `webrtc::AudioTrackSinkInterface::OnData` が発火しないためである。
- CI (`.github/workflows/build.yml`) は 8 プラットフォーム × Python 3.12 / 3.13 / 3.14 の 24 wheel を作る。プラットフォームは ubuntu-26.04 と ubuntu-24.04 の x86_64 / armv8、raspberry-pi-os_armv8、macos-15 と macos-26 の arm64、windows-2025_x86_64 である。
  - armv8 系は x86_64 runner からのクロスコンパイルで、`sysroot_builder.py` が rootfs を生成する。
  - `setup.py` が manylinux tag を手動で設定し、Raspberry Pi 向けのみ `libcamerac.so` を同梱する。
  - PyPI への公開対象はこのうち 6 プラットフォーム (ubuntu-24.04 の x86_64 / armv8、macos-15 / 26 の arm64、windows-2025_x86_64、raspberry-pi-os_armv8) である。
  - E2E テストは Python 3.13 のみを対象にしており、3.12 と 3.14 はコメントアウトされている。
- `src/sora_vad.cpp` の `SoraVAD` は libwebrtc の `webrtc::VoiceActivityDetectorWrapper` (`modules/audio_processing/agc2/vad_wrapper.h`) を利用している。
- `Sora.create_libcamera_source` は全プラットフォームで公開されており、Raspberry Pi 以外では実行時にエラーを返す (`CMakeLists.txt` が Raspberry Pi のみ `USE_V4L2` を定義する)。
- free-threading は未対応である。`src/gil.h` と各所の `gil_scoped_acquire` が GIL を前提にしている。

### 試作

0076 で作成したブランチ `feature/add-sora-rust-sdk-prototype` を起点にする。0076 の設計方針は「既存ビルドは一切変更しない」であったため、C++ 実装と CMake / setup 系の削除は同ブランチ上の後続作業 (0077〜0080) で行われている。現在のブランチは Rust へ全面置き換え済みで、develop には未マージである。

- Rust 6,063 行で、`src/connection.rs` が 1,472 行で最大である。
- `pyproject.toml` を maturin 化し、`module-name = "sora_sdk"` / `python-source = "python"` としている。`Cargo.toml` は `sora_sdk = "2026.2.0-canary.2"` + `pyo3 = "0.29"` + `shiguredo_webrtc = "0.152.1-canary.3"` に依存し、`src/lib.rs` で `#[pymodule(gil_used = false)]` を宣言している。
- 実 Sora への recvonly 接続、音声 980 フレーム / 映像 440 フレームのループバック受信、映像 encoded transform の通過、ログ初期化を実証している。
- 音声は `AdmConfig::NoAudioDevice` では再生ループが回らず `AudioTrackSinkHandler::on_data` が発火しないため、`AudioDeviceModuleHandler` を実装した独自の偽オーディオデバイス (`src/fake_audio_device.rs`) で再生と録音を駆動している。現行の `DummyAudioMixer` とは別の方式である。
- ただし現行 API の形を合わせるため、次の 4 種類の妥協が入っている。
  - 値の合成: `src/connection.rs` の `fire_disconnect` が、実際の close イベントが無いときに WebSocket close code `1000` と理由 `"TYPE-DISCONNECT"` / `"SELF-CLOSED"` を生成して `on_ws_close` を発火する。`on_switched` は切替記録が無いとき要求値から `{"type":"switched",...}` を合成する。`on_set_offer` と `on_disconnect` も受信記録と終了結果から合成する。
  - 引数の破棄: `Sora::new` の `openh264` と `force_i420_conversion` を `let _ = (openh264, force_i420_conversion);` で破棄している。
  - 別方式による代替: `src/vad.rs` の `SoraVAD` が libwebrtc の VAD ではなく実効値の閾値判定になっており、`src/audio_sink.rs` の `resample_pcm` が直線補間になっている。いずれも現行の出力と一致しない。
  - 意図しない公開面からの消失: `SoraTrackInterface.state` / `SoraMediaTrack.stream_id` / `SoraFrameTransformer` 基底が消えている。
- 現行にある `create_libcamera_source` は受け口として残っているが、`src/connection.rs` が常に `"libcamera source is not supported in this build"` を返す。
- 通らない既存テストは試作ブランチの `MEMO.md` の「旧 tests の選別結果」に列挙されている (encoded transform、degradation preference、切替継続の終了符号を求めるもの、同時配信の符号化器表記を求めるもの、単体転送選別器を求めるもの、機器依存のもの)。ファイル単位の特定は分割時に確定する。
- 試作専用の検証関数 (`connect` / `loopback_audio_frames` / `loopback_video_frames` / `logging_self_check`) が公開面に混ざっている。
- `.github/workflows/build.yml` / `build-debug.yml` と `dev.py` / `scripts/pytest_memory_leak_checker.py` が削除されたままで、CI と開発フローは未再構築である。
- 試作ブランチの `MEMO.md` に依存先と版、`gil_used` の判定理由、API 対応メモ、困り度、後続作業の洗い出しが残っている。同ブランチには分割案として `issues/0077`〜`0080` があるが、develop の 0077〜0080 は別の issue が使用済みで番号が衝突している。分割時は develop の空き番号で起票し直す。

### sora-rust-sdk

- crates.io の最新版は `2026.2.0-canary.6`、安定版は `2026.1.0` である。
- 依存する `shiguredo_webrtc` (`~0.154`) の `build.rs` が prebuilt libwebrtc を `shiguredo/webrtc-rs` の Release から SHA-256 検証付きで取得する。CMake と libclang は不要で、`curl` と `tar` があればビルドできる。`source-build` feature を有効にすると CMake によるソースビルドに切り替わる。
- sora-rust-sdk の対応プラットフォームは linux x86_64 / aarch64 (ubuntu-22.04 / 24.04 / 26.04、raspberry-pi-os)、macos aarch64、windows x86_64 である。libwebrtc の prebuilt は `shiguredo_webrtc` の `build.rs` が `CARGO_CFG_TARGET_OS` / `CARGO_CFG_TARGET_ARCH` と `/etc/os-release` から対象を決めて取得し、`WEBRTC_C_TARGET` で明示指定できる。
- `SoraConnectionEventHandler` は `Send` のみを要求し、コールバックは単一タスクから直列に呼ばれる。ブロックさせることは禁止されている (重い処理は自前のタスクへ転送する)。
- `SoraConnection::run(self)` は `async fn` で切断までブロックし、`SoraConnectionHandle` (Clone) で外部から制御する。`SoraConnectionContext::new()` は内部スレッドを 3 本起動するため、プロセスで 1 つに集約して共有する。
- `on_disconnect` / `on_set_offer` / `on_rpc` に対応する受け口が無い。
- encoded transform は映像のみで、`sender_video_transform` / `receiver_video_transform` がある。音声の受け口は無い。
- 受信 Sink は sora-rust-sdk には無く、`shiguredo_webrtc` の `AudioTrackSink` / `VideoSink` を直接使う。`shiguredo_webrtc` の `MediaStreamTrack` には `state()` が無く、`RtpReceiver` にも `stream_id()` が無い。
- `AdmConfig` は `NoAudioDevice` / `UseBuiltIn` / `UseExternal` の 3 種で、PeerConnectionFactory の依存を差し替える `configure_dependencies` に相当する受け口が無い。`AudioMixer` の露出も無い。
- 映像入力は `shiguredo_webrtc` の `AdaptedVideoTrackSource` を使う。libcamera 入力は `libcamera` feature の `LibcameraVideoCapturer` がある。音声の任意 PCM 投入には `AdmConfig` に加えて `AudioDeviceModuleHandler` の実装が要る。
- ログ制御は `shiguredo_webrtc` の `log` モジュール (`LoggingConfig` / `Severity` / `LogSink` / `LogSinkHandler` / `initialize_logging` / `print`) で再現できる。
- 転送フィルター、DataChannel メッセージング、JSON-RPC、TLS / TURN-TLS / プロキシ、コーデック capability と preference は公開 API がある。
- `Error` の `Display` は日本語である。Python に渡すエラーメッセージは英語にする必要がある。

## 設計方針

- sora-rust-sdk + PyO3 + maturin へ置き換える。バインディングは PyO3、ビルドバックエンドは maturin とし、モジュール名は `sora_sdk` を維持する。
- **実測できない値を合成して API の形だけを合わせることを禁止する。** 試作が行っている値の合成、引数の破棄、別方式による代替、意図しない公開面からの消失は採用しない。上流に受け口が無い機能は、上流への追加依頼、実現方式の決定、API 自体の見直しのいずれかで解決する。
- 後方互換は考慮しない (`shiguredo-python` 規約)。そのため `Sora.create_connection` の 49 引数は構造体ベースへ変更し、引数の機械同期をなくす。API の形を維持するために妥協する必要もない。対応プラットフォームも「現行の維持」を目標にせず、実証結果に基づいて確定する。
- free-threading は `shiguredo-python` 規約に従い `#[pymodule(gil_used = false)]` を宣言することを既定とする。宣言しない場合は、依存 (sora-rust-sdk / shiguredo_webrtc) 側の制約と回避策をコードコメントに明記したうえで判断する。
- sora-rust-sdk と `shiguredo_webrtc` は canary 系列に追従する。安定版が出た時点で切り替える。
- モックとスタブは使わない。E2E は実 Sora に対して行う。
- CI の maturin 化と wheel ビルドは本 issue に含める。wheel の公開、PyPI への登録、リリースだけを対象外とし、移行が完了してから別途判断する。
- 本 issue は移行全体を 1 件にまとめた親 issue である。第 1 段で実装単位に分割し、第 2 段を分割先の issue で進める。

## 検討が必要な事項

上流に受け口が無く、現行 API を再現できないもの。

1. `SoraConnection.on_disconnect` — 現行は `SoraSignalingErrorCode` と理由文を返す。sora-rust-sdk に切断結果を取得する受け口が無い。
2. `SoraConnection.on_set_offer` — 現行は受信した offer の SDP を返す。sora-rust-sdk に SDK 内部の offer を取得する受け口が無い。
3. `SoraConnection.on_rpc` — サーバーからの RPC 要求を受ける受け口が sora-rust-sdk に無い。上流にあるのは送信 (`SoraConnectionHandle::send_rpc_request`) のみである。現行 Python SDK は受信 (`on_rpc`) のみを公開しており、送信 API は持たない。
4. `SoraConnection.on_switched` の引数 — 現行は切替内容の JSON 文字列を渡すが、sora-rust-sdk の `on_switched` は引数を取らない。
5. `SoraTrackInterface.state` と `SoraMediaTrack.stream_id` — `shiguredo_webrtc` の `MediaStreamTrack` に状態取得が無い。
6. 音声 encoded transform — sora-rust-sdk は映像のみで、`SoraAudioFrameTransformer` を接続できない。
7. 送信設定の一部 — `degradation_preference` / `audio_streaming_language_code` / `spotlight_number` / 送信側 `simulcast_rid` に対応する設定が sora-rust-sdk に無い。

方式の選定が必要なもの。

8. VAD — libwebrtc の `VoiceActivityDetectorWrapper` は `shiguredo_webrtc` の C API に露出していない。上流への追加依頼、別クレートの利用、自前実装のいずれかを選ぶ。閾値による簡易判定で代替しない。
9. `force_i420_conversion` — C++ SDK 固有の機能で、Rust 側に対応する概念が無い。同等機能を実装するか、公開 API から削除するかを決める。
10. 音声のリサンプル — 現行は `src/sora_audio_sink.h` と `src/sora_audio_stream_sink.h` で libwebrtc の `webrtc::PushResampler<int16_t>` を利用している。`shiguredo_webrtc` にリサンプラの露出が無いため、上流への追加依頼、別クレートの利用、自前実装のいずれかを選ぶ。自前実装にする場合は現行と同等の出力品質が得られることを検証する。
11. libcamera — 現行の `create_libcamera_source` は Raspberry Pi 向けの映像入力経路である。sora-rust-sdk には `libcamera` feature の `LibcameraVideoCapturer` があるため上流の受け口は存在するが、feature の有効化、`native_frame_output` と `controls` 引数の対応、対応プラットフォームでのビルド方法を決める。試作は常にエラーを返す状態であり、このままでは機能が失われる。
12. 受信音声の駆動方式 — 現行は `src/sora_factory.cpp` が `dependencies.audio_mixer` に自前の `DummyAudioMixer` を差し込んで `webrtc::AudioTrackSinkInterface::OnData` を駆動している。`shiguredo_webrtc` にも sora-rust-sdk にも `AudioMixer` の露出が無いため、上流への追加依頼、`AudioDeviceModuleHandler` の実装による代替、別方式のいずれかを選ぶ。試作は偽オーディオデバイスで代替しているが、現行と同じ駆動方式になるかは未検証である。
13. free-threading — 設計方針のとおり `#[pymodule(gil_used = false)]` を宣言することを既定とし、コールバック中継とフレーム受け渡しを GIL 非依存で設計する。宣言しない判断をする場合は、その理由と回避策を確定する。
14. コールバックの Python 中継方式 — 上流のコールバックはブロック禁止であり、Python callable を直接呼ぶと GIL 取得でブロックしうる。キュー経由で専用スレッドへ渡す方式を第一候補とし、13 の判断と整合する方式を確定する。

ビルドと配布。

15. armv8 のクロスコンパイル — 現行は x86_64 runner から armv8 と raspberry-pi-os の wheel をビルドしている。libwebrtc の prebuilt 自体は armv8 向けも配布されているが、sora-rust-sdk の CI は native arm runner のみで、Rust から armv8 wheel を作るクロスコンパイルの実績が無い。`WEBRTC_C_TARGET` と sysroot / リンカ設定で成立するかを実証する。
16. wheel の tag と同梱物 — 現行の手動 manylinux tag 設定と Raspberry Pi 向け `libcamerac.so` 同梱を maturin でどう表現するかを決める。
17. Jetson — `shiguredo_webrtc` に Jetson ターゲットが無いため、移行すると `issues/pending/` の Jetson 対応 (プラットフォーム対応、runtime library 契約、リリース経路、E2E dispatcher の 4 件) は一旦失われる。移行後に再構築するか、Jetson を切り捨てるかを決める。
18. E2E の対象 — 現行は Python 3.13 のみで、3.12 と 3.14 は無効になっている。移行後にどの Python 版とプラットフォームを対象にするかを決める。
19. 移行で影響を受ける既存 issue の処遇 — 次の 3 分類に該当する issue は、対象の削除または動作環境の変化により前提が失われる。1 件ずつ処遇 (移行で解消する / Rust 向けに起票し直す / そのまま残す) を判定する。件数は本 issue の調査時点のものである。
    - C++ 実装 (`src/`)、C++ 用ビルド基盤 (`CMakeLists.txt` / `setup.py` / `run.py` / `buildbase.py` / `pypath.py` / `sysroot_builder.py` / `DEPS`)、nanobind、削除対象の `.github/workflows/build.yml` / `dev.py`、Jetson、または現行 Python API の引数形を前提にするもの: open 14 件 (`0044` / `0050` / `0055` / `0056` / `0059` / `0062` / `0068` / `0075` / `0076` / `0077` / `0081` / `0082` / `0083` / `0097`)、pending 18 件 (`0043` / `0045` / `0072` / `0073` / `0078` / `0079` / `0080` / `0084` / `0085` / `0086` / `0087` / `0088` / `0089` / `0091` / `0092` / `0093` / `0095` / `0096`)
    - 現行の WebRTC スタック (Sora C++ SDK が使う libwebrtc) の挙動を前提にするもの: open 1 件 (`0015`)、pending 1 件 (`0090`)
    - 移行で作り替える `tests/` を前提にするもの: open 6 件 (`0037` / `0038` / `0040` / `0041` / `0064` / `0065`)

検討が必要な事項 1〜14 の受け口と挙動は、試作が sora_sdk `2026.2.0-canary.2` と `shiguredo_webrtc 0.152.1-canary.3` で確認したものである。sora-rust-sdk 側 (1〜4、6、7、11) は最新の canary 版、`shiguredo_webrtc` 側 (5、8、10、12) は `0.154.0` で、それぞれの受け口が無いことを再確認する。

## 完了条件

本 issue は親 issue であり、次をすべて満たしたときに closed にする。

### 第 1 段: 方針確定と分割

- 上流へ依頼する項目 (1〜7) の依頼先・依頼内容・受理されない場合の代替方式が確定し、必要な依頼を出していること。
- 方式の選定が必要な項目 (8〜14) の実現方式が確定していること。
- 1〜4・6・7・11 の受け口不足が sora-rust-sdk の最新 canary 版でも、5・8・10・12 の露出不足が `shiguredo_webrtc 0.154.0` でも成立することが確認されていること。
- Python 公開 API の設計が確定していること。
- 対応プラットフォーム、wheel の配布方法、E2E の対象 (15、16、18) が確定していること。
- Jetson の扱い (17) と、移行で影響を受ける既存 issue (19) の処遇が確定していること。
- 実装単位の issue が起票され、各 issue に変更対象と完了条件が書かれていること。

### 第 2 段: 移行完了

- 分割した issue がすべて closed になっていること。
- 検討が必要な事項で扱いを確定した範囲において、`import sora_sdk` から現行相当の機能が使えること。
- 値の合成、引数の破棄、別方式による代替、意図しない公開面からの消失のいずれも残っていないこと。
- 既存テストが移行され、実 Sora に対して通ること。
- CI が maturin ベースで wheel をビルドできること。
- C++ 実装と C++ 用ビルド基盤 (`buildbase.py` / `run.py` / `pypath.py` / `sysroot_builder.py` / `CMakeLists.txt` / `setup.py` / `DEPS`) が削除され、`pyproject.toml` のビルドバックエンドが maturin になっていること。
- `README.md` と `skills/sora-python-sdk/SKILL.md` の Sora C++ SDK ベースである旨の記述が実態に合わせて更新されていること。
- CHANGES.md の `## develop` にエントリが追記されていること。

## 第 1 段の結果

### 受け口不足の再確認 (2026-09-16)

最新版のソースコードを取得して、検討が必要な事項 1〜12 の受け口の有無を確認した。詳細は `docs/sora-rust-sdk-investigation.md` にある。

- `sora_sdk` は安定版 `2026.1.0`、canary 最新 `2026.2.0-canary.6` である。`shiguredo_webrtc` は `0.154.0` が最新で、canary 系列 (`0.152.1-canary.3`) より新しい。
- 受け口が無いものは 1〜3、5〜10 で、試作時点から解消していない。`on_switched` (4) は受け口があるが引数を取らない。libcamera (11)、`AdmConfig` (12)、`AudioDeviceModuleHandler` (12) は受け口がある。
- `degradation_preference` と rid は `shiguredo_webrtc` 側に部品 (`DegradationPreference` / `RtpParameters::set_degradation_preference` / `RtpEncodingParameters::set_rid`) があるが、`sora_sdk` が映像送信器を外へ出す API を持たないため使えない。
- `2026.1.0` と `2026.2.0-canary.6` の差は映像 transform の 2 フィールドのみで、イベントハンドラのトレイトは両版で同一である。canary 化では 1〜4・6 の状況は変わらない。

### 確定した方針

決定事項の一覧は `docs/migration-to-sora-rust-sdk.md` にある。要点は次である。

- 上流に受け口が無い 8 項目のうち 6 項目は sora-rust-sdk へ、3 項目は webrtc-rs へ追加を依頼する。依頼文のドラフトは `docs/migration-to-sora-rust-sdk.md` にある。依頼の起票は別途行う。
- `force_i420_conversion` は公開 API から削除する。
- 受信音声は `AudioDeviceModuleHandler` を実装した偽オーディオデバイスで駆動する。`AudioMixer` の露出は依頼しない。
- free-threading は `#[pymodule(gil_used = false)]` を宣言する。コールバックはキュー経由で専用スレッドへ渡す。
- 対応プラットフォームは現行 8 プラットフォームを維持し、armv8 系のクロスコンパイルを実証する。成立しないものは実証結果に基づいて落とす。
- E2E は Python 3.12 / 3.13 / 3.14 の全版を対象にする。
- Jetson は移行後に再構築する。`issues/pending/` の Jetson 4 件は pending のまま残す。
- 影響を受ける既存 issue 44 件のうち、`tests/` を前提にする 6 件はテスト移行の 0107 で、残り 38 件は 0108 で 1 件ずつ処遇を判定する。

### 実装単位の issue

第 2 段は次の 11 件で進める。依存関係は各 issue に記載している。

| issue | 内容 | 上流の前提 |
| --- | --- | --- |
| 0099 | ビルド基盤を maturin + PyO3 へ置き換える | なし |
| 0100 | 受信系 API を実装する | G |
| 0101 | 送信系 API を実装する | E |
| 0102 | コールバックの Python 中継を実装する | A B C D |
| 0103 | 接続設定を構造体ベースへ変更し残差 API を実装する | A B C D F |
| 0104 | 音声リサンプラと VAD を実装する | H I |
| 0105 | libcamera 入力を実装する | なし |
| 0106 | CI を maturin 化し wheel とクロスコンパイルを実証する | なし |
| 0107 | 既存テストを移行し実 Sora に対して通す | 該当機能の依頼 |
| 0108 | 影響を受ける既存 issue の処遇を確定する | なし |
| 0109 | README と SKILL.md を追従させる | なし |

上流の依頼の記号 (A〜I) は `docs/migration-to-sora-rust-sdk.md` の依頼一覧に対応する。A〜D と G〜I が受理されるまで 0100 / 0102 / 0103 / 0104 は完了できない。E は音声 encoded transform、F は送信設定 4 項目に対応する。

### 第 1 段の完了条件の達成状況

- 上流へ依頼する項目 (1〜7) の依頼先・依頼内容・受理されない場合の代替方式は `docs/migration-to-sora-rust-sdk.md` で確定した。依頼の起票は未実施である。
- 方式の選定が必要な項目 (8〜14) の実現方式は確定した。
- 1〜4・6・7・11 の受け口不足は `sora_sdk 2026.2.0-canary.6` で、5・8・10・12 の露出不足は `shiguredo_webrtc 0.154.0` で成立することを確認した。
- Python 公開 API の設計方針は確定した。`SoraConnectionConfig` 相当のデータクラスへ変更する。
- 対応プラットフォーム、wheel の配布方法、E2E の対象 (15、16、18) は確定した。
- Jetson の扱い (17) は確定した。既存 issue (19) は分類と担当 issue を確定し、1 件ずつの判定は 0107 と 0108 で行う。
- 実装単位の issue を 11 件起票し、各 issue に変更対象・完了条件・依存関係を書いた。

未実施は上流への依頼の起票である。

## 解決方法

1. 上流へ依頼する項目 (1〜7) について、依頼先・依頼内容・受理されない場合の代替方式を確定し、必要な依頼を出す。
2. 方式の選定が必要な項目 (8〜14) の実現方式を確定する。あわせて 1〜4・6・7・11 の受け口不足が sora-rust-sdk の最新 canary 版でも、5・8・10・12 の露出不足が `shiguredo_webrtc 0.154.0` でも成立するかを確認する。
3. ビルドと配布の項目 (15、16、18) を確定する。
4. Jetson の扱い (17) を決定し、移行で影響を受ける既存 issue (19) の処遇を 1 件ずつ確定する。
5. 決定内容を反映して `Cargo.toml` / `pyproject.toml` / `python/sora_sdk` の構成を確定し、実装単位の issue に分割する。
6. 分割した issue で受信系、送信系、残差 API、ビルド基盤、CI、テスト移行を実装する。
7. クロスコンパイルと wheel 配布を実証する。
8. C++ 実装と C++ 用ビルド基盤を削除し、`README.md` / `skills/sora-python-sdk/SKILL.md` / ドキュメント / サンプルを追従させる。
9. CHANGES.md の `## develop` に `[CHANGE]` エントリを追記する。
