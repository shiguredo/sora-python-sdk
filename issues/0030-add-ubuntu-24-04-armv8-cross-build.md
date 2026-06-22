# ubuntu-24.04_armv8 platform の cross-compile wheel ビルドを sysroot.py 経路で復活させる

- Priority: High
- Created: 2026-06-22
- Completed: {YYYY-MM-DD}
- Model: Opus 4.7
- Branch: feature/add-ubuntu-24-04-armv8-cross-build
- Polished: {YYYY-MM-DD}

## 目的

0024 で multistrap 経路から sysroot.py 経路への置き換えが完了し、 `sysroot.py` と `sysroot/*.json` 4 ファイルは merge 済だが、 `cmake/scripts/fetch_deps.cmake` の `_sora_fetch_rootfs` 関数定義はメインスクリプトから呼び出されておらず、 `cmake/toolchains/*.cmake` 自体も存在しないため、 cross-compile wheel ビルドは CI でも復活していない。

本 issue では 4 platform (ubuntu-22.04_armv8 / ubuntu-24.04_armv8 / raspberry-pi-os_armv8 / ubuntu-22.04_armv8_jetson) のうち最も構成が単純な **`ubuntu-24.04_armv8` 1 platform に絞って**、 `uv build` → `cmake configure` → `_sora_fetch_rootfs` → `sysroot.py build` → wheel 生成の経路を最初から最後まで通す。 これが green になれば、 残り 3 platform は同じパターンで後続 issue として順次足せる。

## 優先度根拠

High:

- 0024 で sysroot.py を merge した直後の最初の cross-compile 復活経路。 本 issue が動かない限り、 後続 3 platform の cross-compile 復活を進める根拠が立たない
- 0024 (closed) の `## スコープ境界` で「cross-compile した wheel を実際に生成する経路 (toolchain ファイル新設、 pyproject.toml override 追加、 `SORA_PYTHON_SDK_PLATFORM` 許容リスト追加、 `_sora_fetch_rootfs` の **実呼び出し**、 CI matrix の `exclude` 解除) は本 issue では行わず、 後続 cross 系 issue で扱う」 と明示されており、 その後続 issue の第 1 弾に該当する
- 撤回された 0017 / 0019 / 0020 (closed) の代替経路としても本 issue が source of truth となる

## 現状

### sysroot.py 側 (0024 merge 済)

- `sysroot.py` (約 1071 行、 リポジトリルート直下) と `sysroot/*.json` 4 ファイル (ubuntu-22.04_armv8 / ubuntu-24.04_armv8 / ubuntu-22.04_armv8_jetson / raspberry-pi-os_armv8) は配置済み
- CLI: `python3 sysroot.py build --config <json> --dest <dir>` で rootfs を構築できる
- 0024 の `## 解決方法` で「実装環境が macOS のため本 PR では未実施」 と明示されており、 ubuntu-24.04 x86_64 host での実機検証 (`dpkg-deb >= 1.21` 要件) は本 issue が最初の試行になる

### cmake 側 (0024 merge 済 / 本 issue で改修)

- `cmake/scripts/fetch_deps.cmake:381-401` に `_sora_fetch_rootfs(rootfs_dir json_config)` 関数定義あり (メインスクリプトから呼び出されていない)
- `cmake/scripts/fetch_deps.cmake:76` の `_SORA_ALLOWED_PLATFORMS` は `ubuntu-24.04_x86_64`、 `macos_arm64`、 `windows_x86_64` の 3 つのみ。 cross 系 platform は configure 時点で `FATAL_ERROR` で落ちる
- `cmake/toolchains/` ディレクトリ自体が存在しない (現状 `cmake/` 配下は `scripts/` のみ)
- メインスクリプトで `CMAKE_SYSROOT` / `CMAKE_FIND_ROOT_PATH` を確定する分岐が無い
- `CMakeLists.txt` 側には既に `if (CMAKE_CROSSCOMPILING)` ガードや `TARGET_OS STREQUAL "ubuntu"` 分岐 (`-nostdinc++ -isystem${LIBCXX_INCLUDE_DIR}` 等) が用意されているため、 cross 経路の C/C++ ビルド設定そのものは既存ロジックを再利用できる

### pyproject.toml 側 (0024 merge 済 / 本 issue で改修)

- `[tool.scikit-build.cmake.define]` で base 値として `TARGET_OS = "ubuntu"` を定義
- macOS / Windows 用 override (`[[tool.scikit-build.overrides]]`) は存在するが、 cross-compile 用 override は無い
- scikit-build-core は `[[tool.scikit-build.overrides]]` の `if.env.<NAME>` トリガーに対応しており、 env 駆動で override を切り替えられる

### CI 側 (0024 merge 済 / 本 issue で改修)

