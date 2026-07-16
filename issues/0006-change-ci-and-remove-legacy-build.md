# レガシーファイル削除と CI 最終整理

- Priority: Medium
- Created: 2026-05-21
- Updated: 2026-07-17
- Model: Composer 2.5
- Branch: feature/change-ci-and-remove-legacy-build

## 目的

0001 〜 0005 で scikit-build-core 移行が完了した後、 CI を `uv build --wheel` ベースで最終整理する。 具体的には、 0001 で削除された `e2e_test` / `publish_wheel` / `create-release` job と build-debug.yml 相当のワークフローを scikit-build-core 前提で再構築し、 PyPI publish 向け manylinux 化（ `auditwheel repair --strip --only-plat` ）と依存アーカイブの sha256 検証を導入する。 レガシービルドファイル（ `run.py` / `buildbase.py` / `pypath.py` / `setup.py` / `MANIFEST.in` ）の削除は 0001 で完了しているため本 issue では扱わない。

## 設計の前提（プロジェクト全体の新方針からの該当部）

- ビルド環境は ubuntu-24.04 x86_64 host のみ
- Linux arm64 は cross-compile only （ 0003 / 0004 ）。 arm64 native runner でのビルドは **廃止** （ `build_ubuntu_arm` job は 0001 で削除済み。 ただし E2E テストの実行 runner としての arm64 native runner は e2e-test.yml に残る）
- macOS / Windows はそれぞれ native build （ 0002 / 0005 ）
- バージョン管理ファイルは `DEPS` （ KEY=value 形式）。 0001 で fetch_deps.cmake の単一情報源になったため **削除しない** （旧計画の deps.json 移行は廃止された）。 sha256 検証の値も `DEPS` に載せる

## スコープ

含む:

- e2e テストの復活:
  - `.github/workflows/build.yml` に `e2e_test` job を新設する（ `uses: ./.github/workflows/e2e-test.yml` + `with: from_build: true` + `secrets: inherit` 。 0001 で旧 job は削除済み）
  - build.yml の workflow env （ `TEST_SIGNALING_URLS` / `TEST_CHANNEL_ID_PREFIX` / `TEST_SECRET_KEY` / `TEST_API_URL` / `OPENH264_VERSION` 。 0001 で削除済み）のうち e2e に必要なものを再導入する
  - `.github/workflows/e2e-test.yml` の全 job から `if: false` を外す
  - e2e-test.yml の matrix が参照する artifact 名（ `${{ matrix.platform.wheel_platform }}_python-${{ matrix.python_version }}` ）を 0001 〜 0005 の upload-artifact 名と整合させる。 `ubuntu-22.04_x86_64` entry の扱いは「 `ubuntu-22.04_x86_64` の扱い確定」とあわせて判断する
- `publish_wheel` / `create-release` job の再構築（ 0001 で両 job と `.github/actions/download` composite は削除済みのため新設）:
  - matrix は 0001 〜 0005 完了後に実際にビルドされる platform 一覧からゼロから設計する（ jetson は Python 3.10 固定で python_version 軸に乗らない点に注意。 0043 の帰結に依存）
  - `create-release` の artifact 取得方式を再設計する（旧 composite 相当を作り直すか、 `download-artifact` の pattern 指定でまとめるか）
  - sdist の扱いを設計する（ 0001 で sdist は凍結中。 sdist 専用 job 化の論点は 0051 、 publish 対象 ubuntu 系列の論点は 0066 、 publish の e2e ゲートの論点は 0067 を取り込む）
- `build_ubuntu` matrix への `ubuntu-22.04_x86_64` entry 追加の要否を確定する（含めるか、 publish 対象から外すか。 e2e-test.yml の同 entry と連動）
- build-debug 相当ワークフローの再設計・新設（ 0001 で build-debug.yml はファイルごと削除済み）:
  - ローカル webrtc-build / sora-cpp-sdk をソースビルドし、 `-DSORA_DIR` / `-DWEBRTC_INCLUDE_DIR` / `-DWEBRTC_LIBRARY_DIR` の手動指定 + `-Ccmake.build-type=Debug` で `uv build --wheel` する経路
  - バージョン文字列の debug 区別（旧 `BUILD_PROFILE=debug` の `+debug` 連結相当）の要否もここで判断する（ 0001 では導入しないと確定済み）
