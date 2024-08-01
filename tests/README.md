# E2E テスト

## ローカル時の環境変数の設定

`.env` ファイルをローカル向けに作成してください。

```bash
TEST_SIGNALING_URL=wss://sora.example.com/signaling
TEST_CHANNEL_ID_PREFIX=sora
TEST_SECRET_KEY=secret
# これはオプションです
OPENH264_PATH=/usr/local/lib/libopenh264.so
```

## 実行方法

基本個別で実行することをお勧めします。

```bash
rye sync
rye run python run.py
rye run pytest -m tests/test_messaging.py -s
```

## 課題

### macOS

- macos-13 で Video Toolbox の H.264/H.265 のテストが動作しない

### Windows

- 日本語を print する文があると pytest が動作しない
- OpenH264 のテストが動作しない
