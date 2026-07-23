# Ubuntu arm64 と Raspberry Pi OS の multistrap をやめて署名検証付き sysroot に切り替える

- Priority: High
- Created: 2026-07-23
- Completed: -
- Model: Cursor Grok 4.5
- Branch: feature/change-multistrap-to-sysroot
- Polished: 2026-07-23

## 目的

現行の `multistrap` + HTTP + `--no-auth` / CI での `/usr/sbin/multistrap` 書き換えによる insecure な rootfs 構築をやめ、 webrtc-build 系の署名検証付き sysroot builder（HTTPS + `signed-by`）へ切り替える。

対象は現行の `run.py` / `buildbase.py` / `setup.py` 経路のままとする。 scikit-build-core 化 、 `fetch_deps.cmake` 、 Makefile / debug workflow の再設計は前提にしない。

Ubuntu arm64 （ 22.04 / 24.04 ）と Raspberry Pi OS arm64 の rootfs をまとめて置き換える。 Jetson は 0043 で扱う。

## 優先度根拠

High とする。

- CI が `/usr/sbin/multistrap` を `sed` で書き換え、 `Acquire::AllowInsecureRepositories=true` を注入している（ `.github/workflows/build.yml` L143-146 と L209-212 の 2 箇所）。
- `buildbase.py` の `install_rootfs()` が `multistrap --no-auth` を実行している。
- Ubuntu / Raspberry Pi OS 用 conf が HTTP の archive を参照している。
- `multistrap` 自体も Debian unstable から削除済みで、 runner 更新の障害になる。
- README は Raspberry Pi OS Trixie をサポート対象としているが、現行 `multistrap/raspberry-pi-os_armv8.conf` は Bookworm のままである。
- 0003 / 0004 / 0061 は 2026-07-23 に「実装せず本 issue に統合」で closed 済みで、後続の 0043 / 0071 / 0072 / 0073 は本 issue の成果物を前提にする。

## 現状

- `run.py` L52-68 の `install_deps()` が 4 target（ `ubuntu-22.04_armv8_jetson` / `raspberry-pi-os_armv8` / `ubuntu-22.04_armv8` / `ubuntu-24.04_armv8` ）で `install_rootfs()` を呼ぶ。 分岐は `platform.target.package_name` だけを見ており、 build host の arch （ `platform.build.arch` ）は考慮しない。
- `buildbase.py` L1074-1118 の `install_rootfs()` は `@versioned` decorator を伴い、 `multistrap --no-auth -a arm64 -d rootfs_dir -f conf` を実行してから、絶対 symlink の相対化を後処理し、さらに Jetson 固有の `libnvbuf_fdmap.so` 相対 symlink 作成（ tegra / nvidia の 2 箇所）を副作用として持つ。
- `run.py` L60-64 で conf の MD5 を計算し `install_dir/rootfs.version` に保存する。 conf 変更以外の要因（ keyring 更新、生成ロジック改変）は cache に反映されない。
- `run.py` L302 の cross build 分岐は `platform.build.arch != platform.target.arch` で `CMAKE_SYSROOT` / `CMAKE_FIND_ROOT_PATH` を渡す。 arm64 native runner での build （ `build_ubuntu_arm` ）ではこの分岐に入らない。
- `multistrap/*.conf` は 4 ファイル。 Ubuntu 2 conf は `noauth=true` / `ignorenativearch=true` を持ち、 HTTP `http://ports.ubuntu.com` を参照する。 Raspberry Pi OS conf は `noauth` を持たないが Bookworm の HTTP archive を参照する。 Jetson conf は本 issue の対象外。
- `.github/workflows/build.yml` の armv8 matrix は 2 種類ある。
  - `build_ubuntu` job (L84-170)：ubuntu-24.04 / ubuntu-22.04 の x86_64 host から cross build する 3 entry（ `ubuntu-22.04_armv8` / `ubuntu-24.04_armv8` / `raspberry-pi-os_armv8` ）。 L142-146 で `if: matrix.platform.arch == 'armv8'` の分岐に入り、 multistrap install + `/usr/sbin/multistrap` の insecure sed patch を実行する。
  - `build_ubuntu_arm` job (L172-228)：arm64 native runner 上で `ubuntu-22.04_armv8` / `ubuntu-24.04_armv8` を build する 2 entry。 L209-212 で無条件に同じ multistrap install + insecure sed patch を実行する。
- Raspberry Pi OS wheel の distribution 名 `sora_sdk_rpi` は `build.yml` L133-136 の `sed -e 's/^name = "sora_sdk"/name = "sora_sdk_rpi"/' -i pyproject.toml` で書き換えて実現する（前後件数の検証は無い）。
- `libcamerac.so` は Sora archive から `run.py` L420-423 で `src/sora_sdk/` へ `shutil.copyfile` してから、 `setup.py` L37-39 の `package_data.additional_files` で wheel に同梱する。 CMake 側では touch しない。
- `pyproject.toml` の `[tool.ty.src].include` は `["src", "tests"]` のみ。 リポジトリルート直下の `.py` は ty の対象に含まれていない。 ruff は既定で `**/*.py` を対象とするため追加設定は不要。 `MANIFEST.in` は `buildbase.py` / `run.py` / `pypath.py` / `VERSION` の 4 行のみで、 sdist からのフルビルドは想定されていない（wheel が主配布物）。

## スコープ

含む:

