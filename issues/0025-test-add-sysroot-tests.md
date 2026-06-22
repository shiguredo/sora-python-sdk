# sysroot.py の単体テスト tests/test_sysroot.py を新設する

- Priority: Medium
- Created: 2026-06-22
- Completed: {YYYY-MM-DD}
- Model: Opus 4.7
- Branch: feature/add-sysroot-tests
- Polished: {YYYY-MM-DD}

## 目的

0024 で新設した `sysroot.py` は、 APT Packages インデックスのパース・依存解決・`.deb` 展開・symlink 後処理など、 ロジック密度の高い関数を多数持つにもかかわらず単体テストが無い状態で merge された (0024 の `## 設計方針` で「`tests/test_sysroot.py` 新設は別 issue (test カテゴリ) で扱う」 と明示)。 後続の cross 系 issue が `cmake/scripts/fetch_deps.cmake:_sora_fetch_rootfs` を実呼び出しした際に初めて bug が顕在化する設計上の弱点があるため、 実呼び出しに先行して単体テストで品質を担保する。

## 優先度根拠

Medium:

- 0024 merge 時点では `sysroot.py` は CMake から呼び出されないため、 即座のサービス影響はない
- ただし後続 cross 系 issue (ubuntu armv8 / jetson / raspberry-pi-os 復活) が `_sora_fetch_rootfs` を実呼び出しに切り替えた瞬間、 単体テスト未整備のままだと「依存解決のバグ」「Packages インデックスのパース誤り」「symlink 後処理の取り違え」 が CI で発覚するリスクが残る
- 後続 cross 系 issue が並列で進む前に整備しておかないと、 同じ問題を複数 issue で個別に踏むことになる

## 現状

- `sysroot.py` (1071 行) に対応するテストファイル `tests/test_sysroot.py` は存在しない
- `tests/` 配下には `test_amd_amf.py` / `test_audio_sink_read_gil.py` 等の E2E 寄り pytest が並ぶが、 sysroot に関連するものは無い
- `pyproject.toml` の `[tool.ty.src].include = ["src", "tests"]` により `sysroot.py` は ty 対象外、 `tests/test_sysroot.py` は新規追加すれば自動的に ty 対象になる
- `pyproject.toml` の `[tool.pytest.ini_options].testpaths = ["tests"]` で `tests/` が pytest 探索対象
- 既存の依存に hypothesis は **未追加** (`pyproject.toml` `[dependency-groups].test` を確認すると `httpx, numpy, pyjwt, pytest, pytest-repeat, pytest-xdist`)

## 設計方針

### 対象関数とテスト戦略

公開 / 内部関数を以下の 3 群に分けてテストする。

**(1) 公開 API (`__all__` 列挙)**:

- `parse_config(path: Path) -> SysrootConfig`: 正常系 4 ファイル + 異常系 (link 絶対 / link `..` / file `/` / file `..` / url スキーマ違反 / name pattern 違反 / packages 空 / repos 空 / link 中間 `..` / 不正 JSON / 必須フィールド欠落 / `allow_insecure` 非 bool / 未知 top-level フィールドの warning) を pytest 単体テストで網羅
- `build_rootfs(...)`: HTTP / `dpkg-deb` 依存を伴うため、 後述の「実 HTTP サーバ + 最小 `.deb` フィクスチャ」 経路で 1 〜 2 ケースだけ統合的に確認する (CI ubuntu-24.04 host 専用、 macOS では `pytest.mark.skipif(platform != "Linux")`)

**(2) 内部関数 (Packages 解析)**:

- `_parse_control_block(lines)`: 単一行 / 継続行が半角スペースで連結されること / 空行・コロン無し行が無視されること
- `_parse_relations(raw)`: `a, b | c (>= 1)` / 改行混入 / arch qualifier `:any` / 空文字列 / `,` のみ
- `_parse_provides(raw)`: 単純名 / バージョン制約付き / 空文字列
- `_strip_version_constraint(token)`: バージョン制約 + arch qualifier の組み合わせ
- `_resolve_dependencies(config, index)`: roots → depends → pre-depends の遷移、 OR 依存の左優先採用、 Provides 解決、 essential skip、 循環依存ガード、 未提供時の `SysrootError` abort、 戻り値の `prerequisites` map が `_topological_order` で消費可能な形であること
- `_topological_order(selected, prerequisites)`: 依存マップから topo order が決定的に出ること、 同レベル内 tie-breaker (selected 順) が保たれること
- `_fetch_all_packages_indexes(config, jobs)`: 実 HTTP サーバ経路 (後述) で `.xz` → `.gz` フォールバック / 並列取得 / fail-fast を確認

**(3) 内部関数 (symlink / cache)**:

