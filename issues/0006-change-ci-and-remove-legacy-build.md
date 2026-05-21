# CI 全面切替と buildbase.py / run.py / setup.py 削除

- Priority: Medium
- Created: 2026-05-21
- Model: Composer 2.5
- Branch: feature/change-ci-and-remove-legacy-build

## 目的

0001〜0005 で scikit-build-core 移行が完了した後、CI を `uv build --wheel` のみに統一し、レガシービルドファイル（`buildbase.py` / `run.py` / `setup.py` / `pypath.py` / `MANIFEST.in`）を削除する。

## 優先度根拠

Medium。機能移行自体は 0001〜0005 で完了する。0006 はクリーンアップと CI 統合であり、0005 完了後に実施可能。

## 現状

- `.github/workflows/build.yml` は全 job で `run.py build` → `uv build` の 2 段階
- `build_pyi` job は x86_64 ネイティブで pyi を生成し artifact 配布
- `build_ubuntu_arm` はネイティブ arm runner での検証用（compiler は clang-19）
- `DEPS` ファイルが残る（0001 で `deps.json` へ移行済み想定）
- `MANIFEST.in` が sdist 用に `buildbase.py` / `run.py` を含める

## 設計方針

- webcodecs-py の `wheel.yml` を参考に CI を簡素化する
- `_deps/` を actions/cache の対象にする（key: `deps.json` + `CMakeLists.txt` + `SORA_PLATFORM`）
- 全 platform job で `uv build --wheel` のみ呼ぶ
- `run.py build` / `setup.py` / `buildbase.py` / `pypath.py` / `MANIFEST.in` / `DEPS` を削除する
- `.github/actions/download-whl` の wheel パターンが scikit-build-core 出力と一致するか確認する

## 完了条件

- `build.yml` / `build-debug.yml` から `run.py build` が消える
- レガシーファイル 5 件がリポジトリから削除される
- 全 CI job が green になる
- publish / release / E2E が通る
- `CHANGES.md` に `[CHANGE]` が追記されている

## 解決方法

- `.github/workflows/build.yml` を更新する
- `.github/workflows/build-debug.yml` を更新する
- 不要ファイルを削除する
- wheel ファイル名の diff を CI で確認する
- release ジョブの artifact path を確認する
