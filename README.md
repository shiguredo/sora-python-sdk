# Sora Python SDK

[![PyPI](https://img.shields.io/pypi/v/sora_sdk)](https://pypi.org/project/sora-sdk/)
[![image](https://img.shields.io/pypi/pyversions/sora_sdk.svg)](https://pypi.python.org/pypi/sora_sdk)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Actions status](https://github.com/shiguredo/sora-python-sdk/workflows/build/badge.svg)](https://github.com/shiguredo/sora-python-sdk/actions)

Sora Python SDK は [WebRTC SFU Sora](https://sora.shiguredo.jp/) の Python クライアントアプリケーションを開発するためのライブラリです。[Sora C++ SDK](https://github.com/shiguredo/sora-cpp-sdk) をベースにしています。

## About Shiguredo's open source software

We will not respond to PRs or issues that have not been discussed on Discord. Also, Discord is only available in Japanese.

Please read <https://github.com/shiguredo/oss/blob/master/README.en.md> before use.

## 時雨堂のオープンソースソフトウェアについて

利用前に <https://github.com/shiguredo/oss> をお読みください。

## Sora Python SDK について

様々なプラットフォームに対応しすぐに使い始められる WebRTC SFU Sora 向けの Python SDK です。

音声や映像デバイスの処理を SDK から独立させているため、様々なライブラリを利用する事ができます。

## 特徴

- [Sora C++ SDK](https://github.com/shiguredo/sora-cpp-sdk) ベース
- WebRTC 部分の機能は [libwebrtc](https://webrtc.googlesource.com/src/) を採用
- Windows / macOS / Linux (Ubuntu / Raspberry Pi OS) プラットフォームに対応
- [WebRTC 統計情報](https://www.w3.org/TR/webrtc-stats/) の取得が可能
- [WebRTC Encoded Transform](https://www.w3.org/TR/webrtc-encoded-transform/) に対応
- 回線が不安定になった際、解像度とフレームレートどちらを維持するかの設定をする [DegradationPreference](https://w3c.github.io/mst-content-hint/#degradation-preference-when-encoding) に対応
  - MAINTAIN_FRAMERATE / MAINTAIN_RESOLUTION / BALANCED が指定できる
- 発話区間の検出が可能な VAD (Voice Activity Detection) に対応
- Intel / Apple / NVIDIA / Raspberry Pi のハードウェアデコーダー/エンコーダーに対応
  - Apple Video Toolbox (H.264 / H.265)
    - macOS arm64 で利用できる
  - Intel VPL (AV1 / H.264 / H.265)
    - Ubuntu x86_64 / Windows x86_64 で利用できる
  - AMD AMF (VP9 /AV1 / H.264 / H.265)
    - Ubuntu x86_64 / Windows x86_64 で利用できる
    - AV1 エンコードは Windows x86_64 でのみ利用できる
    - VP9 はデコードのみ利用できる
  - NVIDIA Video Codec (VP8 / VP9 / AV1 / H.264 / H.265)
    - Ubuntu x86_64 / Windows x86_64 で利用できる
    - VP8 と VP9 はデコードのみ利用できる
  - NVIDIA Jetson JetPack SDK (AV1 / H.264 / H.265)
  - Raspberry Pi (H.264)
    - Raspberry Pi 4 / Raspberry Pi 3 / Raspberry Pi 2 Model B v1.2 / Raspberry Pi Zero 2 W で利用できる
    - V4L2-M2M API を利用している
  - [各プラットフォームで利用可能な HWA への対応](https://github.com/shiguredo/sora-cpp-sdk?tab=readme-ov-file#%E7%89%B9%E5%BE%B4)
- [OpenH264](https://github.com/cisco/openh264) を利用した H.264 のソフトウェアエンコーダー/デコーダーに対応
  - Ubuntu x86_64 / Ubuntu arm64 / Windows x86_64 / macOS arm64 で利用できる
- 音声デバイス処理に [sounddevice](https://pypi.org/project/sounddevice/) などが利用できる
- 映像デバイス処理に [opencv-python](https://pypi.org/project/opencv-python/) などが利用できる
- 音声認識などの入力に受信した音声を利用できる
- 物体検出などの入力に受信した映像を利用できる
- `uv add sora_sdk` や `pip install sora_sdk` でインストールできる
  - Raspberry Pi 向けのパッケージも `uv add sora_sdk_rpi` でインストールできる
- Raspberry Pi 向けに libcamera 用の `create_libcamera_source` を提供
- [NVIDIA Jetson JetPack SDK](https://developer.nvidia.com/embedded/jetpack) に対応

## 利用イメージ

- データチャンネルを利用して Python において映像、音声を解析した結果を Sora 経由で配信する
- Text to Speech の音声を Sora 経由で配信する
- 映像入力に対して Pillow などで加工した映像を Sora を経由で配信する
- A チャンネルの参加者からの映像と音声を B チャンネルに対して加工した上で Sora 経由で配信する

## ドキュメント

[Sora Python SDK](https://sora-python-sdk.shiguredo.jp/)

## サンプル集

[shiguredo/sora-python-sdk-examples](https://github.com/shiguredo/sora-python-sdk-examples)

## sora_sdk パッケージの追加

[uv](https://docs.astral.sh/uv/) の利用を推奨します。

```bash
uv add sora_sdk
```

### Raspberry Pi OS 向けパッケージ

```bash
uv add sora_sdk_rpi
```

### NVIDIA Jetson 向けパッケージ

PyPI 経由ではインストールできません。
パッケージバイナリを配布しておりますので、そちらをご利用ください。

<https://github.com/shiguredo/sora-python-sdk/releases/tag/2024.3.0-jetson-jetpack-6.0.0.0>

## システム条件

- WebRTC SFU Sora 2024.2.0 以降
- Python 3.11 以上

## Python サポートポリシー

直近の 3 バージョンの Python をサポートします。

## 対応プラットフォーム

- Ubuntu 24.04 LTS x86_64
- Ubuntu 24.04 LTS arm64
- Ubuntu 22.04 LTS x86_64
- Ubuntu 22.04 LTS arm64
- macOS Sequoia 15 arm64
- macOS Ventura 14 arm64
- Windows 11 x86_64
- Windows Server 2025 x86_64
- Raspberry Pi OS armv8

### Raspberry Pi OS 向け

- Raspberry Pi OS bookworm (64bit)
  - Raspberry Pi 5
  - Raspberry Pi 4
  - Raspberry Pi 3
  - Raspberry Pi 2 Model B v1.2
  - Raspberry Pi Zero 2 W

> [!CAUTION]
>
> - Raspberry Pi 5 は H.264 ハードウェアエンコーダーが搭載されていません
> - Raspberry Pi 5 の H.265 ハードウェアデコーダーに対応していません

### NVIDIA Jetson 向け

- Ubuntu 22.04 LTS arm64 (NVIDIA Jetson JetPack SDK 6)
  - PyPI からではなくパッケージファイルを利用してください

### macOS の対応バージョン

直近の 2 バージョンをサポートします。

### Ubuntu の対応バージョン

直近の LTS 2 バージョンをサポートします。

## 優先実装

優先実装とは Sora のライセンスを契約頂いているお客様向けに Sora Python SDK の実装予定機能を有償にて前倒しで実装することです。

**詳細は Discord やメールなどでお気軽にお問い合わせください**

- DataChannel 対応
  - [アダワープジャパン株式会社](https://adawarp.com/) 様
- Intel VPL H.265 対応
  - [アダワープジャパン株式会社](https://adawarp.com/) 様

### 優先実装が可能な機能一覧

- Windows 11 arm64
- Ubuntu 22.04 arm64 (NVIDIA Jetson JetPack SDK 6.1)
- Ubuntu 20.04 arm64 (NVIDIA Jetson JetPack SDK 5)

## サポートについて

### Discord

- **サポートしません**
- アドバイスします
- フィードバック歓迎します

最新の状況などは Discord で共有しています。質問や相談も Discord でのみ受け付けています。

<https://discord.gg/shiguredo>

### バグ報告

Discord へお願いします。

## ライセンス

Apache License 2.0

```text
Copyright 2023-2025, tnoho (Original Author)
Copyright 2023-2025, Wandbox LLC (Original Author)
Copyright 2023-2025, Shiguredo Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
```

## OpenH264

<https://www.openh264.org/BINARY_LICENSE.txt>

```text
"OpenH264 Video Codec provided by Cisco Systems, Inc."
```

## NVDIA Video Codec SDK

<https://docs.nvidia.com/video-technologies/video-codec-sdk/12.2/license/index.html>

```text
“This software contains source code provided by NVIDIA Corporation.”
```

## H.264 (AVC) と H.265 (HEVC) のライセンスについて

**時雨堂が提供する libwebrtc のビルド済みバイナリには H.264 と H.265 のコーデックは含まれていません**

### H.264

H.264 対応は [Via LA Licensing](https://www.via-la.com/) (旧 MPEG-LA) に連絡を取り、ロイヤリティの対象にならないことを確認しています。

> 時雨堂がエンドユーザーの PC /デバイスに既に存在する AVC / H.264 エンコーダー/デコーダーに依存する製品を提供する場合は、
> ソフトウェア製品は AVC ライセンスの対象外となり、ロイヤリティの対象にもなりません。

### H.265

H.265 対応は以下の二つの団体に連絡を取り、H.265 ハードウェアアクセラレーターのみを利用し、
H.265 が利用可能なバイナリを配布する事は、ライセンスが不要であることを確認しています。

また、H.265 のハードウェアアクセラレーターのみを利用した H.265 対応の SDK を OSS で公開し、
ビルド済みバイナリを配布する事は、ライセンスが不要であることも確認しています。

- [Access Advance](https://accessadvance.com/ja/)
- [Via LA Licensing](https://www.via-la.com/)