- 各 Linux platform job 末尾に manylinux 化ステップを追加:
  - Linux (x86_64 / armv8 / jetson / rpi): `auditwheel repair --strip --only-plat -w wheelhouse/ dist/*.whl` → repaired wheel を artifact 化
  - macOS / Windows: manylinux 概念がないため `auditwheel` は呼ばない。 0001 / 0002 / 0005 のデフォルト wheel タグをそのまま使う
  - クロス wheel （ armv8 / jetson / rpi ）は pytest を実行できないため、 `auditwheel repair` の成功と `auditwheel show` による manylinux 適合確認をもって検証とする（ 0003 / 0004 からの委譲）
- 依存アーカイブの sha256 検証導入:
  - `DEPS` に platform 別の sha256 キーを追加する（ KEY=value 形式を維持し `source DEPS` 互換を保つ。 キー命名規則（例: `WEBRTC_SHA256_<platform>` ）は実装時に確定。 同じバージョンでも platform が違えばアーカイブが異なるため platform 別に持つ）
  - `_sora_fetch_archive` の `SHA256` キーワード引数（受け口は 0001 で実装済み）に検証ロジックを実装する: download 後に `file(SHA256 ...)` で検証し、 不一致なら FATAL_ERROR で停止。 sha256 キーが無い依存は検証 skip
  - 0001 〜 0005 で取得したアーカイブの sha256 を実機で計算して `DEPS` に書き込む（ 0006 PR 内で 1 回実施）
- `slack_notify` job の `needs:` を `[build_ubuntu, build_macos, build_windows]` で確定する
- `_deps` の `actions/cache` キャッシュ対象化:
  - cache key は `${{ hashFiles('DEPS', 'cmake/scripts/fetch_deps.cmake') }}-${{ matrix.platform.target }}`（ rootfs を含む platform では `multistrap/*.conf` を key に含めるか実装時に判断）
  - LLVM は host 単位で共有するため別 cache key で扱う
- `.gitignore` の整理: `/_install` / `/_source` / `/_package` の残骸エントリを削除する（ 0001 から委譲。 `/_build` は scikit-build-core の build-dir として現役のため維持）
- クロス wheel への pyi / py.typed 同梱経路の整理（ 0003 / 0004 から委譲。 クロスは `SORA_GEN_PYI=OFF` のため同梱されない。 native 生成物を流用して同梱するかどうかを判断し、 同梱する場合の経路を設計する）
- `CHANGES.md` への本 issue 分のエントリ追加（後述）

含まない（別 issue で扱う）:

- レガシーファイル削除（ 0001 で完了済み。 `DEPS` は単一情報源として維持するため削除しない）
- `Makefile` 追加（ 0007 ）
- `pytest tests/` の E2E マーカー再設計（別 issue ）
- `tests/conftest.py` の `import jwt` 依存解消（別 issue ）
- `auditwheel show` の出力を使った実シンボルの深掘り検証（別 issue 。 0006 では `auditwheel repair --strip` の成功と show による manylinux 適合確認まで）
- e2e-test.yml の python_version 拡充（現状 3.13 のみ有効。 0053 で扱う）

## 現状

0001 〜 0005 完了時点で:

- `pyproject.toml` の build backend は `scikit_build_core.build`
- `cmake/scripts/fetch_deps.cmake` が WebRTC / Sora / Boost / OpenH264 / LLVM 全てを取得する。 バージョンは `DEPS` （ 4 キーの KEY=value ）から読む
- build.yml の job 構成:
  - `get_sdk_version` / `build_ubuntu` / `build_macos` （ 0002 で新設） / `build_windows` （ 0005 で新設） / `slack_notify`
  - `build_pyi` / `build_ubuntu_arm` / `e2e_test` / `publish_wheel` / `create-release` は 0001 で削除され存在しない。 `.github/actions/download` composite も存在しない
- `build_ubuntu` matrix:
  - 0001: `ubuntu-24.04_x86_64` のみ
  - 0003: `ubuntu-22.04_armv8` / `ubuntu-24.04_armv8` 追加
  - 0004: `ubuntu-22.04_armv8_jetson` / `raspberry-pi-os_armv8` 追加
  - 0006: `ubuntu-22.04_x86_64` の扱いを確定（含めるか、 publish 対象から外すか）
