# レガシーファイル削除と CI 最終整理

- Priority: Medium
- Created: 2026-05-21
- Model: Composer 2.5
- Branch: feature/change-ci-and-remove-legacy-build

## 目的

0016 〜 0021 で scikit-build-core 移行が完了した後、 CI を `uv build --wheel` ベースに完全統一し、 レガシービルドファイル（ `buildbase.py` / `run.py` / `pypath.py` / `MANIFEST.in` / `DEPS` ）を削除する。 あわせて PyPI publish 向け manylinux 化（ `auditwheel repair --strip --only-plat` ）と依存アーカイブの sha256 検証を導入し、 `CHANGES.md` の整合性を取る。

## 設計の前提（プロジェクト全体の新方針からの該当部）

- ビルド環境は ubuntu-24.04 x86_64 host のみ
- Linux arm64 は cross-compile only （ 0019 / 0020 ）。 arm64 native runner は **廃止** （ `build_ubuntu_arm` を完全削除）
- macOS / Windows はそれぞれ native build （ 0018 / 0021 ）

## スコープ

含む:

- レガシーファイル削除:
  - `buildbase.py`
  - `run.py` （ `format` サブコマンドの代替は 0023 で `Makefile` に移行済み前提）
  - `pypath.py`
  - `MANIFEST.in`
  - `DEPS` （内容は 0016 で `deps.json` に移行済み）
- `.github/workflows/build.yml` の全面整理:
  - `build_pyi` job を **完全削除** （ 0016 で `if: false` 済み）
  - `build_ubuntu_arm` job を **完全削除** （新方針で廃止。 0016 で `if: false` 済み）
  - `build_ubuntu` matrix から `ubuntu-22.04_x86_64` 系を再有効化するかどうかは「現状」セクション参照（ 0016 / 0019 / 0020 / 0021 完了時点で `ubuntu-24.04_x86_64` / `ubuntu-22.04_armv8` / `ubuntu-24.04_armv8` / `ubuntu-22.04_armv8_jetson` / `raspberry-pi-os_armv8` が動く前提）
  - 全 platform job で `uv run python run.py build ...` step が既に削除されている前提を確認し、残っていれば削除する
  - `e2e_test` job の `if: false` を解除し、 `./.github/workflows/e2e-test.yml` 側の hardcode artifact 名を 0016 〜 0021 で確定した artifact 名と整合させる
  - 各 platform job 末尾に manylinux 化ステップを追加:
    - Linux (x86_64 / armv8 / jetson / rpi): `auditwheel repair --strip --only-plat -w wheelhouse/ dist/*.whl` → repaired wheel を artifact 化
    - macOS / Windows: manylinux 概念がないため `auditwheel` は呼ばない。 0016 / 0018 / 0021 のデフォルト wheel タグをそのまま使う
  - `slack_notify` job の `needs:` を `[build_ubuntu, build_macos, build_windows]` で確定する（ `build_ubuntu_arm` は削除済み）
  - `publish_wheel` / `create-release` job を有効化し、 matrix から `ubuntu-22.04_x86_64` 等の disable 対象を削除する。 jetson / RPi entry の publish 経路を確認
- `.github/workflows/build-debug.yml` も同様に `run.py` 経路を削除し、 全 platform で `BUILD_PROFILE=debug uv build --wheel` ベースに統一する
- 依存アーカイブの sha256 検証導入:
  - `deps.json` の各 dep entry に `sha256` フィールドを追加（ optional 。 存在すれば検証、 無ければ skip ）
  - `_sora_fetch_archive` で download 後に `file(SHA256 ...)` で検証し、 不一致なら FATAL_ERROR で停止
  - 0016 〜 0021 で取得したアーカイブの sha256 を実機で計算して `deps.json` に書き込む（ 0022 PR 内で 1 回実施）
- `CHANGES.md` の整理:
  - 既存 `## develop` の `[UPDATE] CMAKE_VERSION を 4.3.2 に上げる` エントリを削除（ 0016 で `[tool.scikit-build.cmake] version` 経由 PyPI 取得に切替済みのため）
  - 既存 `[UPDATE] setuptools を ~=82.0 に上げる` / `[UPDATE] wheel を ~=0.46 に上げる` エントリを削除（ `[build-system] requires` から setuptools / wheel が完全に消えるため）
  - `[CHANGE] レガシービルドファイル (run.py / buildbase.py / pypath.py / MANIFEST.in / DEPS) を削除する` を `[CHANGE]` グループに追加
  - `[CHANGE] arm64 native CI runner (build_ubuntu_arm job) を廃止し、 ubuntu-24.04 x86_64 host からのクロスコンパイル経路に統一する` を `[CHANGE]` グループに追加
  - `[ADD] 依存アーカイブの sha256 検証を導入する` を `[ADD]` グループに追加
  - `[ADD] Linux wheel に auditwheel repair による manylinux タグ付与を導入する` を `[ADD]` グループに追加
- `_build` / `_deps` の `actions/cache` キャッシュ対象化:
  - cache key は `${{ hashFiles('deps.json', 'cmake/scripts/fetch_deps.cmake') }}-${{ matrix.platform.target }}-${{ matrix.python_version }}`
  - LLVM は host 単位で共有するため別 cache key で扱う

