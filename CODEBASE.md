# sora-python-sdk

## ビルド

ビルドはすべてリポジトリのルートディレクトリから実行する。

```bash
uv run python run.py build <target>
```

### 対応ターゲット

- `windows_x86_64`
- `macos_arm64`
- `ubuntu-24.04_x86_64`
- `ubuntu-26.04_x86_64`
- `ubuntu-24.04_armv8`
- `ubuntu-26.04_armv8`
- `ubuntu-22.04_armv8_jetson`
- `raspberry-pi-os_armv8`

### .pyi / py.typed の生成

`run.py build` はクロスコンパイルでない環境では `SORA_GEN_PYI=ON` を付けて拡張をビルドし、nanobind の stubgen で `src/sora_sdk/sora_sdk_ext.pyi` と `src/sora_sdk/py.typed` を生成する。どちらもビルド成果物であり `.gitignore` で除外されている。wheel にはビルド時に生成したものを同梱するため、リポジトリにはコミットしない。

## コミット前の確認

prek の `ty` フックは `src/sora_sdk/sora_sdk_ext.pyi` を必要とする。未ビルドの状態では `sora_sdk_ext` が解決できず `ty` が失敗するため、コミット前に `uv run python run.py build <target>` を実行しておくこと。CI も `build_pyi` の後に `prek` を実行する順序になっている。
