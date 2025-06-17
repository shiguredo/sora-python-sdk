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

```bash
cd examples
uv run python sumomo.py --signaling-url wss://sora.example.com/signaling \
  --channel-id test-channel --role recvonly --use-opencv
```

主なオプション：
- `--signaling-url`: Sora のシグナリング URL（必須）
- `--channel-id`: チャンネル ID（必須）
- `--role`: ロール（sendonly/recvonly/sendrecv）（必須）
- `--use-opencv`: OpenCV を使用して映像を表示
- `--window-width`: ウィンドウ幅（デフォルト: 640）
- `--window-height`: ウィンドウ高さ（デフォルト: 480）
- `--fullscreen`: フルスクリーン表示

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