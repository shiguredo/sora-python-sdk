# sora-sdk-rpi を Raspberry Pi OS 以外の環境でも uv add できるようにする

- Created: 2026-09-11
- Completed: -
- Branch: feature/change-rpi-install-method
- Polished: -
- Reporter: @voluntas

## 目的

`sora-sdk-rpi` は Raspberry Pi OS arm64 向けに libcamera 対応の `create_libcamera_source` を提供する別 distribution だが、PyPI には `manylinux_2_35_aarch64` wheel しか公開されておらず sdist も無い。このため macOS / Windows / Linux x86_64 などの開発環境で `uv add sora-sdk-rpi` や `uv sync` が失敗し、Raspberry Pi を対象に含むプロジェクトを開発機で扱えない。

Raspberry Pi 実機向けのインストール手段を維持しつつ、非 Raspberry Pi 環境でも依存解決と lock が成立する標準的な方法を確定する。

## 現状

### ビルドと公開

- sora-sdk と sora-sdk-rpi は同一リポジトリの `.github/workflows/build.yml` から生成する。`build_ubuntu` job の `sora_sdk_rpi` ステップが `raspberry-pi-os_armv8` のときだけ `pyproject.toml` の `name = "sora_sdk"` を `sora_sdk_rpi` へ sed 置換する。
- `setup.py` の `run_setup` が target ごとの platform tag を決める。`raspberry-pi-os` は `manylinux_2_35_aarch64`、Ubuntu 24.04 は `manylinux_2_38_aarch64` / `manylinux_2_38_x86_64`。
- `publish_wheel` job が `pypa/gh-action-pypi-publish` で `sora_sdk` と `sora_sdk_rpi` の両 wheel を publish する。`.github/actions/download-whl/action.yml` は `sora_sdk_rpi-${VERSION}-${PY_TAG}-${PY_TAG}-manylinux_2_35_aarch64.whl` を前提とする。
- `pyproject.toml` は `name = "sora_sdk"`、`requires-python = ">= 3.12"` で optional-dependencies を持たない。import package 名は両 distribution とも `sora_sdk`。
- `src/sora_sdk_ext.cpp` の `create_libcamera_source` は全プラットフォームのバインディングに存在し、`USE_V4L2` が無効なビルドでは `Libcamera is not supported on this platform` を投げる。

### PyPI の公開物

- `sora-sdk` 2026.1.0: `macosx_15_0_arm64` / `macosx_26_0_arm64` / `manylinux_2_38_x86_64` / `manylinux_2_38_aarch64` / `win_amd64` の wheel と `sora_sdk-2026.1.0.tar.gz`。`requires_dist` は null。
- `sora-sdk-rpi` 2026.1.0: `cp312` / `cp313` / `cp314` の `manylinux_2_35_aarch64` wheel のみ。sdist は全 release を通して 0 件。`requires_dist` は null。

### 再現

uv 0.12.7 (macOS 26 arm64) で確認した。

- `uv add sora-sdk-rpi` は解決に成功するが、install 時に `can't be installed because it doesn't have a source distribution or wheel for the current platform` で失敗する。
- `uv lock` は成功する。`uv sync` は install で同じエラーになる。
- `uv pip compile --python-platform x86_64-unknown-linux-gnu` は `no wheels with a matching platform tag` で失敗する。wheel があるのは linux aarch64 かつ manylinux_2_35 互換の環境だけである。
- `uv add "sora-sdk-rpi; sys_platform == 'linux' and platform_machine == 'aarch64'"` は macOS で成功する。
- `[tool.uv] required-environments` の追加だけでは `uv add` の install エラーは解消しない。

### 背景 (推測を含む)

- Raspberry Pi OS arm64 と Ubuntu arm64 は wheel の platform tag で区別できない。RPi wheel と Ubuntu wheel を同じ `sora_sdk` 名で publish すると、glibc が新しい Pi では Ubuntu wheel が優先して選ばれ libcamera 対応が失われるおそれがある。この回避のため別 distribution 名にしていると読める。
- 両 distribution は同じ import package `sora_sdk` と同じファイル名を持つ。同時インストールするとファイルが衝突する可能性が高い (要検証)。

## 設計方針

保留を解除したら、まず「非 Raspberry Pi 環境で依存解決と lock と install が成立し、Raspberry Pi 実機ではこれまでどおり libcamera 対応 wheel が入る」ことを満たす方法を 1 つに絞る。候補は次のとおり。

- 利用側で platform marker を書く。`sora-sdk-rpi>=<version>; sys_platform == 'linux' and platform_machine == 'aarch64'` のように宣言する。リポジトリ変更なしで非 aarch64 環境の `uv add` / `uv lock` / `uv sync` が成立する。反面、marker 付きの書き方を README.md / skills/sora-python-sdk/SKILL.md に明記する必要があり、`platform_machine == 'aarch64'` は Raspberry Pi OS 以外の Linux arm64 にも一致する。
- `sora-sdk[rpi]` extra を提供する。`[project.optional-dependencies]` に `rpi = ["sora-sdk-rpi==<version>; sys_platform == 'linux' and platform_machine == 'aarch64'"]` を追加する。利用者は `uv add "sora-sdk[rpi]"` と書ける。反面、extra は base の `sora-sdk` を置き換えられないため Pi 上で両 distribution が入り、`sora_sdk` package が衝突する可能性が高い。衝突を避けるには distribution 構成の再設計が要る。
- `sora-sdk-rpi` の sdist を publish する。解決候補は増えるが非 Pi 環境で source build に失敗し、install 失敗は解消しない。
- 利用側で `uv lock` / `--no-install-package` / `[tool.uv] environments` を使う。リポジトリ変更は不要だが `uv add sora-sdk-rpi` 自体は失敗したままで SDK 側の解決にならない。
- distribution 構成を platform 別 native backend と extras に再設計する。`uv add "sora-sdk[rpi]"` が衝突なく成立するが、publish / build / import の全面改修と既存利用者の移行が必要になる。

外部エコシステムで同種のプラットフォーム別 wheel をどう配布しているかを調査したうえで、どれを採用するかと衝突を許容できるかを決める。設計が固まるまでは実装しない。

## 完了条件

- 非 Raspberry Pi 環境 (少なくとも macOS / Windows / Linux x86_64) で `uv add` と `uv sync` が失敗しないインストール方法が決まっている。
- Raspberry Pi OS 実機では `create_libcamera_source` が使える wheel が入る。
- `README.md` と `skills/sora-python-sdk/SKILL.md` のインストール手順が新しい方法に一致している。
- 採用しなかった候補とその理由が issue に残っている。
- 実装する場合は `CHANGES.md` に変更が記載され、CI の `sora_sdk` / `sora_sdk_rpi` wheel publish が壊れていない。

## pending にした理由

- どの方法を採るかが未確定。`sora-sdk[rpi]` extra は `sora-sdk` と `sora-sdk-rpi` が同じ `sora_sdk` package を持つため同時インストールで衝突する可能性が高く、採用には distribution 構成の再設計が必要。
- Raspberry Pi OS と他 Linux arm64 を wheel tag や marker では区別できないという制約があり、利用者の意図どおりに RPi wheel だけを選ばせる方法が確立できていない。
- 外部エコシステムで同種のプラットフォーム別 wheel をどう配布しているかの調査が未完了。
- 上記が決まるまで実装方針を確定できないため保留する。再開するときは reopened にしてから進める。