- `_ensure_usrmerge_symlinks(dest)`: `<dest>/{lib,bin,sbin}` の symlink 生成、 既存ディレクトリ存在時の warning skip、 冪等性
- `_fix_absolute_symlinks(root)`: 絶対 symlink `/usr/lib/real.so` → 相対 symlink `real.so` への置換、 broken symlink がそのまま残ること (機能等価移植の確認)、 root 末尾 `/` を含むパス入力
- `_apply_post_install_symlinks(root, symlinks)`: 冪等性、 既存 dead symlink がある場合の skip、 target 不在時の skip、 jetson 用 2 entry の動作
- `_compute_stamp(config_path, script_path)` / `_read_stamp` / `_write_stamp`: 連続呼び出しで同じ stamp が出ること、 config 変更で stamp が変わること、 script_path 変更で stamp が変わること
- `_deb_cache_name(meta)` / `_sha256_of_file(path)`: ファイル名規約と SHA256 計算

### HTTP / dpkg 依存テストの実装方針

- **CLAUDE.md「モック・スタブ禁止」 規約に従い、 HTTP 取得を伴うテストは python 標準 `http.server` で実 HTTP サーバを立てる**
- `tests/test_sysroot/` ディレクトリを切り、 サブテストファイルに分割 (`test_parse_config.py` / `test_packages_parse.py` / `test_resolve_dependencies.py` / `test_symlinks.py` / `test_http_fetch.py` / `test_build_rootfs.py`)
- フィクスチャ: 最小 Packages インデックス (`.xz` / `.gz` / 両 404) を `tests/test_sysroot/fixtures/` に配置し、 `http.server.ThreadingHTTPServer` でテスト中だけ host
- `dpkg-deb` 依存テスト (`build_rootfs` の整合性確認) は `pytest.mark.skipif(shutil.which("dpkg-deb") is None or sys.platform != "linux")` で skip
- 最小 `.deb` フィクスチャは `tests/test_sysroot/fixtures/debs/` に置く (3 〜 5 個の手作り `.deb` を ar + tar で作る Makefile を同梱、 もしくは fixtures Python script で生成)

### PBT (hypothesis) の適用範囲

`_parse_relations` / `_parse_provides` / `_strip_version_constraint` の境界網羅は hypothesis でカバーすると効率が良い。 ただし本 issue では PBT 追加は scope に含めず、 単体テスト整備のみ。 PBT は別 issue (`pbt-add-sysroot-parsers`) で追加する想定。

### 依存追加

- `pyproject.toml` の `[dependency-groups].test` に `hypothesis` は本 issue では追加しない (PBT は別 issue)
- 既存依存だけでテスト整備可能 (`pytest` / `pytest-xdist` / `pytest-repeat`)

## 完了条件

- `tests/test_sysroot/` 配下に上記分割でテストファイルが揃う
- `uv run pytest tests/test_sysroot/` が macOS / Linux 両方で pass (`dpkg-deb` 依存テストは Linux のみ実行され、 macOS では skip 扱い)
- `uv run pytest tests/test_sysroot/ --cov=sysroot` 等でカバレッジを取れる状態 (本 issue で `pyproject.toml` への coverage 設定追加は scope 外、 ローカル確認のみ)
- 上記 (1) (2) (3) の各関数について、 最低限「正常系 1 + 異常系 1」 のテストが存在する
- `tests/test_sysroot/` 配下の fixtures は再現可能な手順 (Makefile or script) でビルドできる
- `parse_config` 異常系 9 ケース (issue 0024 でスモーク確認した内容) を pytest 化して全て pass

## 解決方法

1. `tests/test_sysroot/__init__.py` および分割テストファイルを作成 (上記設計方針通り)
2. `tests/test_sysroot/fixtures/` に最小 Packages / `.deb` を配置 (生成スクリプトを同梱)
3. `_parse_control_block` / `_parse_relations` 等の内部関数テストを書く
4. `_resolve_dependencies` / `_topological_order` の整合性テストを書く (issue 0024 のレビューで指摘された OR 解決の不整合がリグレッションしないことを確認)
5. `_fix_absolute_symlinks` の `Path(root, target.lstrip("/"))` 経路を tempfile + symlink で検証
6. 実 HTTP サーバ経由で `_fetch_all_packages_indexes` の `.xz` → `.gz` フォールバックを確認
7. `dpkg-deb` がある環境で `build_rootfs` の最小フィクスチャ統合テストを 1 〜 2 ケース書く
8. CI (build.yml の build_ubuntu) で `tests/test_sysroot/` が実行されるよう、 必要なら workflow に pytest step を追加 (`pyproject.toml` の testpaths 設定だけで拾えるなら不要)

## 関連

- 0024 (closed): sysroot.py 新設の親 issue。 `## 設計方針` で「`tests/test_sysroot.py` は別 issue (test カテゴリ) で扱う」 と明示
- PR #302: 0024 の merge 対象
