# sysroot.py の docstring 拡充と CLI ヘルプの英語水準向上

- Priority: Low
- Created: 2026-06-22
- Completed: {YYYY-MM-DD}
- Model: Opus 4.7
- Branch: feature/refactor-sysroot-docstring
- Polished: {YYYY-MM-DD}

## 目的

0024 で新設した `sysroot.py` の docstring と CLI ヘルプは、 0024 のレビュー (review-diff-code 観点 2 / 3) で以下が指摘された:

- 関数の事前条件 / 副作用 / 例外仕様の記述が薄い箇所 (`_clean` / `parse_config` / `_extract_debs_sequential` / `build_rootfs`)
- argparse ヘルプの英語表現が不自然 (`Build a sysroot at --dest from --config` の option 名露出、 `Packages indexes` の不可算名詞扱い)
- docstring に「(issue 設計方針)」 などのメタ参照が残っていた (0024 PR の修正で削除済み)
- `_LOG_PREFIX` のコメント、 `_SSL_CONTEXT` 周辺の規約説明など、 実装者の思考プロセスのコードコメント化が過剰
- ファイル先頭 docstring に「build サブコマンドは ubuntu-24.04 x86_64 host 限定」 とあるが、 `--help` 出力にはホスト要件が出ない

これらをまとめて改善する。

## 優先度根拠

Low:

- 機能には影響しない
- ただし後続 cross 系 issue や `tests/test_sysroot.py` (0025) の作業者が読む頻度が高いファイルなので、 ドキュメント品質は早めに整える価値あり

## 現状

- `sysroot.py` (1071 行) の関数 docstring は 1 行サマリ中心。 副作用・例外仕様の明示が薄い
- argparse の help / description:

  ```python
  parser = argparse.ArgumentParser(
      prog="sysroot.py",
      description="Build a cross-compile sysroot from APT Packages indexes.",
  )
  ...
  build = sub.add_parser("build", help="Build a sysroot at --dest from --config")
  clean = sub.add_parser("clean", help="Remove --dest along with stamp and .debs cache")
  ```

  - `Packages indexes` は不可算名詞扱いで文法的に違和感
  - `Build a sysroot at --dest from --config` は option 名露出で読みにくい
  - host 要件 (ubuntu-24.04 x86_64 + dpkg-deb >= 1.21) が `--help` に出ない

- `_LOG_PREFIX` 直前のコメント (45-50 行) と `_SSL_CONTEXT` 直前のコメント (70-72 行) は規約宣言文を含み、 ノイズが多い
- 関数 docstring の「例」 表記 (`例: \`ubuntu-22.04_armv8\`` 等) が dataclass フィールドコメントに散在し、 自明な情報の繰り返しになっている

## 設計方針

### 関数 docstring の拡充

副作用を持つ関数は以下のサブセクションを docstring に追加する:

- `build_rootfs`: 「副作用」 (`<dest>` ディレクトリへの書き込み / `<cache_dir>` 作成 / stamp 書き込み) / 「例外」 (`SysrootError` 各種)
- `_clean`: 「副作用」 (`<dest>` 配下の削除) / 「冪等性」 (`<dest>` 不在時 no-op)
- `_extract_debs_sequential`: 「副作用」 (`dpkg-deb -x` 呼び出し) / 「例外」 (`SysrootError`)
- `parse_config`: 「例外」 (`SysrootError`)

### CLI ヘルプの英語水準向上

argparse の help / description を以下に書き換える:

- parser description: `Build a cross-compile sysroot from APT package indexes.` (Packages → package、 indexes はそのまま可算扱い)
- build help: `Build the sysroot.`
- clean help: `Remove the sysroot along with its stamp and .deb cache.`
- argparse の `epilog=` を追加して `Note: 'build' requires ubuntu-24.04 x86_64 host with dpkg-deb >= 1.21.` を出す

### コメント整理

- `_LOG_PREFIX` 直前のコメント: 「`Sora deps:` と区別するため `Sora sysroot:` を使う」 だけ残す。 規約宣言文は削除
- `_SSL_CONTEXT` 直前のコメント: 「Python 標準ライブラリ defaults を共有する」 だけ残す。 規約宣言文は削除
- dataclass フィールドコメントの「例: ...」 表記: 削除候補。 例の記述は parse_config のバリデーションメッセージで十分
- `PackageMeta` フィールドの `(Package: フィールド)` 等の Debian field 名注釈: dataclass docstring に「Packages インデックスから読み取った 1 パッケージ分のメタ情報」 とあるので削除可

### セクション区切りコメントの整理

`# ---------- JSON パース ----------` 等のセクション区切りコメントが 1062 行ファイル中 9 個ある。 多すぎ。 以下に統廃合:

- `# ---------- JSON パース ----------`
- `# ---------- HTTP 取得 ----------`
- `# ---------- 依存解決と展開 ----------`
- `# ---------- symlink 後処理 ----------`
- `# ---------- 公開 API と CLI ----------`

合計 5 個に集約。

## 完了条件

- `build_rootfs` / `_clean` / `_extract_debs_sequential` / `parse_config` の docstring に「副作用」 / 「例外」 が記述されている
- argparse の help / description / epilog が英語水準の高い表現に書き換えられている
- `_LOG_PREFIX` / `_SSL_CONTEXT` 直前のコメントが簡潔化されている
- dataclass フィールドの「例:」 / `(Packages フィールド)` 等の冗長コメントが削除されている
- セクション区切りコメントが 9 個 → 5 個程度に集約されている
- `uv run ruff check sysroot.py` / `uv run ruff format --check sysroot.py` が pass
- `python3 sysroot.py --help` / `build --help` / `clean --help` 出力が前より読みやすくなる (人間判断)

## 解決方法

1. argparse の `prog`, `description`, `epilog`, 各 subparser の `help` を書き換え
2. `build_rootfs` / `_clean` / `_extract_debs_sequential` / `parse_config` の docstring に「副作用」 / 「例外」 を追加
3. `_LOG_PREFIX` / `_SSL_CONTEXT` 直前のコメントを 1 行に圧縮
4. dataclass フィールドコメントから冗長な「例:」 と Debian field 名注釈を削除
5. セクション区切りコメントを 5 個に統廃合
6. `uv run ruff check / format --check sysroot.py` で lint pass を確認
7. `python3 sysroot.py --help` 等を実行し人間判断で出力品質を確認

## 関連

- 0024 (closed): sysroot.py 新設の親 issue。 本 issue は 0024 のレビュー指摘 (review-diff-code 観点 2 / 3 / 6) の改善のうちドキュメント品質に絞ったもの
- 0025 (open): sysroot.py 単体テスト追加。 docstring 拡充は 0025 着手前に終わっていると、 テスト作者がテスト対象の事前条件 / 副作用 / 例外仕様を把握しやすい
- 0026 (open): sysroot.py を ty チェック対象に追加。 本 issue とは独立して進められる
