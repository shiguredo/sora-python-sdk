# Makefile による開発ワークフロー追加

- Priority: Medium
- Created: 2026-05-21
- Model: Composer 2.5
- Branch: feature/add-makefile-develop-workflow

## 目的

webcodecs-py と同様に `Makefile` をリポジトリルートに追加し、 開発者が `make develop` / `make wheel` / `make format` / `make clean` で scikit-build-core 経路のビルド / editable install / フォーマット / クリーンアップを行えるようにする。 0007 で `run.py` を削除するため、 `run.py format` の代替を `make format` で提供する。

## 設計の前提

0007 で `run.py` 削除と入れ替わるため、 0007 着手の前に 0008 を完了させて `make format` 代替を用意するか、 0007 PR 内で `run.py format` を一時的に残して 0008 完了後に削除するか、 どちらでも可。 デフォルト順序は **0008 → 0007** とする（依存方向が明示的）。

## スコープ

含む:

- リポジトリルートに `Makefile` を新設する
- `make wheel`: `uv build --wheel` を呼ぶ
- `make develop`: editable install 経路で開発環境にプロジェクトをインストールする。 scikit-build-core の editable install は `uv pip install --no-build-isolation -e .` を使う必要がある（ build-isolation 有効だと毎回フル CMake configure が走る）
- `make format`: C++ ファイル（ `src/**/*.cpp` / `src/**/*.h` ）を `clang-format -i` で整形し、 Python ファイル（ `tests/` / `src/sora_sdk/` ）を `uv run ruff format` で整形する。 既存 `run.py:427-457` `_format` 関数の挙動を踏襲
- `make clean`: scikit-build-core 生成物を削除する。 対象は `_build` / `dist` / `*.egg-info`。 `_deps` は **削除しない** （ 再 fetch コストが大きく、 開発フローでは保持したい）
- `make distclean`: `make clean` 対象 + `_deps` を削除する
- `make test`: `uv build --wheel && uv pip install --force-reinstall dist/*.whl && uv run --no-sync pytest tests/test_version.py` を呼ぶ（ 0001 完了条件と同じ）
- `make` 単独実行（デフォルトターゲット）の挙動を `make wheel` にする
- `.PHONY` 宣言を全ターゲットに付ける

含まない（別 issue で扱う）:

- ローカル `pre-commit` / `prek` フックの追加（既存運用維持）
- 開発者向けドキュメント（ README.md 等）の更新（ CLAUDE.md「ドキュメントは別管理」方針）
- `make develop` で `SORA_SDK_TARGET` をプラットフォーム別に切り替えるロジック（開発者は手動で env 設定）

## 現状

- `run.py:427-457` `_format` 関数で `clang-format -i src/**/*.cpp src/**/*.h` + `uv run ruff format` を実行する
- `run.py` 経由で開発者は `uv run python run.py format` を呼ぶ運用
- webcodecs-py の `Makefile` （ `/Users/voluntas/shiguredo/webcodecs-py/Makefile` ）を参考にする
- `uv sync` は scikit-build-core 経由でプロジェクト本体を install する（ 0001 で確認済み）。 `make develop` の `uv pip install --no-build-isolation -e .` との重複ビルドが起きないかを 0008 実装時に検証する

## 設計方針

### Makefile の骨格

```makefile
.PHONY: all wheel develop format clean distclean test

all: wheel

wheel:
	uv build --wheel

develop:
	uv sync
	uv pip install --no-build-isolation -e .

format:
	find src/ -type f \( -name '*.cpp' -o -name '*.h' \) -print0 | xargs -0 clang-format -i
	uv run ruff format

test: wheel
	uv pip install --force-reinstall dist/*.whl
	uv run --no-sync pytest tests/test_version.py

clean:
	rm -rf _build dist src/sora_sdk.egg-info src/sora_sdk_rpi.egg-info

distclean: clean
	rm -rf _deps
```

`make format` の clang-format 呼び出しは `find -print0 | xargs -0` 形式でファイル名にスペースが含まれても安全に動く形にする。

`make develop` で `uv sync` を先に呼ぶ理由: dev グループ（ pyjwt 等）が install されていないと `tests/conftest.py:8` の `import jwt` が collect 時に失敗する。 続けて `uv pip install --no-build-isolation -e .` でプロジェクト本体を editable install する。

### uv sync と editable install の重複懸念

`uv sync` 単独で scikit-build-core 経由のフルビルドが走る（ 0001 で確認）。 続けて `uv pip install --no-build-isolation -e .` を呼ぶと **同じビルドが 2 回走る** 可能性がある。 これを避ける案:

- 案 A: `uv sync --no-install-project` で project 本体を skip し、 dev グループのみ install。 続けて `uv pip install --no-build-isolation -e .` で editable のみビルドする
- 案 B: `uv sync` のみで終わらせ、 editable は別途宣言する（ 0001 では editable install していない）

0001 で `uv build --wheel` ベースの動作確認は済んでいるが、 editable install の挙動は 0008 が初出。 案 A を採る:

```makefile
develop:
	uv sync --no-install-project
	uv pip install --no-build-isolation -e .
```

`make develop` 後に `uv run python -c "import sora_sdk; print(sora_sdk.__file__)"` が source tree 直下の `src/sora_sdk/__init__.py` を返すか確認する（ editable install の動作検証）。

## 完了条件

- リポジトリ直下に `Makefile` が存在する
- `make wheel` が成功し `dist/*.whl` を生成する
- `make develop` が成功し、 `uv run python -c "import sora_sdk; print(sora_sdk.__file__)"` が source tree 配下のパスを返す（ editable install 動作確認）
- `make format` で `src/**/*.cpp` / `src/**/*.h` / `tests/` / `src/sora_sdk/` が整形される。 差分が無いリポジトリで `make format` を実行しても再差分が出ない（ idempotent ）
- `make clean` 後に `_build` / `dist` が消え、 `_deps` は残る
- `make distclean` 後に `_deps` も消える
- `make test` で `pytest tests/test_version.py` が成功する
- `make` 単独で `make wheel` と同じ挙動になる

## 解決方法

### Makefile

「設計方針 → Makefile の骨格」を `/Users/voluntas/shiguredo/sora-python-sdk/Makefile` として新設する。

### CHANGES.md

`## develop` セクションに追加（種別は `[ADD]` ）:

```
- [ADD] 開発者向け Makefile を追加する
  - @voluntas
```

`### misc` サブセクションではなく `[ADD]` グループに置く（ Makefile はリリース成果物の一部として開発者に公開されるため）。

## ロールバック

0008 マージ後に Makefile に問題が発覚した場合:

1. `git revert -m 1 <merge-commit>` で revert PR を作成
2. revert 後、 `Makefile` が削除される
3. 0007 が先にマージ済みなら `run.py format` は既に削除済みのため、 開発者は再び手打ちで format することになる。 forward fix を選んで個別ターゲットの修正コミットを優先する
