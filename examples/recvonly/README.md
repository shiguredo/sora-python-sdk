# 受信サンプル

Sora から映像と音声を受信するサンプルです。

受信したフレームの表示には OpenCV を使用しており、取得したフレームをそのまま Sora Python SDK で送信できるため。 `cv2.VideoCapture` と `cv2.imshow` を利用した機械学習サンプルを容易に移植可能です。

音声の出力には [python-sounddevice](https://github.com/spatialaudio/python-sounddevice) を使用しています。

### 注意

このサンプルを実行するにあたってはディスプレイとスピーカーが必要です。

## サンプルを実行するにあたって

[examples の README.md のサンプルを実行するにあたって](../README.md#サンプルを実行するにあたって)を完了していない場合は、先にこちらを完了させてください。

## 依存するパッケージのインストール

以下のコマンドを Sora Python SDK のルートディレクトリ(setup.py のあるディレクトリ)から実行し、依存するパッケージをインストールしてください。

```console
pip3 install -r examples/recvonly/requirements.txt
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
python3 ./examples/recvonly/recvonly.py
```

Ctrl + C で終了できます。
