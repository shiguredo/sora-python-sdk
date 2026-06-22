# sysroot.py の Repo.allow_insecure と _KNOWN_OPTIONAL_KEYS の運用を整理する

- Priority: Low
- Created: 2026-06-22
- Completed: {YYYY-MM-DD}
- Model: Opus 4.7
- Branch: feature/refactor-sysroot-config-yagni
- Polished: {YYYY-MM-DD}

## 目的

0024 で新設した `sysroot.py` には、 0024 のレビュー (review-diff-code 観点 2 / 6) で「YAGNI 違反」 として指摘された箇所が 2 つある:

1. **`Repo.allow_insecure`**: dataclass フィールドとして保持されているが、 sysroot.py 内のロジックでは一切参照されていない (`SHA256` 検証は `allow_insecure: true` でも維持されるため、 現状の挙動には影響しない)。 「将来 GPG 検証導入時の拡張点として保持」 と issue 0024 で明記されているが、 GPG 検証が実装されるまでは dead field
2. **`_KNOWN_OPTIONAL_KEYS` / `_KNOWN_OPTIONAL_REPO_KEYS`**: webrtc-rs / momo の `sysroot/*.json` 互換のため `rust_target` / `linker` / `cc` / `cxx` / `cflags` / `cxxflags` を「unknown field 警告を出さない」 ための allowlist として保持しているが、 sora-python-sdk リポジトリの 4 つの JSON ではこれら互換フィールドは一切使われていない

これらを GPG 検証導入のタイミング (将来) まで一旦削除するか、 もしくは「webrtc-rs / momo 互換」 の整合を実際に取って必要な whitelist を厳密にするかを判断・整理する。

## 優先度根拠

Low:

- 機能には影響しない (allow_insecure は dead field、 unknown field warning は CI ログを汚すだけ)
- ただし「将来の拡張点として保持」 が「使われない可能性が高い前提でコードに残し続ける」 と化す前に、 早めに方針を決めて削除 or 厳密化するのが望ましい
- 0024 / 0025 / 0026 / 0027 / 0028 と独立して進められる

## 現状

### Repo.allow_insecure (sysroot.py 85-87 行)

```python
# GPG 検証を行わないかどうか。 現時点では sysroot.py の挙動には影響しないが、
# 将来 GPG 検証を導入する際の拡張点として保持する。
allow_insecure: bool = False
```

- `_parse_repo` でバリデーション + フィールドへの格納 (199-203 行)
- `_KNOWN_OPTIONAL_REPO_KEYS = frozenset(["allow_insecure"])` として「known」 扱い
- sysroot.py 内のロジック (`_fetch_packages_for_repo_unit` / `_download_single_deb` 等) で参照されていない
- JSON 側では `sysroot/raspberry-pi-os_armv8.json` の archive.raspberrypi.org、 `sysroot/ubuntu-22.04_armv8_jetson.json` の NVIDIA jetson common / t234 で `"allow_insecure": true` と明示
- 0024 issue で「現時点では sysroot.py の挙動には影響しない」 と明記

### _KNOWN_OPTIONAL_KEYS (sysroot.py 57-62 行)

```python
# webrtc-rs / momo の sysroot/*.json で使う任意フィールド。 Python 側では使わないが、
# スキーマ互換のため黙って無視する。 ここに含まれない未知フィールドは警告ログを出す。
_KNOWN_OPTIONAL_KEYS: frozenset[str] = frozenset(
    ["rust_target", "linker", "cc", "cxx", "cflags", "cxxflags"],
)
```

- `parse_config` で「真の未知フィールドのみ警告」 のための allowlist
- sora-python-sdk の 4 つの JSON ファイルではこれら 6 フィールドは一切使われていない (`grep -E '"(rust_target|linker|cc|cxx|cflags|cxxflags)"' sysroot/*.json` が 0 件)
- webrtc-rs / momo 側の `sysroot/*.json` で実際にどのキーが使われているかは未検証 (6 個で十分か不明)

## 設計方針

以下の 2 案から 1 つを選ぶ。 着手時にユーザーに判断を仰ぐ:

### 案 A: YAGNI に倒す (両方とも削除)

