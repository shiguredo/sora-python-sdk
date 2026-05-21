# Makefile による開発ワークフロー追加

- Priority: Medium
- Created: 2026-05-21
- Model: Composer 2.5
- Branch: feature/add-makefile-develop-workflow

## 目的

webcodecs-py と同様に `Makefile` をリポジトリルートに追加し、開発者が `make develop` / `make wheel` / `make format` / `make clean` で scikit-build-core 経路のビルド・editable install・フォーマット・クリーンアップを行えるようにする。0006 で `run.py` を削除するため、`run.py format` の代替を `make format` で提供する必要がある。

## 優先度根拠

Medium。ビルド移行（0001 〜 0006）の必須条件ではないが、0006 で `run.py` を削除する以上、format / develop / clean に相当する開発者向け短縮コマンドの代替が必要。0007 が無いと 0006 で `run.py format` が消えた後、開発者は毎回 `uv run ruff format && clang-format -i src/**/*.cpp src/**/*.h` のような長い手打ちが必要になり開発体験が悪化する。

## スコープ

含む:

- リポジトリルートに `Makefile` を新設する
- `make wheel`: `uv build --wheel` を呼ぶ
- `make develop`: editable install 経路で開発環境にプロジェクトをインストールする。scikit-build-core の editable install は `uv pip install --no-build-isolation -e .` を使う必要がある（build-isolation 有効だと毎回フル CMake configure が走る）
- `make format`: C++ ファイル（`src/**/*.cpp` / `src/**/*.h`）を clang-format で整形し、Python ファイル（`tests/` / `src/sora_sdk/`）を `uv run ruff format` で整形する。`run.py:427-457` `_format` 関数の挙動を踏襲
- `make clean`: scikit-build-core 生成物を削除する。対象は `_build` / `dist` / `*.egg-info`。`_deps` は **削除しない**（再 fetch のコストが大きく、開発フローでは保持したい。明示的に削除したい場合は `make distclean`）
- `make distclean`: `make clean` 対象 + `_deps` を削除する
- `make test`: `uv pip install dist/*.whl --force-reinstall && uv run --no-sync pytest tests/test_version.py` を呼ぶ（0001 完了条件と同じ）
- `make` 単独実行（デフォルトターゲット）の挙動を `make wheel` にする
- `.PHONY` 宣言を全ターゲットに付ける

含まない（別 issue で扱う）:

- ローカル `pre-commit` / `prek` フックの追加（既存運用維持。`prek.toml` があれば触らない）
- 開発者向けドキュメント（README.md 等）の更新（CLAUDE.md「ドキュメントは別管理」方針）
- `make develop` で `SORA_SDK_TARGET` をプラットフォーム別に切り替えるロジック（開発者は手動で env 設定）

## 依存 issue への影響（事実記述）

- 0006 完了状態を前提とする。`run.py format` が削除済みで、`make format` がその代替になる
- 0001 完了状態を前提とする。`[tool.uv] package = false` が設定されていない（0001 で `[tool.uv]` には触らない方針）。`uv sync` 単独でプロジェクトが install される挙動と `make develop` の `uv pip install -e .` の挙動が重複しないかを検証必須
- webcodecs-py の `Makefile` (`/Users/voluntas/shiguredo/webcodecs-py/Makefile`) を参考にする

## 現状

- 既存開発ビルドフロー: `uv run python run.py build <target>` → `uv build`（2 段階。0001 〜 0006 で `uv build --wheel` に統一済み）
- 既存フォーマットフロー: `uv run python run.py format`（`run.py:427-457` で `clang-format -i` + `uv run ruff format` を呼ぶ）
- webcodecs-py の Makefile (`/Users/voluntas/shiguredo/webcodecs-py/Makefile`):

  ```
  .PHONY: wheel develop test format clean

  wheel:
  	uv build --wheel

  develop: wheel
  	uv pip install -e . --force-reinstall
  	@echo "Copying .pyi stub file..."
  	@cp _build/cp*/webcodecs_ext.pyi src/webcodecs/ 2>/dev/null || true

  test: develop
  	uv run pytest tests/ --timeout=10

  format:
  	clang-format -i src/bindings/*.cpp src/bindings/*.h
  	uv run ruff format tests/

  clean:
  	rm -rf _build dist *.egg-info _deps
  ```

  注意点: webcodecs-py の `develop` は `wheel` の wheel 生成後に **`uv pip install -e .`（editable install）** を実行している。これは scikit-build-core では「wheel ビルド + editable install」で 2 回 CMake configure が走る可能性がある。webcodecs-py での実運用上問題が無ければ採用、問題があれば `uv pip install --no-build-isolation -e .` 単独に変更

## 設計方針

### Makefile の構造

webcodecs-py を参考に sora-python-sdk 固有の差分を吸収:

