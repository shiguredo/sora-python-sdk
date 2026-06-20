# macOS arm64 ネイティブビルド対応

- Priority: High
- Created: 2026-05-21
- Polished: 2026-06-20
- Completed: 2026-06-20
- Model: Composer 2.5
- Branch: feature/change-scikit-build-core-native-deps

## 目的

0016 で `ubuntu-24.04_x86_64` 向けに実装した `scikit-build-core` + `cmake/scripts/fetch_deps.cmake` を macOS arm64 host でも動作させ、 macOS arm64 runner 上で `uv build --wheel` 一発で macOS arm64 用 wheel を生成できる状態にする。 0016 で `if: false` で disable した `build_macos` job を復活させ、 `macos-14_arm64` / `macos-15_arm64` 両 matrix で同一 wheel タグ (`cp3XY-cp3XY-macosx_14_0_arm64`) の wheel を生成する。

## 設計の前提（プロジェクト全体の新方針からの該当部）

- ビルド環境は `ubuntu-24.04_x86_64` host のみに集約するが、 macOS arm64 と Windows x86_64 は例外的にそれぞれの OS で native build を維持する (cross-compile しない)。 macOS native は macOS arm64 runner で native build する。
- clang は libwebrtc 同梱 clang バイナリを継続使用する (0016 の `_sora_fetch_llvm` が host platform を自動推定し、 macOS arm64 host では Mac arm64 用 Chromium clang tarball を自動 DL する)。
- wheel の deployment target は `14.0` で統一する。 macos-14 / macos-15 両 runner で同じ wheel タグを生成し、 macOS 14 ユーザが pip install できる状態を維持する。
- 本 issue の行番号参照は全て 0016 完成形を前提とする (0016 未 merge で先行着手する場合は base ブランチを 0016 のフィーチャーブランチに置く)。

## スコープ

含む:

- `cmake/scripts/fetch_deps.cmake` の `SORA_PYTHON_SDK_PLATFORM` 自動検出ブロックを Darwin 分岐対応に書き直す (`if(NOT ... STREQUAL "Linux") FATAL_ERROR endif()` の早期 return を `if/elseif/else` の分岐構造に置換する)。 許容リストに `macos_arm64` を追加し、 FATAL_ERROR メッセージから旧 issue 番号 (0002 / 0003 / 0004 / 0005) を消して現番号 (0021) に直す。 冒頭コメント L5 の `issues/0001-...` 参照も `issues/0016-...` に書き換える。
- `fetch_deps.cmake` の Darwin 分岐冒頭に `find_program(_XCRUN_EXECUTABLE xcrun NO_CACHE)` で Xcode Command Line Tools の存在を検出するガードを追加する (不在時は `xcode-select --install` への誘導 FATAL_ERROR)。
- `pyproject.toml` に `[[tool.scikit-build.overrides]]` 1 ブロックで macOS override を追加する (`if.platform-system = "^darwin"`)。
- `.github/workflows/build.yml` の `build_macos` job を scikit-build-core 経路で完結させる: `if: false` 削除 / `build_pyi` artifact 経路の step 削除 / `run.py build` 行削除 / `uv build` を `uv build --wheel` 化 / `uv sync` を `uv sync --no-install-project` 化 / matrix の `python_host_platform` を両 entry とも `macosx-14.0-arm64` に統一 / `MACOSX_DEPLOYMENT_TARGET` env を追加。 matrix の `target` / `os` キーは削除する。
- `slack_notify.needs` を `[build_ubuntu]` から `[build_ubuntu, build_macos]` に戻す。

含まない (別 issue で扱う):

