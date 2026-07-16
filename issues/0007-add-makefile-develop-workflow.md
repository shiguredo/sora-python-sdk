# Makefile による開発ワークフロー追加

- Priority: Medium
- Created: 2026-05-21
- Updated: 2026-07-17
- Model: Composer 2.5
- Branch: feature/add-makefile-develop-workflow

## 目的

webcodecs-py と同様に `Makefile` をリポジトリルートに追加し、 開発者が `make develop` / `make wheel` / `make format` / `make clean` で scikit-build-core 経路のビルド / editable install / フォーマット / クリーンアップを行えるようにする。 `run.py` は 0001 で削除され、 フォーマットは prek の ruff-format / clang-format フックが担うため、 `make format` は prek フックの手動実行入口として提供する。

## 設計の前提

前提は 0001 の完了（ scikit-build-core 経路の成立と `run.py` の削除）。 フォーマット手段は 0001 完了後も prek フックで確保されているため、 0006 との順序依存は無く、 0001 完了後いつでも着手できる。

## スコープ

含む:

- リポジトリルートに `Makefile` を新設する
- `make wheel`: `uv build --wheel` を呼ぶ
- `make develop`: editable install 経路で開発環境にプロジェクトをインストールする。 scikit-build-core の editable install は `uv pip install --no-build-isolation -e .` を使う必要がある（ build-isolation 有効だと毎回フル CMake configure が走る）
- `make format`: prek の整形系フック（ ruff-format / clang-format ）を全ファイルに対して手動実行する入口とする（ `prek run ruff-format clang-format --all-files` ）。 整形ルールの単一情報源は `prek.toml` とし、 Makefile 側に整形コマンドを重複実装しない
- `make clean`: ビルド生成物を削除する。 対象は `_build` / `dist` / `src/*.egg-info` （ egg-info は setuptools 時代の残骸掃除。 scikit-build-core は egg-info を生成しない）。 `_deps` は **削除しない** （ 再 fetch コストが大きく、 開発フローでは保持したい）
- `make distclean`: `make clean` 対象 + `_deps` を削除する
- `make test`: `uv build --wheel && uv pip install --force-reinstall dist/*.whl && uv run --no-sync pytest tests/test_version.py` を呼ぶ（ 0001 の動作確認手順と同じ。 前段の `uv sync --no-install-project` は `make develop` が担う前提）
- `make` 単独実行（デフォルトターゲット）の挙動を `make wheel` にする
- `.PHONY` 宣言を全ターゲットに付ける

含まない（別 issue で扱う）:

- `prek.toml` 自体の変更（既存フック構成を維持する）
- 開発者向けドキュメント（ README.md 等）の更新（ CLAUDE.md「ドキュメントは別管理」方針）
- `make develop` で `SORA_SDK_TARGET` をプラットフォーム別に切り替えるロジック（開発者は手動で env 設定）

## 現状

- フォーマットは `prek.toml` の ruff-format / clang-format フック（ commit hook + `prek run` の手動実行）で行う運用が確立している
- 旧 `run.py:426-456` の `_format` 関数（ `clang-format -i` + `uv run ruff format` 。 パス指定なしでプロジェクト全体を整形）は 0001 で run.py ごと削除される。 削除後は git 履歴 (`git show <削除前コミット>:run.py`) で参照する
- webcodecs-py の `Makefile` （ `/Users/voluntas/shiguredo/webcodecs-py/Makefile` ）を参考にする
- 0001 完了後は素の `uv sync` が scikit-build-core 経由でプロジェクト本体をビルド・install する想定（ 0001 の動作確認手順は `uv sync --no-install-project` を必須としている）。 `make develop` の `uv pip install --no-build-isolation -e .` との重複ビルドが起きないかを 0007 実装時に実機で検証する

## 設計方針

### Makefile の骨格

```makefile
.PHONY: all wheel develop format clean distclean test

all: wheel

wheel:
	uv build --wheel

develop:
	uv sync --no-install-project
	uv pip install --no-build-isolation -e .

format:
	prek run ruff-format clang-format --all-files

test: wheel
	uv pip install --force-reinstall dist/*.whl
	uv run --no-sync pytest tests/test_version.py

clean:
	rm -rf _build dist src/*.egg-info

distclean: clean
	rm -rf _deps
```

`make format` は prek フックの手動実行入口に徹する。 整形対象・除外・ツールバージョンは `prek.toml` が単一情報源のため、 Makefile 側で `find` / `clang-format` / `ruff format` を直接呼ばない。 prek 本体のインストール前提（ pyproject の依存には prek が無い。 system ツール運用か `uv tool` 経由か）は実装時に確定する。

### uv sync と editable install の重複懸念

素の `uv sync` は scikit-build-core 経由のフルビルドが走る想定（ 0001 実装後に実機確認）。 続けて `uv pip install --no-build-isolation -e .` を呼ぶと **同じビルドが 2 回走る** 可能性がある。 これを避けるため `make develop` は `uv sync --no-install-project` で project 本体を skip し、 dev グループ（ pyjwt 等。 `tests/conftest.py:8` の `import jwt` が collect 時に必要）のみ install した上で editable install を行う（上記骨格の形）。

`--no-build-isolation` では build requirements が環境に入っている必要がある。 0001 で nanobind は `[dependency-groups] dev` から `[build-system] requires` に移るため、 `uv sync --no-install-project` だけでは scikit-build-core / nanobind / cmake / ninja が環境に入らない可能性がある。 webcodecs-py の Makefile の対応方法を確認し、 必要なら editable install 前に build requirements を明示 install する step を挟む（ 0007 実装時に検証・確定する）。

`make develop` 後に `uv run python -c "import sora_sdk; print(sora_sdk.__file__)"` が source tree 直下の `src/sora_sdk/__init__.py` を返すか確認する（ editable install の動作検証）。

## 完了条件

- リポジトリ直下に `Makefile` が存在する
- `make wheel` が成功し `dist/*.whl` を生成する
- `make develop` が成功し、 `uv run python -c "import sora_sdk; print(sora_sdk.__file__)"` が source tree 配下のパスを返す（ editable install 動作確認）
- `make format` で prek の ruff-format / clang-format フックが全ファイルに適用される。 差分が無いリポジトリで `make format` を実行しても再差分が出ない（ idempotent ）
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

0007 マージ後に Makefile に問題が発覚した場合:

1. `git revert -m 1 <merge-commit>` で revert PR を作成
2. revert 後、 `Makefile` が削除される
3. revert 後も prek の ruff-format / clang-format フックが機能するため、 フォーマット手段は失われない。 forward fix を選んで個別ターゲットの修正コミットを優先する
