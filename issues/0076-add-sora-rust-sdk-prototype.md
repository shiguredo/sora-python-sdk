# sora-rust-sdk をベースにした PyO3 + Maturin プロトタイプを作成する

- Created: 2026-09-04
- Completed: -
- Branch: feature/add-sora-rust-sdk-prototype
- Polished: {YYYY-MM-DD}

## 目的

将来の sora-rust-sdk ベースへの切り替えの可否を判断するため、PyO3 + Maturin による最小のプロトタイプでビルドと接続の成立を確認する。

現行の Sora C++ SDK + nanobind 構成は WebRTC / Boost / LLVM / sysroot を含むネイティブビルドが重く、移行可否を机上検討だけでは判断できない。実際に触れるものを作り、不確実性を潰すことが必要である。

## 現状

- ビルド入口は `CMakeLists.txt` の `nanobind_add_module` による `sora_sdk_ext` ターゲット定義で、バインディング本体は `src/sora_sdk_ext.cpp` のモジュール定義を起点に `SoraConnection` などを公開している。
- `pyproject.toml` の `dependency-groups` の `dev` に `nanobind` が入り、`setup.py` / `run.py` / `buildbase.py` が Sora C++ SDK / WebRTC / Boost の取得と CMake ビルドを担い、`DEPS` の `SORA_CPP_SDK_VERSION` が依存版を pin している。
- Python 公開面は `src/sora_sdk` の `__init__` が `sora_sdk_ext` の再 export と Sink 系ラッパーで構成されている。
- sora-rust-sdk 側の API / スレッドモデル / コールバック方式は未調査で、Python からどこまで薄く呼べるか不明である。

## 設計方針

- 既存ビルドは一切変更しない。`CMakeLists.txt` / `setup.py` / `run.py` / `DEPS` / `src` 配下の現行拡張は現状維持し、プロトタイプは別ディレクトリに隔離する。
- shiguredo-python スキルの Rust binding 規約に従い、maturin + PyO3 での構成とする。PyO3 は free-threading 対応版を選び、モジュールの `gil_used` の扱いはプロトタイプのスレッド確認結果で決める。
- 機能は最小限に絞る。import できること、バージョン取得相当の呼び出しができること、テスト用 Sora への接続と切断ができることまでとする。音声 / 映像フレームの受け渡し、既存 API の全面移植、wheel 公開、CI 組み込みは対象外とし、後続 issue に切り出す。
- 調査結果はプロトタイプ内のメモに残し、全面移行の後続 issue の判断材料にする。

## 完了条件

- プロトタイプがローカルでビルドでき、Python から import できること。
- テスト用 Sora に対して接続と切断が確認できること。
- 既存の wheel ビルド (現行の nanobind 経路) が壊れていないこと。
- 全面移行に向けた後続作業の洗い出しがプロトタイプ内のメモとして残っていること。