1. リポジトリルートに `sysroot_builder.py` を追加する（module と CLI を 1 ファイルに同梱、 CLI 専用の別ファイルは作らない）。
2. `tests/sysroot_builder/test_sysroot_builder.py` を追加する（ネットワーク・モック・スタブ禁止）。 pytest は rootdir からテストファイルの親までにあるすべての `conftest.py` をロードする仕様のため、単に子 `conftest.py` を空で置いても親 `tests/conftest.py` の `from sora_sdk import SoraLoggingSeverity` は必ず実行される。 拡張未 build 時でも sysroot builder の単体テストを走らせるため、 pytest 実行時に `--confcutdir=tests/sysroot_builder` を渡す運用を採用する（子 `conftest.py` は追加しない）。
3. `sysroot/` ディレクトリを新設し、 3 target の JSON を追加する。 keyring は `sysroot/keyrings/` に配置する。
   - `sysroot/ubuntu-22.04_armv8.json`
   - `sysroot/ubuntu-24.04_armv8.json`
   - `sysroot/raspberry-pi-os_armv8.json`
   - `sysroot/keyrings/debian-archive-keyring.gpg`
   - `sysroot/keyrings/raspberrypi-archive-keyring.asc`
4. `RepositoryConfig` に optional `pin_priority: int | None` を追加する（詳細は「設計方針 › repository pinning 」節）。
5. `run.py` の `install_deps()` を書き換え、 `platform.target.os == "jetson"` 以外の 3 target について build host が cross build のときだけ sysroot builder を呼ぶ。 Jetson だけは `install_rootfs()` を継続呼び出しする。
6. `run.py` に `install_sysroot()` helper 関数を追加する（`buildbase.py` は melpon/buildbase テンプレートで `curl -LO` 上書き更新想定のため、リポジトリ固有の追加関数は `run.py` 側に置く）。 既存 `install_*` の `@versioned` パターンとは意図的に別系統。 `install_rootfs()` （テンプレート由来）は Jetson 用にそのまま呼び続ける（改名しない）。
7. Ubuntu / Raspberry Pi OS 用 `multistrap/*.conf` を 3 ファイル削除する（Jetson conf は残す）。
8. `.github/workflows/build.yml` の 2 箇所（ L142-146 と L209-212 ）から multistrap install と `/usr/sbin/multistrap` の insecure sed patch を削除する。
9. `.github/workflows/build.yml` の `build_ubuntu` / `build_ubuntu_arm` に必要な依存インストールを追加する（各 job / entry ごとの粒度は「設計方針 › CI 」節を参照）。
10. Raspberry Pi OS を Trixie に合わせる（ Bookworm conf は残さない）。 `libstdc++-11-dev` を `libstdc++-14-dev` へ引き上げる。
11. `pyproject.toml` の `dependency-groups.test` に `pytest-timeout~=2.4.0` （ compatible release 、 `>=2.4.0, <2.5.0` を意味する）を追加し、 `uv.lock` を更新する。 他 test 依存は unpinned のままとするが、新規 unit test で `--timeout=10` を渡すため `pytest-timeout` の 2.4 minor 系列を固定する。 依存 pin 方針の全体整合は `refresh-issue` の対象として別途扱う。
12. `pyproject.toml` の `[tool.ty.src].include` に `"sysroot_builder.py"` を追記する。 ruff は既定で拾うため設定変更しない。
13. `MANIFEST.in` は変更しない（ `sysroot_builder.py` / `sysroot/` を sdist に含めない）。
14. `CHANGES.md` `## develop` に entry を追加する（後述）。

含まない:

- Jetson （ `ubuntu-22.04_armv8_jetson` / `multistrap/ubuntu-22.04_armv8_jetson.conf` / `install_rootfs()` の Jetson 固有 side effect ）。 0043 で扱う。
- scikit-build-core 化、 `fetch_deps.cmake` 、 Makefile / debug workflow の再設計。
- `auditwheel` / publish / E2E の再設計。 `setup.py` の手動 manylinux tag （`manylinux_2_31_aarch64` / `manylinux_2_35_aarch64`）と Trixie glibc の整合、および `libstdc++-14-dev` 引き上げに伴う libstdc++ ABI （`GLIBCXX_3.4.32` 以降）の bundling / auditwheel 再検証は本 issue のスコープ外とし、既存経路を壊さない範囲でビルドが通れば良い。 0052 / 0066 / 0067 で扱う。
- arm64 native build の廃止判断。 0068 が扱う。本 issue は arm64 native runner でも multistrap install と insecure sed patch を除去するのみで、 sysroot builder は build host が cross build（ `platform.build.arch != platform.target.arch` ）の場合だけ呼ぶ。
- `build.yml` L133-136 の `sora_sdk_rpi` への `sed` 書き換えを検証付きに強化する変更（別 issue で扱う）。
- `libcamerac.so` 同梱経路を CMake の `install(FILES ...)` へ切り替える変更（別 issue で扱う）。
- `_deps/.fetch.lock` 等の scikit-build-core 前提の並列 configure lock 。同一 `install_dir/rootfs` を触る `run.py build` を並列実行しないことを前提とする。
- WebRTC / Sora / Boost archive の SHA-256 検証。 0070 で扱う。
- CI job 間の sysroot cache 。 0071 で扱う。同一 checkout 内の再利用は本 issue で検証する。
- `_install/<target>/rootfs` を CI job 冒頭で削除する step の追加。 CI は GitHub-hosted の fresh runner を毎 job で使うため事前削除は不要。 0071 の cache 導入後に fingerprint mismatch が問題化した場合は 0071 で扱う。

## 設計方針

### sysroot builder の移植元と契約

