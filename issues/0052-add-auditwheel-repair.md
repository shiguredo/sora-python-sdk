# Ubuntu wheel に auditwheel repair を導入する

- Priority: High
- Created: 2026-06-23
- Updated: 2026-07-17
- Completed: -
- Model: GPT-5
- Branch: feature/add-auditwheel-repair
- Polished: 2026-07-17

## 目的

0001 / 0003 が生成する `linux_x86_64` / `linux_aarch64` wheel を `auditwheel repair` で検査・修復し、target の glibc baseline と実依存に一致する manylinux wheel を生成する。

setup.py の文字列置換で tag だけを付ける旧方式は 0001 で削除済みのため復活させず、repair 後の wheel だけを Ubuntu の最終 artifact とする。

## 優先度根拠

- 0001 / 0003 の未修復 `linux_*` wheel は PyPI の汎用 Linux 配布物として完成しておらず、0066 の publish 再開前に必要である。
- 特に Ubuntu arm64 wheel は x86_64 host で cross build されるため、host library を誤って同梱しない検証が必要である。配布前の必須工程なので High とする。

## 前提

- 0001 と 0003 の完了後に実装する。
- 対象は汎用 Ubuntu 3 target だけとする。Raspberry Pi OS は Trixie / libcamera 固有の `linux_aarch64` wheel を維持し、Jetson は 0043 / 0045 完了後の別対応とする。
- publish / GitHub Release の artifact 集約は 0066、E2E は 0067 で扱う。

## 現状

- 0001 の ubuntu-24.04 x86_64 wheel は `linux_x86_64` tag になる。
- 0003 の ubuntu-22.04 / 24.04 arm64 wheel は scikit-build-core の override で `linux_aarch64` tag になる。
- 旧 setup.py の手動 manylinux tag は 0001 で削除される。
- wheel の外部共有 library、versioned symbol、実際に満たす manylinux policy を検査する工程が無い。

## 設計方針

### tool と target policy

test dependency group に `auditwheel>=6.7,<7` を追加し、`uv.lock` を更新する。6.7.0 は non-Python ELF の dependency tree と grafted library の RPATH 修正を含むため下限とする。

Ubuntu job は `patchelf` / `binutils` を APT で明示的に install し、repair 前に `patchelf --version` が 0.14 以上であることを確認する。

target policy は次に固定する。

| target | input tag | repair tag |
| --- | --- | --- |
| `ubuntu-24.04_x86_64` | `linux_x86_64` | `manylinux_2_39_x86_64` |
| `ubuntu-22.04_armv8` | `linux_aarch64` | `manylinux_2_35_aarch64` |
| `ubuntu-24.04_armv8` | `linux_aarch64` | `manylinux_2_39_aarch64` |

各 matrix entry は `dist/` の input wheel が厳密に 1 件であることを確認し、次の順で処理する。

1. `auditwheel show <input>` を診断 log として保存する。
2. `auditwheel repair --plat <tag> --only-plat --ldpaths <validated-paths> -w wheelhouse <input>` を実行する。`--strip` は使わない。
3. `wheelhouse/` の output が厳密に 1 件であることを確認する。
4. output に `auditwheel show` を再実行する。
5. filename と `WHEEL` metadata の platform tag が表と一致することを確認してから input wheel と置換する。

要求 policy を満たせない場合、0 件 / 複数件、tag 不一致は artifact upload 前に失敗させる。`auditwheel` を呼ばず tag だけを書き換える fallback は設けない。

### AArch64 native repair job

auditwheel 6.7 の `--plat` choices は実行 host architecture から作られるため、x86_64 process で `manylinux_*_aarch64` を指定しない。wheel build は 0003 の ubuntu-24.04 x86_64 cross job のまま維持し、repair だけを target と同じ architecture / Ubuntu version の GitHub-hosted runner へ分離する。

