# Sora Python SDK Examples

このディレクトリには Sora Python SDK のサンプルコードが含まれています。

## 注意事項

**重要**: これらのサンプルを実行するには、Sora Python SDK を自前でビルドする必要があります。PyPI からインストールしたパッケージでは動作しません。

## ビルド方法

リポジトリのルートディレクトリで以下のコマンドを実行してください：

```bash
# SDK のビルド（プラットフォームに応じて選択）
uv run python3 run.py <アーキテクチャ>

# 例: macOS ARM64 の場合
uv run python3 run.py macos_arm64

# 例: Ubuntu 22.04 x86_64 の場合
uv run python3 run.py ubuntu-22.04_x86_64
```

利用可能なアーキテクチャ：
- `windows_x86_64`
- `macos_arm64`
- `ubuntu-22.04_x86_64`
- `ubuntu-24.04_x86_64`
- `ubuntu-22.04_armv8`
- `ubuntu-24.04_armv8`
- `ubuntu-22.04_armv8_jetson`

オプション：
- `--debug`: デバッグビルドを行う
- `--relwithdebinfo`: RelWithDebInfo 設定でビルドする
- `--local-webrtc-build-dir`: ローカルの WebRTC ビルドディレクトリを指定
- `--local-sora-cpp-sdk-dir`: ローカルの Sora C++ SDK ディレクトリを指定

## 依存関係のインストール

examples の依存関係（opencv-python など）をインストールするには、リポジトリのルートディレクトリで以下のコマンドを実行してください：

```bash
# workspace member を含むすべての依存関係をインストール
uv sync --all-packages
```

## サンプルの実行

### sumomo.py

Sora C++ SDK の sumomo サンプルと互換性のある Python 実装です。SDL の代わりに OpenCV を使用して映像を表示します。

#### 基本的な使用例

##### 1. 映像受信のみ（recvonly）
```bash
cd examples

# 基本的な受信
uv run python sumomo.py --signaling-url wss://sora.example.com/signaling \
  --channel-id test-channel --role recvonly --use-opencv

# フルスクリーンで受信
uv run python sumomo.py --signaling-url wss://sora.example.com/signaling \
  --channel-id test-channel --role recvonly --use-opencv --fullscreen

# 大きめのウィンドウで受信
uv run python sumomo.py --signaling-url wss://sora.example.com/signaling \
  --channel-id test-channel --role recvonly --use-opencv \
  --window-width 1280 --window-height 720
```

##### 2. 映像送信のみ（sendonly）
```bash
# テストパターンを送信
uv run python sumomo.py --signaling-url wss://sora.example.com/signaling \
  --channel-id test-channel --role sendonly

# HD 解像度で送信
uv run python sumomo.py --signaling-url wss://sora.example.com/signaling \
  --channel-id test-channel --role sendonly --resolution HD

# ビットレート指定して送信
uv run python sumomo.py --signaling-url wss://sora.example.com/signaling \
  --channel-id test-channel --role sendonly --video-bit-rate 1000
```

##### 3. 送受信（sendrecv）
```bash
# 基本的な送受信
uv run python sumomo.py --signaling-url wss://sora.example.com/signaling \
  --channel-id test-channel --role sendrecv --use-opencv

# VP9 コーデックを使用した送受信
uv run python sumomo.py --signaling-url wss://sora.example.com/signaling \
  --channel-id test-channel --role sendrecv --use-opencv \
  --video-codec-type VP9

# 音声なしで送受信
uv run python sumomo.py --signaling-url wss://sora.example.com/signaling \
  --channel-id test-channel --role sendrecv --use-opencv \
  --audio false
```

##### 4. マルチストリーム配信
```bash
# マルチストリーム有効
uv run python sumomo.py --signaling-url wss://sora.example.com/signaling \
  --channel-id test-channel --role recvonly --use-opencv \
  --multistream true

# スポットライト機能（3人まで表示）
uv run python sumomo.py --signaling-url wss://sora.example.com/signaling \
  --channel-id test-channel --role recvonly --use-opencv \
  --spotlight true --spotlight-number 3
```

##### 5. サイマルキャスト配信
```bash
# サイマルキャスト送信
uv run python sumomo.py --signaling-url wss://sora.example.com/signaling \
  --channel-id test-channel --role sendonly --simulcast true

# サイマルキャスト受信（品質自動調整）
uv run python sumomo.py --signaling-url wss://sora.example.com/signaling \
  --channel-id test-channel --role recvonly --use-opencv \
  --simulcast true
```