- 移植元は webrtc-build の `sysroot_builder.py` / `tests/sysroot_builder/test_sysroot_builder.py` 。 canonical source として `59a0ce0` （日本語コメント付き版）を採用し、 `2c15196` （コメント除去前の実装）は履歴として pin する。 本リポジトリでは webrtc-build から直接移植し、 sora-cpp-sdk 側の派生実装は参考に留める（ sora-cpp-sdk 側は本 issue が求める `pin_priority` を持たないため、移植元にはできない）。
- `SysrootConfig` / `RepositoryConfig` を frozen dataclass とし、 JSON の必須値、重複、使用可能文字を APT 実行前に検証する。
- リポジトリ URL は HTTPS だけを許可し、全リポジトリに `signed_by` を要求する。いずれの違反も validation error として拒否する。
- `APT_CONFIG` 、 `Dir::State` 、 `Dir::Cache` 、 `Dir::Etc::*` 、 `Dir::Etc::preferences` 、 `Dir::Etc::preferencesparts` を一時ディレクトリへ向け、ホストの `/var/lib/apt` と `/etc/apt` を読み書きしない。
- `APT::Architecture=arm64` を設定し、 `apt-get update` 、 `apt-get --download-only install` 、 `dpkg-deb --extract` の順で実行する。 maintainer script と chroot は使わず、 root 権限を要求しない。 `apt-get install` は `--no-install-recommends` 相当を有効にし、 JSON の `packages` に列挙した直接依存とその Depends だけを解決する（ Recommends は展開しない）。 これは cross-build に不要な runtime package を sysroot に混入させないための境界。
- usrmerge link 、 sysroot 内で解決できる絶対 symlink の相対化、 triplet 固有 pkg-config file への互換 link を後処理する。解決不能な `/etc/alternatives` 等の絶対 symlink は変更しない。 Jetson が `install_rootfs()` 側で行う `libnvbuf_fdmap.so` 相対 symlink 作成は sysroot builder には移植しない（両者は APT dpkg-deb 出力と multistrap 出力の別々のデータに対して独立に共通の絶対 symlink 相対化を行う）。
- 設定値と署名鍵内容の SHA-256 、 `MANIFEST_VERSION` を manifest に保存する。 fingerprint の入力は「 JSON 内容 + keyring 内容 + `MANIFEST_VERSION` 」であり、生成物の完成後に manifest として 1 ファイルにまとめて書く。同一 fingerprint は再利用し、不一致の既存出力は `--force` 無しでは削除しない。
- 同じ親ディレクトリの一時領域で完成させ、 rename によって出力先を入れ替える。失敗時は既存 sysroot を戻す。 APT download / deb 展開 / 後処理が失敗した段階では既存 sysroot に触れない。
- manifest 名は cross repository で builder と生成物の形式を識別できる互換名として `.webrtc-build-sysroot.json` を恒久的に維持する。この意図を定数のコメントにも残す。後処理または生成形式を変えた場合は、同じ変更で `MANIFEST_VERSION` と該当テストを更新する。
- APT が解決した package version は manifest の `deb_files` に記録するが、 JSON では pin しない。「再利用」は同一設定で一度生成した sysroot を固定して使うことを意味し、 repository の時点再現までは保証しない。
- ログとエラーメッセージは英語、コメントとテストの説明は日本語とする。エラーメッセージの末尾にピリオドを付けず、ソースとテストのコメントに issue 番号を書かない。

### CLI 契約

- ドキュメント上の呼び出し形式（手動実行）：

  ```text
  python3 sysroot_builder.py --config <json> --dest <rootfs> [--force]
  ```

- CI や `install_sysroot()` からの呼び出しは `sys.executable` を使い、 `python` alias に依存しない。詳細は次節を参照。
- CLI は subcommand を設けず、設定を読み込み、 `config.name` と JSON のファイル stem が一致することを検証してから `build_sysroot()` を呼ぶ。
- `main(argv: Sequence[str] | None = None) -> int` と argument parser を分離して unit test 可能にする。
- 終了コードと出力の契約：
  - `SysrootConfigError` / `SysrootBuildError` / `subprocess.CalledProcessError` / 入出力に伴う `OSError` は英語のエラーを標準エラーへ出して `1` で終了する。
  - 成功または再利用は `0` で終了する。
  - 想定外の例外は原因調査のため stack trace を維持する（捕捉して 1 で潰さない）。
  - logging level は `INFO` とする。
- `--force` は由来不明または fingerprint 不一致の既存 rootfs を利用者が明示的に置き換える場合だけ使う。 `install_sysroot()` からは常に `False` で呼ぶ。開発者が依存を更新して sysroot を作り直す場合は、 CLI を直接叩いて `--force` を付ける。

### repository pinning

Raspberry Pi repository の overlay package を Debian repository より優先し、 Raspberry Pi OS 向けに調整された `libcamera-dev` / `libc6-dev` 等を確実に選ぶため、 `RepositoryConfig` に optional な `pin_priority: int | None` を追加する。

- 未指定時は APT の既定 priority を変更しない。
- 指定可能範囲は `1..1000` とし、 `bool` は拒否する。
- pin 対象は repository URL の hostname とし、 `urllib.parse.urlsplit()` で取得する。 userinfo 、 query 、 fragment 、 hostname 不在の URL を拒否する validation を本 issue で追加する。
- pin が 1 件以上あれば一時 work directory に `preferences` を生成し、 `_apt_options()` の `Dir::Etc::preferences` をそのファイルへ向ける。 `preferencesparts` は空の隔離 directory へ向け、 host の APT preferences を参照しない。
- stanza は `Package: *` / `Pin: origin "<hostname>"` / `Pin-Priority: <value>` とする。
- pin は hostname 全体へ作用するため、同じ hostname を持つ repository 間では `None` と数値の混在を含め、異なる `pin_priority` を validation error とする。
- repository object の未知 key を拒否し、 `pin_priority` の綴り間違いを黙って無視しない。
- `pin_priority` が指定された repository だけ fingerprint payload に同 field を追加する。未指定 repository へ `null` を追加せず、既存 pin 無し schema の fingerprint を変えない。 manifest 自体の schema は変えないため `MANIFEST_VERSION` は更新しない。