含まない（別 issue で扱う）:

- `Makefile` 追加（ 0023 ）
- `pytest tests/` の E2E マーカー再設計（別 issue ）
- `tests/conftest.py` の `import jwt` 依存解消（別 issue ）
- `auditwheel show` での実シンボル深検証（別 issue 。 0022 では `auditwheel repair --strip` が成功することのみ確認）

## 現状

0016 〜 0021 完了時点で:

- `pyproject.toml` の build backend は `scikit_build_core.build`
- `cmake/scripts/fetch_deps.cmake` が WebRTC / Sora / Boost / OpenH264 / LLVM 全てを取得する
- `build_pyi` / `build_ubuntu_arm` / `build_macos` / `build_windows` / `e2e_test` の各 job:
  - `build_pyi`: 0016 で `if: false`
  - `build_ubuntu_arm`: 0016 で `if: false` （ 0022 で削除）
  - `build_macos`: 0018 で復活済み
  - `build_windows`: 0021 で復活済み
  - `e2e_test`: 0016 で `if: false`
- `build_ubuntu` matrix:
  - 0016: `ubuntu-24.04_x86_64` のみ
  - 0019: `ubuntu-22.04_armv8` / `ubuntu-24.04_armv8` 追加
  - 0020: `ubuntu-22.04_armv8_jetson` / `raspberry-pi-os_armv8` 追加
  - 0022: `ubuntu-22.04_x86_64` の扱いを確定（含めるか、 publish 対象から外すか）
- `setup.py` は 0016 で削除済み
- `run.py` / `buildbase.py` / `pypath.py` / `MANIFEST.in` / `DEPS` は残っているが scikit-build-core 経路では参照されていない
- `slack_notify` job の `needs:` は 0016 / 0018 / 0021 で `[build_ubuntu, build_macos, build_windows]` に確定済み
- `publish_wheel` / `create-release` は 0016 期間中タグを打たない運用で停止していた

## 設計方針

### レガシーファイル削除順序

1. `buildbase.py` / `pypath.py` / `MANIFEST.in` / `DEPS` を `git rm`
2. `run.py` を `git rm` （ 0023 で `Makefile` に移行済みの `format` 機能を含めて完全削除）
3. `git grep -r "buildbase\|pypath\|MANIFEST\.in\|run\.py build"` で残存参照を確認
4. CHANGES.md にエントリ追加

`run.py` の `format` サブコマンドは 0023 で `make format` に移行する。 0022 着手前に 0023 が完了している前提（依存関係上は 0023 → 0022 ）。 もし順序を逆にする場合は `run.py format` を一時的に残して 0023 で削除する。

### auditwheel repair の導入

各 Linux platform job 末尾に追加:

```yaml
- name: Audit wheel (Linux only)
  if: ${{ runner.os == 'Linux' }}
  run: |
    uv pip install auditwheel
    mkdir -p wheelhouse
    for whl in dist/*.whl; do
      uv run auditwheel repair --strip --only-plat -w wheelhouse/ "${whl}"
    done
    # 元の wheel を repaired で置き換える
    rm dist/*.whl
    mv wheelhouse/*.whl dist/
- name: Upload Artifact
  uses: actions/upload-artifact@...
  with:
    name: ${{ matrix.platform.name }}_python-${{ matrix.python_version }}
    path: "dist/"
```

manylinux タグの正解値（実シンボル検証）は 0022 では行わない。 `auditwheel repair --only-plat` で必要な platform tag が自動的に決まる。 既存 `setup.py` で hardcode していたタグと一致しない場合は実体（ glibc バージョン）優先で確定する。

### sha256 検証

`deps.json` の各 entry に sha256 フィールドを追加:

```json
{
  "webrtc": {
    "version": "m149.7827.0.0",
    "url_template": "https://github.com/shiguredo-webrtc-build/webrtc-build/releases/download/{version}/webrtc.{platform}.{ext}",
    "strip_components": 1,
    "sha256": {
      "ubuntu-24.04_x86_64": "...",
      "ubuntu-22.04_armv8": "...",
      "ubuntu-24.04_armv8": "...",
      "macos_arm64": "...",
      "windows_x86_64": "..."
    }
  }
}
```

platform ごとの sha256 を別 hash で持つ（同じバージョンでも platform が違えば異なるアーカイブのため）。

`fetch_deps.cmake` の `_sora_fetch_archive` を以下のように拡張:

```cmake
function(_sora_fetch_archive name url stamp_path dest_dir strip_components)
  cmake_parse_arguments(_arg "" "SHA256" "" ${ARGN})
  # ... download ...
  if(_arg_SHA256)
    file(SHA256 "${_archive}" _actual_sha256)
    if(NOT _actual_sha256 STREQUAL "${_arg_SHA256}")
      file(REMOVE "${_archive}")
      message(FATAL_ERROR
        "SHA256 mismatch for ${name}. "
        "Expected: ${_arg_SHA256}. "
        "Actual:   ${_actual_sha256}.")
    endif()
  endif()
  # ... extract ...
endfunction()
```

