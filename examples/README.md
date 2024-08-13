# Python Sora SDK サンプル集

## セットアップ

[Rye](https://rye.astral.sh/) というパッケージマネージャーを利用しています。

インストール方法は <https://rye.astral.sh/guide/installation/> をご確認ください。

### 依存パッケージのビルド

```bash
rye sync
```

## サンプルの種類

- media_sendonly
- media_recvonly
- messaging_sendrecv
- messaging_sendonly
- messaging_recvonly
- hideface_sender

## サンプルコードの実行

`.env.template` をコピーして `.env` に必要な変数を設定してください。

```bash
cp .env.template .env
```

例えば `media_recvonly` サンプルを実行する場合は以下のコマンドを実行してください。

```bash
rye run media_recvonly
```
