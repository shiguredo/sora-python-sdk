# Sora Python SDK サンプル

Sora Python SDK を使用することで、どのようなことができるか解りやすくするためにサンプルを用意しました。

## 各サンプルについて

上から順により応用が効いたものになっています。最初は recvonly と sendonly を試し動作を確認することをお勧めします。

### recvonly

Sora から受信した映像と音声を再生します。

### sendonly

Web カメラより取得した映像とマイクより取得した音声を Sora に送信します。

### hideface_sender

Web カメラより取得した映像を顔検出にかけ、顔の部分を画像に置き換えた上で Sora に映像を送信します。 

### whisper

Open AI の高精度な音声認識モデルである [Whisper](https://github.com/openai/whisper) を使用して、受信した音声を認識しコンソールに表示します。

## サンプルを実行するにあたって

サンプルの実行にあたっては venv の利用を強く推奨します。

venv の利用方法がわからない場合は以下を参照してください。venv を利用しない。もしくは既に使用している場合は Sora Python SDK のインストール まで飛ばしてください

### 仮想環境の作成とアクティベート

Sora Python SDK のルートディレクトリ(setup.py のあるディレクトリ)で以下のコマンドを実行し、 `.venv` という仮想環境を作成します。

```console
python3 -m venv .venv
```

次に仮想環境をアクティベートします。このコマンドは OS により異なります。

Mac, Ubuntu の場合

```console
.venv/bin/activate
```

Windows の場合

```console
./.venv/Scripts/activate
```

アクティベートはコンソールを閉じてしまった場合、サンプルを実行する前に再度実行する必要があります。

### Sora Python SDK のインストール

venv をアクティベートした状態で Sora Python SDK をインストールします。インストール方法は [Sora Python SDK の README.md](../README.md#ビルド) を参照してください。

### Sora Python SDK の設定

全てのサンプルは Sora の接続設定をコード中に記述する必要があります。サンプル中の下記の部分、特に `signaling_url`, `channel_id`, `metadata` を必要に応じてご自身の Sora の設定に置き換えてください。

```python
connection = sora.create_connection(
    signaling_url="signaling_url",
    role="recvonly",
    channel_id="channel_id",
    client_id="sendonly",
    metadata={'access_token': 'access_token'}
)
```
