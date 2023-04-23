# 送信サンプル

Web カメラより取得した映像とマイクより取得した音声を Sora に送信するサンプルです。

Web カメラからのフレーム取得には OpenCV を使用しており、取得したフレームをそのまま Sora Python SDK で送信できるため。 `cv2.VideoCapture` と `cv2.imshow` を利用した機械学習サンプルを容易に移植可能です。

マイクからの音声取得には [python-sounddevice](https://github.com/spatialaudio/python-sounddevice) を使用しています。

### 注意

このサンプルを実行するにあたっては Web カメラとマイクが必要です。 MacBook Air の内蔵カメラは利用できない場合があります。その場合は USB カメラを別途接続してください。

## サンプルを実行するにあたって

[examples の README.md のサンプルを実行するにあたって](../README.md#サンプルを実行するにあたって)を完了していない場合は、先にこちらを完了させてください。

## 依存するパッケージのインストール

以下のコマンドを Sora Python SDK のルートディレクトリ(setup.py のあるディレクトリ)から実行し、依存するパッケージをインストールしてください。

```console
pip3 install -r examples/sendonly/requirements.txt
```

また、依存している python-sounddevice は PortAudio を使用します。 Ubuntu の場合のみ後述の手順でインストールしてください。

## (Ubuntu のみ)PortAudio のインストール

Ubuntu の場合には PortAudio が自動的にインストールされませんので、以下のコマンドでインストールしてください。

```console
sudo apt install libportaudio2
```

## サンプルを実行する

サンプルを以下のコマンドで実行してください。

```console
python3 ./examples/sendonly/sendonly.py
```

Ctrl + C で終了できます。
