# 変更履歴

- CHANGE
  - 後方互換性のない変更
- UPDATE
  - 後方互換性がある変更
- ADD
  - 後方互換性がある追加
- FIX
  - バグ修正

## develop

- [CHANGE] `SoraTransformableFrame` のタイポ `mine_type` を `mime_type` に修正する
  - 誤った公開プロパティ名をそのまま残さない
  - `mine_type` は削除する（alias は残さない）
  - @voluntas
- [CHANGE] Ubuntu arm64 と Raspberry Pi OS の rootfs 生成を multistrap から署名検証付き sysroot builder に切り替える
  - insecure な `multistrap` / `--no-auth` / `AllowInsecureRepositories` への依存を撤去する
  - Raspberry Pi OS wheel の動作対象を Trixie 以降に変更する（Bookworm 以前は非対応）
  - libstdc++ 依存を 14 に引き上げ、`GLIBCXX_3.4.32` 未満の環境を動作対象外とする
  - wheel の manylinux tag （`manylinux_2_35_aarch64`）は本変更では変更しない
  - Jetson の rootfs 生成は本変更の対象外とし、既存経路のまま残す
  - 既存の `_install/<target>/rootfs` を持つローカル環境では、初回 build 前に該当 rootfs と `_install/<target>/rootfs.version` を手動削除する（sysroot builder は由来不明の既存 rootfs を `--force` 無しで拒否する）
  - @voluntas
- [UPDATE] wheel を `~=0.47` に上げる
  - `0.47.x` を許可する
  - @voluntas
- [UPDATE] setuptools を `~=83.0` に上げる
  - `83.0.x` を許可する
  - @voluntas
- [UPDATE] nanobind を `2.13.0` に上げる
  - ABI バージョン 19 から 20 への変更に伴い拡張の再コンパイルが必要
  - オブジェクト構築、ndarray 交換、関数呼び出し、安定 ABI ディスパッチのパフォーマンスが大幅に改善
  - 数多くのクラッシュ、未定義動作、メモリリーク、free-threading のデータ競合が修正
  - @voluntas
- [UPDATE] Sora C++ SDK のバージョンを `2026.2.0-canary.25` に上げる
  - WEBRTC_BUILD_VERSION を `m150.7871.3.1` に上げる
  - CMAKE_VERSION を `4.3.2` に上げる
  - BOOST_VERSION を `1.91.0` に上げる
  - @voluntas
- [UPDATE] libwebrtc m148 で `ArrayView` が C++ 標準の `std::span` に移行したため追従する
  - 参考リンク : libwebrtc の `ArrayView` 移行の issue
    - https://issuetracker.google.com/issues/439801349
  - @torikizi
- [FIX] `disconnect()` 後の `send_data_channel()` / `get_stats()` が `conn_` の null チェック無しで SEGV する問題を修正する
  - `Connect()` と同じ `RuntimeError` を返すようにする
  - @voluntas
- [FIX] `SoraVideoFrame` / `SoraAudioFrame` / `SoraTransformableFrame` の ndarray が親フレームへの参照を持たず UAF しうる問題を修正する
  - `data()` / `get_data()` が返す ndarray の owner に親フレームを紐付ける
  - @voluntas
- [FIX] `disconnect()` が `OnDisconnect` 待ちで永久ブロックしうる問題を修正する
  - 最大 10 秒の有限待ちにし、待ち中の `KeyboardInterrupt` でも抜けられるようにする
  - @voluntas
- [FIX] `rtc_log()` が `PyFrame_GetCode` の新参照を解放せず参照リークする問題を修正する
  - 使い終わった `PyCodeObject` を `Py_DECREF` し、Python C-API 呼び出しを GIL 保持下に揃える
  - @voluntas
- [FIX] `SoraAudioSource::OnData` の 1 オーバーロードだけ `track_` の null チェックが抜けていた問題を修正する
  - 他オーバーロードと同様に publisher 破棄後は no-op にする
  - @voluntas
- [FIX] `SoraAudioSourceInterface` が不正な `sample_rate` / `channels` を検査せずクラッシュしうる問題を修正する
  - `sample_rate < 100` または `channels < 1` のとき `ValueError` を返す
  - @voluntas
- [FIX] `SoraAudioSourceInterface` の `audio_observers_` がロックなしで操作される問題を修正する
  - `observer_lock_` で保護し、`SetVolume` はスナップショット後にロック外でコールバックする
  - @voluntas
- [FIX] `SoraVideoSource` の `queue_` / `finished_` に明示的な同期が無い問題を修正する
  - `queue_mtx_` と `std::atomic<bool> finished_` で保護し、待機は `GILMutexLock` を使う
  - @voluntas
- [FIX] `SoraVideoSource` に `Disposed` override が無くワーカスレッド停止がデストラクタ依存だった問題を修正する
  - `Disposed()` で `finished_` を立てて待機解除し、`join` はデストラクタに残す
  - @voluntas
- [FIX] `Sora::ConvertJsonValue` が Python 整数を `int` にキャストして int32 範囲超で例外になる問題を修正する
  - `PyLong_Check` と `nb::cast<int64_t>` で大きな整数を通し、`bool` 分岐は先に維持する
  - @voluntas