##### 6. DataChannel 経由のシグナリング
```bash
# DataChannel シグナリング有効
uv run python sumomo.py --signaling-url wss://sora.example.com/signaling \
  --channel-id test-channel --role sendrecv --use-opencv \
  --data-channel-signaling true --ignore-disconnect-websocket true
```

##### 7. セキュア接続
```bash
# クライアント証明書を使用
uv run python sumomo.py --signaling-url wss://sora.example.com/signaling \
  --channel-id test-channel --role recvonly --use-opencv \
  --client-cert /path/to/client.crt \
  --client-key /path/to/client.key \
  --ca-cert /path/to/ca.crt

# 非セキュア接続（開発環境用）
uv run python sumomo.py --signaling-url wss://sora.example.com/signaling \
  --channel-id test-channel --role recvonly --use-opencv \
  --insecure
```

##### 8. プロキシ経由の接続
```bash
# HTTP プロキシ経由
uv run python sumomo.py --signaling-url wss://sora.example.com/signaling \
  --channel-id test-channel --role recvonly --use-opencv \
  --proxy-url http://proxy.example.com:8080 \
  --proxy-username user --proxy-password pass
```

##### 9. メタデータ付き接続
```bash
# メタデータを含めて接続
uv run python sumomo.py --signaling-url wss://sora.example.com/signaling \
  --channel-id test-channel --role sendonly \
  --metadata '{"name": "Test User", "room": "Room A"}'

# クライアント ID を指定
uv run python sumomo.py --signaling-url wss://sora.example.com/signaling \
  --channel-id test-channel --role recvonly --use-opencv \
  --client-id "user-12345"
```

##### 10. 高度なコーデック設定
```bash
# H.264 パラメータ指定
uv run python sumomo.py --signaling-url wss://sora.example.com/signaling \
  --channel-id test-channel --role sendonly \
  --video-codec-type H264 \
  --video-h264-params '{"profile_level_id": "42e01f"}'

# H.265 を使用
uv run python sumomo.py --signaling-url wss://sora.example.com/signaling \
  --channel-id test-channel --role sendonly \
  --video-codec-type H265
```

#### 主なオプション

##### 必須オプション
- `--signaling-url`: Sora のシグナリング URL
- `--channel-id`: チャンネル ID
- `--role`: ロール（sendonly/recvonly/sendrecv）

##### 表示関連
- `--use-opencv`: OpenCV を使用して映像を表示
- `--window-width`: ウィンドウ幅（デフォルト: 640）
- `--window-height`: ウィンドウ高さ（デフォルト: 480）
- `--fullscreen`: フルスクリーン表示

##### 映像・音声設定
- `--resolution`: 解像度（QVGA/VGA/HD/FHD/4K または WIDTHxHEIGHT）
- `--video`: 映像の送信有無（デフォルト: true）
- `--audio`: 音声の送信有無（デフォルト: true）
- `--video-codec-type`: 映像コーデック（VP8/VP9/AV1/H264/H265）
- `--audio-codec-type`: 音声コーデック（OPUS）
- `--video-bit-rate`: 映像ビットレート
- `--audio-bit-rate`: 音声ビットレート

##### 配信モード
- `--multistream`: マルチストリーム（true/false/none）
- `--spotlight`: スポットライト（true/false/none）
- `--spotlight-number`: スポットライト配信数
- `--simulcast`: サイマルキャスト（true/false/none）

##### 接続設定
- `--client-id`: クライアント ID
- `--metadata`: メタデータ（JSON 形式）
- `--data-channel-signaling`: DataChannel シグナリング使用
- `--ignore-disconnect-websocket`: WebSocket 切断を無視

##### セキュリティ
- `--insecure`: 非セキュア接続を許可
- `--client-cert`: クライアント証明書
- `--client-key`: クライアント秘密鍵
- `--ca-cert`: CA 証明書

##### プロキシ
- `--proxy-url`: プロキシ URL
- `--proxy-username`: プロキシユーザー名
- `--proxy-password`: プロキシパスワード

##### ログ
- `--log-level`: ログレベル（verbose/info/warning/error/none）

その他のオプションは `--help` で確認できます。

### トラブルシューティング

#### オーディオデバイスのエラーメッセージが大量に表示される場合

`failed to retrieve the playout delay` などのメッセージが大量に表示される場合は、ログレベルを調整してください：

```bash
# ログを完全に無効化
uv run python sumomo.py --log-level none ...

# エラーログのみ表示
uv run python sumomo.py --log-level error ...
```

## 依存関係

- Python >= 3.11
- opencv-python >= 4.8.0
- sora_sdk（ローカルビルド版）