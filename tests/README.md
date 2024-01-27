# e2e test

## ローカル時の環境変数の設定

`.env` ファイルをローカル向けに作成してください。

```bash
TEST_SIGNALING_URL=wss://sora.example.com/signaling
TEST_CHANNEL_ID_PREFIX=sora_
TEST_SECRET_KEY=secret
```

## 実行方法

**基本個別で実行することをオススメ**

```bash
$ rye sync
$ rye run python run.py
$ rye run pytest -m tests/test_messaging.py -s
```