- [FIX] `Sora` の破棄順序が原因で GC のタイミング次第にプロセスが SIGSEGV でクラッシュしうる問題を修正する
  - `Sora::~Sora` が `PeerConnectionFactory` を先に破棄した後に io_context を破棄していたため、io_context に残った handler が握る `sora::SoraSignaling` の破棄が破棄済みの signaling スレッドへ Marshal して use-after-free になっていた
  - 破棄順序を「子への破棄通知 → io_context の停止・破棄 → factory の破棄」に修正する
  - io スレッドや signaling スレッドとの相互待ちを防ぐため、スレッドの終了待ちの間は GIL を解放する
  - e2e テストの `test_audio_sink_callbacks` などで flaky に発生していた SEGV クラッシュの原因
  - @voluntas
- [FIX] `gil_scoped_acquire` / `gil_scoped_release` が `Py_IsInitialized()` が偽のときに未初期化メンバをデストラクタで読む未定義動作を修正する
  - メンバをデフォルト初期化し、early return 経路でもデストラクタが確定した値を読むようにする
  - @voluntas
- [FIX] `SoraVideoFrame` / `SoraVideoSource` が配列確保メモリを非配列 `unique_ptr` で保持していた未定義動作を修正する
  - `std::unique_ptr<uint8_t[]>` に直し、破棄時に `delete[]` が呼ばれるようにする
  - @voluntas
- [FIX] `SoraConnection::OnTrack` で `transceiver` / `receiver` が null のときに SIGSEGV しうる問題を修正する
  - `SoraMediaTrack` 構築時の null 参照によるプロセスクラッシュを防ぐ
  - null 時は警告ログのみ出し Python コールバックは呼ばない
  - @voluntas
- [FIX] Encoded Transform の `Transform` が GIL を取得せずに Python を呼び出していた問題を修正する
  - `SoraAudioFrameTransformer` / `SoraVideoFrameTransformer` の `Transform` を GIL 保持下で実行する
  - @voluntas
- [FIX] デフォルト User-Agent が `Sora Unity SDK` になっていたのを `Sora Python SDK` に修正する
  - `user_agent` 未指定時のコピペ残骸で、Sora サーバ側のクライアント識別が誤っていた
  - @voluntas
- [FIX] `SoraConnection::OnPush` が GIL を取得せずに Python コールバックを呼んでいた問題を修正する
  - GIL 非保持の内部スレッドから Python C API を呼ぶ未定義動作であり、参照カウント競合によるメモリ破壊で `push` 受信時にプロセスが SIGSEGV でクラッシュしうる問題があった
  - @sile
- [FIX] 音声コールバックが GIL を取得せずに Python を呼び出していた問題を修正する
  - `SoraAudioSink` と `SoraAudioStreamSink` の音声コールバックを GIL 保持下で実行する
  - @voluntas
- [FIX] `SoraConnection` の `connection_tp_clear` が `on_rpc_` を解放していなかった問題を修正する
  - `connection_tp_traverse` は `on_rpc_` を `Py_VISIT` で GC に報告しているのに `connection_tp_clear` が解放しておらず、traverse/clear が非対称で CPython の循環 GC の契約に反していた
  - `on_rpc` ハンドラを含む参照循環を循環 GC が断ち切れず接続オブジェクトのグラフ全体がリークしうる問題があった
  - @sile
- [FIX] `SoraAudioSink.read()` が待機中に GIL を解放していなかった問題を修正する
  - `read()` はデータを待つ間ずっと GIL を保持しており、`read(timeout=T)` がブロックする間、同一プロセスの他の Python スレッドが最大 T 秒間停止していた
  - @sile
- [FIX] `SoraAudioSink.read()` がシグナル割り込み時に Python 例外を握り潰していた問題を修正する
  - メインスレッドで `read()` の待機中にシグナル (Ctrl-C による SIGINT 等) を受け取ると、シグナルハンドラが送出した例外を呼び出し側へ伝播せず握り潰していた
  - 加えて、シグナルで待機を抜けた際に要求フレーム数に満たないバッファをそのまま読み出し、バッファ外アクセスによってプロセスのクラッシュやメモリ破壊に至りうる問題もあった
  - いずれもメインスレッドで `read()` を呼んだ場合にのみ発生し、ワーカースレッドなどメインスレッド以外で `read()` を呼ぶ一般的な使い方では影響しない
  - @sile
- [FIX] `SoraConnection` のデストラクタで `Disposed()` が最大 3 回呼ばれ subscriber 通知が重複しうる問題を修正する
  - `DisposePublisher::Disposed()` に `std::atomic<bool> disposed_` による冪等性ガードを追加する
  - デストラクタ内の重複 `Disposed()` 呼び出しを削除し 1 回に集約する
  - @voluntas
- [FIX] `client_cert` / `client_key` / `ca_cert` を `nb::bytes::c_str()` で渡しており NUL バイトで切り詰められる問題を修正する
  - `std::string(c_str(), size())` でバイト列を忠実に伝搬する
  - @voluntas
- [FIX] `SoraAudioFrame` の pickle 経路で `int16_t` を `uint16_t` に詰め替えている型不整合を修正する
  - `VectorData()` / `__getstate__` / `__setstate__` の全経路を `std::vector<int16_t>` に統一する
  - pickle の後方互換性は切り捨てる（プロセス内一時データのため）
  - @voluntas

### misc

- [UPDATE] actions/checkout を v7.0.0 に上げる
  - @voluntas
- [UPDATE] astral-sh/setup-uv を v8.3.2 に上げる
  - @voluntas
