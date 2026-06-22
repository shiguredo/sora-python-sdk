# multistrap 経路から sysroot.py 経路への置き換え

- Priority: High
- Created: 2026-06-22
- Model: Opus 4.7
- Branch: feature/change-replace-multistrap-with-sysroot
- Polished: 2026-06-22

## 目的

cross-compile 用 sysroot の構築経路を multistrap から自前 Python スクリプト `sysroot.py` に置き換える。 撤回された 0017 / 0019 / 0020 (closed) は cross-compile 個別対応を進めようとしていたが、 multistrap の上流停滞と CI での脆い `sed` パッチ運用が共通課題として残ったため、 本 issue で **sysroot 取得経路だけを単独で切り出して** 共通基盤を確立する。

本 issue の scope は「sysroot を生成する仕組み」 と「`multistrap/` 4 ファイル・ multistrap 系 CI step の撤去」 まで。 cross-compile した wheel を実際に生成する経路 (toolchain ファイル新設、 pyproject.toml override 追加、 `SORA_PYTHON_SDK_PLATFORM` 許容リスト追加、 `_sora_fetch_rootfs` の **実呼び出し**、 CI matrix の `exclude` 解除) は本 issue では行わず、 後続 cross 系 issue で扱う。 `sysroot.py` の単体テスト (`tests/test_sysroot.py`) と `[tool.ty.src].include` への追加は別 issue (test / lint カテゴリ) で扱う。

## 優先度根拠

High:

- multistrap は Debian / Ubuntu 上流のメンテが停滞しており、 Ubuntu 26.04 (2026-04 LTS) で配布終了する見込みがある。 確証は `https://launchpad.net/ubuntu/+source/multistrap` の Latest version 更新日と Debian salsa (`https://salsa.debian.org/installer-team/multistrap`) の最新 commit 日時を実装着手時に確認し、 上流停滞の根拠 (例: 直近 2 年間 commit 無し) を PR description に記載する
- 既存 CI で `sudo sed -e '...AllowInsecureRepositories=true' -i /usr/sbin/multistrap` で multistrap 本体にパッチを当てており、 multistrap 側の更新で壊れるリスクがある
- 撤回された 0017 / 0019 / 0020 の代替として、 本 issue の `sysroot.py` を後続 cross 系 issue (ubuntu armv8 / jetson / Raspberry Pi OS) が共通基盤として再利用する。 本 issue を先行させないと、 後続 issue で同じ仕組みを書き直すことになる

## 現状

- `.github/workflows/build.yml` の `build_ubuntu` job 内 `if: matrix.platform.arch == 'armv8'` ガード配下で以下が現役で実行されている (`raspberry-pi-os_armv8` も `arch=armv8` 設定のため当ガードに含まれる):
  - `sudo apt-get -y install multistrap binutils-aarch64-linux-gnu` + multistrap 本体への `sed -e '...AllowInsecureRepositories=true' -i /usr/sbin/multistrap`
  - `uv run python run.py build ${{ matrix.platform.target }}` (内部で `run.py` から `buildbase.py:install_rootfs` を呼び `multistrap --no-auth -a arm64 -d <rootfs_dir> -f <conf>` を実行)
  - 対象 entry は `ubuntu-22.04_armv8` / `ubuntu-24.04_armv8` / `raspberry-pi-os_armv8` の 3 つで、 いずれも matrix `exclude:` で既に無効化されている
  - 同 if ガード配下に `sora_sdk_rpi` rename step (`if: matrix.platform.name == 'raspberry-pi-os_armv8'`) もあるが、 exclude 済 entry でしか走らないため本 issue では触らない (0020 由来の対応で後続 RPi 復活 issue で再利用)
- `build_ubuntu_arm` job (`if: false` 済) 内にも同様の multistrap install + sed パッチがあるが、 当 job ごと 0022 で削除予定のため本 issue では触らない
- `.github/workflows/build-debug.yml` に multistrap 言及無し (`grep -nc multistrap` 0 件)
- `buildbase.py` 内 multistrap 言及は `install_rootfs` (定義 1 関数) のみ。 `run.py` 内呼び出しは 1 箇所のみ。 これらは 0022 で `run.py` / `buildbase.py` ごと一括削除予定 (0022 のスコープに `multistrap/` 削除は含まないが、 `buildbase.py` を消す副作用で `install_rootfs` も消える)
- 現在 scikit-build-core 経路には cross-compile sysroot を構築する仕組みが存在しない
- `multistrap/*.conf` 4 ファイル:
  - `ubuntu-22.04_armv8.conf` (jammy main+universe, packages: `libstdc++-11-dev` ほか 3 つ)
  - `ubuntu-24.04_armv8.conf` (noble main+universe, packages: `libstdc++-13-dev` ほか 3 つ)
  - `ubuntu-22.04_armv8_jetson.conf` (jammy main+universe + NVIDIA L4T r36.3 common + t234, packages: `libstdc++-10-dev` + NVIDIA Jetson 系)
  - `raspberry-pi-os_armv8.conf` (Debian bookworm main + archive.raspberrypi.org bookworm。 `noauth=true` 無しで CI の `sed` パッチが `AllowInsecureRepositories=true` を強制注入することで成立)