- `.github/workflows/build.yml:84` の `build_ubuntu` matrix に `ubuntu-24.04_armv8` entry あり (`runs_on: ubuntu-24.04`, `os: ubuntu`, `arch: armv8`)
- `.github/workflows/build.yml:118-122` の `exclude:` で `ubuntu-22.04_armv8`、 `ubuntu-24.04_armv8`、 `raspberry-pi-os_armv8` の armv8 系 entry は無効化済み
- 0024 で multistrap install + sed パッチ step と `uv run python run.py build && uv build` step は削除済
- `build_ubuntu_arm` job (`if: false` 済) は 0022 で job ごと削除予定。 本 issue では触らない

## 設計方針

### スコープ境界

本 issue で行うこと:

- `cmake/toolchains/aarch64-linux-gnu.cmake` を新設
- `cmake/scripts/fetch_deps.cmake` を改修
  - `_SORA_ALLOWED_PLATFORMS` に `ubuntu-24.04_armv8` を追加
  - メインスクリプトに cross 系 platform 用の分岐を追加し、 `_sora_fetch_rootfs` を呼び出して `CMAKE_SYSROOT` を確定する
- `pyproject.toml` に cross 用 `[[tool.scikit-build.overrides]]` を追加
- `.github/workflows/build.yml` の `exclude:` から `ubuntu-24.04_armv8` を削除し、 build step を sysroot.py 経路に書き換え
- `CHANGES.md` に `[ADD]` エントリを追加

本 issue で行わないこと (後続 issue):

- `ubuntu-22.04_armv8` / `raspberry-pi-os_armv8` / `ubuntu-22.04_armv8_jetson` の cross-compile 復活 (本 issue が green になった後、 1 platform 1 issue で順次)
- `auditwheel repair --only-plat` による manylinux タグ確定 (0022 で扱う)
- `sysroot.py` の単体テスト (0025 で扱う)
- `sysroot.py` を ty 型チェック対象に追加 (0026 で扱う)
- `_sora_fetch_rootfs` の dry-run 検証 (0027 で扱う。 本 issue が green なら 0027 は不要になる可能性あり)
- `sysroot.py` の docstring 拡充 (0028 で扱う)
- `Repo.allow_insecure` / `_KNOWN_OPTIONAL_KEYS` の YAGNI 整理 (0029 で扱う)
- 0022 (`run.py` / `buildbase.py` / `MANIFEST.in` / `build_ubuntu_arm` job 削除) との順序依存はない (互いに独立)

### cmake/toolchains/aarch64-linux-gnu.cmake の新設

CMake の cross-compile toolchain ファイルとして以下を設定する:

- `CMAKE_SYSTEM_NAME=Linux`
- `CMAKE_SYSTEM_PROCESSOR=aarch64`
- `CMAKE_C_COMPILER_TARGET=aarch64-linux-gnu`
- `CMAKE_CXX_COMPILER_TARGET=aarch64-linux-gnu`
- `CMAKE_FIND_ROOT_PATH=${CMAKE_SYSROOT}` (`CMAKE_SYSROOT` は fetch_deps.cmake 側で確定)

`CMAKE_C_COMPILER` / `CMAKE_CXX_COMPILER` は fetch_deps.cmake で LLVM 同梱 clang に確定する既存ロジックを再利用するため、 toolchain ファイル側では設定しない。

### cmake/scripts/fetch_deps.cmake の改修

1. `_SORA_ALLOWED_PLATFORMS` に `ubuntu-24.04_armv8` を追加 (76 行目)
2. platform → JSON ファイルのマッピングを明示する (例: `set(_SORA_SYSROOT_JSON_ubuntu-24.04_armv8 "sysroot/ubuntu-24.04_armv8.json")`)
3. メインスクリプトの LLVM 取得直後あたりに cross 系 platform 分岐を追加:
   - 現在の platform が cross 系 (= `ubuntu-24.04_armv8` 等) の場合:
     - rootfs 構築先を `_PLATFORM_ROOT/rootfs` に決定
     - sysroot JSON config を `${CMAKE_SOURCE_DIR}/sysroot/<platform>.json` から特定
     - `_sora_fetch_rootfs(<rootfs_dir>, <json_config>)` を呼ぶ
     - `CMAKE_SYSROOT=<rootfs_dir>` を `CACHE PATH FORCE` で確定

### pyproject.toml の cross 用 override 追加

`[[tool.scikit-build.overrides]]` を以下のように 1 件追加する:

```toml
[[tool.scikit-build.overrides]]
if.env.SORA_PYTHON_SDK_PLATFORM = "ubuntu-24.04_armv8"
inherit.cmake.define = "append"
cmake.define.TARGET_OS = "ubuntu"
cmake.define.SORA_PYTHON_SDK_PLATFORM = "ubuntu-24.04_armv8"
cmake.define.CMAKE_TOOLCHAIN_FILE = "cmake/toolchains/aarch64-linux-gnu.cmake"
```

