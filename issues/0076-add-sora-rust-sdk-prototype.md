# sora-rust-sdk をベースにした PyO3 + Maturin プロトタイプを作成する

- Created: 2026-09-04
- Completed: 2026-09-04
- Branch: feature/add-sora-rust-sdk-prototype
- Polished: 2026-09-04

## 目的

将来の sora-rust-sdk ベースへの切り替えの可否を判断するため、PyO3 + Maturin による最小のプロトタイプでビルドと接続の成立を確認する。

現行の Sora C++ SDK + nanobind 構成は WebRTC / Boost / LLVM / sysroot を含むネイティブビルドであり、取得物と手順が多いため、移行可否を机上検討だけでは判断できない。実際に触れるものを作り、不確実性を潰すことが必要である。

## 現状

- ビルド入口は `CMakeLists.txt` の `nanobind_add_module` による `sora_sdk_ext` ターゲット定義で、バインディング本体は `src/sora_sdk_ext.cpp` のモジュール定義を起点に `SoraConnection` などを公開している。
- `pyproject.toml` の `dependency-groups` の `dev` に `nanobind` が入り、`setup.py` / `run.py` / `buildbase.py` が Sora C++ SDK / WebRTC / Boost の取得と CMake ビルドを担い、`DEPS` の `SORA_CPP_SDK_VERSION` が依存版を pin している。
- Python 公開面は `src/sora_sdk` の `__init__` が `sora_sdk_ext` の再 export と Sink 系ラッパーで構成されている。
- 本リポジトリ内では sora-rust-sdk への言及や API 文書等の一次資料は確認できておらず、API / スレッドモデル / コールバック方式は未調査である。Python からどこまで薄く呼べるか不明である。

## 設計方針

- 既存ビルドは一切変更しない。`CMakeLists.txt` / `setup.py` / `run.py` / `DEPS` / `src` 配下の現行拡張と、トップレベルの `pyproject.toml` の setuptools 経路は現状維持する。
- プロトタイプは `rust/` に隔離し、独自の `pyproject.toml` の maturin 経路と `Cargo.toml` を置く。ビルドは `uv run maturin build` で行い、現行の wheel ビルド経路に触れない。
- 着手時の第 1 段として sora-rust-sdk のリポジトリ URL と利用版を特定し、`rust/` 直下の `MEMO.md` に記録してから依存追加する。
- shiguredo-python スキルの Rust binding 規約に従う。PyO3 は 0.23 以上を使い、モジュールには `#[pymodule(gil_used = false)]` を付けることを既定とする。free-threading で安全に動作しない場合は理由をコメントで明記して付けない。
- 機能は最小限に絞る。import できること、版を参照できること (sora-rust-sdk 側が提供する版情報または PyO3 モジュールの `__version__` のいずれか、調査で判明した手段)、テスト用 Sora への接続と切断ができることまでとする。音声 / 映像フレームの受け渡し、既存 API の全面移植、wheel 公開、CI 組み込みは対象外とし、後続 issue に切り出す。
- 接続確認は既存 E2E と同じ前提で行う。`tests/conftest.py` の `Settings` が読む環境変数で指定される実 Sora を使い、モックやスタブは使わない。接続・切断の成否は終了コードで判定できる手順で確認する。
- 調査結果と全面移行の後続作業の洗い出しは `rust/` 直下の `MEMO.md` に残す。

## 完了条件

- `rust/` でプロトタイプがビルドでき、Python から import できること。
- 版を参照できること (手段は `MEMO.md` に記録されていること)。
- 既存 E2E と同じ環境変数で指定される実 Sora に対して接続と切断が確認できること。
- 現行の wheel ビルド手順が通ること (現行の nanobind 経路が壊れていないこと)。
- `rust/` 直下の `MEMO.md` に依存先 URL・版、API 対応メモ、`gil_used` 判定と理由、後続作業の洗い出しが残っていること。

## 解決方法

- `rust/` に maturin + PyO3 の隔離プロトタイプを作り、完了条件をすべて確認した。
  ビルドと import、版参照 (`__version__` + `Cargo.lock`)、実 Sora への接続と切断、
  現行 wheel ビルドの非破壊、後続洗い出しのメモ化を満たした。
- 追加検証として音声 / 映像 Sink 受信、encoded 変換、ログ制御の到達も実証し、
  pytest 12 件が通る状態にした。VAD は対象外として後続に切り出した。
- 全面置き換えは別 issue に切り出して続ける。