- `cmake/scripts/fetch_deps.cmake` の `_SORA_ALLOWED_PLATFORMS` には `ubuntu-24.04_x86_64`, `macos_arm64`, `windows_x86_64` の 3 つしか登録されておらず、 cross 系 platform は FATAL_ERROR で落ちる (本 issue では触らない)
- `pyproject.toml` の `[tool.ty.src].include = ["src", "tests"]` によりリポジトリルートの `*.py` は ty 型チェック対象外 (既存 `run.py` / `buildbase.py` / `pypath.py` / `canary.py` も対象外運用)。 ruff はデフォルトで repo 全 `*.py` を対象とするため `sysroot.py` も自動含有
- `MANIFEST.in` (4 行) は `buildbase.py` / `run.py` / `pypath.py` / `VERSION` を include 。 0022 で削除予定
- 実装着手前の事前確認: 4 つの sysroot.json で参照する Packages インデックスの存在性を `curl -fI` で確認した結果 (2026-06-22 時点):
  - `http://ports.ubuntu.com/ubuntu-ports/dists/{jammy,noble}/main/binary-arm64/Packages.xz`: 200
  - `http://deb.debian.org/debian/dists/bookworm/main/binary-arm64/Packages.xz`: 200
  - `http://archive.raspberrypi.org/debian/dists/bookworm/main/binary-arm64/Packages.xz`: **404** (`.gz` は 200)
  - `https://repo.download.nvidia.com/jetson/{common,t234}/dists/r36.3/main/binary-arm64/Packages.xz`: **404** (`.gz` は 200)
  - 結論: NVIDIA Jetson と Raspberry Pi の repo は `Packages.xz` を配布しないため、 sysroot.py の処理フロー (3) は `.xz` → `.gz` のフォールバックチェーンを必ず実装する
- 参考実装: `shiguredo/webrtc-rs` リポジトリと `shiguredo/momo` リポジトリの `sysroot/*.json` が同種の sysroot を Rust 製 `shiguredo_sysroot` で構築。 sora-python-sdk 側は Rust toolchain 依存を避けるため Python で再実装する

## 設計方針

### スコープ境界

本 issue で行うこと:

- `sysroot.py` をリポジトリルートに新設する (scikit-build-core の `${CMAKE_SOURCE_DIR}/sysroot.py` で最短パス参照、 既存 `run.py` 等が並ぶリポジトリルートの慣例とも整合)
- `sysroot/` ディレクトリと配下 4 つの JSON 設定ファイルを新設する (ディレクトリ構造と JSON スキーマは `shiguredo/webrtc-rs` / `shiguredo/momo` の `sysroot/*.json` 慣例に合わせる)
- `cmake/scripts/fetch_deps.cmake` の **`_sora_fetch_llvm` 関数定義の直後、 `# ---------- メインスクリプト ----------` コメント行の直前** に `_sora_fetch_rootfs` **関数を定義** する (関数自体は登録するが、 メインスクリプトから呼び出さない)
- `MANIFEST.in` に `include sysroot.py` と `recursive-include sysroot *.json` を追加する (0022 で `MANIFEST.in` ごと削除されるまでの間、 sdist に sysroot.py と sysroot/*.json を含めるため)
- `multistrap/` 4 ファイルを削除する
- `.github/workflows/build.yml` の以下 step を削除する:
  - `if: matrix.platform.arch == 'armv8'` の multistrap install + sed パッチ step まるごと (`binutils-aarch64-linux-gnu` も同 step に同居しているため一緒に削除される。 後続 cross 系 issue で linker / strip として復活させる)
  - 同じ if ガード内の `uv run python run.py build ... && uv build` step まるごと
  - `build_ubuntu_arm` job 内 multistrap step は 0022 で job ごと削除予定のため触らない
  - `sora_sdk_rpi` rename step は exclude 済 entry でしか走らないため触らない
- `buildbase.py:install_rootfs` と `run.py` の multistrap 呼び出しブロックは 0022 で `run.py` / `buildbase.py` ごと一括削除予定のため、 本 issue では削除しない (本 issue merge 後は cross 系 wheel ビルド step が無くなるため `install_rootfs` 関数はデッドコードになる)
- `CHANGES.md` に `[CHANGE]` + `[ADD]` の 2 エントリを追加する

本 issue で行わないこと (後続 issue で扱う):

- `_SORA_ALLOWED_PLATFORMS` への cross 系 platform 追加
- `cmake/toolchains/*.cmake` の新設、 `pyproject.toml` への cross 用 override 追加、 `TARGET_OS` の cross 系切り替え
- `fetch_deps.cmake` メインスクリプトからの `_sora_fetch_rootfs` 呼び出し追加、 `CMAKE_SYSROOT` / `CMAKE_FIND_ROOT_PATH` の cache 変数設定
- `build.yml` matrix `exclude:` からの cross entry 復活と cross 用 build step 追加
- `auditwheel repair --only-plat` 対応 (0022 で扱う。 sysroot 内 `libc6-dev` の glibc バージョンが manylinux タグ確定に直結する点も 0022 で扱う)
- `tests/test_sysroot.py` 新設 (test カテゴリの別 issue)。 テスト用追加依存は CLAUDE.md「モック・スタブ禁止」 規約に従い実 HTTP サーバ (`http.server`) で行う想定
- `pyproject.toml` の `[tool.ty.src].include` への `sysroot.py` 追加 (lint カテゴリの別 issue)
- `Makefile` への sysroot 関連ターゲット追加 (0023 の Makefile 追加後に必要なら別 issue)
- 0022 polish は 0022 自身の polish-issue で扱う。 0022 を本 issue より **先に** merge してはならない (0022 が `run.py` / `buildbase.py` を消した後だと本 issue の「現状」 参照対象が消える)
- cross 系 issue が 4 platform を 1 runner で並列 build する際の `--cache-dir` 共有設計 (`<dest>/.debs/` をそのまま使うか、 別の共通 cache に集約するか)

本 issue を merge した直後の状態:

- `multistrap/` 4 ファイルと multistrap 系 CI step は消える
- `ubuntu-22.04_armv8` / `ubuntu-24.04_armv8` / `raspberry-pi-os_armv8` 向け wheel は CI で生成されない (元から `exclude:` で無効化されていたため CI は green を維持)。 `ubuntu-22.04_armv8_jetson` は build.yml に matrix entry が無いため影響なし (jetson 用 JSON は本 issue で新設するが、 build.yml で参照するのは後続 jetson 復活 issue)
- `sysroot.py` の単体 CLI 動作は完了条件で検証する。 `_sora_fetch_rootfs` 関数定義は配置済みだがメインスクリプトから呼ばれないため CI configure で sysroot.py は起動しない。 cmake は関数定義の構文だけは parse するため文法エラーは検出できるが、 関数本体内のロジック (`execute_process` の引数誤り等) は呼ばれるまで評価されない (後続 cross 系 issue で実呼び出ししたときに初めて顕在化する可能性がある)
- `buildbase.py:install_rootfs` と `run.py` の multistrap 呼び出しブロックはデッドコードとして残る (0022 で削除予定)

### sysroot.py の新設

リポジトリルートに `sysroot.py` を新規作成する。 `shiguredo-python` スキルに従って実装する (スキルが source of truth)。 sora-python-sdk 固有のローカル決定:

- ログ prefix は cmake 側の `Sora deps:` と区別するため `Sora sysroot: ...` 形式
- `__all__` には `SysrootConfig`, `Repo`, `PostInstallSymlink`, `PackageMeta`, `parse_config`, `build_rootfs`, `main` を公開 (将来 `tests/test_sysroot.py` から import される想定)。 補助関数 (`fetch_packages_index`, `resolve_dependencies`, `download_debs`, `extract_debs`, `fix_absolute_symlinks`, `ensure_usrmerge_symlinks`, `apply_post_install_symlinks`, `compute_stamp`) は module 内部実装として `__all__` には載せない
- dataclass は `@dataclass(frozen=True, slots=True, kw_only=True)` を基本とする
- ruff (lint) は対象、 ty (型チェック) は本 issue 対象外 (別 issue)。 本 issue merge 後は ruff style check + 完了条件 4 コマンドの integration 検証で品質を担保する (単体テストは test issue で追加)

#### CLI 仕様

```
python3 sysroot.py build --config <json> --dest <dir> [--cache-dir <dir>] [--jobs <n>] [--force] [--verbose]
python3 sysroot.py clean --dest <dir>
```

- `--config <json>`: JSON 設定ファイルのパス (必須)
- `--dest <dir>`: rootfs 展開先ディレクトリ (必須)。 内部で `Path.resolve()` で絶対パスに正規化
- `--cache-dir <dir>`: `.deb` ダウンロードキャッシュ場所 (デフォルト `<dest>/.debs/`。 `<dest>` 内配置で `clean` 時に同時削除。 `.debs/` 配下は `.deb` バイナリのみで `usr/include` / `usr/lib` 等の sysroot 探索パスと衝突しないため `CMAKE_SYSROOT=<dest>` で参照されても安全)
- `--jobs <n>`: 並列度 (デフォルト `min(8, os.cpu_count() or 4)`、 範囲 1-32。 範囲外は CRITICAL abort)。 GitHub Actions runner (4 vCPU) で自然に 4、 開発者の高 core マシンで 8 まで。 `download_debs` と `fetch_packages_index` にのみ適用、 `extract_debs` は常にシーケンシャル
- `--force`: stamp 一致でも強制再構築
- `--verbose`: DEBUG レベルログ出力
- `clean`: `<dest>` ディレクトリと `<dest>/.sysroot.stamp` を削除する (`<dest>/.debs/` も同時に消える)。 `<dest>` 不在時は no-op exit 0

`python3 sysroot.py` 直接実行を正規の起動方法とする (`uv run python sysroot.py` でも動くが起動オーバーヘッドあり)。 cmake からは `${Python_EXECUTABLE}` で実行する。 shebang は付けない。

動作環境: `build` サブコマンドは ubuntu-24.04 x86_64 host 限定 (`dpkg-deb` 1.21 以降が `data.tar.zst` 圧縮 `.deb` を扱える前提)。 CI でも `runs-on: ubuntu-24.04` 前提。 `clean` サブコマンドと sysroot.py のコード編集は OS 非依存。 Python 3.12 / 3.13 / 3.14 の標準ライブラリのみ使用 (追加依存なし)。 `Packages.zst` (zstd 圧縮インデックス) は標準ライブラリで扱えないため対象外。

#### 処理フロー

1. **設定ファイルのパース**: JSON を `parse_config(path: Path) -> SysrootConfig` で読む。 バリデーション: `name` 非空 (`[a-zA-Z0-9_\-\.]+`)、 `arch` 非空 (`arm64` 想定、 他値は警告ログ)、 `packages` / `repos` / `repos[].suites` / `repos[].components` は 1 つ以上の非空配列、 `repos[].url` は `http://` または `https://` 始まり (末尾 `/` は正規化で削除)、 `repos[].allow_insecure` は bool (デフォルト false)、 `post_install_symlinks[].link` は `<dest>` 相対 (絶対パス・先頭 `/`・`..` 含む値は CRITICAL abort = パストラバーサル防止)、 `post_install_symlinks[].file` は basename のみ (`/` または `..` を含む値は CRITICAL abort)。 JSON スキーマで定義された任意フィールド (`rust_target` 等) は黙って無視、 スキーマ外の真の未知フィールドは警告ログを出して無視
2. **usrmerge symlink を `<dest>` 直下に先行作成**: `.deb` 展開前に `<dest>` 直下に `lib` -> `usr/lib`, `bin` -> `usr/bin`, `sbin` -> `usr/sbin` の 3 symlink を張る (`.deb` 内が `/lib/...` 配下にファイルを置く transitional package があっても symlink 経由で `/usr/lib/...` に書き込まれて usrmerge 状態に統一される)。 aarch64 では `usr/lib64` は不要のため `lib64` symlink は作らない
3. **Packages インデックスの取得・解析**: 各 repo の `<url>/dists/<suite>/<component>/binary-<arch>/Packages.xz` を取得。 HTTP 404 (= 未配布) なら即 `Packages.gz` にフォールバック (NVIDIA / RPi は `.xz` を配布せず `.gz` のみ)、 両方とも 404 なら CRITICAL abort。 非圧縮 `Packages` (拡張子なし) は archive.raspberrypi.org / NVIDIA でも 200 で配布されているが、 APT 公式の圧縮形式優先の慣例に従い sysroot.py は対象外とする (将来必要なら別 issue で追加)。 5xx / network error は worker 内で 3 回まで 1 秒 sleep でリトライ。 並列度は `--jobs` 個まで (`concurrent.futures.ThreadPoolExecutor`)、 エラー伝播は fail-fast (`as_completed` で 1 つでも例外なら残りを `cancel()` してから再 raise)。 TLS と proxy は Python 標準ライブラリ defaults を尊重する (`urllib.request.getproxies()`、 `ssl.create_default_context()`)。 `ssl.create_default_context()` で生成した `SSLContext` は module-level で 1 つだけ生成し、 **構成後は読み取り専用の定数とみなして** 全 worker で共有する (`SSLContext` は CPython 標準で thread セーフな共有が前提。 shiguredo-python の「グローバル可変状態を持たない」 規約への違反ではなく immutable 共有資源としての扱い)。 取得した Packages を `lzma.decompress` / `gzip.decompress` で伸長し `Package:` ブロックを行ベースでパースして 1 つの `dict[str, PackageMeta]` に統合する。 統合順序: `repos` 配列内では各 repo の `suites` 配列の先頭から末尾の順、 各 suite 内では `components` 配列の先頭から末尾の順、 同一 (suite, component) 内では Packages ファイル内出現順で **同一 repo 内は配列末尾が後勝ち** (apt の updates 反映と同等。 NVIDIA の Packages.gz には同名パッケージの複数バージョンが平然と並んでいる前提)。 `Provides:` は別 dict (キー: 仮想パッケージ名、 値: 実 provider 名のリスト) に展開する
4. **依存解決**: roots (JSON の `packages` 配列) から `Depends:` と `Pre-Depends:` の和集合を再帰的に辿る。 `Recommends:` / `Suggests:` / `Breaks:` / `Conflicts:` / `Replaces:` は無視。 各依存候補について以下を適用 (OR 依存 `a | b | c` は左から、 単独依存はそのまま):
   - 同名の実パッケージが `dict[str, PackageMeta]` に存在すれば採用 (この際の repo 横断選択は **`repos` 配列順で最初に見つかった repo を優先** = jetson の `nvidia-jetpack` は NVIDIA common、 `nvidia-l4t-camera` は t234、 RPi の `libcamera-dev` は archive.raspberrypi.org から確実に取得される)
   - 存在しなければ `Provides:` インデックスで仮想パッケージとして解決を試み、 該当する実 provider のリストを `sorted()` した先頭を採用 (Packages ファイル内出現順は repo mirror で安定しないため `sorted()` で決定的に)
   - 仮想パッケージとして該当 provider も無ければ「純粋仮想依存」 として skip し、 OR 依存なら次の候補へ進む
   - OR 依存の全候補が純粋仮想、 または単独依存が純粋仮想だった場合は CRITICAL abort (意図せぬ MTA / cron 等の混入を防ぐ)。 abort 時の対応: 該当パッケージを JSON の `packages` から除外するか、 JSON で代替 provider を明示する形に修正する (後続 issue で `excludes` フィールド等の追加を検討)
   - バージョン制約 (`>= 1.0`) は評価せず、 `dict[str, PackageMeta]` の最新エントリ (処理フロー 3 の後勝ち結果) を採用
   - `Essential: yes` パッケージは依存集合に追加しない (cross-compile 用 sysroot に `dpkg` / `apt` 等は不要)
   - 循環依存・既訪問は visited set でガード (`graphlib.TopologicalSorter` には循環を持ち込まない)
5. **`.deb` のダウンロード**: Packages インデックスから得た URL を `--jobs` 個まで並列取得し、 Packages 内の `SHA256:` フィールドと照合 (不一致なら即 abort、 `allow_insecure: true` でも SHA256 検証は維持)。 キャッシュ内ファイル名は `<package_name>_<version>_<arch>_<sha256[:12]>.deb` の正規化形式 (repo 間衝突を完全に防ぐ)。 既存ファイルの SHA256 が一致すれば再ダウンロードしない
6. **`.deb` の展開**: `dpkg-deb -x <package>.deb <dest>` を **シーケンシャル実行** する (同名ファイル衝突の決定性を保証するため、 並列禁止)。 展開順は `graphlib.TopologicalSorter` で依存グラフから topological order を計算し、 同レベルのノード間は `add()` 呼び出し順 (JSON `packages` リスト順 + transitive 発見順) を tie-breaker とする。 同名ファイルは後勝ちで上書き。 `subprocess.run([...], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)` で呼び、 非 0 終了時は `CalledProcessError.stderr` をログに含めて raise する (`stdout` は捨てて巨大ログのメモリ消費を避ける)。 `update-alternatives` 系の master symlink は postinst 未実行のため作成されないが、 cross-compile では実害なし
7. **絶対パス symlink の相対化**: `fix_absolute_symlinks(root: Path) -> None` で `<dest>` 内の絶対パス symlink を相対パスに置き換える (`buildbase.py:install_rootfs` の挙動を機能等価で移植)
8. **post_install_symlinks の補完**: JSON の `post_install_symlinks` 配列を読み、 各エントリ `{link, file}` について以下を冪等に適用する:
   ```
   target_file = Path(root) / Path(link).parent / file
   link_path = Path(root) / link
   if target_file.exists() and not link_path.exists():
       link_path.symlink_to(file)
   ```
   `link` と `file` は必ず同一ディレクトリ (file は basename のみ)。 NVIDIA 公式 `.deb` 内に `libnvbuf_fdmap.so` -> `libnvbuf_fdmap.so.1.0.0` 等の symlink が含まれない問題に対応する
9. **キャッシュ stamp**: `<dest>/.sysroot.stamp` に `sha256(JSON content + sysroot.py 自身の SHA256)` を書き込む。 `build` 時に stamp 一致なら全処理 skip (`--force` 無し時)。 sysroot.py の空白・コメント変更でも SHA256 が変わるため再構築されるが、 これは許容する (品質より再現性を優先)。 host 環境 (`dpkg-deb` バージョン等) は stamp に含めない (運用環境を ubuntu-24.04 x86_64 host 限定にしている前提。 host 更新時は手動で `--force` または `clean`)

`Release` / `InRelease` の OpenPGP 署名検証と Release ファイル経由の Packages 整合性検証は **どちらも行わない** (multistrap の `noauth=true` 相当)。 Python 標準ライブラリで OpenPGP を扱えないため。 `.deb` ファイル単位の改ざん検出は Packages 内 `SHA256:` 経由で行う (Packages ファイル自身の改ざんは検出不能、 multistrap と同レベルの threat model)。

### sysroot/*.json の新設

`shiguredo/webrtc-rs` と `shiguredo/momo` の `sysroot/*.json` ディレクトリ配置と JSON スキーマ慣例に合わせる。 packages / repos は sora-python-sdk 固有の組み合わせ。

#### JSON スキーマ

`SysrootConfig`:

| key | 型 | 必須/任意 | 説明 |
|---|---|---|---|
| `name` | string | 必須 | ログ・stamp 表示用。 `[a-zA-Z0-9_\-\.]+` パターン、 非空必須 |
| `arch` | string | 必須 | `arm64` を想定。 他値は警告ログを出してそのまま使用 |
| `packages` | string[] | 必須 | 1 つ以上の非空配列。 依存解決の roots |
| `repos` | Repo[] | 必須 | 1 つ以上の Repo 配列 |
| `post_install_symlinks` | PostInstallSymlink[] | 任意 (デフォルト `[]`) | jetson 用 symlink 補完 |
| `rust_target` / `linker` / `cc` / `cxx` / `cflags` / `cxxflags` | 任意 | Python では無視 (webrtc-rs / momo スキーマ互換のため許容) |

`Repo`:

| key | 型 | 必須/任意 | 説明 |
|---|---|---|---|
| `url` | string | 必須 | `<url>/dists/<suite>/<component>/binary-<arch>/Packages.{xz,gz}` を取得。 `http://` または `https://` 始まり、 末尾 `/` 正規化 |
| `suites` | string[] | 必須 | 1 つ以上の非空配列。 同一 repo 内は配列末尾が後勝ち |
| `components` | string[] | 必須 | 1 つ以上の非空配列。 同一 suite 内は配列末尾が後勝ち |
| `allow_insecure` | bool | 任意 (デフォルト false) | webrtc-rs / momo スキーマには無い拡張。 現時点では sysroot.py の挙動に差は無い (GPG 検証は常に行わない)。 将来 GPG 検証を導入する際の拡張点 |

`PostInstallSymlink`:

| key | 型 | 必須/任意 | 説明 |
|---|---|---|---|
| `link` | string | 必須 | `<dest>` 相対 symlink パス。 絶対パス・先頭 `/`・`..` を含む値は CRITICAL abort |
| `file` | string | 必須 | symlink target の basename のみ (`/` `..` を含む値は CRITICAL abort)。 `link` と同一ディレクトリの実体 |

#### 4 ファイルの内容

各 JSON の packages は既存 `multistrap/*.conf` の値を完全に保持する (本 issue は経路置換のため集合は変えない)。 suite は単一に絞る (`*-updates` / `*-security` は含めない、 multistrap 経路と取得バージョンが概ね一致する)。 repos URL は webrtc-rs / momo の慣例に合わせて APT 正規 layout (`ports.ubuntu.com/ubuntu-ports`) を使う。 `repos` 配列順は依存解決ルール「先頭優先」 を意識した順序にする (各パッケージが意図した repo から取得されるよう設計):

| ファイル | 主要 packages | repos (配列順 = 先頭優先) |
|---|---|---|
| `sysroot/ubuntu-22.04_armv8.json` | `libc6-dev`, `libstdc++-11-dev`, `libxext-dev`, `libdbus-1-dev` | `http://ports.ubuntu.com/ubuntu-ports` jammy, main+universe |
| `sysroot/ubuntu-24.04_armv8.json` | `libc6-dev`, `libstdc++-13-dev`, `libxext-dev`, `libdbus-1-dev` | `http://ports.ubuntu.com/ubuntu-ports` noble, main+universe |
| `sysroot/ubuntu-22.04_armv8_jetson.json` | `libc6-dev`, `libstdc++-10-dev`, `libxext-dev`, `libdbus-1-dev`, `nvidia-jetpack`, `nvidia-l4t-camera`, `nvidia-l4t-multimedia` | (1) `http://ports.ubuntu.com/ubuntu-ports` jammy main+universe, (2) `https://repo.download.nvidia.com/jetson/common` r36.3 main (allow_insecure), (3) `https://repo.download.nvidia.com/jetson/t234` r36.3 main (allow_insecure) |
| `sysroot/raspberry-pi-os_armv8.json` | `libc6-dev`, `libstdc++-11-dev`, `libcamera-dev`, `libasound2-dev`, `libpulse-dev`, `libudev-dev`, `libexpat1-dev`, `libnss3-dev`, `libxext-dev`, `libxtst-dev` | (1) `http://archive.raspberrypi.org/debian` bookworm main (allow_insecure), (2) `http://deb.debian.org/debian` bookworm main |

設計判断:

- jetson の `packages` は `multistrap/ubuntu-22.04_armv8_jetson.conf` の `[Ports]` / `[Jetson]` / `[T234]` 3 section の packages をフラットに合成。 解決ルール「先頭優先 + 同名は実パッケージ優先」 により、 Ubuntu 公式パッケージは ports から、 NVIDIA 系は nvidia repos から自然に分離して取得される
- RPi の `repos` は archive.raspberrypi.org を **先頭** に置く。 Debian bookworm 公式にも `libcamera-dev` は存在するが、 RPi 用カーネルパッチ版を確実に取得するため。 他パッケージは archive.raspberrypi.org に存在しないため自動的に Debian 公式から取得される
- jetson の `nvidia-jetpack` は meta-package で transitive 依存が大きい。 実装着手時の依存ツリー確認は完了条件「事前確認」 で扱う (host の apt を介さず Packages.gz を `curl | gunzip | awk` で直接読む)

jetson 用 `post_install_symlinks` (4 ファイル中 jetson のみ):

```json
"post_install_symlinks": [
    { "link": "usr/lib/aarch64-linux-gnu/tegra/libnvbuf_fdmap.so",  "file": "libnvbuf_fdmap.so.1.0.0" },
    { "link": "usr/lib/aarch64-linux-gnu/nvidia/libnvbuf_fdmap.so", "file": "libnvbuf_fdmap.so.1.0.0" }
]
```

JetPack 6 (L4T r36) 以降は `nvidia/` ディレクトリのみ実体が存在する想定。 旧 L4T r35 系は `tegra/` 側のみだったため両方を許容 (実体非存在側は何も作らない、 冪等に動作)。

### fetch_deps.cmake への `_sora_fetch_rootfs` 関数定義

`cmake/scripts/fetch_deps.cmake` の **`_sora_fetch_llvm` 関数定義の直後、 `# ---------- メインスクリプト ----------` コメント行の直前** に `_sora_fetch_rootfs(rootfs_dir json_config)` を追加する。 メインスクリプトからは呼び出さない。

設計上の要点:

- 関数シグネチャは 2 引数 (`rootfs_dir`, `json_config`) のみ。 既存 `_sora_fetch_archive` 等が `stamp_path` を取って CMake 側で stamp 比較するのと異なり、 stamp 管理は sysroot.py 側に閉じる (Python で SHA256 計算するのが自然)
- 関数冒頭で `${CMAKE_SOURCE_DIR}/sysroot.py` の存在を `if(NOT EXISTS ...)` で確認し、 不在なら `message(FATAL_ERROR ...)`
- 中身は `${Python_EXECUTABLE} ${CMAKE_SOURCE_DIR}/sysroot.py build --config ${json_config} --dest ${rootfs_dir}` を `execute_process` で起動し、 非 0 終了で `message(FATAL_ERROR ...)`
- 関数本体のロジックは本 issue では動的検証されない (cmake は呼ばれない関数の構文のみ parse する)。 後続 cross 系 issue で実呼び出ししたときに初めて関数本体の bug が顕在化する可能性があり、 本 issue では構文エラーのみ検出可能

### MANIFEST.in の更新

既存 `MANIFEST.in` (4 行) に以下を追加する:

```
include sysroot.py
recursive-include sysroot *.json
```

`uv build --sdist` で sysroot.py と sysroot/*.json を sdist に含めるため。 `MANIFEST.in` 自体は 0022 で削除予定だが、 本 issue merge 後 0022 merge 前の期間に sdist 配布物として欠落しないよう明示する。 scikit-build-core 経由でも `MANIFEST.in` は読まれるが、 sdist 生成時に取り込まれない場合は `pyproject.toml` の `[tool.scikit-build.sdist.include]` 設定を併用する形に切り替える (実装着手時に検証する)。

### multistrap/ の削除と .github/workflows/build.yml の更新

- `multistrap/` ディレクトリと配下 4 ファイルを `git rm -r multistrap/` で削除する
- `.github/workflows/build.yml` から `if: matrix.platform.arch == 'armv8'` の 2 step (multistrap install + sed パッチ、 および `uv run python run.py build && uv build`) をまるごと削除する
- 削除後の `build_ubuntu` job には armv8 用 build step が無くなる。 対象 matrix entry は `exclude:` 済のため CI 自体は green を維持する。 cross-compile wheel ビルドの復活は後続 cross 系 issue で行う

### CHANGES.md の更新

`## develop` セクションに次の 2 エントリを追加する (`shiguredo-changelog` 規約):

```
- [CHANGE] cross-compile 用 sysroot 構築から multistrap を廃止する
  - multistrap は Debian/Ubuntu 上流のメンテが停滞しており、 Ubuntu 26.04 で配布終了見込みのため
  - 本 PR merge 後、 armv8 系 cross-compile wheel は CI で生成されない (元から matrix exclude 済)。 後続 cross 系 issue で sysroot.py 経由に切り替えて再開する
  - @voluntas
- [ADD] cross-compile 用 sysroot 構築スクリプト sysroot.py と sysroot/*.json を追加する
  - リポジトリルートに sysroot.py、 sysroot/ 配下に ubuntu-22.04_armv8 / ubuntu-24.04_armv8 / ubuntu-22.04_armv8_jetson / raspberry-pi-os_armv8 用 JSON を配置
  - @voluntas
```

## 完了条件

以下の検証コマンドは ubuntu-24.04 x86_64 host (GNU coreutils / GNU find / GNU awk / bash 4 以降) で実行する。 macOS の BSD find / awk では `-lname` / `-printf` 等が動かない。

### 事前確認 (PR description に結果を記載)

- `https://launchpad.net/ubuntu/+source/multistrap` の Latest version 更新日と `https://salsa.debian.org/installer-team/multistrap` の最新 commit 日時 (上流停滞の根拠。 `apt list multistrap` の `deprecated` / `obsolete` grep は Debian/Ubuntu の `apt` がパッケージ状態の deprecated マークを返さないため使えない)
- jetson の `nvidia-jetpack` 依存ツリー確認 (host の apt は repo を追加しない限り nvidia パッケージを認識しないため、 Packages.gz を直接読む):

  ```
  curl -s 'https://repo.download.nvidia.com/jetson/common/dists/r36.3/main/binary-arm64/Packages.gz' \
    | gunzip | awk '/^Package: nvidia-jetpack$/{flag=1} flag; /^$/{flag=0}'
  ```

  `awk` パターンの `^Package: nvidia-jetpack$` で末尾アンカーを必ず付け、 `nvidia-jetpack-dev` / `nvidia-jetpack-runtime` を誤って拾わないようにする。 出力の `Depends:` と `Pre-Depends:` を目視し、 純粋仮想依存 (`mail-transport-agent` 等) が含まれないことを確認する。 含まれる場合は JSON の `packages` を個別 `nvidia-l4t-*` パッケージのサブセットに切り替えるか、 OR 依存の代替を明示する
- `dpkg-deb --version` の 1 行目 (`data.tar.zst` 対応の `1.21.x` 以降であること)
- `uv build --sdist && tar tzf dist/*.tar.gz | grep -E 'sysroot(\.py|/.*\.json)$'` で sysroot.py と sysroot/*.json が sdist に含まれていること (本 issue で MANIFEST.in に追加した行の有効性確認)

### rootfs 構築の検証 (PR description にコマンド実行ログを markdown コードブロックで貼る)

jetson rootfs は 8 GB に達するため `/tmp` (GitHub Actions runner は ~14 GB) で 4 platform 全てを同時に保持できない。 ローカル検証では **1 platform ごとに `clean` してから次へ進む** (`build A → 検証 A → clean A → build B → ...`)。 別の選択肢として jetson のみ `--dest /var/tmp/rootfs-jetson` (Linux で `/var/tmp` は ~30 GB 級) を使う:

```
python3 sysroot.py build --config sysroot/ubuntu-22.04_armv8.json --dest /tmp/rootfs-target
# 下記検証を実施 → ログを PR description に貼る
python3 sysroot.py clean --dest /tmp/rootfs-target

python3 sysroot.py build --config sysroot/ubuntu-24.04_armv8.json --dest /tmp/rootfs-target
# 検証 → clean → ...

python3 sysroot.py build --config sysroot/ubuntu-22.04_armv8_jetson.json --dest /var/tmp/rootfs-jetson
# 検証 → clean

python3 sysroot.py build --config sysroot/raspberry-pi-os_armv8.json --dest /tmp/rootfs-target
# 検証 → clean
```

各 rootfs について以下を確認 (`<rootfs>` は `--dest` で指定したディレクトリ):

- `<rootfs>/usr/include/aarch64-linux-gnu/sys/types.h` が存在 (`libc6-dev` 展開で得られる)
- `cstddef` ヘッダが存在 (platform 別に明示的に `test`):
  - ubuntu-22.04_armv8 / raspberry-pi-os_armv8: `test -e <rootfs>/usr/include/c++/11/cstddef`
  - ubuntu-24.04_armv8: `test -e <rootfs>/usr/include/c++/13/cstddef`
  - ubuntu-22.04_armv8_jetson: `test -e <rootfs>/usr/include/c++/10/cstddef`
- `find <rootfs> -type l -lname '/*' | wc -l` が 0 (絶対パス symlink が残っていない)
- `<rootfs>/lib` / `<rootfs>/bin` / `<rootfs>/sbin` の usrmerge symlink が張られている
- MTA / cron 系 binary (`exim4`, `sendmail`, `postfix`, `cron`) が `<rootfs>/usr/sbin/` 配下に存在しない (純粋仮想 abort 設計が機能していることの確認)
- 各 rootfs のファイル内容合計サイズ (`find <rootfs> -type f -printf '%s\n' | awk '{s+=$1}END{print s}'`) が次の上限以下:
  - ubuntu-22.04_armv8 / ubuntu-24.04_armv8: 200 MB
  - raspberry-pi-os_armv8: 300 MB
  - ubuntu-22.04_armv8_jetson: 8 GB (事前確認で 8 GB を超える見込みなら JSON の `packages` を `nvidia-l4t-core` 等のサブセットに絞る)
- 構築時間: ubuntu / RPi 系は 5 分以内、 jetson は 30 分以内 (シーケンシャル展開の累積時間。 30 分を超える場合は `extract_debs` 並列化 + 同名衝突対策の別 issue 起票を検討)
- jetson 追加: `<rootfs>/usr/lib/aarch64-linux-gnu/nvidia/libnvbuf_fdmap.so.1.0.0` 実体が存在する場合に同ディレクトリの `libnvbuf_fdmap.so` symlink が張られている (実体非存在側は symlink も無い)
- RPi 追加: `<rootfs>/usr/include/libcamera/libcamera.h` 相当のヘッダが存在 (archive.raspberrypi.org 由来の `libcamera-dev` 確認)
- `uv run ruff check sysroot.py` と `uv run ruff format --check sysroot.py` が pass (ruff lint は本 issue scope。 ty は別 issue。 整合性検証は完了条件 4 コマンドの integration build で代替)

### キャッシュ動作

- 2 回目以降の build で stamp 一致時に全処理が skip され `find <rootfs> -newer <rootfs>/.sysroot.stamp -print` が空
- sysroot.py を 1 行変更すると stamp 不一致で再構築される
- `--force` で stamp 一致時も強制再構築される
- `clean` で `<dest>` と `<dest>/.sysroot.stamp` と `<dest>/.debs/` が削除される

### 削除確認

- `test ! -d multistrap`
- `grep -nc multistrap .github/workflows/build.yml` が 0
- `grep -nE '_sora_fetch_rootfs\b' cmake/scripts/fetch_deps.cmake` が関数定義 1 件のみ (呼び出し 0 件)
- `grep 'sysroot' MANIFEST.in` で `include sysroot.py` と `recursive-include sysroot *.json` が確認できる
- `build_ubuntu` matrix の `exclude:` が armv8 / RPi entry を引き続き無効化していて、 本 issue merge 後も `ubuntu-24.04_x86_64` × 3 Python の native build entry のみが実行される

## 解決方法

「設計方針」 セクションの各サブセクションを順次実装する。 shiguredo-git の「1 コミット = 1 論理的変更」 と「各コミットで CI green を維持」 を両立するため、 以下の 6 コミットに分ける:

1. `sysroot/` ディレクトリ + 4 つの JSON ファイル新設 + `MANIFEST.in` に `recursive-include sysroot *.json` 追加
2. `sysroot.py` 新設 (shiguredo-python 規約準拠で実装) + `MANIFEST.in` に `include sysroot.py` 追加
3. ローカル ubuntu-24.04 x86_64 host で完了条件 4 コマンドを実行し検証 (コミットは作らない、 PR description にログ貼り付け)
4. `cmake/scripts/fetch_deps.cmake` のヘルパ関数領域末尾に `_sora_fetch_rootfs` 関数定義追加
5. `multistrap/` 削除 + `.github/workflows/build.yml` から multistrap 系 2 step 削除 (両者を 1 コミットにすることで CI が中間状態で壊れない)
6. `CHANGES.md` に `[CHANGE]` + `[ADD]` の 2 エントリ追記

## ロールバック

`sysroot.py` の根本設計 (APT Packages Index 直接解析 + `dpkg-deb -x` 展開) に起因する不具合で追加コミットで前進できない場合に revert を選ぶ。 個別パッケージ解決の不具合や JSON 設定の誤りは追加コミットで前進させる。

手順: `git revert -m 1 <merge-commit>` で revert PR を作成し merge する。 revert 後の状態確認:

- `test -d multistrap && ls multistrap/*.conf | wc -l` が 4
- `grep -nc multistrap .github/workflows/build.yml` が 2 以上 (multistrap install + sed パッチ復活)
- `test ! -f sysroot.py && test ! -d sysroot`
- `grep -nE '_sora_fetch_rootfs\b' cmake/scripts/fetch_deps.cmake` が 0 件
- `build_ubuntu` matrix の `exclude:` が armv8 / RPi entry を引き続き無効化していて CI が green

キャッシュディレクトリ (`<dest>/.debs/` と `<dest>/.sysroot.stamp`) はそのまま残しても無害 (次回 build まで参照されない)。