- `CMakeLists.txt` の更新 (`if(TARGET_OS STREQUAL "macos")` ブロックは 0016 で既に存在し、 macOS override で `TARGET_OS = "macos"` が渡れば自動的に有効化される)。
- `_sora_fetch_openh264` の FATAL_ERROR メッセージ修正 (xcrun ガードで Xcode CLT 不在は事前検出するため、 OpenH264 ヘッダ取得経路に到達するときは必ず `make` が存在する。 メッセージ整備は 0021 で Windows 経路と合わせて行う)。
- Linux arm64 cross-compile (0017 / 0019 / 0020) と Windows x86_64 native (0021): 各 issue で扱う。 0017 / 0019 / 0020 / 0021 と 0018 は同じ `SORA_PYTHON_SDK_PLATFORM` 自動検出ブロック・同じ `slack_notify.needs` を編集するため、 develop 取込み順序は `0017 → 0018 → 0019 → 0020 → 0021` を前提とする (issue 番号順)。 後発 PR が rebase で衝突解決する。
- macOS バージョン拡充: 既存 `macos-14_arm64` / `macos-15_arm64` 2 entry の維持のみ。
- macOS x86_64 native: プロジェクトのサポート対象外。
- PyPI publish 経路の復活: `publish_wheel` / `create-release` は 0022 で復活する。 0018 で macos-14 / macos-15 両 entry の wheel タグが同一 (`macosx_14_0_arm64`) になるため、 0022 polish 時に `publish_wheel.matrix` から `macos-15_arm64` を外し sdist 残置条件 (`build.yml:382`) を `macos-14_arm64 && python_version == '3.12'` に付け替える指示を確定する (本 issue 内では実施しない)。
- `build-debug.yml` (0022) / `Makefile` (0023) は本 issue では触らない。

## 現状

- `cmake/scripts/fetch_deps.cmake:19-23` で `CMAKE_HOST_SYSTEM_NAME != "Linux"` なら FATAL_ERROR で停止する。 macOS host では `Phase 1 only supports Linux host; got 'Darwin'` で必ず失敗する。 同ファイル L5 / L22 / L58-59 に旧 issue 番号 (`0001` / `0002` / `0005`) への参照が残る。
- `fetch_deps.cmake:67` の `_LLVM_HOST_KEY = ${CMAKE_HOST_SYSTEM_PROCESSOR}-${CMAKE_HOST_SYSTEM_NAME}` は ubuntu バージョンを含まない設計で、 macOS host では `arm64-Darwin` が得られる。 Rosetta 経由で起動した CMake は `x86_64-Darwin` を返すが、 本 issue で追加する Darwin 分岐の arm64 ガードで弾く。
- `.github/workflows/build.yml:227-277` の `build_macos` job は `if: false` で disable 中。 matrix は `macos-15_arm64` / `macos-14_arm64` × Python 3.12 / 3.13 / 3.14 = 6 entry。 step は `build_pyi` artifact の download → cp → `uv sync` → `uv run python run.py build macos_arm64` + `uv build` の 2 段構成で、 `env: _PYTHON_HOST_PLATFORM / ARCHFLAGS` を渡している。
- `run.py build macos_arm64` 経路は 0022 で `run.py` ごと削除予定。 本 issue では `build.yml` から呼び出しを外すのみ。

## 設計方針

### SORA_PYTHON_SDK_PLATFORM 算出の macOS 対応 (fetch_deps.cmake)

既存 `fetch_deps.cmake:19-23` の `if(NOT CMAKE_HOST_SYSTEM_NAME STREQUAL "Linux") FATAL_ERROR endif()` 早期 return を削除し、 既存 L25-48 の `/etc/os-release` 抽出処理を `if(CMAKE_HOST_SYSTEM_NAME STREQUAL "Linux")` ブロック内に移動する。 続けて `elseif(... STREQUAL "Darwin")` 分岐と `else()` 分岐を追加する。 既存 Linux ブロックを先頭に保ち、 続けて Darwin → Windows の順で固定する (0016 既存実装の差分最小化のため。 0021 は `elseif(... STREQUAL "Windows")` を Darwin 分岐の後に挿入する)。 完成形の擬似コード:

```cmake
if(NOT SORA_PYTHON_SDK_PLATFORM)
  if(CMAKE_HOST_SYSTEM_NAME STREQUAL "Linux")
    # 既存 L25-48 の /etc/os-release 抽出処理をそのまま移動
    # set(SORA_PYTHON_SDK_PLATFORM "ubuntu-${_OS_VERSION_ID}_${CMAKE_HOST_SYSTEM_PROCESSOR}" ... FORCE)
  elseif(CMAKE_HOST_SYSTEM_NAME STREQUAL "Darwin")
    find_program(_XCRUN_EXECUTABLE xcrun NO_CACHE)
    if(NOT _XCRUN_EXECUTABLE)
      message(FATAL_ERROR
        "Xcode Command Line Tools が見つかりません。 "
        "ターミナルで 'xcode-select --install' を実行してください。")
    endif()
    if(NOT CMAKE_HOST_SYSTEM_PROCESSOR STREQUAL "arm64")
      message(FATAL_ERROR
        "macOS host must be arm64; got '${CMAKE_HOST_SYSTEM_PROCESSOR}'. "
        "macOS x86_64 is not supported.")
    endif()
    set(SORA_PYTHON_SDK_PLATFORM "macos_arm64" CACHE STRING "" FORCE)
  else()
    message(FATAL_ERROR
      "Unsupported host: '${CMAKE_HOST_SYSTEM_NAME}'. "
      "Supported hosts: Linux (ubuntu only), Darwin (arm64 only). "
      "Windows host will be added in 0021.")
  endif()
endif()
```

