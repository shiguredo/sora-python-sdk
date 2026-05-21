# CI 全面切替とレガシーファイル削除

- Priority: Medium
- Created: 2026-05-21
- Model: Composer 2.5
- Branch: feature/change-ci-and-remove-legacy-build

## 目的

0001 〜 0005 で scikit-build-core 移行が完了した後、CI を `uv build --wheel` ベースに完全統一し、レガシービルドファイル（`buildbase.py` / `run.py` / `pypath.py` / `MANIFEST.in` / `DEPS`）を削除する。あわせて PyPI publish 向け manylinux 化（`auditwheel repair --strip --only-plat`）を導入し、`CHANGES.md` の整合性を取る。

## 優先度根拠

Medium。機能移行自体は 0001 〜 0005 で完了する。0006 はクリーンアップと CI 統合であり、0005 完了後に実施可能。0001 で disable した CI job を 0003 / 0004 / 0005 で順次再有効化済みのため、0006 では「全 job が新経路で動く」状態を確認しつつ legacy ファイルを削除する。

## スコープ

含む:

- `.github/workflows/build.yml` を全面整理:
  - `build_pyi` job を **削除**（0001 で `if: false` 済み、本 issue で job 自体を削除）
  - `build_ubuntu` matrix から `ubuntu-22.04_x86_64` を再有効化する（0005 / 0006 で扱う宣言があった残件）
  - 全 platform job で `uv run python run.py build ...` ステップが既に削除されている前提を確認し、残っていれば削除する
  - 各 platform job 末尾に `wheel tags --remove --platform-tag <tag>` または `auditwheel repair --strip --only-plat -w wheelhouse/ dist/*.whl` を追加してタグ強制 / manylinux 化を行う（macOS / Windows は manylinux 概念がないため `wheel tags` のみ、Linux は `auditwheel repair`）
- `.github/workflows/build-debug.yml` も同様に `run.py` 経路を削除
- レガシーファイル削除:
  - `buildbase.py`
  - `run.py`（`format` サブコマンドの代替は 0007 で `Makefile` に移行済み前提）
  - `pypath.py`
  - `MANIFEST.in`
  - `DEPS`
- `CHANGES.md` の整理:
  - 既存 `## develop` セクション内の `[UPDATE] CMAKE_VERSION を 4.3.2 に上げる` エントリを削除（0001 で `[tool.scikit-build.cmake] version` 経由 PyPI 取得に切り替わったため意味を失う。0001 でも削除指示したが、Sora C++ SDK バージョンアップエントリのサブ箇条書きとして残っている場合はそこも削除）
  - 0001 で追加した `[CHANGE] build backend を setuptools から scikit-build-core に切り替える` エントリのサブ箇条書きを 0005 で更新済みの内容で確定
  - `[CHANGE] レガシービルドファイル (`run.py` / `buildbase.py` / `pypath.py` / `MANIFEST.in` / `DEPS`) を削除する` エントリを 0001 `[CHANGE]` の直後に追加
- PyPI publish 経路の動作確認:
  - `publish_wheel` / `create-release` job を有効化（0001 で `if: false` していた場合）
  - tag push 時の release flow が全 platform で動くことを confirm
- `_build` / `_deps` を `actions/cache` キャッシュ対象にする（既存に同様の cache step があれば確認、無ければ新規追加。cache key は `deps.json` + `CMakeLists.txt` + `SORA_PYTHON_SDK_PLATFORM`）
- `.github/actions/download-whl` などの再利用 action が新 wheel ファイル名規約と整合するか確認し、必要なら修正

含まない（別 issue で扱う）:

- `Makefile` 追加（0007）
- `pytest tests/` の E2E マーカー再設計（別 issue）
- `tests/conftest.py` の `import jwt` 依存解消（別 issue）
- `auditwheel show` 等での実シンボル深検証（別 issue。0006 では `auditwheel repair --strip` が成功することのみ確認）

