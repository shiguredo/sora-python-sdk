# Python Sora SDK サンプル集

## セットアップ

[Rye](https://rye.astral.sh/) というパッケージマネージャーを利用しています。

インストール方法は <https://rye.astral.sh/guide/installation/> をご確認ください。

### 依存パッケージのビルド

```bash
rye sync
```

## サンプルコードの実行

`.env.template` をコピーして `.env` に必要な変数を設定してください。

```bash
cp .env.template .env
```

例えば `media_sendonly.py` を実行する場合は以下のコマンドを実行してください。

```bash
rye run python3 src/media_sendonly.py
```
