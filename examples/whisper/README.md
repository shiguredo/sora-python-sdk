# 音声認識(whisper)サンプル

Open AI の高精度な音声認識モデルである [Whisper](https://github.com/openai/whisper) を使用して、受信した音声を認識しコンソールに表示するサンプルです。

十分な音声認識精度を得るためには一定の長さの音声データが必要なため、すでに認識結果を表示した音声データを再利用します。そのため認識結果が一部重複します。

### 注意

Whisper は認識精度は高いものの、非常に重い音声認識エンジンです。動作は macOS 13.x の Apple Silicon でのみ確認しています。

## サンプルを実行するにあたって

[examples の README.md のサンプルを実行するにあたって](../README.md#サンプルを実行するにあたって)を完了していない場合は、先にこちらを完了させてください。

## 依存するパッケージのインストール

以下のコマンドを Sora Python SDK のルートディレクトリ(setup.py のあるディレクトリ)から実行し、依存するパッケージをインストールしてください。

```console
pip3 install -r examples/whisper/requirements.txt
```

また、このサンプルでは上記コマンドではインストールされない Whisper.cpp を使用しますので後述の手順に従ってインストールしてください。

## Whisper.cpp のインストール

このサンプルでは Whisper を利用するにあたって十分な実行速度を稼ぐため [Whisper.cpp](https://github.com/ggerganov/whisper.cpp) を使用しています。 Whisper.cpp を Python から実行するため binding には[こちら](https://github.com/aarnphm/whispercpp)を使用しました。

### pip でのインストール

以下のコマンドで Whisper.cpp の Python binding を pip でインストールできます。

```console
pip3 install whispercpp
```

### pip でインストールした場合のエラーとその対処

インストールしてもサンプルを実行できなかった場合は以下を確認してください。

#### `GLIBCXX_3.4.29` not found と表示される

libstdc++6 が古い可能性があるため下記のコマンドでアップデートを行ってください。

```console
sudo apt update libstdc++6
```

アップデートを行った後に下記のコマンドを実行することで確認することができます。

```console
strings /lib/x86_64-linux-gnu/libstdc++.so.6 | grep GLIBCXX_3.4.29
```

出力がある場合には実行可能になっていますので、再度サンプルを実行してください。

出力がない場合は `GLIBCXX_3.4.29` がインストールできないため後述のソースからビルドしてのインストールをお試しください。

#### 実行時にビルドを行った Python のバージョンと一致しないと表示された場合

pip で配布されているものを実行することはできません。
pip でインストールされているものを以下のコマンドでアンインストールしてください。

```console
pip3 uninstall whispercpp
``` 

アンインストール後に後述のソースからビルドしてのインストールをお試しください。

### ソースからビルドしてのインストール

以下のコマンドを実行してインストールしてください。

```console
pip3 install git+https://github.com/aarnphm/whispercpp.git@v0.0.17 -vv
```

### ソースからビルドしてのインストールした場合のエラーとその対処

ソースからビルドしてのインストールが失敗する場合は以下を確認してください。

#### `f'spec_for_{name}'` で SyntaxError: invalid syntax というエラーがでる

ビルド時に実行される python が python2.7 を参照しているため生じています。

以下のコマンドで python を python3 に紐づけることで解決します。

```console
sudo apt install python-is-python3
```

## サンプルを実行する

サンプルを以下のコマンドで実行してください。

```console
python3 ./examples/whisper/whisper.py
```

Ctrl + C で終了できます。
