# sysroot.py を ty 型チェック対象に追加する

- Priority: Medium
- Created: 2026-06-22
- Completed: {YYYY-MM-DD}
- Model: Opus 4.7
- Branch: feature/add-ty-include-sysroot
- Polished: {YYYY-MM-DD}

## 目的

0024 で新設した `sysroot.py` は `pyproject.toml` の `[tool.ty.src].include = ["src", "tests"]` に含まれていないため、 ty (静的型チェッカ) の対象外で運用されている。 0024 の `## 設計方針` で「`[tool.ty.src].include` への `sysroot.py` 追加は別 issue (lint カテゴリ) で扱う」 と明示されており、 本 issue で対応する。

## 優先度根拠

Medium:

- `sysroot.py` は 1071 行で型ヒントを徹底的に書いてあるが、 ty 対象外のため型不整合が CI で検出されない
- 0024 のレビューで `# type: ignore[...]` を `typing.cast` で置き換えたが、 ty 対象になっていれば「そもそも cast が要らない構造に直す」 圧がかかる
- 即座のサービス影響はないが、 後続 cross 系 issue で `sysroot.py` を改修するたびに型不整合の手戻りが発生するリスクがある

## 現状

- `pyproject.toml` (109-112 行):

  ```toml
  [tool.ty.src]
  # 型チェック対象のファイル・ディレクトリ
  # https://docs.astral.sh/ty/reference/configuration/#src-include
  include = ["src", "tests"]
  ```

- `sysroot.py` は repo root 直下に配置。 ruff は repo 全 `*.py` を対象にするが ty は `[tool.ty.src].include` 指定だけ
- 同じ理由で repo root 直下の `run.py` / `buildbase.py` / `pypath.py` / `canary.py` も ty 対象外運用 (0024 の `## 現状` で言及済み)
- `[dependency-groups].lint = ["ruff", "ty"]` で ty は dev 依存に含まれている

## 設計方針

- `[tool.ty.src].include` に `"sysroot.py"` を追加する
- 既存の `run.py` / `buildbase.py` / `pypath.py` / `canary.py` は **本 issue では追加しない** (0022 で `run.py` / `buildbase.py` 削除予定、 `pypath.py` / `canary.py` は別途検討)
- `uv run ty check` を実行し、 既存対象 (`src` / `tests`) と新規 `sysroot.py` をまとめて型エラーなく pass することを確認
- 型エラーが出た場合は別途修正 (本 issue scope に含める)

### 想定される型エラーと対応

`sysroot.py` の `parse_config` / `_parse_repo` / `_parse_post_install_symlink` は 0024 のレビュー指摘を受けて `typing.cast` で型を絞り込んでいる。 ty で実際にチェックすると、 以下が問題になる可能性がある:

- `cast("Mapping[str, object]", raw)` の文字列形式キャストが ty で warning を出すか
- `Repo(suites=tuple(cast("list[str]", suites)))` の二段キャストで `list[str]` への絞り込みが ty で受け入れられるか
- `_resolve_dependencies` の戻り値 `tuple[list[PackageMeta], dict[str, list[str]]]` が build_rootfs 側で正しく分解されるか
- `cf.ThreadPoolExecutor` の `futures: dict[cf.Future[str], int]` 型注釈の妥当性

これらは事前確認では分からないため、 着手時に ty を実行して具体的なエラー一覧を取り、 対応方針を決める。

## 完了条件

- `pyproject.toml` の `[tool.ty.src].include` に `"sysroot.py"` が追加されている
- `uv run ty check` が pass (新規 `sysroot.py` で型エラーが出ないこと)
- prek の `ty check` フックが `sysroot.py` を自動的にチェック対象に含めることを確認 (新規ファイル変更時の挙動)

## 解決方法

1. `pyproject.toml` の `[tool.ty.src].include` を `["src", "tests"]` から `["src", "tests", "sysroot.py"]` に変更
2. `uv run ty check` を実行
3. 型エラーが出た場合:
   - `cast` の書き方を見直す (文字列形式 vs 通常形式、 不要な cast の削除)
   - 関数シグネチャの型を絞る (`Mapping[str, object]` → `dict[str, object]` 等)
   - `_resolve_dependencies` 等の戻り値型注釈を厳密化
4. ty pass まで反復し、 最終的に lint hook も含めて pass する状態にする

## 関連

- 0024 (closed): sysroot.py 新設の親 issue。 `## 設計方針` で「`[tool.ty.src].include` への `sysroot.py` 追加 (lint カテゴリの別 issue)」 と明示
