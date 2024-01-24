# Sora Python SDK

[![PyPI](https://img.shields.io/pypi/v/sora_sdk)](https://pypi.org/project/sora-sdk/)
[![image](https://img.shields.io/pypi/pyversions/sora_sdk.svg)](https://pypi.python.org/pypi/sora_sdk)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Actions status](https://github.com/shiguredo/sora-python-sdk/workflows/build/badge.svg)](https://github.com/shiguredo/sora-python-sdk/actions)

Sora Python SDK は [WebRTC SFU Sora](https://sora.shiguredo.jp/) の Python クライアントアプリケーションを開発するためのライブラリです。[Sora C++ SDK](https://github.com/shiguredo/sora-cpp-sdk) をベースにしています。

## About Shiguredo's open source software

We will not respond to PRs or issues that have not been discussed on Discord. Also, Discord is only available in Japanese.

Please read https://github.com/shiguredo/oss/blob/master/README.en.md before use.

## 時雨堂のオープンソースソフトウェアについて

利用前に https://github.com/shiguredo/oss をお読みください。

## Sora Python SDK について

様々なプラットフォームに対応しすぐに使い始められる WebRTC SFU Sora 向けの Python SDK です。

## 特徴

- [Sora C++ SDK](https://github.com/shiguredo/sora-cpp-sdk) ベース
- WebRTC 部分の機能は [libwebrtc](https://webrtc.googlesource.com/src/) を採用
- Windows / macOS / Linux (Ubuntu) プラットフォームに対応
- NVIDIA Jetson に対応
- Intel / Apple / NVIDIA のハードウェアデコーダー/エンコーダーに対応
- [OpenH264](https://github.com/cisco/openh264) を利用した H.264 のソフトウェアエンコーダー/デコーダーに対応
- 物体検出などの入力に Sora 経由で受信した映像が利用できる
- 音声認識などの入力に Sora 経由で受信した音声を利用できる
- `pip install sora_sdk` でインストール可能

## 利用イメージ

- データチャンネルを利用して Python において映像、音声を解析した結果を Sora 経由で配信する
- Text to Speech の音声を Sora 経由で配信する
- 映像入力に対して Pillow などで加工した映像を Sora を経由で配信する
- A チャンネルの参加者からの映像と音声を B チャンネルに対して加工した上で Sora 経由で配信する

## ドキュメント

[Sora Python SDK](https://sora-python-sdk.shiguredo.jp/)

## サンプル集

[Sora Python SDK サンプル集](https://github.com/shiguredo/sora-python-sdk-samples)

## sora_sdk パッケージの追加

### pip

```console
$ pip install sora_sdk
```

### Rye

[Rye](https://rye-up.com/)

```
$ rye add sora_sdk
$ rye sync
```

## システム条件

- WebRTC SFU Sora 2023.2.0 以降
- Python 3.8 以上

## 対応プラットフォーム

- Windows 11 x86_64 以降
- macOS 13 arm64 以降
- Ubuntu 22.04 x86_64
- Ubuntu 20.04 arm64
  - Python 3.8 のみ対応
  - NVIDIA Jetson JetPack SDK 5.1.2

## 対応機能

- Sora の機能へ追従
- VP8 / VP9 / AV1 / H.264 のハードウェアアクセラレーター (HWA) 対応
- OpenH264 を利用した H.264 のソフトウェアエンコーダー/デコーダーへの対応

## 優先実装

優先実装とは Sora のライセンスを契約頂いているお客様向けに Sora Python SDK の実装予定機能を有償にて前倒しで実装することです。

**詳細は Discord やメールなどでお気軽にお問い合わせください**

- DataChannel 対応
  - [アダワープジャパン株式会社](https://adawarp.com/) 様

### 優先実装が可能な機能一覧

**詳細は Discord やメールなどでお気軽にお問い合わせください**

- Ubuntu 22.04 arm64
  - Python 3.10
  - NVIDIA Jetson JetPack SDK 6.0

## サポートについて

### Discord

- **サポートしません**
- アドバイスします
- フィードバック歓迎します

最新の状況などは Discord で共有しています。質問や相談も Discord でのみ受け付けています。

https://discord.gg/shiguredo

### バグ報告

Discord へお願いします。

## ライセンス

Apache License 2.0

```
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

https://www.openh264.org/BINARY_LICENSE.txt

```
"OpenH264 Video Codec provided by Cisco Systems, Inc."
```