メインスクリプトで platform ごとに sha256 を `string(JSON GET)` で取り出して渡す。 sha256 が無い entry は検証 skip （既存 0016 〜 0021 移行期間との後方互換用）。

### actions/cache 導入

各 platform job の `uv build --wheel` 前に:

```yaml
- name: Cache deps
  uses: actions/cache@...
  with:
    path: |
      _deps
    key: deps-${{ matrix.platform.target }}-${{ hashFiles('deps.json', 'cmake/scripts/fetch_deps.cmake') }}
    restore-keys: |
      deps-${{ matrix.platform.target }}-
- name: Cache LLVM
  uses: actions/cache@...
  with:
    path: |
      _deps/llvm
    key: llvm-${{ runner.os }}-${{ hashFiles('deps.json') }}
```

LLVM は host 単位で共有するため `runner.os` を key に含める。 platform は不要。

## 完了条件

- レガシーファイル削除後、 `git grep -r "buildbase\|pypath\|MANIFEST\.in\|run\.py"` で残存参照が無い
- `.github/workflows/build.yml` の `build_pyi` / `build_ubuntu_arm` job が存在しない
- `build_ubuntu` / `build_macos` / `build_windows` 全 entry が green
- `e2e_test` job が green （ matrix 内 disable 対象 platform が無い状態）
- Linux wheel の platform tag が `auditwheel repair --only-plat` で確定する manylinux タグ（実機 glibc 互換）になる
- `deps.json` の各 entry の sha256 検証が動く（手動で sha256 を書き換えて FATAL_ERROR が出ることを確認）
- `actions/cache` が hit して 2 回目以降のビルドで `_deps/` が DL されない
- `publish_wheel` / `create-release` を tag push で 1 回試して全 platform wheel が PyPI に publish される
- `slack_notify` job が green （ `needs: [build_ubuntu, build_macos, build_windows]` ）

## 解決方法

### git rm

```bash
git rm buildbase.py run.py pypath.py MANIFEST.in DEPS
```

### .github/workflows/build.yml

- `build_pyi` job 全体を削除
- `build_ubuntu_arm` job 全体を削除
- `e2e_test.if: false` を削除し、 hardcode artifact 名を 0016 〜 0021 で確定した名前に合わせる
- 各 Linux platform job 末尾に `auditwheel repair` step を追加
- `actions/cache` step を追加（ deps + LLVM の 2 種）
- `publish_wheel` / `create-release` の matrix から `ubuntu-22.04_x86_64` 等の disable 対象を削除し、 jetson / RPi entry の publish 経路を確認

### .github/workflows/build-debug.yml

`run.py` 経路を削除して `BUILD_PROFILE=debug uv build --wheel` ベースに統一する。

### deps.json

各 entry に sha256 フィールド追加。 0022 PR 内で実機 `curl -sL <url> | sha256sum` で計算する。

### cmake/scripts/fetch_deps.cmake

- `_sora_fetch_archive` に `SHA256` キーワード引数追加
- メインスクリプトで platform ごとに sha256 を取り出して渡す

### CHANGES.md

`## develop` セクション内のエントリを以下のように整理する:

```
## develop

- [CHANGE] build backend を setuptools から scikit-build-core に切り替える
  - @voluntas
- [CHANGE] macOS arm64 ネイティブビルドを scikit-build-core 経路に移行する
  - @voluntas
- [CHANGE] Linux arm64 wheel を ubuntu-24.04 x86_64 host からのクロスコンパイルで生成するように切り替える
  - @voluntas
- [CHANGE] Jetson / Raspberry Pi OS wheel を ubuntu-24.04 x86_64 host からのクロスコンパイルで生成するように切り替える
  - @voluntas
- [CHANGE] Windows x86_64 ネイティブビルドを scikit-build-core 経路に移行する
  - @voluntas
- [CHANGE] レガシービルドファイル (run.py / buildbase.py / pypath.py / MANIFEST.in / DEPS) を削除する
  - @voluntas
- [CHANGE] arm64 native CI runner (build_ubuntu_arm job) を廃止し、 ubuntu-24.04 x86_64 host からのクロスコンパイル経路に統一する
  - @voluntas
- [ADD] 依存アーカイブの sha256 検証を導入する
  - @voluntas
- [ADD] Linux wheel に auditwheel repair による manylinux タグ付与を導入する
  - @voluntas
```

既存 `[UPDATE] setuptools` / `[UPDATE] wheel` / `[UPDATE] CMAKE_VERSION` エントリは削除する。

## ロールバック

0022 マージ後に CI が大きく壊れた場合:

1. `git revert -m 1 <merge-commit>` で revert PR を作成
2. revert 後、 削除した legacy ファイルが復元されるか確認
3. `build_pyi` / `build_ubuntu_arm` job も復元されるが、 0016 〜 0021 で完了した scikit-build-core 経路と並存することになる
4. forward fix を選ぶ判断: `auditwheel repair` の単一不具合 / sha256 検証の不具合 / actions/cache の単一不具合なら追加コミットで対応する