## 依存 issue への影響（事実記述）

- 0001 〜 0005 完了状態を前提とする
- 0007 完了状態（`Makefile` で `format` / `develop` 等が提供される）を前提とする（`run.py format` を削除するため）
- `tests/conftest.py:8` の `import jwt` 依存は本 issue では触らない。0001 完了時点で `uv sync` 経由で `pyjwt` が dev グループに入っているため pytest collect は通る

## 現状

- 0001 完了時点で `build_pyi` job は `if: false`、各 platform job の `needs: [build_pyi]` 削除と `build_pyi` artifact ダウンロード step 削除が済んでいる
- 0003 / 0004 / 0005 完了時点で `build_ubuntu` matrix の armv8 / jetson / RPi、`build_macos`、`build_windows` が再有効化済み
- 0002 で追加された `verify_macos_fetch_deps` job は 0005 完了時に削除済み
- `MANIFEST.in` は setuptools 専用のため scikit-build-core 移行（0001）時点で読まれなくなっているが、ファイル自体は残っている
- `DEPS` は 0001 で `deps.json` に内容移行済みだが、ファイル自体は残っている
- `run.py format` は 0007 で `Makefile` の `make format` に移行済み前提
- `run.py build` は 0001 〜 0005 で `uv build --wheel` 経路に置換済み（CI / 開発者ともに `run.py build` を呼ばない）
- `publish_wheel` / `create-release` は 0001 で `needs:` 経由 skip 状態の可能性あり（0005 で `build_macos` / `build_windows` 再有効化で復活しているはず）

## 設計方針

### CI workflow 整理

- `.github/workflows/build.yml`
  - `build_pyi` job を完全削除（0001 で `if: false` 済み）
  - `build_ubuntu` matrix の `exclude:` を空にし（または exclude 自体を削除）、`ubuntu-22.04_x86_64` / `ubuntu-24.04_x86_64` / `ubuntu-22.04_armv8` / `ubuntu-24.04_armv8` / `ubuntu-22.04_armv8_jetson` / `raspberry-pi-os_armv8` の全 6 entry が回るようにする
  - 各 platform job の step は次の構造に統一:

    ```yaml
    - uses: actions/checkout@<sha>
    - uses: actions/setup-python@<sha>
      with:
        python-version: ${{ matrix.python_version }}
    - uses: astral-sh/setup-uv@<sha>
    # platform 固有依存 (Linux armv8: multistrap, macOS: 不要, Windows: 不要)
    - if: contains(matrix.platform.target, 'armv8')
      run: sudo apt-get -y install multistrap binutils-aarch64-linux-gnu
    # RPi のみ pyproject.toml の name 書き換え
    - if: matrix.platform.target == 'raspberry-pi-os_armv8'
      run: sed -i 's/^name = "sora_sdk"/name = "sora_sdk_rpi"/' pyproject.toml
    - run: uv build --wheel
      env:
        SORA_SDK_TARGET: ${{ matrix.platform.target }}
        # macOS / Linux クロス: _PYTHON_HOST_PLATFORM
        # macOS: MACOSX_DEPLOYMENT_TARGET も追加
    # wheel タグ post-process (target ごとに分岐)
    - run: |
        case "${{ matrix.platform.target }}" in
          ubuntu-*_x86_64|ubuntu-*_armv8|*_armv8_jetson|raspberry-pi-os_armv8)
            uvx auditwheel repair --strip -w wheelhouse/ dist/*.whl
            mv wheelhouse/* dist/
            ;;
          macos_arm64)
            uv tool run wheel tags --remove --platform-tag "macosx_${OSX_VER}_arm64" dist/*.whl
            ;;
          windows_x86_64)
            : # scikit-build-core デフォルトで win_amd64 になるため post-process 不要
            ;;
        esac
    - uses: actions/upload-artifact@<sha>
      with: ...
    ```

  - `auditwheel repair --strip` は `--only-plat` を付けると wheel タグの platform 部のみ変更（manylinux 互換マークを付けない）になり、付けないと auditwheel 標準の manylinux 検出が走る。0006 では `--only-plat` 付き運用（webcodecs-py と同方針）
  - manylinux タグ番号は target ごとに固定（22.04_x86_64 → `manylinux_2_31_x86_64`、24.04_x86_64 → `manylinux_2_35_x86_64`、22.04_armv8 → `manylinux_2_31_aarch64`、24.04_armv8 → `manylinux_2_35_aarch64`、jetson → `manylinux_2_17_aarch64.manylinux2014_aarch64`、RPi → `manylinux_2_35_aarch64`）
  - `auditwheel repair --plat <tag>` で明示する形になる（`--only-plat` と `--plat <tag>` の併用）