Raspberry Pi repository は `pin_priority: 990` とする。 Debian repository は pin しない。 Ubuntu 側は全て `ports.ubuntu.com` 1 種類のため pin しない。 Raspberry Pi 側 Trixie repository に `libcamera-dev` がまだ公開されていない過渡期の場合は Debian trixie main の `libcamera-dev` に fallback するが、これは builder としては許容する（実機動作の確認は 0067 の E2E に委ねる）。

### 現行ビルド経路への接続

`run.py` の import に `install_sysroot` を追加する。 `install_deps()` の rootfs 生成分岐を次の擬似コードに書き換える。

```python
if platform.target.os == "jetson":
    # 既存 multistrap 経路を現行どおり維持する（Jetson は 0043 で扱うため相対パスも変更しない）
    conf = os.path.join("multistrap", f"{platform.target.package_name}.conf")
    version_md5 = hashlib.md5(open(conf, "rb").read()).hexdigest()
    install_rootfs(
        version=version_md5,
        version_file=os.path.join(install_dir, "rootfs.version"),
        install_dir=install_dir,
        conf=conf,
    )
elif (
    platform.target.package_name
    in ("raspberry-pi-os_armv8", "ubuntu-22.04_armv8", "ubuntu-24.04_armv8")
    and platform.build.arch != platform.target.arch
):
    # x86_64 host からの cross build のときだけ sysroot builder を呼ぶ
    config_path = os.path.join(BASE_DIR, "sysroot", f"{platform.target.package_name}.json")
    install_sysroot(config_path=config_path, install_dir=install_dir)
# それ以外（arm64 native runner の 2 target）は rootfs を作らない
```

- Jetson 判定は `platform.target.os == "jetson"` を採用する（`buildbase.py:2228-2235` の `PlatformTarget.package_name` は Jetson の base Ubuntu version を含む合成キーで、将来 base OS が変わると壊れるため）。 これは `run.py:332` / `CMakeLists.txt:136` の既存判定と整合する。
- arm64 native runner で rootfs を作らない設計は現行 CI matrix において回帰しない。 Ubuntu 分岐は `run.py:302` の cross build 分岐（`platform.build.arch != platform.target.arch`）でのみ `CMAKE_SYSROOT` を渡すため、 arm64 native × Ubuntu では rootfs は事実上未使用。 Raspberry Pi OS 分岐（ `run.py:352-372` ）は cross build ガード無しで `CMAKE_SYSROOT` を無条件に付与するが、現行 CI matrix では `raspberry-pi-os_armv8` は `build_ubuntu` の x86_64 host cross build 経路でしか build しないため衝突しない。 将来 arm64 native runner で `raspberry-pi-os_armv8` を build する構成が加わる場合は、 Raspberry Pi OS 分岐にも同等の cross build ガードを入れる必要があるが、それは本 issue のスコープ外（ 0068 の判断領域）とする。
- `install_deps()` と `run.py:302` の CMake 分岐は同じ `platform.build.arch != platform.target.arch` を独立に持つが、責務分離（依存取得 vs コンパイル引数）のため許容する。共通化はしない。
- `install_sysroot()` は `run.py` に定義する（`buildbase.py` は melpon/buildbase テンプレートで `curl -LO` 上書き運用のため、独自関数を書くと次回同期で確実に消失する）。 `run.py` 側は既存 `BASE_DIR` （`run.py` L36 で定義済み）をそのまま使う。 `buildbase.py` の変更は不要。
- `run.py` に `install_sysroot(config_path: str, install_dir: str, force: bool = False) -> None` を追加する。 内部は `buildbase.cmd([sys.executable, os.path.join(BASE_DIR, "sysroot_builder.py"), "--config", config_path, "--dest", os.path.join(install_dir, "rootfs"), *(["--force"] if force else [])])` 相当を実行し、失敗時は例外を送出する。 `@versioned` decorator は使わず、再利用判定は builder 側 manifest に一本化する（テンプレート由来の `install_*` の `@versioned` / `version_file` パターンは意図的に踏襲しない。この非対称は `install_sysroot()` 内のコメントで日本語で明示する）。
- `run.py` の `from buildbase import ...` は変更しない（`install_sysroot()` は `run.py` 内定義のため import 追加不要）。 `install_sysroot()` から `cmd` を呼ぶ際は `buildbase.cmd(...)` の形で参照する（既存 import に頼らず、明示 module 参照で 1 本化する）。
- rootfs の配置先は現行どおり `install_dir/rootfs` を維持し、後続の CMake 引数を壊さない。 `CMAKE_FIND_ROOT_PATH_MODE_*` は現行の `BOTH` を維持し、 host fallback を許すのは scikit-build-core 化まで先送りとする（本 issue は「 rootfs 取得手段の置換」に限定する）。
- 非 Jetson では `install_dir/rootfs.version` file を作らない。 Jetson のみ現行と同じく MD5 を書く。既存の `rootfs.version` が残っていた場合、 sysroot builder は manifest 名 `.webrtc-build-sysroot.json` を見て「由来不明の rootfs は `--force` 無しで拒否」する契約に従うため、開発者は該当 rootfs を手動削除して builder を実行し直す。 CI （ GitHub-hosted 、毎 job fresh checkout ）では既存 rootfs は存在しないため事前削除 step は追加しない。
- 同一 `install_dir` に対して `run.py build` を並列実行しないことを前提とする。並列 configure の直列化 lock は本 issue では追加しない。
- Jetson target の呼び出しは本 issue では触らない。 0043 まで Jetson は `install_rootfs()` + `multistrap` 経路のままとする。

### JSON schema と配置

- 全 JSON は `sysroot/<config-name>.json` に配置する。 CLI は `config.name` と JSON ファイル stem の一致を検証する。
- schema:

  ```json
  {
      "name": "<file stem>",
      "arch": "arm64",
      "triplet": "aarch64-linux-gnu",
      "packages": ["..."],
      "repositories": [
          {
              "url": "https://...",
              "suite": "...",
              "components": ["main", "..."],
              "signed_by": "<absolute or relative path>",
              "pin_priority": 990
          }
      ]
  }
  ```

