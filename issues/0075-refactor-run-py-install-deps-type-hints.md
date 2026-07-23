# run.py の install_deps() の未型付けパラメータに型ヒントを付ける

- Priority: Low
- Created: 2026-07-23
- Completed: -
- Model: Opus 4.7
- Branch: feature/refactor-run-py-install-deps-type-hints
- Polished: {YYYY-MM-DD}

## 目的

`run.py` の `install_deps()` の引数 4 個（`source_dir` / `build_dir` / `install_dir` / `debug`）と戻り値に型ヒントが付いていない。 `shiguredo-python` 規約「型ヒントを必ず付けること（関数の引数・戻り値、モジュールトップレベルの変数、クラス属性）」と AGENTS.md「Don't live with broken windows」の観点で、この broken window を塞ぐ。

## 優先度根拠

Low とする。

- 実害は無い（現状の呼び出しコードは全て `_build()` からの内部呼び出しで、型が揃わなくても走る）
- ただし `shiguredo-python` の必須規約に反する pre-existing な違反として残っている
- 0074 の PR (#332) の実装で `install_deps()` の本体を書き換えたときに、隣接する broken window として複数のレビュアーが指摘したが、本 issue のスコープ外として意図的に残した経緯がある

## 現状

`run.py` L64-74（`0735755` 時点）の `install_deps()` シグネチャ：

```python
def install_deps(
    platform: Platform,
    source_dir,
    build_dir,
    install_dir,
    debug,
    local_webrtc_build_dir: str | None,
    local_webrtc_build_args: list[str],
    local_sora_cpp_sdk_dir: str | None,
    local_sora_cpp_sdk_args: list[str],
):
```

- `source_dir` / `build_dir` / `install_dir` / `debug` の 4 引数と戻り値に型注釈が無い
- 同じファイル内の `_build()` (L254-) は既に `debug: bool` / `relwithdebinfo: bool` などが型付けされており、`install_deps` だけ未対応の状態
- 呼び出し元 `_build()` L240-249 の `install_deps(platform, source_dir, build_dir, install_dir, debug, ...)` からは、 `source_dir` / `build_dir` / `install_dir` は `os.path.join(...)` 由来の `str` 、 `debug` は argparse 由来の `bool` が渡っている
- `install_deps()` は同ファイル外から呼ばれない（`run.py` は独立実行スクリプト）

## 設計方針

`install_deps()` の未型引数と戻り値に型ヒントを追加する。

- `source_dir: str`
- `build_dir: str`
- `install_dir: str`
- `debug: bool`
- 戻り値: `-> None`

隣接する `install_sysroot()` (L40) は既に型付け済みなので触らない。 `install_deps()` 以外に未型の関数（例: `_find_clang_binary` / `_get_platform` / `_build` / `_format` / `main`）が残っていないかは実装時に軽く確認し、同時に対応するかは別 issue との切り分けを検討する。基本は本 issue の対象を `install_deps()` に限定する。

## 完了条件

- `install_deps()` の全引数と戻り値に型ヒントが付く
- `uv run ty check` が `install_deps()` について型関連の diagnostic を出さない
- `uv run python run.py build <target>` の実行が回帰しない（既存 CI で担保）
- ローカルで `uv run ruff format --check run.py` / `uv run ruff check run.py` が pass する

## 解決方法

1. `run.py` の `install_deps()` シグネチャに型を追加する
2. `pyproject.toml` の `[tool.ty.src].include` は `run.py` を含んでいないため、`run.py` を追加するか、`install_deps()` の変更が既存の CI ワークフローで確認できることを検証する
3. `CHANGES.md` の `## develop` `### misc` サブセクションに `[UPDATE]` エントリを追加する（機能に直接影響しない refactor のため、`### misc` に配置する。 `shiguredo-changelog` 規約参照）

## 参考

- 0074 の PR (#332) のレビューコメント（規約整合性観点で `install_deps` の未型引数が指摘された）
- `run.py` は `melpon/buildbase` テンプレートで上書きされる `buildbase.py` とは別ファイルなので、テンプレート同期による戻り事故は起きない
- `shiguredo-python` の型ヒント必須規約
- AGENTS.md 「Don't live with broken windows」