- `.github/workflows/build-debug.yml` も同様に整理。`uv run python run.py build` step を削除し `uv build --wheel` のみに

### レガシーファイル削除

- 以下を `git rm` で削除:
  - `buildbase.py`
  - `run.py`
  - `pypath.py`
  - `MANIFEST.in`
  - `DEPS`
- 削除前に各ファイルへの参照を `git grep -nE 'buildbase|run\\.py|pypath|MANIFEST|DEPS'` で確認し、`.github/workflows/`、`tests/`、`pyproject.toml`、`Makefile`（0007 で追加）、`README.md` 等で参照が残っていれば事前修正
- `buildbase.py` は外部リポジトリ（melpon/buildbase）からのコピーで、0001 〜 0005 で完全に置き換えられているため削除して問題ない
- `pypath.py` は scikit-build-core が `find_package(Python)` で同等機能を提供するため不要

### `CHANGES.md` 整理

- `## develop` セクションの編集:
  - `[UPDATE] CMAKE_VERSION を 4.3.2 に上げる`（既存。Sora C++ SDK バージョンアップエントリのサブ箇条書きとして存在）を削除
  - 0001 で追加した `[CHANGE] build backend を setuptools から scikit-build-core に切り替える` エントリを以下に書き換え（0001 / 0005 / 0006 の変更を統合）:

    ```
    - [CHANGE] build backend を setuptools から scikit-build-core に切り替える
      - 全 platform (ubuntu / macOS / Windows / armv8 cross / jetson / RPi) で `uv build --wheel` 一発による wheel 生成を実現する
      - レガシービルドファイル (`run.py` / `buildbase.py` / `pypath.py` / `MANIFEST.in` / `DEPS`) を削除する
      - WebRTC / Sora C++ SDK / Boost / OpenH264 / libwebrtc 同梱 clang の取得を CMake configure 内で完結させる
      - PyPI publish 用 wheel タグは `auditwheel repair --strip --only-plat` または `wheel tags` で post-process する
      - @voluntas
    ```

  - 既存の他エントリ（`Sora C++ SDK のバージョンを 2026.2.0-canary.11 に上げる` 等）は機能と無関係なため変更しない

### `_build` / `_deps` のキャッシュ

- `_build` は `wheel_tag` 別ディレクトリで Python バージョン別。`_deps` は `SORA_PYTHON_SDK_PLATFORM` 別と `_deps/llvm/<host_key>` 別
- `actions/cache` で `key:` を `${{ runner.os }}-${{ matrix.platform.target }}-${{ matrix.python_version }}-${{ hashFiles('deps.json', 'CMakeLists.txt', 'cmake/scripts/*.cmake') }}` のように設定し、`path:` を `_deps`、`_build` の両方にする
- ただしキャッシュサイズが GB 単位になるため GitHub Actions のキャッシュ上限（10GB / repo）を超えないかは実装時に確認
- キャッシュ無効化条件: `deps.json` / `CMakeLists.txt` / `cmake/scripts/*.cmake` 変更時、または手動 `actions/cache` clear

### PyPI publish 経路の動作確認

