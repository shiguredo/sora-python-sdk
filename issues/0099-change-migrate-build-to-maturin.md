# sora-rust-sdk + PyO3 + maturin へビルド基盤を置き換える

- Created: 2026-09-16
- Completed: -
- Branch: feature/change-migrate-build-to-maturin
- Polished: {YYYY-MM-DD}

## 目的

Sora C++ SDK の prebuilt 取得、CMake、sysroot 構築を自前で維持する現行のビルド基盤を、maturin + PyO3 へ置き換える。sora-rust-sdk が依存する `shiguredo_webrtc` は prebuilt libwebrtc を取得するため、CMake と sysroot 構築が不要になり維持対象が大きく減る。

現行の `pyproject.toml` はビルドバックエンドに setuptools を指定しており、`shiguredo-python` 規約が定める C++ binding の scikit-build-core + nanobind 経路とも異なる。移行により maturin + PyO3 規約に揃う。

## 現状

- ビルドは `CMakeLists.txt` の `nanobind_add_module(sora_sdk_ext ...)` を入口とし、`setup.py` / `run.py` / `buildbase.py` / `pypath.py` / `sysroot_builder.py` が Sora C++ SDK / WebRTC / Boost / rootfs を取得・生成する。この 6 ファイルで 4,358 行である。
- `DEPS` が `SORA_CPP_SDK_VERSION` `2026.3.0-canary.6`、`WEBRTC_BUILD_VERSION` `m154.8037.1.1`、`BOOST_VERSION` `1.92.0` を pin している。
- C++ 実装は `src/` 直下の 5,897 行で、バインディングの起点は `src/sora_sdk_ext.cpp` の `NB_MODULE(sora_sdk_ext, m)` である。
- Python 公開 API の正本はビルド時に生成される `src/sora_sdk/sora_sdk_ext.pyi` である。`CODEBASE.md` のとおり、pyi と `py.typed` は成果物でありコミットしていない。
- `pyproject.toml` の dev 依存に `nanobind==3.0.1` がある。`prek.toml` には C / C++ 向けの clang-format フックがある。
- 移行後の構成は試作ブランチで実証済みである。`module-name = "sora_sdk"` / `python-source = "python"` の maturin 構成、`Cargo.toml` の `sora_sdk = "2026.2.0-canary.6"` + `pyo3 = "0.29"` + `shiguredo_webrtc = "0.154"`、`src/lib.rs` の `#[pymodule(gil_used = false)]` である。

## 設計方針

- `docs/migration-to-sora-rust-sdk.md` の決定事項に従う。
- ビルドバックエンドは maturin、バインディングは PyO3 とし、モジュール名は `sora_sdk` を維持する。import 名を変えないため、利用者の import 文は変わらない。
- 後方互換は考慮しない (`shiguredo-python` 規約)。公開 API の形は後続 issue で確定する。
- 本 issue では C++ 実装と C++ 用ビルド基盤を削除し、Rust のクレートが `uv sync` 後にビルドできる最小構成まで作る。公開 API の実装は後続 issue で行う。
- 削除対象は `src/` の C++ 原始、`CMakeLists.txt` / `setup.py` / `run.py` / `buildbase.py` / `pypath.py` / `sysroot_builder.py` / `DEPS` / `MANIFEST.in` / `.clang-format` / `dev.py` / `scripts/pytest_with_llvm.py` / `scripts/pytest_memory_leak_checker.py` / `multistrap/` / `sysroot/` / `src/sora_sdk/sora_sdk_ext.pyi` である。
- `pyproject.toml` から `nanobind` と setuptools のビルドバックエンド指定を外し、maturin へ切り替える。`prek.toml` の clang-format フックを削除する。
- `README.md` と `skills/sora-python-sdk/SKILL.md` の Sora C++ SDK ベースである旨の記述は、ドキュメント追従の issue で扱う。本 issue では触らない。
- 既存テストは後続のテスト移行 issue で扱う。本 issue では `tests/` のテスト本体を移行しない。ただし C++ 実装を削除すると `tests/` が import できなくなるため、本 issue の完了時点で `tests/` が壊れていてよい。テスト移行の issue が着手されるまで、CI のテスト段階は無効化するか、ビルドと import だけを確認する最小の確認に置き換える。無効化した範囲と理由を本 issue に記録する。

## 完了条件

- `pyproject.toml` のビルドバックエンドが maturin になり、`uv build` で wheel が作れること。
- `uv run maturin develop` または `uv sync` の後に `import sora_sdk` できること。
- C++ 実装 (`src/` の C++ 原始) と C++ 用ビルド基盤 (`CMakeLists.txt` / `setup.py` / `run.py` / `buildbase.py` / `pypath.py` / `sysroot_builder.py` / `DEPS`) が削除されていること。
- `src/lib.rs` で `#[pymodule(gil_used = false)]` を宣言していること。
- `pyproject.toml` に `nanobind` が残っておらず、`prek.toml` に C / C++ 向けのフックが残っていないこと。
- `prek run --all-files` が通ること。
- `CHANGES.md` の `## develop` に `[CHANGE]` エントリを追記していること。ビルドバックエンドとバインディングの変更は利用者に影響する後方互換のない変更であるため `[CHANGE]` とする。

## 依存

- 先行する issue は無い。本 issue が移行の起点である。
- 後続の受信系・送信系・コールバック中継・接続設定・リサンプラと VAD・libcamera・テスト移行の各 issue は本 issue の完了後に着手する。

## 解決方法
