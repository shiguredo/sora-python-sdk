# sdist を wheel publish matrix から分離して専用 artifact にする

- Priority: Medium
- Created: 2026-06-23
- Updated: 2026-07-17
- Completed: -
- Model: GPT-5
- Branch: feature/fix-sdist-build-fragile
- Polished: 2026-07-17

## 目的

sdist の生成を特定 platform / Python の wheel job の副作用から分離し、ubuntu-24.04 x86_64 の専用 job で 1 回だけ生成・検証する。wheel artifact と sdist artifact を混在させず、0066 が安全に publish / release できる入力契約を作る。

## 優先度根拠

- 特定 matrix entry の失敗や glob の評価結果によって sdist だけ欠落する release を防ぐ必要がある。
- wheel build 自体には影響せず、0066 の publish 再開までは外部公開も行われないため Medium とする。

## 前提

- 0001 〜 0005 の完了後に実装する。
- 本 issue は sdist の生成・検証・artifact 化だけを扱う。PyPI publish、GitHub Release、E2E gate は 0066 / 0067 で扱う。
- sdist から生成した検証用 wheel を配布 wheel として使わない。各 platform の配布 wheel は 0001 〜 0005 / 0052 の build artifact を使う。

## 現状

旧 `publish_wheel` は macos-15_arm64 × Python 3.12 の 1 matrix entry だけで `*.tar.gz` を残し、他 entry では glob を使って退避する。単一 job の成否と shell glob に sdist の有無が依存する。

0001 は scikit-build-core 移行時に publish job を削除し、sdist を一時的に生成しない方針にする。さらに `MANIFEST.in` を削除するため、トップレベル `VERSION` を含む source 一式が scikit-build-core の sdist に入ることを新経路で検証する必要がある。

## 設計方針

### build_sdist job

`.github/workflows/build.yml` に matrix を持たない `build_sdist` job を追加する。

- runner: ubuntu-24.04 x86_64。
- Python: プロジェクトの最小対応版 3.12。
- command: `uv sync --no-install-project` の後に `uv build --sdist`。
- output: `dist/` に `sora_sdk-<VERSION>.tar.gz` が厳密に 1 件。
- artifact: `source-distribution`。wheel artifact の `<platform>_python-<version>` pattern と一致させない。

0 件、複数件、`.tar.gz` 以外、filename の distribution / version 不一致は upload 前に失敗させる。`[ -e dist/*.tar.gz ]` や `find ... | head -1` は使わず、nullglob と配列件数で検査する。

### source 内容の検証

sdist を一時 directory へ展開し、root directory が 1 件だけで path traversal entry / root 外 symlink が無いことを確認する。少なくとも次を必須とする。

- `VERSION` / `DEPS` / `pyproject.toml` / `CMakeLists.txt`。
- `src/sora_sdk/` と C++ source / header。
- `cmake/scripts/fetch_deps.cmake` と toolchain。
- `sysroot_builder.py` / `sysroot/`。
- license / README。

scikit-build-core の dynamic version provider が展開後の `VERSION` を読めることも確認する。

### sdist 単独 smoke

repository checkout の source や `_deps` を参照しない一時 directory で、展開した sdist だけから ubuntu-24.04 x86_64 wheel を生成する。

1. sdist を展開する。
2. clean uv environment を作る。
3. 展開 root で `uv build --wheel` を実行する。
4. 生成 wheel を install する。
5. import と `sora_sdk.__version__ == VERSION` を検証する。

検証 wheel は一時 directory と一緒に破棄し、`source-distribution` artifact や通常 wheel artifact へ混ぜない。mock / stub は使わず、実際の network と通常の native dependency fetch を通す。

### downstream 契約

0066 は `source-distribution` artifact が 1 件だけあり、basename / SHA-256 / source 内容検査が成功済みであることを前提にする。本 issue は publish credential、`id-token` permission、release 作成を追加しない。

## 完了条件

- branch / tag のどちらでも `build_sdist` が 1 回だけ実行される。
- `source-distribution` に期待 basename の sdist が厳密に 1 件だけ含まれる。
- sdist に必須 source / metadata / sysroot file が含まれる。
- 展開した sdist だけから native wheel を build・install し、version / import smoke が成功する。
- 検証 wheel が artifact に混入しない。
- wheel build matrix に sdist の生成、退避、publish 条件分岐が無い。
- 0066 が artifact 名と期待件数を静的に参照できる。

## 解決方法

1. `build_sdist` job と source 内容検査を追加する。
2. sdist 単独の native wheel build / install smoke を追加する。
3. `source-distribution` artifact を upload する。
4. wheel matrix から sdist 用 glob / 条件分岐を除去する。
5. `CHANGES.md` の `## develop` に次を追加する。

```
- [FIX] sdist を専用ジョブで生成・検証する
  - @voluntas
```

## ロールバック

本 issue の squash commit を `git revert <squash-commit>` すると sdist artifact が無くなる。旧 wheel matrix への相乗り方式は復活させず、0066 の sdist publish / release を停止して forward fix する。
