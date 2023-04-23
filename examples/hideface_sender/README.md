# 送信前映像処理サンプル

Web カメラより取得した映像を顔検出にかけ、顔の部分を画像に置き換えた上で Sora に映像を送信するサンプルです。

顔の検出には [mediapipe](https://developers.google.com/mediapipe) の [Face Detector](https://developers.google.com/mediapipe/solutions/vision/face_detector/) を使用し、検出した顔領域の画像置き換えには [pillow](https://python-pillow.org/) を使用しています。

### 注意

このサンプルを実行するにあたっては Web カメラとマイクが必要です。 MacBook Air の内蔵カメラは利用できない場合があります。その場合は USB カメラを別途接続してください。

## サンプルを実行するにあたって

[examples の README.md のサンプルを実行するにあたって](../README.md#サンプルを実行するにあたって)を完了していない場合は、先にこちらを完了させてください。

## 依存するパッケージのインストール

以下のコマンドを Sora Python SDK のルートディレクトリ(setup.py のあるディレクトリ)から実行し、依存するパッケージをインストールしてください。

```console
pip3 install -r examples/hideface_sender/requirements.txt
```

また、依存している mediapipe は OS によってインストールするパッケージを変えたほうが良いため `requirements.txt` には含んでおりません。後述の手順を参照してください。

## mediapipe のインストール

Apple Silicon 搭載製品は公式の mediapipe では高速動作しないため、下記のコマンドでフォークをインストールしてください。

```console
pip3 install mediapipe-silicon
```

その他の CPU の場合は下記のコマンドでインストールしてください。

```console
pip3 install mediapipe
```

## サンプルを実行する

サンプルを以下のコマンドで実行してください。

```console
python3 ./examples/hideface_sender/hideface_sender.py
```

Ctrl + C で終了できます。