- `Repo.allow_insecure` フィールド削除
- `_KNOWN_OPTIONAL_KEYS` / `_KNOWN_OPTIONAL_REPO_KEYS` 削除
- JSON 側 (`sysroot/raspberry-pi-os_armv8.json` / `sysroot/ubuntu-22.04_armv8_jetson.json`) の `"allow_insecure": true` を削除
- 未知フィールド warning は単純化 (`{"name", "arch", "packages", "repos", "post_install_symlinks"}` 以外は警告)
- GPG 検証導入時 / webrtc-rs / momo 互換が必要になった時点で再度フィールド / allowlist を追加

メリット: コードがシンプル。 dead code が消える。
デメリット: 将来 webrtc-rs / momo の JSON を流用する際に「unknown field warning が大量に出る」 → わずらわしい

### 案 B: 互換性を厳密にする

- webrtc-rs (`shiguredo/webrtc-rs`) と momo (`shiguredo/momo`) の `sysroot/*.json` を実検証
- 実際に使われているフィールドを `_KNOWN_OPTIONAL_KEYS` に正確に列挙
- `Repo.allow_insecure` は「GPG 検証導入時に使う」 のではなく、 「allow_insecure: true なら SHA256 検証を緩める」 のような実意味を持たせるか、 もしくは「allow_insecure: true 時に warning ログを 1 行出す」 のような副作用を実装する
- JSON 側の `"allow_insecure": true` 記述に意味を持たせる

メリット: 「将来の拡張点として保持」 が「現に効くフィールド」 になる
デメリット: webrtc-rs / momo の調査が必要、 仕様検討が要る

### 推奨

案 A (YAGNI) を推奨。 GPG 検証の導入計画が具体化していない以上、 dead field を残す理由が薄い。 webrtc-rs / momo 互換も「実際に流用する issue」 が立った時点で必要分だけ追加すれば十分。 着手時にユーザー判断を仰ぐ。

## 完了条件

- 案 A / 案 B どちらかを選択して実装
- `uv run ruff check sysroot.py` / `uv run ruff format --check sysroot.py` が pass
- 4 つの JSON が `parse_config()` でロードできる (案 A の場合、 JSON 側の `"allow_insecure": true` 削除も含む)
- 案 A の場合、 `Repo.allow_insecure` 関連のコード行が全て削除されている
- 案 A の場合、 `_KNOWN_OPTIONAL_KEYS` / `_KNOWN_OPTIONAL_REPO_KEYS` 定数と参照が全て削除されている
- 案 B の場合、 webrtc-rs / momo の `sysroot/*.json` の実検証結果と allowlist 更新内容が PR description に記載されている

## 解決方法

### 案 A を選択した場合

1. `sysroot.py` から `Repo.allow_insecure` フィールド削除 (85-87 行)
2. `_parse_repo` から `allow_insecure_raw` のバリデーション削除 (199-203 行)
3. `Repo(...)` 構築から `allow_insecure=...` 削除
4. `_KNOWN_OPTIONAL_KEYS` / `_KNOWN_OPTIONAL_REPO_KEYS` 定数削除
5. `_parse_repo` の `known_keys` を `frozenset(["url", "suites", "components"])` に簡素化
6. `parse_config` の `known_keys` を `frozenset(["name", "arch", "packages", "repos", "post_install_symlinks"])` に簡素化
7. `sysroot/raspberry-pi-os_armv8.json` から `"allow_insecure": true` 削除 (1 箇所)
8. `sysroot/ubuntu-22.04_armv8_jetson.json` から `"allow_insecure": true` 削除 (2 箇所)
9. lint + smoke test を実行

### 案 B を選択した場合

1. webrtc-rs / momo の `sysroot/*.json` を取得し実フィールドを列挙
2. `_KNOWN_OPTIONAL_KEYS` を webrtc-rs / momo 実フィールドに更新
3. `Repo.allow_insecure` に意味を持たせる実装 (例: `allow_insecure: true` 時に warning ログ 1 行)
4. lint + smoke test を実行

## 関連

- 0024 (closed): sysroot.py 新設の親 issue。 `Repo.allow_insecure` と `_KNOWN_OPTIONAL_KEYS` の現状記述は 0024 の `## 設計方針` に明記
- 0025 (open): sysroot.py 単体テスト追加。 本 issue の実装変更後にテストも追従する必要があるため、 本 issue は 0025 着手前に進めるのが望ましい
- 0026 / 0027 / 0028 (open): いずれも本 issue とは独立して進められる