- [UPDATE] tailscale/github-action を v4.1.3 に上げる
  - @voluntas
- [UPDATE] Homebrew/actions/setup-homebrew を最新の master に追従する
  - @voluntas
- [UPDATE] Slack 通知を `rtCamp/action-slack-notify` から `shiguredo/github-actions/slack-notify` に切り替える
  - @voluntas
- [UPDATE] `pyproject.toml` の `[tool.ruff.lint]` に `extend-select = ["I", "UP", "PT"]` を追加する
  - @voluntas

## 2025.5.2

**リリース日**: 2025-12-22

- [FIX] `video_h265_params` への対応漏れを追加する
  - @voluntas

## 2025.5.1

**リリース日**: 2025-12-08

- [UPDATE] Sora C++ SDK のバージョンを `2025.6.2` に上げる
  - libcamera 0.6 への対応
  - @voluntas

## 2025.5.0

**リリース日**: 2025-12-01

- [ADD] Python 3.14 の対応を追加する
  - @voluntas
- [ADD] Python 3.11 の対応を終了する
  - @voluntas
- [UPDATE] CMake 3.27 以降のポリシー警告に対応する
  - CMP0144: `<PackageName>_ROOT` 変数の命名規則に対応し、`BOOST_ROOT` を `Boost_ROOT` に変更
  - CMP0167: FindBoost モジュールの廃止に対応し、Boost の検索を Config モードに移行
  - @voluntas
- [UPDATE] Sora C++ SDK のバージョンを `2025.6.1` に上げる
  - LIBWEBRTC_VERSIONを `m143.7499.1.0` に上げる
  - CMAKE_VERSION を `4.1.2` に上げる
  - @voluntas @melpon @torikizi
- [UPDATE] `simulcast_request_rid` をシグナリング接続時に指定できるようにする
  - Sora C++ SDK への追従
  - @voluntas
- [ADD] `raspberry-pi-os_armv8` の対応を追加する
  - `VideoCodecImplementation.RASPI_V4L2M2M` を追加
  - `Sora.create_libcamera_source()` 関数を追加
  - @melpon
- [ADD] GitHub Actions でデバッグバイナリを作る仕組みを追加する
  - 元々存在していた `build-debug.yml` をリニューアルした
  - @melpon
- [FIX] macOS のビルドで使うコンパイラと標準ライブラリを libwebrtc 提供のものにする
  - m140 から libwebrtc 提供のものでビルドするように変更したため
  - @melpon

### misc

- [ADD] Raspberry Pi OS armv8 向けの E2E テストを追加する
  - @voluntas
- [ADD] libcamera のテストを追加する
  - @voluntas

## 2025.4.0

**リリース日**: 2025-09-12

- [CHANGE] run.py をサブコマンド形式に変更する
  - 従来: `python run.py <target>`
  - 新形式: `python run.py build <target>`
  - @voluntas
- [ADD] run.py に format サブコマンドを追加する
  - C++ ファイルの clang-format によるフォーマット機能
  - Python ファイルの ty によるタイプチェック機能
  - @voluntas
- [UPDATE] .github/workflows 内のすべてのワークフローファイルを新しい run.py build 形式に更新する
  - @voluntas
- [UPDATE] nanobind を `2.9.2` に上げる
  - @voluntas
- [UPDATE] Sora C++ SDK のバージョンを `2025.5.0` に上げる
  - WEBRTC_BUILD_VERSION を `m139.7258.3.0` に上げる
  - CMAKE_VERSION を `4.1.0` に上げる
  - BOOST_VERSION を `1.89.0` に上げる
  - @melpon @voluntas
- [FIX] GitHub Actions の check_ubuntu_wheel ジョブで uv 0.8 以降の externally managed Python 環境エラーを修正する
  - `uv run --with` から `uv pip install` を使用する方式に変更
  - checkouts せずに仮想環境を作成して wheel ファイルをテストするように変更
  - @voluntas

### misc

- [CHANGE] PyPI への publish を OIDC に切り替える
  - @voluntas
- [CHANGE] build から e2e-test-only を workflow_call で呼び出すようにする
  - @voluntas
- [CHANGE] e2e-test を e2e-test-only.yml に統一する
  - @voluntas
- [UPDATE] actions/checkout と actions/download-artifact を v5 に上げる
  - @torikizi

## 2025.3.0

**リリース日**: 2025-07-09

- [UPDATE] Sora C++ SDK のバージョンを `2025.4.0` に上げる
  - WEBRTC_BUILD_VERSION を `m138.7204.0.0` に上げる
    - `ACMResampler` の廃止に伴い、`PushResampler` を利用するように変更
      - `acm_resampler.h` のインクルードを削除して、`push_resampler.h` をインクルードするように変更
    - `Resample10Msec` から `Resample` へ変更
      - `Resample10Msec` で一度に行っていた入力と出力のサンプリングを `webrtc::InterleavedView` を利用してシンプルに行うように変更
    - PeerConnectionFactoryDependendencies の `audio_processing` は廃止されたので削除
    - `default_task_queue_factory.h` のインクルードを削除
    - `dependencies.task_queue_factory` は廃止されたので `env` 経由で取得するように変更
  - CMAKE_VERSION を `4.0.3` に上げる
  - @melpon @torikizi