- `arch` は本 issue の対象では `arm64` のみを許容する（whitelist validation）。 `amd64` / `aarch64` などの別表記は validation error にする。
- `signed_by` は絶対パスと相対パスの両方を許可する。相対パスは JSON ファイルのあるディレクトリ（すなわち `sysroot/`）を基準に解決する。 keyring は `sysroot/keyrings/` に配置し、 JSON からは `keyrings/<name>` の相対パスで参照する。 Ubuntu の system keyring を使う場合は絶対パス `/usr/share/keyrings/ubuntu-archive-keyring.gpg` を使う。
- repository object の未知 key を validation error にする（ pin priority の綴り違いの防止）。
- keyring は `.gpg` （ binary ）と `.asc` （ ASCII armored ）の両形式を許容する。 APT の `signed-by` はどちらも受け付けるため区別しない。

### Ubuntu 22.04 / 24.04 arm64 用 JSON

`sysroot/ubuntu-22.04_armv8.json` と `sysroot/ubuntu-24.04_armv8.json` を追加する。 packages は現行 conf の 4 パッケージを維持する。

| target | suite | packages | signed_by |
| --- | --- | --- | --- |
| `ubuntu-22.04_armv8` | `jammy` | `libstdc++-11-dev`, `libc6-dev`, `libxext-dev`, `libdbus-1-dev` | `/usr/share/keyrings/ubuntu-archive-keyring.gpg` |
| `ubuntu-24.04_armv8` | `noble` | `libstdc++-13-dev`, `libc6-dev`, `libxext-dev`, `libdbus-1-dev` | `/usr/share/keyrings/ubuntu-archive-keyring.gpg` |

- Ubuntu archive keyring は repository に vendoring せず、 CI で `ubuntu-keyring` package を明示的に install して system の絶対パスを使う。 GitHub-hosted の Ubuntu 22.04 / 24.04 runner には `ubuntu-keyring` が pre-install されているが、 runner image 変更に対する回帰予防として明示 install する。 `test -f /usr/share/keyrings/ubuntu-archive-keyring.gpg` を検証 step に含めて存在を保証する。 Ubuntu keyring の SHA-256 pin は行わず、整合性は APT の InRelease 検証と `signed-by` に委ねる（ Ubuntu 側の keyring 更新頻度と revoke 対応を考慮した意図的なリスク受容）。
- repositories は `https://ports.ubuntu.com/ubuntu-ports` 1 種類のみ、 `components` は `main universe` を継承する。 pin は不要。

### Raspberry Pi OS Trixie 用 JSON

`sysroot/raspberry-pi-os_armv8.json` を追加する。 suite は Trixie 、 packages は現行 conf の 10 パッケージ集合を維持しつつ `libstdc++-11-dev` を `libstdc++-14-dev` へ引き上げる。

```json
{
    "name": "raspberry-pi-os_armv8",
    "arch": "arm64",
    "triplet": "aarch64-linux-gnu",
    "packages": [
        "libc6-dev",
        "libstdc++-14-dev",
        "libasound2-dev",
        "libpulse-dev",
        "libudev-dev",
        "libexpat1-dev",
        "libnss3-dev",
        "libxext-dev",
        "libxtst-dev",
        "libcamera-dev"
    ],
    "repositories": [
        {
            "url": "https://deb.debian.org/debian",
            "suite": "trixie",
            "components": ["main"],
            "signed_by": "keyrings/debian-archive-keyring.gpg"
        },
        {
            "url": "https://archive.raspberrypi.com/debian",
            "suite": "trixie",
            "components": ["main"],
            "signed_by": "keyrings/raspberrypi-archive-keyring.asc",
            "pin_priority": 990
        }
    ]
}
```

Debian keyring は Debian Trixie の `debian-archive-keyring` 2025.1 package から `debian-archive-keyring.gpg` を移植する。

- package の SHA-256 : `9ea7778e443144ca490668737a8ab22dd3e748bb99e805e22ec055abeb3c7fac`
- keyring file の SHA-256 : `506b815cbb32d9b6066b4a2aa524071e071761e7e7f68c3ac74f3061ba852017`
- Trixie archive / security / stable key の fingerprint （3 件）：
  - `04B54C3CDCA79751B16BC6B5225629DF75B188BD`
  - `5E04A1E3223A19A20706E20F9904613D4CCE68C6`
  - `41587F7DB8C774BCCF131416762F67A0B2C39DE4`

Raspberry Pi archive keyring は webrtc-build の `2c15196` から `sysroot/keyrings/raspberrypi-archive-keyring.asc` として移植する。

- 配布元： `https://archive.raspberrypi.com/debian/raspberrypi.gpg.key`
- OpenPGP fingerprint ： `CF8A1AF502A2AA2D763BAE7E82B129927FA3303E`
- SHA-256 ： `76603890d82a492175caf17aba68dc73acb1189c9fd58ec0c19145dfa3866d56`

Ubuntu runner の system Debian keyring は Trixie key を含まない可能性が高いため使用しない。 sysroot が参照するのは repository vendored の 2 keyring のみとする。

PR 作成時の検証コマンド：

```bash
shasum -a 256 sysroot/keyrings/debian-archive-keyring.gpg
shasum -a 256 sysroot/keyrings/raspberrypi-archive-keyring.asc
gpg --show-keys --keyid-format long sysroot/keyrings/debian-archive-keyring.gpg
gpg --show-keys --keyid-format long sysroot/keyrings/raspberrypi-archive-keyring.asc
```

