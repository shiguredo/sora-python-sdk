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

- [UPDATE] nanobind を `2.8.0` に上げる
  - @voluntas
- [UPDATE] Sora C++ SDK のバージョンを `2025.5.0-canary.2` に上げる
  - WEBRTC_BUILD_VERSION を `m139.7258.3.0` に上げる
  - @melpon
- [FIX] GitHub Actions の check_ubuntu_wheel ジョブで uv 0.8 以降の externally managed Python 環境エラーを修正する
  - `uv run --with` から `uv pip install` を使用する方式に変更
  - checkouts せずに仮想環境を作成して wheel ファイルをテストするように変更
  - @voluntas

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