| target | build runner | repair runner |
| --- | --- | --- |
| `ubuntu-22.04_armv8` | `ubuntu-24.04` x86_64 | `ubuntu-22.04-arm` |
| `ubuntu-24.04_armv8` | `ubuntu-24.04` x86_64 | `ubuntu-24.04-arm` |

cross build job は最終 artifact 名を使用せず、`auditwheel-input-<platform>_python-<version>` を upload する。この内部 artifact は raw wheel 1 件、flat な `repair-root/`、`repair-input-manifest.json` だけを含む。extension の再帰 `DT_NEEDED` を `_deps/<platform>` / sysroot で解決し、manylinux allowlist を含む必要 library closure 全体を `repair-root/` へ stage する。

各 entry は symlink の参照先を検証後、basename が `DT_NEEDED` の SONAME と完全一致する通常 file として copy する。versioned real file 名を保持して symlink だけ除く構成にはしない。同じ SONAME が複数の異なる digest へ解決される場合、SONAME と ELF 内 `DT_SONAME` が異なる場合、由来不明 file、x86_64 ELF、root 外 realpath を拒否する。

manifest は source commit SHA、platform、Python / ABI、raw wheel filename / SHA-256、各 staged library の元 provenance kind / package または dependency、relative path、SHA-256、SONAME、ELF architecture を持つ。repair job は artifact 完全名で取得し、file 件数、manifest、全 digest / ELF / SONAME を auditwheel 実行前に再検証する。

AArch64 repair job は host の `LD_LIBRARY_PATH` を継承せず、`AUDITWHEEL_LD_LIBRARY_PATH` も明示的に unset して空であることを確認し、flat な `repair-root/` だけを auditwheel の `--ldpaths` に指定する。native runner の `/etc/ld.so.conf` / system multiarch directory は渡さない。各再帰 `DT_NEEDED` SONAME が `repair-root/<SONAME>` の厳密に 1 file へ解決することを事前検証する。verbose repair log の graft source が `repair-root/` 外なら失敗させ、manylinux allowlist library が output wheel へ graft されていないことも確認する。

stable job ID は `repair_ubuntu_arm`、`needs: [build_ubuntu]` とする。matrix は Ubuntu arm64 2 target × Python 3 ABI の 6 entry に固定する。0052 適用時点の `slack_notify.needs` へ `repair_ubuntu_arm` を追加し、0067 は `e2e_test.needs` / `ci_result`、0066 は `prepare_release.needs` へ同 job を引き継ぐ。repair の failure / cancelled / skipped を publish 前に必ず失敗として集約する。

ubuntu-24.04 x86_64 native entry も `--ldpaths` を明示し、`_deps/ubuntu-24.04_x86_64` と realpath 検証済みの Ubuntu 24.04 x86_64 system multiarch directory だけを許可する。architecture ごとの path list を混用しない。

repair 前後の wheel を一時 directory へ展開し、extension と graft された全 ELF を `readelf` で検査する。auditwheel 実行前に raw wheel 内の全 ELF と flat `repair-root/` の全 ELF の `DT_RPATH` / `DT_RUNPATH` を検査し、wheel / repair-root 内へ留まる `$ORIGIN` 相対 path だけを許可する。build host / native runner の絶対 path、空要素、root 外へ解決する `$ORIGIN`、別 architecture directory があれば失敗させる。staged dependency 自身の RPATH / RUNPATH を未検査のまま auditwheel へ渡さない。

- 全 ELF が期待 architecture である。
- 非 manylinux allowlist の `DT_NEEDED` が wheel 内または target dependency / sysroot 内で一意に解決できる。
- output に x86_64 と AArch64 が混在しない。
- grafted library の RUNPATH / RPATH が wheel 内の解決先を指し、build host の絶対 path を含まない。

実際の Ubuntu arm64 wheel 全 3 ABI を matching AArch64 repair runner 上で show / repair する。test 用 ELF や別 wheel では代用しない。arm64 native runner は wheel の compile / link を行わず、cross build 済み raw wheel の検査・repair・metadata 更新だけを行う。auditwheel の `--strip` は使用せず、symbol strip が必要なら独立 issue で扱う。