- build-debug.yml は 0001 で削除され存在しない
- e2e-test.yml はファイルとして残り、 全 job に `if: false` が付いている（ 0001 ）。 schedule トリガは 12032d2 で既にコメントアウト済み。 artifact 名は `${{ matrix.platform.wheel_platform }}_python-${{ matrix.python_version }}` 参照で、 python_version は 3.13 のみ有効（ 0053 ）、 `amd-amf_x86_64` entry はコメントアウト中。 armv8 の E2E は arm64 native runner （ `ubuntu-24.04-arm` 等）で実行される（ビルドの native runner 廃止とは別）
- `slack_notify` job の `needs:` は 0001 / 0002 / 0005 で `[build_ubuntu, build_macos, build_windows]` に確定済み
- tag を打たない運用のため publish は止まっている（ publish job 自体が無い）
- 関連 open issue: 0051 （ sdist の残し方）・ 0066 （ publish 対象 ubuntu 系列）・ 0067 （ publish の e2e ゲート）は本 issue の publish 再構築に論点として吸収される。 0052 （ setup.py の手動タグ → auditwheel repair ）は setup.py が 0001 で削除されるため前提が消滅し、 auditwheel 導入は本 issue と重複する（統合・クローズの判断は別途）

## 設計方針

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

manylinux タグの正解値（実シンボル検証）は 0006 では行わない。 `auditwheel repair --only-plat` で必要な platform tag が自動的に決まる。 旧 `setup.py` （ 0001 で削除。 git 履歴参照）で hardcode していたタグ、 および 0003 の `wheel.tags` override / 0004 の `wheel tags` post-process が付与するタグと一致しない場合は実体（ glibc バージョン）優先で確定する。 クロスコンパイル wheel （ aarch64 ）に対して x86_64 host 上の auditwheel が外部ライブラリを解決できるか（ rootfs をライブラリ探索パスに通す必要があるか）は実装時に確認する。

### sha256 検証

`DEPS` に platform 別の sha256 キーを追加する（キー命名は実装時に確定。 例）:

```
WEBRTC_BUILD_VERSION=m150.7871.3.0
WEBRTC_SHA256_ubuntu-24.04_x86_64=...
WEBRTC_SHA256_macos_arm64=...
```

KEY=value 形式を維持するため、 0001 で実装済みの `DEPS` パーサ（ webrtc `VERSIONS` と共通の KEY=value パーサ）をそのまま使って取り出せる。 shell の `source DEPS` 互換も維持される（キー名に使えない文字が入る場合はエスケープ規則を実装時に確定する）。

`fetch_deps.cmake` の `_sora_fetch_archive` は 0001 で `SHA256` キーワード引数の受け口（ `cmake_parse_arguments(_arg "" "SHA256" "" ${ARGN})` ）を持っている。 0006 では検証ロジックを実装する:

```cmake
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
```

メインスクリプトで platform ごとの sha256 キーを `DEPS` から取り出して渡す。 キーが無い依存は検証 skip （移行期間との後方互換用）。

### actions/cache 導入

各 platform job の `uv build --wheel` 前に:

```yaml
- name: Cache deps
  uses: actions/cache@...
  with:
    path: |
      _deps
    key: deps-${{ matrix.platform.target }}-${{ hashFiles('DEPS', 'cmake/scripts/fetch_deps.cmake') }}
    restore-keys: |
      deps-${{ matrix.platform.target }}-
- name: Cache LLVM
  uses: actions/cache@...
  with:
    path: |
      _deps/llvm
    key: llvm-${{ runner.os }}-${{ hashFiles('DEPS') }}
```

LLVM は host 単位で共有するため `runner.os` を key に含める。 platform は不要。 deps cache の path （ `_deps` 全体）が LLVM cache の path （ `_deps/llvm` ）を包含して二重保存にならないよう、 path の切り分け（例: deps 側を `_deps/<platform>` に絞る）は実装時に確定する。

### e2e 復活