上記出力を本 issue 掲載の SHA-256 と fingerprint と付き合わせる。

### Raspberry Pi OS 固有の担保範囲

- `libcamerac.so` の `DT_NEEDED` の SONAME が Trixie sysroot の `libcamera-dev` で解決できることは、実機 E2E で 0067 が確認する。本 issue では sysroot 内に `libcamera-dev` が展開されることまで担保する。
- 本 issue の `sora_sdk_rpi` wheel は Raspberry Pi OS Trixie 以降での動作のみをサポートする。 wheel が要求する `libstdc++` 最小 ABI （ `GLIBCXX_3.4.32` 以降）と glibc は Trixie の値に依存し、 Bookworm 以前へ install しても import に失敗する。 サポート境界の告知は `CHANGES.md` entry で行う。

### CI

`.github/workflows/build.yml` の書き換え方針。 `build_ubuntu` の armv8 entry の step は書き換え後、次の順序で並べる：

1. `checkout` / `download-artifact` / `.pyi` と `py.typed` のコピー（現行維持）
2. `sora_sdk_rpi` への `sed`（Raspberry Pi OS entry のみ、現行維持）
3. `libx11-dev` の install（現行維持）
4. `binutils-aarch64-linux-gnu` の install（armv8 全 entry）
5. `ubuntu-keyring` install + 存在確認（Ubuntu armv8 entry のみ、新規）
6. `Verify vendored keyrings`（Raspberry Pi OS entry のみ、新規）
7. `setup-uv` + `uv sync`（現行維持）
8. `uv run python run.py build <target>` + `uv build`（現行維持。 armv8 の内側で SORA_SDK_TARGET を渡す）
9. `Verify Raspberry Pi OS sysroot contents`（Raspberry Pi OS entry のみ、新規）
10. `Upload Artifact`（現行維持）

`build_ubuntu_arm` は matrix に `raspberry-pi-os_armv8` を含まないため上記 step 2 / 6 / 9 が対象外となり、また rootfs を作らないため step 5 も追加しない。 step 3 / 4 / 7 / 8 / 10 のみ実行する。

- L142-146 （ `build_ubuntu` の armv8 分岐）を次の擬似コードで書き換える：

  ```yaml
  - if: ${{ matrix.platform.arch == 'armv8' }}
    run: |
      sudo apt-get -y install binutils-aarch64-linux-gnu
  - if: ${{ matrix.platform.os == 'ubuntu' && matrix.platform.arch == 'armv8' }}
    run: |
      sudo apt-get -y install ubuntu-keyring
      test -f /usr/share/keyrings/ubuntu-archive-keyring.gpg
  - if: ${{ matrix.platform.name == 'raspberry-pi-os_armv8' }}
    name: Verify vendored keyrings
    run: |
      set -eux
      cd sysroot/keyrings
      sha256sum -c <<'EOF'
      506b815cbb32d9b6066b4a2aa524071e071761e7e7f68c3ac74f3061ba852017  debian-archive-keyring.gpg
      76603890d82a492175caf17aba68dc73acb1189c9fd58ec0c19145dfa3866d56  raspberrypi-archive-keyring.asc
      EOF
  ```

  `ca-certificates` は Ubuntu 22.04 / 24.04 runner に既定 install 済みのため追加 install しない。 `multistrap` package と `/usr/sbin/multistrap` の insecure sed patch は削除する。

- Raspberry Pi OS entry では `run.py build` 完了後、次の代表 header 検証 step を追加する：

  ```yaml
  - if: ${{ matrix.platform.name == 'raspberry-pi-os_armv8' }}
    name: Verify Raspberry Pi OS sysroot contents
    run: |
      set -eux
      root="_install/raspberry-pi-os_armv8/rootfs"
      test -f "$root/usr/include/aarch64-linux-gnu/sys/stat.h"
      test -f "$root/usr/include/c++/14/vector"
      test -f "$root/usr/include/libcamera/libcamera/camera.h"
      test -f "$root/usr/include/alsa/asoundlib.h"
      test -f "$root/usr/include/pulse/pulseaudio.h"
      test -f "$root/usr/include/nss/nss.h"
      python3 -c "import json; m=json.load(open('$root/.webrtc-build-sysroot.json')); assert len(m['deb_files']) >= 10, m['deb_files']"
  ```

- L209-212 （ `build_ubuntu_arm` ）を次のように書き換える：

  ```yaml
  - run: |
      sudo apt-get -y install binutils-aarch64-linux-gnu
  ```

  `binutils-aarch64-linux-gnu` は arm64 native runner では厳密には不要だが、現状踏襲で install する（削除可否は 0068 で扱う）。 `multistrap` package と insecure sed patch は削除する。 現行 `build_ubuntu_arm` matrix には `raspberry-pi-os_armv8` が含まれないため、 vendored keyring 検証 step は不要。将来 matrix に追加する場合はその PR で keyring 検証 step も合わせて追加する。

### テスト

`tests/sysroot_builder/test_sysroot_builder.py` は webrtc-build のテストを移植し、少なくとも次をネットワーク接続・モック・スタブ無しで検証する。

- 相対 keyring path の解決 、 必須値 、 重複 、 HTTPS 、 `signed_by` の validation 。
- checkout path に依存しない fingerprint 。
- `_apt_options()` と `_write_apt_files()` が APT の state / cache / sources / preferences を一時ディレクトリへ隔離し、 HTTPS + `signed-by` の sources.list を生成すること。
- 解決可能な絶対 symlink の相対化と、解決不能 link の維持。
- pkg-config 互換 link 。
- manifest 一致時の再利用。
- 古い manifest 、由来不明 directory 、壊れた symlink の `--force` 無しでの拒否。
- `_install_completed_sysroot()` が完成済み directory を入れ替えることと、存在しない `new_root` で配置に失敗した場合に既存 directory を復元すること。
- CLI における config name とファイル stem の不一致拒否。
- CLI の argument parser が `--force` を正しく解釈すること。 APT 呼び出しへの伝播は integration test で確認する。
- `pin_priority` の正常値 、 範囲外 、 `bool` 拒否 、 同一 hostname の競合、 fingerprint 挙動（ pin 無し既存 schema の fingerprint が変わらないこと）。
- userinfo / query / fragment / hostname 不在の URL と repository object の未知 key の拒否。
- `arch` の whitelist validation （`arm64` 以外を拒否する）。
- host APT preferences を参照せず、期待する `preferences` stanza を生成すること。