許容リスト (現行 L52) は `set(_SORA_ALLOWED_PLATFORMS "ubuntu-24.04_x86_64" "macos_arm64")` に拡張する (CMake の `set(VAR "a" "b")` は 2 要素 list として展開され、 `list(FIND ...)` はそのまま動く)。 既存 FATAL_ERROR メッセージ (L58-59 の `Other platforms will be added in 0002 ...`) は `Other platforms will be added in 0021 (Windows)` に書き換える。 冒頭コメント (L5 `issues/0001-...`) は `issues/0016-...` に書き換える。 既存 Darwin 早期 return ブロックの FATAL_ERROR メッセージ (L22 `macOS (0002) / Windows (0005)`) は削除ブロックなので残らない。

`_LLVM_HOST_KEY` の組み立て (現行 L67) は変更不要。 Darwin 分岐の arm64 ガードで Rosetta 起動を弾くため、 後段では必ず `arm64-Darwin` が得られる。

`_XCRUN_EXECUTABLE` 変数は本ガード内のみで使い (SDK パス取得は CMake / clang に委譲)、 既存 `_SORA_TAR_EXECUTABLE` (L180) / `_SORA_MAKE_EXECUTABLE` (L208) と同じ `NO_CACHE` で cache を汚染しない。 `find_program` の引数書式は既存 `_SORA_MAKE_EXECUTABLE` と揃えて `NAMES` を省略する。 `NO_CACHE` 指定により 2 回目 configure で再評価されるため、 1 回目で `xcode-select --install` 実行後に 2 回目を走らせるとガードを自動 pass する。

### TARGET_OS と cmake.define の macOS override (pyproject.toml)

scikit-build-core 関連セクションを一塊にするため、 `[tool.scikit-build.metadata.version]` (現行 L54-57) の直後、 `[tool.pytest.ini_options]` (現行 L59) の直前に、 次の 1 ブロックを挿入する:

```toml
[[tool.scikit-build.overrides]]
if.platform-system = "^darwin"
inherit.cmake.define = "append"
cmake.define.TARGET_OS = "macos"
cmake.define.CMAKE_OSX_ARCHITECTURES = "arm64"
cmake.define.CMAKE_OSX_DEPLOYMENT_TARGET = "14.0"
cmake.define.CMAKE_C_COMPILER_TARGET = "aarch64-apple-darwin"
cmake.define.CMAKE_CXX_COMPILER_TARGET = "aarch64-apple-darwin"
```

設計上の注意:

- `if.platform-system` は scikit-build-core が `sys.platform` を `re.search` で評価するため、 `darwin` 単独でも `^darwin` でも実機差異は出ない。 本プロジェクトでは将来の suffix 付与に備えてアンカー付き `^darwin` で揃える。
- `inherit.cmake.define = "append"` を明示する。 既定値 `"none"` だと override の `cmake.define` テーブルが base `[tool.scikit-build.cmake.define]` 全体を置換するため、 ubuntu host で必要なデフォルトが macOS host で消える危険がある。 `"append"` で base のキーを保ったまま macOS 用キーを追加する。
- `TARGET_OS = "macos"` は 0016 の `[tool.scikit-build.cmake.define] TARGET_OS = "ubuntu"` デフォルトを後勝ち上書きする。 scikit-build-core の override は配列の出現順に評価され、 同じキーへの set は後出しが勝つ。
- `CMAKE_OSX_DEPLOYMENT_TARGET = "14.0"` は cmake が clang を起動する際の `-mmacosx-version-min=14.0` 注入を担う。 生成 `.so` の `LC_BUILD_VERSION` (mach-o) が `minos 14.0` で固定される。
- `CMAKE_OSX_ARCHITECTURES = "arm64"` は単一アーキ wheel を保証する (universal2 にしない)。
- `CMAKE_OSX_SYSROOT` は明示しない。 CMake は未設定時に `xcrun --sdk macosx --show-sdk-path` 相当で SDK を自動検出する。
- `CMAKE_SYSTEM_PROCESSOR` は渡さない (`CMAKE_CROSSCOMPILING` を立てないため)。