- build.yml に `e2e_test` job を新設する: `needs: [build_ubuntu, build_macos, build_windows]` 相当 + `uses: ./.github/workflows/e2e-test.yml` + `with: from_build: true` + `secrets: inherit`
- e2e-test.yml の全 job から `if: false` を外す
- e2e-test.yml の `wheel_platform` 一覧と build 側の artifact 名を突き合わせ、 ビルドされない platform の entry （ `ubuntu-22.04_x86_64` を build matrix に含めない判断をした場合など）を削除する
- schedule トリガの復活有無を判断する（ 12032d2 でコメントアウトされた経緯を確認の上）

### publish_wheel / create-release の再構築

旧 job （削除前 build.yml:344-504 。 git 履歴参照）を参考に、 scikit-build-core 経路の artifact 前提で新設する。 tag push （ `tags/202*` ）起動・PyPI trusted publishing ・GitHub release 作成という骨格は踏襲し、 matrix / artifact 取得 / sdist の 3 点を再設計する（スコープ節参照）。

## 完了条件

- build.yml に `e2e_test` job が存在し、 e2e-test.yml の全 job から `if: false` が外れ、 有効な matrix entry （現状 python 3.13 のみ）で green になる
- Linux wheel の platform tag が `auditwheel repair --only-plat` で確定する manylinux タグ（実機 glibc 互換）になる
- `DEPS` の sha256 検証が動く（手動で sha256 を書き換えて FATAL_ERROR が出ることを確認）
- `actions/cache` が hit して 2 回目以降のビルドで `_deps/` が DL されない
- 再構築した `publish_wheel` / `create-release` を tag push で 1 回試して全 platform wheel が PyPI に publish され、 GitHub release が作成される
- `slack_notify` job が green （ `needs: [build_ubuntu, build_macos, build_windows]` ）
- `.gitignore` に `/_install` / `/_source` / `/_package` が残っていない
- build-debug 相当ワークフローが workflow_dispatch で 1 回 green になる

## 解決方法

### .github/workflows/build.yml

- `e2e_test` job を新設し、 e2e 用 env を再導入する
- 各 Linux platform job 末尾に `auditwheel repair` step を追加
- `actions/cache` step を追加（ deps + LLVM の 2 種）
- `publish_wheel` / `create-release` job を新設する（ artifact 取得方式・matrix・sdist は「設計方針 → publish_wheel / create-release の再構築」）

### .github/workflows/e2e-test.yml

全 job の `if: false` を外し、 artifact 名・platform entry を build 側と整合させる。

### build-debug 相当ワークフロー

「設計方針」の通り新設する（ファイル名は build-debug.yml を踏襲してよい）。

### DEPS

platform 別 sha256 キーを追加する。 0006 PR 内で実機 `curl -sL <url> | sha256sum` で計算する。

### cmake/scripts/fetch_deps.cmake

- `_sora_fetch_archive` の `SHA256` 受け口に検証ロジックを実装
- メインスクリプトで platform ごとに sha256 を取り出して渡す

### .gitignore

`/_install` / `/_source` / `/_package` を削除する。

### CHANGES.md

`## develop` の各グループに本 issue 分のみ追加する（ 0001 〜 0005 / 0007 のエントリは各 issue が自分で追加するため触らない）:

```
- [CHANGE] arm64 native CI runner (build_ubuntu_arm job) を廃止し、 ubuntu-24.04 x86_64 host からのクロスコンパイル経路に統一する
  - @voluntas
- [ADD] 依存アーカイブの sha256 検証を導入する
  - @voluntas
- [ADD] Linux wheel に auditwheel repair による manylinux タグ付与を導入する
  - @voluntas
```

（ `build_ubuntu_arm` の job 削除自体は 0001 で行われるが、 リリースノート上の廃止告知は 0003 の方針に従い本 issue でまとめて記載する）

## ロールバック

0006 マージ後に CI が大きく壊れた場合:

1. `git revert -m 1 <merge-commit>` で revert PR を作成
2. revert 後、 新設した `e2e_test` / `publish_wheel` / `create-release` / build-debug 相当 job が消え、 e2e-test.yml の全 job に `if: false` が戻り、 `DEPS` の sha256 キーと fetch_deps.cmake の検証ロジックが消えることを確認
3. forward fix を選ぶ判断: `auditwheel repair` の単一不具合 / sha256 検証の不具合 / actions/cache の単一不具合なら追加コミットで対応する
