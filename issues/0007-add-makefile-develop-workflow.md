# Makefile による開発ワークフロー追加

- Priority: Medium
- Created: 2026-05-21
- Model: Composer 2.5
- Branch: feature/add-makefile-develop-workflow

## 目的

webcodecs-py と同様に `Makefile` を追加し、開発者が `make develop` / `make wheel` / `make format` / `make clean` でビルド・フォーマットできるようにする。0006 で削除する `run.py format` の代替となる。

## 優先度根拠

Medium。ビルド移行の必須条件ではないが、0006 で `run.py` を削除するには format 手段の代替が必要。

## 現状

- 開発ビルドは `uv run python run.py build <target>` → `uv build` が必要
- フォーマットは `uv run python run.py format`（clang-format + ruff format）
- webcodecs-py は `Makefile` で `develop` / `wheel` / `format` / `clean` を提供している

## 設計方針

- webcodecs-py の `Makefile` を参考にする
- `develop`: `uv build --wheel` + `uv pip install -e .` + pyi を `_build/` から `src/sora_sdk/` に cp
- `wheel`: `uv build --wheel`
- `format`: clang-format（`src/**/*.cpp` / `src/**/*.h`）+ `uv run ruff format`
- `clean`: `_build` / `dist` / `_deps` / `*.egg-info` を削除
- デフォルト target は ubuntu-24.04_x86_64 向け env を想定する

## 完了条件

- `make develop` でローカル開発用インストールができる
- `make format` で C++ / Python のフォーマットが実行できる
- `make clean` でビルド成果物が削除できる
- README 以外のドキュメント更新は AGENTS.md に従い別管理とする

## 解決方法

- ルートに `Makefile` を追加する
- 0006 完了後に `run.py` を削除する
- `CHANGES.md` に `[ADD]` を追記する
