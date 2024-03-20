# Python Sora SDK サンプル集

## About Shiguredo's open source software

We will not respond to PRs or issues that have not been discussed on Discord. Also, Discord is only available in Japanese.

Please read https://github.com/shiguredo/oss/blob/master/README.en.md before use.

## 時雨堂のオープンソースソフトウェアについて

利用前に https://github.com/shiguredo/oss をお読みください。

## サンプルコードの実行方法

[Rye](https://github.com/mitsuhiko/rye) というパッケージマネージャーを利用しています。

Linux と macOS の場合は `curl -sSf https://rye-up.com/get | bash` でインストール可能です。
Windows は https://rye-up.com/ の Installation Instructions を確認してください。

### 依存パッケージのビルド

```console
$ rye sync
```

### サンプルコードの実行

```console
$ cp .env.template .env
# .env に必要な変数を設定してください。
$ rye run media_recvonly
```

## ライセンス

Apache License 2.0

```
Copyright 2023-2024, tnoho (Original Author)
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