```makefile
.PHONY: wheel develop test format clean distclean

wheel:
	uv build --wheel

develop: wheel
	uv pip install dist/*.whl --force-reinstall
	@echo "Copying .pyi stub file from _build/..."
	@cp _build/cp*/sora_sdk_ext.pyi src/sora_sdk/ 2>/dev/null || true
	@cp _build/cp*/py.typed src/sora_sdk/ 2>/dev/null || true

test: develop
	uv run --no-sync pytest tests/test_version.py

format:
	@command -v clang-format >/dev/null 2>&1 || { echo "clang-format not found"; exit 1; }
	clang-format -i src/*.cpp src/*.h
	uv run ruff format src/ tests/

clean:
	rm -rf _build dist *.egg-info src/sora_sdk/sora_sdk_ext.*.so src/sora_sdk/sora_sdk_ext.*.dylib src/sora_sdk/sora_sdk_ext.*.pyd src/sora_sdk/sora_sdk_ext.pyi src/sora_sdk/py.typed

distclean: clean
	rm -rf _deps
```

主な差分 / 設計判断:

- `develop` の install 方法: webcodecs-py は `uv pip install -e .` だが、sora-python-sdk では **`uv pip install dist/*.whl --force-reinstall` （非 editable）** を採用する。理由:
  - 0001 完了条件で「`uv pip install --force-reinstall dist/*.whl`（非 editable）で pytest が通る」が確定済み
  - editable install は scikit-build-core で `pip install --no-build-isolation -e .` 必須（`uv pip install -e .` だと毎回フルビルド）であり、開発フローで毎回 `make develop` を打つと configure 時間が長い
  - editable install の挙動は scikit-build-core 0.10+ で `[tool.scikit-build.editable] mode = "redirect"` 設定が必要、`mode = "inplace"` だと source tree を更新する。安定運用が確認できるまで非 editable を採用
- `develop` の pyi コピー: 0001 で `install(FILES ${CMAKE_CURRENT_BINARY_DIR}/sora_sdk_ext.pyi DESTINATION sora_sdk)` 経由 wheel 内に pyi が同梱される。`uv pip install dist/*.whl` で site-packages に pyi が入るが、`src/sora_sdk/` にもコピーすることで IDE 補完が利く（src/ 配下を IDE が PYTHONPATH に入れる慣行）
- `format` の対象パス: `src/*.cpp` / `src/*.h`（webcodecs-py は `src/bindings/*.cpp` だが sora は `src/` 直下に集約）。Python は `src/` と `tests/`
- `clean` で消す対象: `_build` / `dist` / `*.egg-info` に加え、`src/sora_sdk/sora_sdk_ext.*.so` 等のビルド生成物（0001 で `.gitignore` に追加済みだが、開発中に残っているケースで cleanup する）。`_deps` は **`distclean` でのみ削除**（再 fetch が大きいため通常 clean では保持）
- `test` ターゲット追加: 0001 完了条件の pytest 検証を 1 コマンドで実行できるようにする

### scikit-build-core editable install の調査

- `make develop` で wheel 経由 install を採用するが、将来 editable install に切り替える場合の調査メモを `make develop` ターゲットのコメントに残す:

  ```makefile
  # NOTE: scikit-build-core editable install (`uv pip install --no-build-isolation -e .`) は
  # configure を毎回スキップする mode = "redirect" で動かす必要がある。
  # 安定運用が確認できるまで非 editable (wheel 経由) を採用。
  ```

### Makefile の `command -v` チェック

- `format` は `clang-format` 不在時にサイレント失敗しないよう `command -v clang-format` でガード
- `ruff` は `uv run ruff format` で uv 環境内 ruff を呼ぶため、`uv sync` 済みなら必ず動く（追加チェック不要）

### CHANGES.md エントリ

- 0007 で `Makefile` 追加は機能追加 (`[ADD]`) として 0001 / 0006 の `[CHANGE]` とは別エントリに記載:

  ```
  - [ADD] 開発者向けの Makefile を追加する
    - `make develop` / `make wheel` / `make format` / `make clean` / `make distclean` / `make test`
    - @voluntas
  ```

  順序規約（CHANGE → ADD → UPDATE → FIX）に従い、0001 / 0006 の `[CHANGE]` の **後** に挿入する

## 完了条件

- リポジトリルートに `Makefile` が新設される
- `make wheel` で `uv build --wheel` が実行され `dist/sora_sdk-*.whl` が生成される
- `make develop` で wheel 生成 → install → pyi コピーが順に走る
- `make format` で C++ ファイル（`src/*.cpp` / `src/*.h`）と Python ファイル（`src/` / `tests/`）が整形される
- `make clean` で `_build` / `dist` / `*.egg-info` / `src/sora_sdk/sora_sdk_ext.*` が消える
- `make distclean` で `clean` 対象 + `_deps` が消える
- `make test` で `pytest tests/test_version.py` が通る
- `make` 単独実行で `make wheel` 相当になる
- `CHANGES.md` の `## develop` セクションに `[ADD] 開発者向けの Makefile を追加する` エントリが順序規約に従って追加される

## 解決方法

- リポジトリルートに `Makefile` を新設（設計方針の内容）
- 0006 完了時点で `run.py` が削除済みなので、`Makefile` の `format` ターゲットが `run.py format` 完全代替になる
- `CHANGES.md` の `## develop` セクションに `[ADD] 開発者向けの Makefile を追加する` を追加（0001 / 0006 の `[CHANGE]` エントリの後、`[UPDATE]` 群の前）
- 1 ステップ目に実装する検証: `make develop` 実行 → `python -c "import sora_sdk; print(sora_sdk.__version__)"` で import 成功 + バージョン取得が動くことを確認
