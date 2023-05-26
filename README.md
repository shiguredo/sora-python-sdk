# Sora Python SDK

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

Sora Python SDK は [WebRTC SFU Sora](https://sora.shiguredo.jp/) の Python クライアントアプリケーションを開発するためのライブラリです。[Sora C++ SDK](https://github.com/shiguredo/sora-cpp-sdk) をベースにしています。

## About Shiguredo's open source software

We will not respond to PRs or issues that have not been discussed on Discord. Also, Discord is only available in Japanese.

Please read https://github.com/shiguredo/oss/blob/master/README.en.md before use.

## 時雨堂のオープンソースソフトウェアについて

利用前に https://github.com/shiguredo/oss をお読みください。

## Sora Python SDK について

様々なプラットフォームに対応した WebRTC SFU Sora 向けの Python SDK です。

## 特徴

- [Sora C++ SDK](https://github.com/shiguredo/sora-cpp-sdk) ベース
- WebRTC 部分の機能は [libwebrtc](https://webrtc.googlesource.com/src/) を採用
- 物体検出などの入力に Sora 経由で受信した映像が利用できる
- 音声認識などの入力に Sora 経由で受信した音声を利用できる

## 利用イメージ

- データチャンネルを利用して Python において映像、音声を解析した結果を Sora 経由で配信する
- Text to Speech の音声を Sora 経由で配信する
- 映像入力に対して Pillow などで加工した映像を Sora を経由で配信する
- A チャンネルの参加者からの映像と音声を B チャンネルに対して加工した上で Sora 経由で配信する

## ドキュメント

TBD

### ビルド

Linux のみ以下のインストールが必要です。

```
sudo apt install libdrm-dev libva-dev
```

#### Rye

[Rye](https://github.com/mitsuhiko/rye) というパッケージマネージャーを利用しています。

Linux と macOS の場合は `curl -sSf https://rye-up.com/get | bash` でインストール可能です。
Windows は https://rye-up.com/ の Installation Instructions を確認してください。

```console
$ rye sync
```

## サンプル

```console
$ rye run python examples/recvonly.py
```

## システム条件

- WebRTC SFU Sora 2022.2.0 以降
- Python 3.10 以上

## 対応プラットフォーム

- macOS 12.4 arm64 以降
- Ubuntu 20.04 x86_64
- Ubuntu 22.04 x86_64
- Windows 10 1809 x86_64 以降

### 未検証

- Ubuntu 20.04 arm64
- Ubuntu 22.04 arm64

## 対応機能

TBD

## 優先実装

優先実装とは Sora のライセンスを契約頂いているお客様限定で Sora Python SDK の実装予定機能を有償にて前倒しで実装することです。

### 優先実装が可能な機能一覧

**詳細は Discord やメールなどでお気軽にお問い合わせください**

TBD

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

Copyright 2023-2023, tnoho (Original Author)
Copyright 2023-2023, Shiguredo Inc.

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

```

```
