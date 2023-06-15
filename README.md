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

https://sora-python-sdk.shiguredo.jp/

#### Rye

[Rye](https://github.com/mitsuhiko/rye) というパッケージマネージャーを利用しています。

Linux と macOS の場合は `curl -sSf https://rye-up.com/get | bash` でインストール可能です。
Windows は https://rye-up.com/ の Installation Instructions を確認してください。

```console
$ rye sync
$ rye run python run.py
$ rye run python -m build
```

これで dist/ 以下に `*.whl` ファイルが作成されます。

## 実装上の注意

- Sora Python SDK のコールバックメソッドは、Python ランタイムのスレッドではなく、 C++ で実装された処理を実行するために別に立てたスレッドから呼び出されるため、以下の点に注意する必要があります:
  - コールバックの中で例外を使う場合には、必ずコールバック内でキャッチして外に漏らしてはいけません （例外が外に漏れると Python プログラムが異常終了します）
  - コールバック処理の中にブロックする処理を記述してはいけません （コールバック時呼び出しスレッド上では WebRTC 通信を実現する諸々の処理も走っているので、ブロックするとそれらの実行を阻害してしまう）
- 一度切断された Sora インスタンスを使い回して、新しい接続を始めることはできません

## システム条件

- WebRTC SFU Sora 2023.1.0 以降
- Python 3.8 以上

## 対応プラットフォーム

- Windows 10 1809 x86_64 以降
- macOS 12.4 arm64 以降
- Ubuntu 22.04 x86_64
- Ubuntu 20.04 arm64
  - NVIDIA Jetson JetPack SDK 5 系

### 未検証

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
Copyright 2023-2023, Wandbox LLC (Original Author)
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