- `publish_wheel` matrix が全 platform を含むことを確認
- `create-release` job が `needs: [build_ubuntu, build_ubuntu_arm, build_macos, build_windows]` で全 build job 完了を待つ設計を維持
- tag push (`refs/tags/2026.*`) 時の動作確認は 0006 PR では実環境テストできないため、merge 後の次回 tag push で実 publish 動作を確認する（README に「0006 merge 後の最初の tag push でも実 publish を慎重に確認する」を申し送り）

### `.github/actions/download-whl` の整合

- 新 wheel ファイル名規約（例: `sora_sdk-<version>-cp3XY-cp3XY-manylinux_2_35_x86_64.whl`）が既存 download action の glob pattern と一致するか確認
- 不一致なら action.yml の inputs / glob を更新

## 完了条件

- `.github/workflows/build.yml` から `build_pyi` job が消える
- `run.py` / `buildbase.py` / `pypath.py` / `MANIFEST.in` / `DEPS` がリポジトリから削除される
- `build_ubuntu` matrix の全 6 entry × Python 3.12 / 3.13 / 3.14（jetson は 3.10）= 17 entry（22.04_x86_64 / 24.04_x86_64 / 22.04_armv8 / 24.04_armv8 / RPi × 3 Python ＋ jetson × 1 Python）が green
- `build_macos` / `build_windows` 全 entry が green
- `build-debug.yml` も同様に動く
- PyPI publish 用に各 wheel が正しい manylinux タグ / macosx タグ / win_amd64 タグを持つ
- `CHANGES.md` の `## develop` セクションに 0006 までの変更が統合された `[CHANGE]` エントリが残り、`[UPDATE] CMAKE_VERSION を 4.3.2 に上げる` 等のレガシーエントリが削除されている
- `_build` / `_deps` の actions/cache が動き、2 回目以降の CI run で deps 取得が cache hit する
- `tests/test_version.py` のみが pytest で通る状態は 0001 から継続（E2E マーカー再設計は別 issue）

## 解決方法

- `.github/workflows/build.yml`
  - `build_pyi` job 全体を削除
  - `build_ubuntu` matrix の `exclude:` 削除または空化
  - 各 platform job の step を「`uv build --wheel` + 必要に応じて `auditwheel repair` or `wheel tags`」の 2 段構造に統一
  - `actions/cache` step を追加（`_deps` / `_build` 対象、key は `deps.json` + `CMakeLists.txt` + `cmake/scripts/*` の hash）
  - `actions/upload-artifact` の wheel ファイル名 glob を新規約に合わせる
- `.github/workflows/build-debug.yml`
  - 同様に `run.py` 経路削除、`uv build --wheel` 集約、`BUILD_PROFILE=debug` env
- `.github/actions/download-whl/action.yml` を確認し、新 wheel ファイル名規約に合わせて glob を更新
- 以下を `git rm`:
  - `buildbase.py`
  - `run.py`
  - `pypath.py`
  - `MANIFEST.in`
  - `DEPS`
- 削除前に `git grep -nE 'from buildbase|from run|from pypath|import buildbase|import run\\.|import pypath|MANIFEST|^DEPS=' -- ':!issues' ':!CHANGES.md'` で参照確認
- `CHANGES.md`
  - `## develop` セクションの `[UPDATE] CMAKE_VERSION を 4.3.2 に上げる` を削除
  - 0001 `[CHANGE]` エントリのサブ箇条書きを上記設計方針の内容に書き換え
- `tests/` 変更なし
- 1 ステップ目に実装する検証: `auditwheel repair --strip --only-plat --plat manylinux_2_35_x86_64 dist/sora_sdk-*-cp312-cp312-linux_x86_64.whl` をローカル ubuntu-24.04 ホストで実行し、出力 wheel が `cp312-cp312-manylinux_2_35_x86_64` ファイル名で正しく生成されることを確認する