この override 構造 (`if.platform-system` 条件 + 複数 `cmake.define`) は 0019 / 0020 の cross 用 `[[tool.scikit-build.overrides]]` でも条件キー (`if.env.SORA_SDK_TARGET`) を変えて再利用される。

### wheel タグ `macosx_14_0_arm64` を 3 つの env で確定する

`build_macos` の `uv build --wheel` step に次の 3 つの env を渡す:

```yaml
- run: uv build --wheel
  env:
    _PYTHON_HOST_PLATFORM: "macosx-14.0-arm64"
    ARCHFLAGS: "-arch arm64"
    MACOSX_DEPLOYMENT_TARGET: "14.0"
```

役割分担 (scikit-build-core 0.11.6 の `builder/wheel_tag.py:65-87` 実装を参照):

- `MACOSX_DEPLOYMENT_TARGET = "14.0"` env: **wheel タグの確定の主役**。 scikit-build-core の wheel タグ darwin 分岐は `MACOSX_DEPLOYMENT_TARGET` と `ARCHFLAGS` のみから `packaging.tags.mac_platforms()` でタグ算出する。 加えて CPython の `sysconfig.get_platform()` の Darwin 分岐 (`_osx_support._get_macosx_deployment_target()`) も同 env を参照する。
- `ARCHFLAGS = "-arch arm64"` env: wheel タグの arch 部 (`arm64`) を確定する。 CPython の sysconfig が cflags に追加するアーキ指定を上書きし、 nanobind 経由の universal2 化も防ぐ。
- `CMAKE_OSX_DEPLOYMENT_TARGET = "14.0"` (cmake.define 経由): clang への `-mmacosx-version-min` 注入で `.so` の `LC_BUILD_VERSION` を固定する。 `MACOSX_DEPLOYMENT_TARGET` env と同値を二重指定するのは `.so` の `LC_BUILD_VERSION` と wheel タグ表示値を確実に整合させるため (両者が異なる値の場合 CMake は `CMAKE_OSX_DEPLOYMENT_TARGET` cache 変数を優先する)。
- `_PYTHON_HOST_PLATFORM = "macosx-14.0-arm64"`: CPython の `sysconfig.get_platform()` を上書きする。 scikit-build-core の wheel タグ darwin 分岐は参照しないが、 macos-15 runner で `sysconfig.get_platform()` が `macosx-15.0-arm64` を返すのを上書きするガードとして残す (両 runner で同じ wheel タグを得るための保険)。

matrix の `python_host_platform` は両 entry とも `macosx-14.0-arm64` に統一する。 macos-15 runner でも 14.0 タグが出るため、 macos-14 / macos-15 で同名 wheel が生成される (CI artifact 名 `${{ matrix.platform.name }}_python-${{ matrix.python_version }}` は別なので衝突しない)。 macos-15 entry を維持する根拠は macOS 15 host から 14.0 deployment target wheel を生成できることのカナリア。 観測点は (1) wheel タグが `macosx_14_0_arm64` で生成されること、 (2) `vtool -show-build dist/*/sora_sdk_ext.cpython-3XY-darwin.so` で `minos 14.0` を返すこと。

3 つの env のいずれかを CI step で書き忘れると、 macos-15 runner で wheel タグが `macosx_15_0_arm64` で確定し完了条件で fail する。 build.yml 編集時は env ブロックに 3 つ揃っていることを PR レビューで目視確認する。

### CI 影響 (.github/workflows/build.yml)

`build_macos` job (現行 L227-277) の変更:

- `if: false` (L228) を削除。
- `needs: [build_pyi]` (L249) を削除。
- `actions/download-artifact` step (L254-257) と `cp sora_sdk/py.typed src/sora_sdk/py.typed` + `cp sora_sdk/sora_sdk_ext.pyi src/sora_sdk/sora_sdk_ext.pyi` の 2 行 step (L258-260) を削除。
- `uv sync` (L265) を `uv sync --no-install-project` に書き換える (理由: `uv sync` 単独だと scikit-build-core 経由でプロジェクト本体の build が走り、 続く `uv build --wheel` と二重 build になるため。 macOS arm64 では LLVM tarball + Chromium clang DL が走るためビルド 1 回でも 8-12 分かかり、 二重 build を避ける効果が Linux より大きい)。
- `uv run python run.py build ${{ matrix.platform.target }}` 行 (L267) を削除。 同 step に残る `uv build` を `uv build --wheel` に書き換える。
- 同 step の `env:` に `MACOSX_DEPLOYMENT_TARGET: "14.0"` を追加する (既存 `_PYTHON_HOST_PLATFORM` / `ARCHFLAGS` は維持)。
- matrix の `macos-15_arm64` entry の `python_host_platform: "macosx-15.0-arm64"` を `macosx-14.0-arm64` に書き換える。
- matrix から `target: macos_arm64` キーと `os: macos` キーを削除する。 残すキーは `name` / `runs_on` / `python_host_platform` / `archflags`。 `name` は (1) 同 step 内 Upload Artifact が `name: ${{ matrix.platform.name }}_python-${{ matrix.python_version }}` で参照する、 (2) 0022 で復活する publish_wheel / create-release も同じ artifact 名規約で download する、 という 2 経路で参照されるため必須。 削除した `target` / `os` キーは 0022 でも復元不要。

`slack_notify` job (現行 L330) の `needs:` を `[build_ubuntu]` から `[build_ubuntu, build_macos]` に書き換える。

`timeout-minutes: 15` (L251) は維持する。

## 完了条件

- macOS arm64 host (`macos-14_arm64` / `macos-15_arm64`) + Python 3.12 / 3.13 / 3.14 で `uv build --wheel` が成功する (ローカル直列で 3 通り、 CI matrix の 6 entry で green)。
- 生成 wheel のタグが両 runner ともに `cp3XY-cp3XY-macosx_14_0_arm64` で一致する。 macos-15 runner でも `macosx_15_0_arm64` にならない。
- wheel 内に次が含まれる:
  - `sora_sdk/sora_sdk_ext.cpython-3XY-darwin.so` (3XY は 312 / 313 / 314)
  - `sora_sdk/sora_sdk_ext.pyi`
  - `sora_sdk/py.typed`
  - `sora_sdk/__init__.py` などの Python ソース
  - `python -m zipfile -l dist/*.whl` で内容確認。 dist-info の Version が `VERSION` ファイルと一致。
- ローカル動作確認手順 (env を CI と同じく明示的に渡して実行する):
  1. `uv venv`
  2. `uv sync --no-install-project`
  3. `MACOSX_DEPLOYMENT_TARGET=14.0 _PYTHON_HOST_PLATFORM=macosx-14.0-arm64 ARCHFLAGS='-arch arm64' uv build --wheel`
  4. `uv pip install --force-reinstall dist/*.whl`
  5. `uv run --no-sync pytest tests/test_version.py` が成功する
  6. `uv run --no-sync python -c "from sora_sdk import sora_sdk_ext; print(sora_sdk_ext.__file__)"` が `site-packages/sora_sdk/sora_sdk_ext.cpython-3XY-darwin.so` を出力する
  7. `uv run --no-sync python -c "import sora_sdk; s = sora_sdk.Sora(); print(s)"` が `<sora_sdk.sora_sdk_ext.Sora object at 0x...>` 形式の文字列を標準出力に表示する (例外で落ちず、 print で C++ オブジェクトの repr が出る)
  8. `vtool -show-build $(uv run --no-sync python -c 'from sora_sdk import sora_sdk_ext; print(sora_sdk_ext.__file__)') | grep -E 'platform|minos'` が `platform MACOS` と `minos 14.0` を返す (`.so` の `LC_BUILD_VERSION` が `CMAKE_OSX_DEPLOYMENT_TARGET = "14.0"` 注入で固定されていることの確認、 `vtool` は Xcode CLT 同梱)
- 同じ Python ABI で 2 回目の `uv build --wheel` を実行すると `_deps/macos_arm64/.stamps/*` と `_deps/llvm/arm64-Darwin/.stamps/llvm` の mtime が変化しない (log に `Sora deps: webrtc cache hit` 等の cache hit メッセージが出る)。
- CI で `build_macos` の 6 entry が green になり、 `slack_notify` job が `needs: [build_ubuntu, build_macos]` の依存関係下で green になる。

## 解決方法

### cmake/scripts/fetch_deps.cmake

設計方針「SORA_PYTHON_SDK_PLATFORM 算出の macOS 対応」の擬似コード通り適用する。 行レベル要点:

- L5 のコメント `# 詳細は issues/0001-change-scikit-build-core-native-deps.md を参照。` を `# 詳細は issues/0016-change-scikit-build-core-native-deps.md を参照。` に書き換える。
- L19-23 の `if(NOT ... STREQUAL "Linux") FATAL_ERROR endif()` 早期 return ブロックを削除する。
- L25-48 を `if(... STREQUAL "Linux")` でくるみ直し、 `elseif(... STREQUAL "Darwin")` (xcrun ガード + arm64 ガード + `SORA_PYTHON_SDK_PLATFORM` 設定) と `else()` (Unsupported host FATAL_ERROR) 分岐を追加する。
- L52 を 2 要素 `set(_SORA_ALLOWED_PLATFORMS "ubuntu-24.04_x86_64" "macos_arm64")` に拡張する。
- L58-59 の FATAL_ERROR メッセージ末尾を `Other platforms will be added in 0021 (Windows).` に書き換える。

### pyproject.toml

設計方針「TARGET_OS と cmake.define の macOS override」の TOML 1 ブロックを `[tool.scikit-build.metadata.version]` (現行 L54-57) 直後、 `[tool.pytest.ini_options]` (現行 L59) 直前に挿入する。 base `[tool.scikit-build.cmake.define]` (L48-49) との物理距離はあるが、 scikit-build-core の override 評価は宣言順序ではなく `if` 条件マッチで動くため、 セクション順は意味的に影響しない。

### CMakeLists.txt

触らない (0016 後の `if(TARGET_OS STREQUAL "macos")` ブロックは現行 L129-149 に存在し、 macOS override で `TARGET_OS = "macos"` が渡れば自動的に有効化される)。

### .github/workflows/build.yml

設計方針「CI 影響」の指示通り `build_macos` job (現行 L227-277) を編集し、 `slack_notify.needs` (現行 L330) を `[build_ubuntu, build_macos]` に戻す。

### CHANGES.md

現行 `CHANGES.md` の `## develop` セクション直下にある最初の `[CHANGE] build backend を ... scikit-build-core に切り替える` エントリ (現行 `CHANGES.md:14-15`) の **直後** に、 次の 3 行 (タイトル + 補足 1 行 + 担当者) を挿入する:

```
- [CHANGE] macOS arm64 ネイティブビルドの build_macos job を復活させる
  - 0016 で disable した build_macos job を scikit-build-core 経路で再有効化する
  - @voluntas
```

実装時に他 issue が先に develop へ merge されていた場合は、 `## develop` ヘッダ直下の最初の `[CHANGE]` エントリの直後に挿入する (行番号は実装時に再確認)。

## ロールバック

revert は `pyproject.toml` の macOS override / `fetch_deps.cmake` の Darwin 分岐 / xcrun ガード / `build_macos` 復活設定の根本設計に起因する不具合で、 追加コミットで修正できない場合に選ぶ。 個別関数や設定値レベル (FATAL_ERROR 文言 / matrix の `python_host_platform` / env の追加) は revert ではなく追加コミットで前進させる。

手順: `git revert -m 1 <merge-commit>` で revert PR を作成し、 `build_macos` job が再び `if: false` で disable された状態を CI で確認する。 revert 後の macOS host は再び `fetch_deps.cmake:19-23` の FATAL_ERROR で `uv build --wheel` が configure 段階で落ちるため、 `_deps/macos_arm64/` と `_deps/llvm/arm64-Darwin/` は残置可能 (実害なし)。

## 実装時の補足

- 実装ブランチは 0016 と同じ `feature/change-scikit-build-core-native-deps` に相乗りした。 1 PR に 0016 と 0018 が同梱される。
- 設計方針・解決方法の「FATAL_ERROR メッセージや冒頭コメントから旧 issue 番号を消して現番号 (0016 / 0021) に直す」指示は、 `shiguredo-issues` 規約「ソースコード本体・ドキュメントに issue 番号を書かない」を優先し、 番号書き換えではなく **番号削除** で対応した (`fetch_deps.cmake` の冒頭 issue 参照コメント・許容リスト不一致時の FATAL_ERROR の「will be added in 0021 (Windows)」末尾・Unsupported host FATAL_ERROR の「Windows host will be added in 0021」末尾・Darwin 分岐コメントの「Windows サポートは 0021 で追加予定」を削除)。
- `CHANGES.md` エントリも同規約に従い、 内部 job 名 (`build_macos`) を露出せず利用者視点の文言とした。
- レビューで指摘された 0016 由来の `uv sync` lockfile 同期 (dev-dependencies からの `nanobind` 抜けの反映) を同一コミットに同梱した。 0018 のスコープ外だが commit message で明示している。
