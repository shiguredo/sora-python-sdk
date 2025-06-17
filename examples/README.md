# Sora Python SDK Examples

このディレクトリには Sora Python SDK のサンプルコードが含まれています。

## 注意事項

**重要**: これらのサンプルを実行するには、Sora Python SDK を自前でビルドする必要があります。PyPI からインストールしたパッケージでは動作しません。

## ビルド方法

リポジトリのルートディレクトリで以下のコマンドを実行してください：

```bash
# SDK のビルド
python -m build
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

## 依存関係

- Python >= 3.11
- opencv-python >= 4.8.0
- sora_sdk（ローカルビルド版）