- [UPDATE] Ubuntu arm64 では Clang 19 に上げる
  - libwebrtc m137 を上げたことで clang 18 ではビルドが通らなくなったため
  - @voluntas
- [ADD] `__version__` でバージョンを取得できるようにする
  - @voluntas
- [ADD] WebSocket 接続時に User Agent を上書きする機能を追加する
  - @melpon
- [ADD] `on_rpc` コールバック関数を追加する
  - @melpon
- [FIX] pyi ファイルをバージョン毎に生成していなかった問題を修正する
  - @voluntas
- [FIX] Ubuntu 24.04 arm64 のクロスコンパイル時に Python 3.11 と Python 3.13 でビルドが失敗する問題を修正する
  - run.py でハードコードされていた `python3.12` を動的にバージョンを取得するように修正
  - CMakeLists.txt でクロスコンパイル時の Python 設定を改善
  - @voluntas

### misc

- [CHANGE] GitHub Actions 経由のリリースを gh コマンドに切り替える
  - @voluntas
- [CHANGE] VERSION ファイルを SDK のバージョンのみにする
  - @voluntas
- [CHANGE] 依存ライブラリを指定する VERSION ファイルを DEPS に変更する
  - @voluntas
- [UPDATE] [mypy](https://github.com/python/mypy) から [ty](https://github.com/astral-sh/ty) に切り替える
  - @voluntas
- [UPDATE] [python-dotenv](https://github.com/theskumar/python-dotenv) を [pydantic-settings](https://github.com/pydantic/pydantic-settings) に切り替える
  - @voluntas
- [ADD] GitHub Actions で Ubuntu 向けの whl ファイルの動作を uv run --with で動作確認するようにする
  - @voluntas
- [ADD] .github ディレクトリに copilot-instructions.md を追加
  - @torikizi

## 2025.2.3

**リリース日**: 2025-05-23

- [FIX] 切断時に落ちる問題を解消するために Sora C++ SDK をアップデートする
  - @melpon

## 2025.2.2

**リリース日**: 2025-05-15

- [FIX] Python 3.13 でメモリーリークが発生していた問題を修正する
  - @melpon

## 2025.2.1

**リリース日**: 2025-05-01

- [FIX] PyPI を Organization に移行事によるトークンへの切り替もれを対応
  - GitHub Actions の Secret 変更のためコード自体に変更は無し
  - @voluntas

## 2025.2.0

**リリース日**: 2025-05-01

- [UPDATE] nanobind を `2.7.0` に上げる
  - @voluntas
- [UPDATE] Sora C++ SDK のバージョンを `2025.3.0-canary.7` に上げる
  - 正式リリースまでは以下をアップデートしていく
  - WEBRTC_BUILD_VERSION を `m136.7103.0.0` に上げる
  - CMAKE_VERSION を `4.0.1` に上げる
  - BOOST_VERSION を `1.88.0` に上げる
  - OPENH264_VERSION を `v2.6.0` に上げる
  - @torikizi

### misc

- [UPDATE] GitHub Actions の windows を windows-2025 に更新する
  - @voluntas
- [UPDATE] E2E テストのタイムアウトを 20 分に延長する
  - @voluntas
- [UPDATE] GitHub Actions の tailscale を v3 に上げて windows と macos にも追加する
  - [v3](https://github.com/tailscale/github-action/releases/tag/v3.1.0) で Windows と macOS に対応した
  - @voluntas

## 2025.1.0

**リリース日**: 2025-03-19

- [CHANGE] Python 3.10 のサポートを終了する
  - [SPEC 0 — Minimum Supported Dependencies](https://scientific-python.org/specs/spec-0000/) を参考に直近 3 バージョンのサポートに変更する
  - @voluntas
- [CHANGE] macOS Sonoma 13 のサポートを終了する
  - @voluntas
- [CHANGE] シグナリング接続時の ``"type": "connect"`` 時に ``multistream`` 項目を送らないようにする
  - Sora 2022.1.0 以前には接続できなくなる
  - @voluntas
- [CHANGE] `client_cert` と `client_key` の指定にはパスではなく中身の文字列を指定するようにする
  - C++ SDK 側の仕様変更に追従する
  - @voluntas
- [CHANGE] `ca_cert`, `client_cert`, `client_key` の指定には `str` ではなく `bytes` を使うようにする
  - @tnoho
- [CHANGE] `Sora()` の引数から `use_hardware_encoder` を削除
  - デフォルトでは常に libwebrtc 実装のエンコーダ/デコーダを利用します
  - ハードウェアエンコーダ/デコーダを利用するには `video_codec_preference` を利用して下さい
  - @melpon
- [UPDATE] GitHub Actions の Windows ビルドで Windows 2025 を利用する
  - @voluntas
- [ADD] OpenH264 を Windows x86_64 に対応する
  - @melpon
- [ADD] AMD AMF を Ubuntu x86_64 と Windows x86_64 に対応する
  - @melpon
- [ADD] エンコード時の劣化の優先順位を指定できるようにする
  - `Sora.create_connection()` の引数に `degradation_preference` を追加する
  - `SoraDegradationPreference` を追加
    - `MAINTAIN_RESOLUTION` は解像度を優先
    - `MAINTAIN_FRAMERATE` はフレームレートを優先
    - `BALANCED` はバランスを優先
    - `DISABLED` は無効
  - @voluntas
- [ADD] WebRTC Encoded Transform に対応する
  - `SoraTransformableAudioFrame` と `SoraTransformableVideoFrame` を追加
  - `SoraAudioFrameTransformer` と `SoraVideoFrameTransformer` を追加
  - `create_connection()` の引数に `audio_frame_transformer` と `video_frame_transformer` を追加
  - `SoraMediaTrack` に `set_frame_transformer()` を追加
  - @tnoho
- [ADD] 転送フィルターを複数指定できるようにする
  - `Sora.create_connection()` の引数に `forwarding_filter` を追加する
  - @voluntas
- [ADD] サーバー証明書チェック用の CA 証明書を指定できるようにする
  - `Sora.create_connection()` の引数に `ca_cert` を追加する
  - @voluntas
- [ADD] Python 3.13 に対応する
  - @voluntas
- [ADD] `on_ws_close` コールバックを追加する
  - @tnoho
- [ADD] `on_signaling_message` コールバックを追加する
  - @tnoho
- [ADD] Ubuntu 24.04 armv8 のビルドを arm64 上でできるようにする
  - @melpon
- [ADD] Ubuntu 24.04 armv8 に対応する
  - @melpon
- [ADD] `on_ws_close` コールバックを追加する
  - @tnoho
- [ADD] `Sora.create_connection()` の引数に `audio_opus_params` を追加する
  - @melpon
- [ADD] `data_channels` の要素に `header` を指定可能にする
  - @melpon
- [ADD] `WebRTC Encoded Transform` に対応する
  - @tnoho
- [ADD] `Sora()` の引数に `video_codec_preference` を追加
  - @melpon
- [ADD] video_codec_preference を構築するために必要な以下のクラス、関数、enum を追加
  - `SoraVideoCodecCapability`
  - `SoraVideoCodecPreference`
  - `get_video_codec_capability()`
  - `create_video_codec_preference_from_implementation()`
  - `SoraVideoCodecType`
  - @melpon
- [UPDATE] nanobind を `2.5.0` に上げる
  - @voluntas
- [UPDATE] Sora C++ SDK のバージョンを `2025.2.0` に上げる
  - WEBRTC_BUILD_VERSION を `m132.6834.5.8` に上げる
    - libwebrtc のモジュール分割に追従するため `rtc::CreateRandomString` のヘッダを追加
    - Sora CPP SDK の `absl::optional` を `std::optional` に変更した仕様に追従する
    - Sora CPP SDK の `absl::nullopt` を `std::nullopt` に変更した仕様に追従する
  - CMAKE_VERSION を `3.31.6` に上げる
  - BOOST_VERSION を `1.87.0` に上げる
  - OPENH264_VERSION を `v2.6.0` に上げる
  - @torikizi @voluntas
- [FIX] nanobind が libstdc++ を使ってしまっていたのを libc++ を使うように修正する
  - @melpon

### misc

- [UPDATE] Boost のダウンロード URL を変更する
  - @voluntas
- [UPDATE] サイマルキャストの E2E テストについて encoderImplementation の値チェック内容を緩和する
  - サイマルキャストの encoderImplementation のチェックを文字列一致としていたが、帯域推定機能を有効にした後、値が安定しなくなったためチェック内容を緩和した
  - サイマルキャストの encoderImplementation の結果を以下の通り修正
    - `SimulcastEncoderAdapter (libaom, libaom, libaom)` -> `SimulcastEncoderAdapter` と `libaom` を含む
    - `SimulcastEncoderAdapter (libvpx, libvpx, libvpx)` -> `SimulcastEncoderAdapter` と `libvpx` を含む
    - `SimulcastEncoderAdapter (OpenH264, OpenH264, OpenH264)` -> `SimulcastEncoderAdapter` と `OpenH264` を含む
    - `SimulcastEncoderAdapter (VideoToolbox, VideoToolbox, VideoToolbox)` -> `SimulcastEncoderAdapter` と `VideoToolbox` を含む
  - @voluntas
- [UPDATE] ubuntu-latest を ubuntu-24.04 に変更する
  - @voluntas
- [CHANGE] CI の Ubuntu から libva と libdrm をインストールしないようにする
  - @voluntas
- [CHANGE] CMakefile の依存から libva と libdrm を削除する
  - @voluntas
- [CHANGE] ruff と mypy と pytest はバージョンを未指定にして、常に最新版を利用するようにする
  - @voluntas
- [CHANGE] 利用していなかった auditwheel を削除する
  - @voluntas
- [CHANGE] examples を <https://github.com/shiguredo/sora-python-sdk-examples> に移動する
  - @voluntas
- [CHANGE] rye から uv に変更する
  - @voluntas
- [CHANGE] サンプルアプリの src ディレクトリ構成を変更する
  - @voluntas
- [CHANGE] サンプルアプリの E2E テストを一旦削除する
  - @voluntas
- [ADD] pytest 実行時に sora_sdk のバージョンを表示する
  - @voluntas
- [ADD] dev-dependencies に pytest-repeat を追加する
  - <https://github.com/pytest-dev/pytest-repeat>
  - @voluntas
- [ADD] .env.template に TEST_LIBWEBRTC_LOG を追加する
  - none, verbose, error, warning, info, のいずれかを指定可能
  - @voluntas
- [ADD] Ubuntu 24.04 armv8 向けの E2E テストを追加する
  - @voluntas
- [ADD] pyjwt を dev-dependencies に追加する
  - @voluntas
- [ADD] macos-15 を E2E テストに追加する
  - @voluntas
- [ADD] canary.py を追加
  - @voluntas
- [ADD] Python 3.13 を E2E テストに追加する
  - @voluntas
- [ADD] macos-15 を E2E テストに追加する
  - @voluntas
- [ADD] tests/ に E2E テストを追加する
  - @voluntas
- [ADD] examples に E2E テストを追加する
  - @voluntas
- [ADD] AMD AMF の E2E テストを追加する
  - @voluntas
- [ADD] Intel VPL の E2E テストを追加する
  - @voluntas
- [ADD] Intel VPL の E2E テストに AV1 を追加する
  - @voluntas
- [ADD] Opus 16khz / mono のテストを追加する
  - @voluntas
- [FIX] run.py で local_sora_cpp_sdk_dir を設定した際に boost が引けなくなってしまっている問題を修正する
  - @tnoho
- [FIX] examples の設定に virtual = true を指定するようにする
  - これを指定しないとエラーになる
  - @voluntas

## 2024.3.0

**リリース日**: 2024-08-05

- [CHANGE] Jetson 5 の対応を削除
  - 以降は support/jetson-jetpack-6 ブランチで Jetson 6 のみの対応となる
  - @melpon
- [CHANGE] run.py の実行にターゲットの指定を必須にする
  - @melpon
- [UPDATE] 対応 Python バージョンの 3.8 と 3.9 のサポートを終了する
  - 対応 Ubuntu の最小である 22.04 が Python 3.10 なのでそれに合わせる
  - @voluntas
- [UPDATE] Sora C++ SDK のバージョンを `2024.7.0` に上げる
  - @voluntas
- [UPDATE] nanobind を `2.0.0` に上げて固定する
  - @melpon
- [UPDATE] cmake のバージョンを `3.29.6` に上げる
  - @voluntas
- [UPDATE] libwebrtc のバージョンを `m127.6533.1.1` に上げる
  - rtc::TaskQueue が廃止され、webrtc::TaskQueueBase を直接利用する方式変更に追従した
  - @voluntas
- [UPDATE] run.py を buildbase 化する
  - @melpon
- [UPDATE] Github Actions の Windows ビルドで Rye を利用する
  - @voluntas
- [UPDATE] GitHub Actions で pyi 生成用の Ubuntu を 24.04 に上げる
  - @voluntas
- [UPDATE] Github Actions のビルドで windows-2022 を利用する
  - Sora CPP SDK 2024.7.0 (libwebrtc m127) から windows-2022 でビルドする
  - @miosakuma
- [ADD] run.py の対応プラットフォームに ubuntu-24.04_x86_64 を追加する
  - @voluntas
- [ADD] Github Actions の対応プラットフォームに ubuntu-24.04_x86_64 と macos-14_arm64 を追加する
  - @voluntas
- [ADD] Github Actions でビルドに成功したら Slack へ通知するようにする
  - @voluntas
- [ADD] sora_sdk に型を付ける
  - @melpon
- [ADD] Sora C++ SDK と libwebrtc のローカルビルドを利用可能にする
  - @melpon
- [ADD] SoraConnection に get_stats 関数を追加
  - @melpon
- [FIX] SoraAudioSink.read が timeout を無視して失敗を返すケースがあったので修正する
  - @enm10k
- [FIX] SoraAudioSink.read が timeout を無視するケースがある問題を修正した結果、
  read の実行タイミングによってはクラッシュするようになったので修正する
  - @enm10k
- [FIX] MSVC の内部コンパイラエラーによって Windows で nanobind のビルドが出来ないのを修正する
  - @melpon

## 2024.2.0

**日時**: 2024-04-09

- [ADD] Sora Python SDK Samples を `examples` に移動する
  - @voluntas
- [CHANGE] Lyra のサポートを廃止し、以下のオプションを削除する
  - audio_codec_lyra_bitrate
  - audio_codec_lyra_usedtx
  - check_lyra_version
  - @enm10k
- [ADD] `on_switched` コールバックを追加する
  - @enm10k
- [UPDATE] nanobind を `1.9.2` に上げて固定する
  - @voluntas
- [UPDATE] ruff の最小を `0.3.0` に上げる
  - @voluntas
- [UPDATE] Sora C++ SDK のバージョンを `2024.6.0` に上げる
  - libwebrtc で `cricket::MediaEngineDependencies` が廃止された変更に追従する
  - WEBRTC_BUILD_VERSION を `m122.6261.1.0` に上げる
    - Ubuntu のビルドを通すために、 \_\_assertion_handler というファイルをコピーする処理を追加した
  - BOOST_VERSION を `1.85.0` に上げる
  - @enm10k @melpon
- [UPDATE] Intel VPL を利用した H.265 に対応
  - Sora C++ SDK のバージョンを `2024.6.0` に上げることで対応
  - @enm10k
- [FIX] pyproject.toml の `[rye.tool]` virtual = true を削除する
  - virtual = true は pip version 24 からはデフォルトが wheel が削除されるようになったための暫定対応だった
  - そのために pyproject.toml の `build-system.requires` に wheel と setuptools を指定する
  - @zztkm
- [FIX] サンプルアプリで 1080p の映像を送信すると 2-3 FPS しか出ないのを修正
  - ビデオキャプチャの設定に FOURCC と FPS を設定するようにする
  - 初期値は "MJPG", 30 を設定し、`.env` の `SORA_VIDEO_FOURCC`, `SORA_VIDEO_FPS` で変更可能とする
  - @melpon
- [FIX] Ubuntu 20.04 arm64 NVIDIA Jetson 5.1.2 で AV1 が正常に配信されない問題を修正
  - Sora C++ SDK のバージョンを `2024.6.0` に上げることで解消
  - @enm10k

## 2024.1.0

**2024-02-20**

- [CHANGE] フォーマッターを Ruff に変更する
  - @voluntas
- [CHANGE] SoraAudioSource.on_data の引数名を変更
  - @tnoho
- [CHANGE] SoraVideoSource.on_captured の引数名を変更
  - @tnoho
- [CHANGE] SoraVAD.analyze の引数名を変更
  - @tnoho
- [CHANGE] SoraConnection.on_track の引数を SoraMediaTrack に変更
  - @tnoho
- [UPDATE] auditwheel を `6.0.0` にアップデートする
  - @voluntas
- [UPDATE] build を `1.0.3` にアップデートする
  - @voluntas
- [UPDATE] wheel を `0.42.0` にアップデートする
  - @voluntas
- [UPDATE] build を `1.0.3` にアップデートする
  - @voluntas
- [UPDATE] pytest を `8.0.0` にアップデートする
  - @voluntas
- [UPDATE] setuptools の最小を `69.1` にする
  - @voluntas
- [UPDATE] ruff の最小を `0.2.2` にする
  - @voluntas
- [UPDATE] nanobind の最小を `1.8.0` にする
  - @voluntas
- [UPDATE] actions/setup-python@v5 に上げる
  - @voluntas
- [UPDATE] SoraMediaTrack を追加
  - @tnoho
- [UPDATE] Sora C++ SDK のバージョンを `2024.1.0` に上げる
  - WebRTC m116 で cricket::Codec は protected になったので cricket::CreateVideoCodec に修正する
  - WebRTC m118 でパッケージディレクトリが変更されたためそれに追従する
  - WebRTC m120 の webrtc::EncodedImage API の変更に追従する
  - WEBRTC_BUILD_VERSION を `m120.6099.1.2` に上げる
  - BOOST_VERSION を `1.83.0` に上げる
  - CMAKE_VERSION を `3.28.1` に上げる
  - @voluntas @miosakuma
- [UPDATE] ForwardingFilter に version と metadata を追加する
  - `Sora 2023.2.0` へ追従
  - `C++ SDK 2024.1.0` へ追従
  - @miosakuma
- [UPDATE] NVIDIA JetPack を `5.1.2` に上げる
  - @miosakuma
- [UPDATE] OpenH264 を `v2.4.1` に上げる
  - @voluntas
- [ADD] GitHub Actions workflows/build.yml を平日 14:00 JST 定期実行する
  - @voluntas
- [ADD] 発話区間の検出が可能な SoraVAD の追加
  - @tnoho
- [ADD] リアルタイム性を重視した AudioStreamSink の追加
  - @tnoho
- [ADD] AudioStreamSink が返す音声フレームとして pickle が可能な AudioFrame を追加
  - @tnoho
- [FIX] `pyproject.toml` の `[rye.tool]` に `virtual = true` を追加する
  - これで Windows ビルド失敗の原因である `--e file:.` が消える
  - @voluntas
- [ADD]H.265 に対応
  - Sora C++ SDK のバージョンアップに伴い macOS で H.265 が利用可能になる
  - @voluntas @miosakuma

## 2023.3.1

**2023-07-13**

- [FIX] C++ SDK のバージョンを 2023.7.2 にあげる
  - 特定のタイミングで切断が発生すると Closing 状態で止まってしまう問題が修正された
  - @sile

## 2023.3.0

**2023-07-06**

- [CHANGE] Sora.create_connection() が複数のシグナリング URL を受け取れるようにする
  - C++ SDK の仕様に合わせるための破壊的な変更
  - `signaling_url` は廃止して `signaling_urls` で置き換える
  - `signaling_urls` は `List[str]` を受け取る
  - @sile

## 2023.2.0

**2023-07-03**

- [ADD] OpenH264 に対応
  - Ubunut 22.04 x86_64 でのみ対応
  - @melpon

## 2023.1.2

**2023-06-28**

- [FIX] Windows の Python 用ライブラリが dll ではなく pyd だったのを修正する
  - @melpon

## 2023.1.1

**2023-06-27**

- [FIX] connect 直後に disconnect すると落ちるのを修正
  - @melpon
- [FIX] C++ SDK のバージョンを 2023.7.1 に上げる
  - @voluntas

## 2023.1.0

**2023-06-20**

- [UPDATE] `create_video_source()` と `set_enabled()` の引数に名前をつける（キーワード引数で呼べるようにする）
  - @sile
- [UPDATE] C++ SDK のバージョンを 2023.7.0 に上げる
  - @sile
- [UPDATE] 映像コーデックパラメータを指定可能にする
  - `Sora.create_connection()` の引数に以下を追加:
    - `video_vp9_params`
    - `video_av1_params`
    - `video_h264_params`
  - @sile
- [FIX] 転送フィルターのルールの "operator" フィールドが誤って "op" になっていたのを修正する
  - @sile
- [UPDATE] nanobind の最小バージョンを 1.4.0 にする
  - @voluntas
- [UPDATE] sora_client に "Sora Python SDK {PYTHON_SDK_VERSION}" を設定する
  - 今までは C++ SDK のデフォルト値が使用されていた
  - PYTHON_SDK_VERSION の部分には pyproject.toml の project.version に記載の値が使用される
  - @sile
- [FIX] 0 を途中で含むデータを送受信すると途中で途切れる問題を修正
  - @sile
- [ADD] libwebrtc のログを有効にするための `enable_libwebrtc_log()` 関数を追加する
  - `sora_sdk.enable_libwebrtc_log(sora_sdk.SoraLoggingSeverity.INFO)` といった感じで使用する
  - ログレベル (severity) は libwebrtc 準拠で `VERBOSE`, `INFO`, `WARNIGN`, `ERROR`, `NONE` の五段階
  - @sile
- [CHANGE] デフォルトでは libwebrtc のログは出さないようにする
  - @sile
- [CHANGE] audio および video パラメータが None を受け取れるようにする
  - 今までは `bool` だったのを他のパラメータに合わせて `opitonal<bool>` に変更
  - @sile
- [ADD] C++ SDK が提供して Python SDK が未提供だったシグナリングパラメータを追加する
  - 以下のパラメータを追加する:
    - bundle_id
    - signaling_notify_metadata
    - video_bit_rate
    - audio_bit_rate
    - simulcast
    - spotlight
    - spotlight_nubmer
    - simulcast_rid
    - spotlight_focus_rid
    - spotlight_unfocus_rid
    - forwarding_filter
    - data_channel_signaling_timeout
    - disconnect_wait_timeout
    - websocket_close_timeout
    - websocket_connection_timeout
    - audio_codec_lyra_bitrate
    - audio_codec_lyra_usedtx
    - check_lyra_version
    - audio_streaming_language_code
    - insecure
    - client_cert
    - client_key
    - proxy_url
    - proxy_username
    - proxy_password
    - proxy_agent
  - いずれも未指定の場合には C++ SDK のデフォルト値が採用される
  - @sile
- [UPDATE] boost のバージョンを 1.82.0 に更新する
- [UPDATE] libwebrtc のバージョンを m114.5735.2.0 に更新する
- [UPDATE] Sora C++ SDK のバージョンを 2023.6.0 に更新する
  - @sile
- [UPDATE] `Sora.connect()` メソッドにバリデーションを追加する
  - 以下のケースでは例外を送出するようにする:
    - `connect()` 呼び出し後に、同じインスタンスで再度 `connect()` を呼び出した場合
    - `disconnect()` 呼び出し後に、同じインスタンスで `connect()` を呼び出した場合
  - @sile
- [UPDATE] SIGSEGV などの異常終了を発生しにくくする
  - 合わせてサンプルコードの整理（e.g., シグナルハンドラを使わなくする）も行っている
  - @sile
- [CHANGE] メッセージング系のサンプルでは音声および映像を無効にする
  - `messaging_{sendrecv,sendonly,recvonly}.py` では `Sora.create_connectoin(audio=False, video=False, ...)` を指定する
  - @sile
- [ADD] Python SDK では常にマルチストリームを有効にする
  - デフォルト値を使うのではなく `sora::SoraSignalingConfig::multistream` フィールドに明示的に `true` を指定する
  - @sile
- [ADD] Sora.create_connection() メソッドに音声・映像コーデックを指定するための引数を追加する
  - `audio_codec_type` および `video_codec_type` 引数
  - デフォルトは未指定
  - @sile
- [ADD] Sora.create_connection() メソッドに音声・映像の有効無効を指定するための引数を追加する
  - `audio` および `video` 引数
  - デフォルトはどちらも `true`
- [UPDATE] Sora::ConvertDataChannels() の実装をリファクタリング
  - @sile
- [ADD] データチャネルを使ったサンプルを追加する
  - 以下の三つを追加:
    - test/messaging_readonly.py
    - test/messaging_sendonly.py
    - test/messaging_sendrecv.py
  - @sile
- [CHANGE] `SoraConnection.on_message()` コールバックの第二引数の方を `str` から `bytes` に変更する
  - 文字列以外の任意のバイト列が送受信可能なため
  - @sile
- [ADD] `SoraConnection` クラスに `send_data_channel(label: str, data: bytes)` メソッドを追加する
  - データチャネル経由でメッセージを送信するためのメソッド
  - 使用するためには `Sora.create_connection()` で以下のオプションを指定する必要がある:
    - `data_channel_signaling=True`
    - `data_channels=[{"label": ..., "direction": ..., ...}, ...]`
  - なお `create_connection()` の後、 `SoraConnection.on_data_channel(label: str)` コールバックが呼び出されるまでは、該当ラベルに対するメッセージ送信は行えないので注意が必要
  - @sile
- [ADD] `Sora.create_connection()` メソッドにデータチャネル関連の引数を追加する
  - 追加したのは以下の引数:
    - `data_channels`
    - `data_channel_signaling`
    - `ignore_disconnect_websocket`
  - @sile
- [ADD] PyPI に登録する GitHub Actions を追加する
  - @melpon
- [ADD] rye を使ってビルドとパッケージングが出来るようにする
  - @melpon
- [ADD] nanobind を利用して Sora C++ SDK ベースの Python SDK を追加する
  - @tnoho