これにより `SORA_PYTHON_SDK_PLATFORM=ubuntu-24.04_armv8 uv build --wheel` 1 発で sysroot 構築 → wheel 生成までが完結する。

### .github/workflows/build.yml の改修

1. `build_ubuntu` matrix の `exclude:` から `ubuntu-24.04_armv8` を削除
2. 該当 platform 用の build step を追加:

```yaml
- name: Build wheel (cross)
  if: matrix.platform.arch == 'armv8'
  env:
    SORA_PYTHON_SDK_PLATFORM: ${{ matrix.platform.target }}
  run: uv build --wheel
```

host は `runs-on: ubuntu-24.04` (sysroot.py の `dpkg-deb >= 1.21` 要件)。 既存の x86_64 用 step との分岐は `matrix.platform.arch` で行う。

### CHANGES.md の追加エントリ

`shiguredo-changelog` 規約に従い `## develop` セクションに以下を追加する:

```
- [ADD] ubuntu-24.04_armv8 platform の cross-compile wheel ビルドを sysroot.py 経路で復活する
  - 0024 で停止していた cross-compile wheel ビルドを scikit-build-core (cmake) → _sora_fetch_rootfs → sysroot.py 経路で再開
  - 残り 3 platform (ubuntu-22.04_armv8 / raspberry-pi-os_armv8 / ubuntu-22.04_armv8_jetson) は後続 issue で順次対応
  - @voluntas
```

## 完了条件

- `cmake/toolchains/aarch64-linux-gnu.cmake` が新設されている
- `cmake/scripts/fetch_deps.cmake` の `_SORA_ALLOWED_PLATFORMS` に `ubuntu-24.04_armv8` が含まれている
- `cmake/scripts/fetch_deps.cmake` のメインスクリプトで cross 系 platform 時に `_sora_fetch_rootfs` が呼ばれ、 `CMAKE_SYSROOT` が `CACHE PATH FORCE` で確定される
- `pyproject.toml` に env 駆動の cross 用 `[[tool.scikit-build.overrides]]` が追加されている
- `.github/workflows/build.yml` の `exclude:` から `ubuntu-24.04_armv8` が外れている
- `CHANGES.md` の `## develop` セクションに `[ADD]` エントリが追加されている
- CI で `ubuntu-24.04_armv8` × 3 Python (3.12 / 3.13 / 3.14) の wheel が artifact として生成され、 関連 job が green
- ローカル macOS では以下のみ確認可能 (実機検証は CI 上のみ):
  - `uv run ruff check` / `uv run ruff format --check` が pass
  - `uv run ty check` が pass (`sysroot.py` は ty 対象外のままで本 issue 範囲外)
  - `python3 -c "import json; json.load(open('sysroot/ubuntu-24.04_armv8.json'))"` が成功

## 解決方法

1. `cmake/toolchains/aarch64-linux-gnu.cmake` を新規作成
2. `cmake/scripts/fetch_deps.cmake` を改修
   - `_SORA_ALLOWED_PLATFORMS` 拡張
   - platform → JSON マッピング追加
   - メインスクリプトに cross 分岐追加 (`_sora_fetch_rootfs` 呼び出し + `CMAKE_SYSROOT` 確定)
3. `pyproject.toml` に cross 用 `[[tool.scikit-build.overrides]]` を追加
4. `.github/workflows/build.yml` の `exclude:` から `ubuntu-24.04_armv8` を削除し、 build step を sysroot.py 経路に書き換え
5. `CHANGES.md` に `[ADD]` エントリを追加
6. PR を出して CI で動作検証 (ローカル macOS では実機検証不可なため、 PR 上で debug する)

## 関連

- 0017 (closed): aarch64-linux cross-compile を multistrap 経路で復活させようとして閉じられた issue。 本 issue は sysroot.py 経路での再挑戦
- 0019 (closed): aarch64-linux cross-compile を multistrap 経路で進めようとして閉じられた issue
- 0020 (closed): jetson / RPi platform 対応を multistrap 経路で進めようとして閉じられた issue
- 0024 (closed): sysroot.py 新設の親 issue。 本 issue で行うこと / 行わないことの境界が明示されている
- 0027 (open): cmake `_sora_fetch_rootfs` の dry-run 検証。 本 issue が green になれば 0027 は不要になる可能性あり
- 0025 / 0026 / 0028 / 0029 (open): sysroot.py 周辺の test / lint / doc / refactor。 本 issue とは独立して進められる
- 0022 (open): `run.py` / `buildbase.py` / `MANIFEST.in` / `build_ubuntu_arm` job の削除。 本 issue とは独立。 順序依存なし