これらは APT 実行前の早期 return / error だけを通し、 unit test から実ネットワークへ接続しない。実際の APT download は CI の wheel build で integration test する。

検証コマンド（初回または `pytest-timeout` 追加直後は先に `uv sync` を実行する）：

```bash
uv sync
uv run --no-sync ruff check sysroot_builder.py tests/sysroot_builder/
uv run --no-sync ruff format --check sysroot_builder.py tests/sysroot_builder/
uv run --no-sync ty check
uv run --no-sync pytest --confcutdir=tests/sysroot_builder tests/sysroot_builder/ --timeout=10
```

`--confcutdir` により親 `tests/conftest.py` （拡張 build 済みの `sora_sdk` を top-level import する）の巻き込みが遮断され、拡張未 build でも sysroot builder の unit test が走る。

`pyproject.toml` の `dependency-groups.test` に `pytest-timeout~=2.4.0` を追加する。 `pyproject.toml` の `[tool.ty.src].include` は `["src", "tests", "sysroot_builder.py"]` に変更する。 ruff は既定でリポジトリルート直下の `.py` を対象とするため追加設定は不要。

## 完了条件

- `multistrap` 、 `--no-auth` 、 `AllowInsecureRepositories` 、 `/usr/sbin/multistrap` の書き換えが `build_ubuntu` の cross 経路と `build_ubuntu_arm` の native 経路の双方から消えている（ Jetson 経路は残る）。
- Ubuntu / Raspberry Pi OS 用 `multistrap/*.conf` （3 ファイル）が削除され、 `multistrap/ubuntu-22.04_armv8_jetson.conf` だけが残っている。
- `sysroot_builder.py` と `sysroot/` （ JSON 3 件、 keyring 2 件）が追加されている。
- Ubuntu 22.04 / 24.04 arm64 と Raspberry Pi OS arm64 の wheel が、 x86_64 host cross build 経路（ `build_ubuntu` の armv8 entry ）で成功する。
- arm64 native runner で `uv run python run.py build <target>` および `uv build` が multistrap install と insecure sed 無しで完走し、 wheel が生成される（ `build_ubuntu_arm` の 2 entry ）。
- native ubuntu-24.04 x86_64 build （ `build_ubuntu` の x86_64 entry ）と `pytest` smoke test が引き続き成功する（回帰防止）。
- macOS / Windows / Jetson の build 経路に回帰が無い。
- Raspberry Pi OS wheel の distribution 名が `sora_sdk_rpi` 、 import 名が `sora_sdk` のままで、 `libcamerac.so` が wheel に同梱されている。
- 「設計方針 › CI 」節で追加した `Verify vendored keyrings` step と `Verify Raspberry Pi OS sysroot contents` step が Raspberry Pi OS entry の build 前後で通っている（keyring SHA-256 の固定値照合、代表 6 header の存在、 manifest `.webrtc-build-sysroot.json` の `deb_files` に 10 package 分の deb が記録されていることまで担保する）。
- sysroot が APT state を一時ディレクトリへ隔離し、 HTTPS + `signed_by` 以外の repository 設定を validation error で拒否する。
- unit test 、 `ruff check` 、 `ruff format --check` 、 `ty check` 、 `pytest tests/sysroot_builder/test_sysroot_builder.py --timeout=10` が完走する。
- 同一設定の 2 回目実行で sysroot を再生成せず、 fingerprint 不一致の既存 sysroot は `--force` 無しで拒否する。
- APT download / deb 展開 / 後処理が失敗した段階では既存 sysroot に触れず、完成した出力だけに manifest が存在する。最終 rename の失敗時は既存 sysroot を復元する。
- 現行の `install_dir/rootfs.version` file は Jetson だけで作成される（非 Jetson では作らない）。
- `sysroot_builder.py` のログとエラーメッセージが英語で、末尾にピリオドが無い。コメントとテストの説明が日本語である。ソースとテストのコメントに issue 番号が含まれない。
- `pyproject.toml` の `[tool.ty.src].include` に `"sysroot_builder.py"` が追記されている。 `dependency-groups.test` に `pytest-timeout~=2.4.0` が追加されている。 `uv.lock` が pyproject.toml の変更に追従し、 `uv sync --frozen` が成功する。
- `pytest --confcutdir=tests/sysroot_builder tests/sysroot_builder/ --timeout=10` が拡張未 build の checkout で完走する。
- `CHANGES.md` の `## develop` セクションに entry が追記されている。

## 解決方法

以下の順で 1 PR にまとめて実装する。 コミット粒度は `shiguredo-git` スキルの規約に従い、 step ごとに 1 コミット以上に分割する（1 step = 1 コミットではなく、必要に応じて更に分ける）。