### native x86_64 と artifact

ubuntu-24.04 x86_64 は repair 後の wheel を clean venv へ install し、`tests/test_version.py` と import smoke を実行する。arm64 は x86_64 host へ install せず、0067 の arm64 runner E2E へ引き継ぐ。

AArch64 repair job は raw input の source SHA / platform / ABI / wheel digest を保持し、repair 後 wheel を通常の最終 artifact 名 `<platform>_python-<version>` で厳密に 1 件 upload する。内部 `auditwheel-input-*` artifact は 0066 / 0067 の download pattern と一致させない。x86_64 は従来どおり build job 内で repair 後の同名最終 artifact を upload する。

## 完了条件

- Ubuntu 3 target × Python 3.12 / 3.13 / 3.14 の全 9 wheel が表の manylinux tag になる。
- filename と `WHEEL` metadata が同じ単一 tag を持つ。
- Ubuntu 22.04 / 24.04 の matching AArch64 GitHub-hosted runner 上で実 AArch64 wheel の show / repair が全 ABI 成功し、compile / link は実行しない。
- allowlist を含む全再帰 dependency を manifest 検証済み flat `repair-root/` だけから一意に解決し、graft source を同 root 内へ限定する。allowlist library は output wheel へ graft せず、output wheel に x86_64 ELF、未解決 dependency、build host 絶対 path が無い。
- show / repair が検証済み `--ldpaths` を必須とし、`LD_LIBRARY_PATH` / `AUDITWHEEL_LD_LIBRARY_PATH`、host の default loader path、raw wheel / staged ELF の不正 RPATH / RUNPATH を経由しない。
- ubuntu-24.04 x86_64 の repaired wheel を install して version / import smoke が成功する。
- Raspberry Pi OS / macOS / Windows / Jetson job が `auditwheel` を実行せず、既存 tag を維持する。
- 0066 が取得する各 Ubuntu artifact に repaired wheel が厳密に 1 件だけ存在する。
- `repair_ubuntu_arm` の result を Slack、E2E、release gate が参照し、internal `auditwheel-input-*` artifact が publish / release bundle に混入しない。

## 解決方法

1. `pyproject.toml` / `uv.lock` に auditwheel を追加する。
2. cross build job に sealed repair input staging / manifest / internal artifact を追加する。
3. Ubuntu 22.04 / 24.04 AArch64 repair job に patchelf / binutils、auditwheel、`--ldpaths`、input provenance 検証を追加する。
4. wheel 件数検査、show、repair、tag / ELF / dependency 検査を最終 artifact upload 前へ追加する。
5. x86_64 native install smoke と全 AArch64 ABI の実 wheel repair を CI で確認する。
6. `CHANGES.md` の `## develop` に次を追加する。

```
- [ADD] Ubuntu wheel に auditwheel repair による manylinux タグ付与を導入する
  - @voluntas
```

## ロールバック

問題が発生した場合は本 issue の squash commit を `git revert <squash-commit>` し、Ubuntu の publish を停止する。未修復の `linux_*` wheel を PyPI へ公開する fallback は認めず、forward fix 後に publish を再開する。

## 参照（一次資料）

- auditwheel 公式 README: https://github.com/pypa/auditwheel/blob/main/README.rst
- auditwheel 6.7.0 release: https://github.com/pypa/auditwheel/releases/tag/6.7.0
- auditwheel 6.7.0 `repair` CLI 実装: https://github.com/pypa/auditwheel/blob/6.7.0/src/auditwheel/main_repair.py
- GitHub-hosted runner の architecture / label: https://docs.github.com/en/actions/reference/runners/github-hosted-runners
- Python Packaging User Guide の platform compatibility tag: https://packaging.python.org/en/latest/specifications/platform-compatibility-tags/
