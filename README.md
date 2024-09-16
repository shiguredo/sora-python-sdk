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
- Windows / macOS / Linux (Ubuntu) プラットフォームに対応
- WebRTC 統計情報の取得が可能
- Intel / Apple / NVIDIA のハードウェアデコーダー/エンコーダーに対応
  - Intel VPL (AV1 / H.264 / H.265)
  - Apple Video Toolbox (H.264 / H.265)
  - NVIDIA Video Codec SDK (VP9 / H.264 / H.265)
  - NVIDIA Jetson JetPack SDK (AV1 / H.264 / H.265)
  - [各プラットフォームで利用可能な HWA への対応](https://github.com/shiguredo/sora-cpp-sdk?tab=readme-ov-file#%E7%89%B9%E5%BE%B4)
- [OpenH264](https://github.com/cisco/openh264) を利用した H.264 のソフトウェアエンコーダー/デコーダーに対応
- 音声デバイス処理に [sounddevice](https://pypi.org/project/sounddevice/) などが利用できる
- 映像デバイス処理に [opencv-python](https://pypi.org/project/opencv-python/) などが利用できる
- 音声認識などの入力に受信した音声を利用できる
- 物体検出などの入力に受信した映像を利用できる
- `uv add sora_sdk` や `pip install sora_sdk` でインストール可能
- [NVIDIA Jetson JetPack SDK](https://developer.nvidia.com/embedded/jetpack) に対応

## 利用イメージ

- データチャンネルを利用して Python において映像、音声を解析した結果を Sora 経由で配信する
- Text to Speech の音声を Sora 経由で配信する
- 映像入力に対して Pillow などで加工した映像を Sora を経由で配信する
- A チャンネルの参加者からの映像と音声を B チャンネルに対して加工した上で Sora 経由で配信する

## ドキュメント

[Sora Python SDK](https://sora-python-sdk.shiguredo.jp/)

## サンプル集

[examples](examples) を参照してください。

## sora_sdk パッケージの追加

### pip

```bash
pip install sora_sdk
```

### uv

[uv](https://docs.astral.sh/uv/)

```bash
uv add sora_sdk
uv sync
```

### NVIDIA Jetson 向けパッケージ

PyPI 経由ではインストールできません。
パッケージバイナリを配布しておりますので、そちらをご利用ください。

## システム条件

- WebRTC SFU Sora 2023.2.0 以降
- Python 3.10 以上

## 対応プラットフォーム

- Windows 11 x86_64
- Windows Server 2022 x86_64
- macOS Ventura 14 arm64
- macOS Sonoma 13 arm64
- Ubuntu 24.04 LTS x86_64
- Ubuntu 22.04 LTS x86_64
- Ubuntu 22.04 LTS arm64 (NVIDIA Jetson JetPack SDK 6)
  - PyPI からではなくパッケージファイルを利用してください

## 優先実装

優先実装とは Sora のライセンスを契約頂いているお客様向けに Sora Python SDK の実装予定機能を有償にて前倒しで実装することです。

**詳細は Discord やメールなどでお気軽にお問い合わせください**

- DataChannel 対応
  - [アダワープジャパン株式会社](https://adawarp.com/) 様
- Intel VPL H.265 対応
  - [アダワープジャパン株式会社](https://adawarp.com/) 様

### 優先実装が可能な機能一覧

**詳細は Discord やメールなどでお気軽にお問い合わせください**

- Windows 11 arm64
- Ubuntu 24.04 arm64
- Ubuntu 22.04 arm64
- Ubuntu 20.04 arm64 (NVIDIA Jetson JetPack SDK 5)
- AMD Video Core Next (VCN) 対応
  - VP9 / AV1 / H.264 / H.265
- Python 3.9 以前への対応

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
Copyright 2023-2024, tnoho (Original Author)
Copyright 2023-2024, Wandbox LLC (Original Author)
Copyright 2023-2024, Shiguredo Inc.

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

このリポジトリに含まれる `shiguremaru.png` ファイルのライセンスは [CC BY-NC-ND 4.0](https://creativecommons.org/licenses/by-nc-nd/4.0/deed.ja) です。

## OpenH264

<https://www.openh264.org/BINARY_LICENSE.txt>

```text
"OpenH264 Video Codec provided by Cisco Systems, Inc."
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