1. `sysroot_builder.py` （ module + CLI 一体）と `tests/sysroot_builder/test_sysroot_builder.py` を webrtc-build の `59a0ce0` から移植する（`2c15196` は履歴 pin のみ）。 `pin_priority` の追加とテスト追加も本 step で行う。
2. `sysroot/` ディレクトリを追加し、 3 JSON と 2 keyring を配置する。 vendored keyring の SHA-256 と fingerprint を PR 作成前に `shasum` と `gpg --show-keys` で照合し、本 issue の値と一致することを確認する。
3. `run.py` に `install_sysroot()` helper を追加し、 `install_deps()` を「設計方針 › 現行ビルド経路への接続」節の擬似コードに従って書き換える。 `buildbase.py` は melpon/buildbase テンプレートのため触らず、テンプレート由来の `install_rootfs()` は Jetson 経路で継続呼び出しする。
4. `multistrap/ubuntu-22.04_armv8.conf` / `multistrap/ubuntu-24.04_armv8.conf` / `multistrap/raspberry-pi-os_armv8.conf` の 3 ファイルを削除する。 Jetson conf は残す。
5. `.github/workflows/build.yml` の L142-146 と L209-212 から multistrap install と `/usr/sbin/multistrap` の insecure sed patch を削除する。 「設計方針 › CI 」節の擬似コードに従って target 別の install / verify step を再構成する。
6. `pyproject.toml` の `dependency-groups.test` に `pytest-timeout~=2.4.0` を追加し `uv.lock` を更新する。 `[tool.ty.src].include` に `"sysroot_builder.py"` を追記する。 `MANIFEST.in` は変更しない。
7. `CHANGES.md` の `## develop` に entry を追記する（ `shiguredo-issues` の規約により、 `CHANGES.md` には issue 番号を書かない）：

   ```markdown
   - [CHANGE] Ubuntu arm64 と Raspberry Pi OS の rootfs 生成を multistrap から署名検証付き sysroot builder に切り替える
     - Ubuntu arm64 と Raspberry Pi OS の cross build 経路を再構築し、insecure な `multistrap` / `--no-auth` / `AllowInsecureRepositories` の依存を撤去する
     - Raspberry Pi OS wheel の動作対象を Trixie 以降とし、Bookworm 以前は非対応にする
     - libstdc++ 依存を 14 に引き上げるため、`GLIBCXX_3.4.32` 以降を持たない旧環境では import に失敗する
     - wheel の manylinux tag （`manylinux_2_35_aarch64`）は本変更では触らない
     - Jetson の rootfs 生成は本変更では触らず、insecure な `multistrap` / `--no-auth` 経路のまま残す
     - 既存の `_install/<target>/rootfs` を持つローカル環境では、初回 build 前に該当 rootfs と `_install/<target>/rootfs.version` を手動削除する必要がある（sysroot builder は由来不明の既存 rootfs を `--force` 無しで拒否する）
     - @voluntas
   ```

8. CI で Ubuntu arm64 cross / arm64 native / Raspberry Pi OS cross の build と macOS / Windows / Jetson の build が通ることを確認する。

close 手順（ `shiguredo-issues` / `shiguredo-git` 規約）：

- 追記コミットと rename コミットを連続して作る当日のシステム日付で `Completed:` を埋める。 merge 予定日で先に埋めない（ merge がずれた場合の再修正フローが定義できないため）。
- 追記コミット `0074 解決方法を追記する` で `Completed:` を当日日付に更新し、「解決方法」節に実際の commit hash / PR 番号を追記する。
- 続いて `git mv issues/0074-change-multistrap-to-sysroot.md issues/closed/` を実行するリネームだけのコミットを `0074 closed Ubuntu arm64 と Raspberry Pi OS の multistrap をやめて署名検証付き sysroot に切り替える` として作る。
- 先行 issue は既に 2026-07-23 に closed 済みのため本 issue では触らない。

## ロールバック

本 issue の実装 PR で問題が発生した場合は、 PR の squash commit を `git revert` する。 squash commit の revert は `.github/workflows/build.yml` も multistrap 経路へ戻すが、 insecure な multistrap 経路の稼働を避けるため、 revert PR には対象 armv8 job / entry に `if: false` を追加して build を一時停止する commit も併せて含める。 その後、次の PR で sysroot 実装を修正して forward fix する。 `multistrap` / `--no-auth` / `AllowInsecureRepositories` / `/usr/sbin/multistrap` の書き換えを能動的に復活させる修正は行わない。

## 関連

- 0043 （ Jetson ）は本 issue 完了後に、同じ `sysroot_builder.py` / `sysroot/` を前提へ refresh する。
- 0068 との整合は「スコープ › 含まない」節参照（本 issue は arm64 native runner 上のビルド継続の是非には踏み込まない）。
- 0070 / 0071 との整合は「スコープ › 含まない」節参照（archive の SHA-256 検証と CI job 間 sysroot cache は本 issue のスコープ外）。

## 参照（一次資料）

- webrtc-build （ `https://github.com/shiguredo/webrtc-build` ）の `sysroot_builder.py` 、 `tests/sysroot_builder/test_sysroot_builder.py` 、 `sysroot/keyrings/raspberrypi-archive-keyring.asc` （ commit `59a0ce0` を canonical 、 `2c15196` を履歴として pin ）。
- Raspberry Pi repository `https://archive.raspberrypi.com/debian/dists/trixie/` の Trixie Release / InRelease 。 keyring 配布元 `https://archive.raspberrypi.com/debian/raspberrypi.gpg.key` 。
- Debian Trixie の `debian-archive-keyring` 2025.1 package （ Debian pool `https://ftp.debian.org/debian/pool/main/d/debian-archive-keyring/` ）と Debian 13 archive signing key の一覧（ `https://ftp-master.debian.org/keys.html` ）。
- Ubuntu の `ubuntu-keyring` package が提供する `/usr/share/keyrings/ubuntu-archive-keyring.gpg` （ Ubuntu pool `https://packages.ubuntu.com/noble/ubuntu-keyring` ）。
- melpon/buildbase の README （ `https://github.com/melpon/buildbase` ）。 `buildbase.py` は `curl -LO` で上書き更新するテンプレートである旨の根拠。
