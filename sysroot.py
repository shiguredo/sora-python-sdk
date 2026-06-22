"""cross-compile 用 sysroot を APT Packages インデックスから直接構築するスクリプト。

multistrap の代替として動作する。 host の APT 設定や rootfs 内の postinst を介さず、
APT の Packages インデックス (`.xz` / `.gz`) を直接読んで依存解決し、 `.deb` を
ダウンロードして `dpkg-deb -x` で展開するだけのシンプルな実装。

build サブコマンドは ubuntu-24.04 x86_64 host 限定 (`dpkg-deb` 1.21 以降が
`data.tar.zst` 圧縮 `.deb` を扱える前提)。 clean サブコマンドと本ファイルの
コード編集は OS 非依存。
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import graphlib
import gzip
import hashlib
import json
import logging
import lzma
import os
import re
import shutil
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

__all__ = [
    "PackageMeta",
    "PostInstallSymlink",
    "Repo",
    "SysrootConfig",
    "build_rootfs",
    "main",
    "parse_config",
]

# 公開できるログ prefix。 cmake 側の `Sora deps:` と区別するため `Sora sysroot:` を使う。
_LOG_PREFIX = "Sora sysroot"

# 標準 logging を使う。 module-level の logger オブジェクトは可変状態ではなく
# logging モジュールが管理する共有資源として扱う。
logger = logging.getLogger("sora_sysroot")

# JSON の `name` フィールドに許容する文字種。
_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\.]+$")

# webrtc-rs / momo の sysroot/*.json で使う任意フィールド。 Python 側では使わないが、
# スキーマ互換のため黙って無視する。 ここに含まれない未知フィールドは警告ログを出す。
_KNOWN_OPTIONAL_KEYS: frozenset[str] = frozenset(
    ["rust_target", "linker", "cc", "cxx", "cflags", "cxxflags"],
)

# Repo 側の任意フィールド。 同じ理由で webrtc-rs / momo 互換のため許容する。
_KNOWN_OPTIONAL_REPO_KEYS: frozenset[str] = frozenset(["allow_insecure"])


# CRITICAL abort 用の例外。 main から catch して exit(1) を出す。
class SysrootError(Exception):
    """sysroot 構築の継続不能なエラー (設定不正・ネットワーク永続失敗・整合性破壊など)。"""


# TLS は標準ライブラリ defaults を尊重する。 SSLContext は CPython 標準で thread セーフな
# 共有が前提で、 構成後は読み取り専用とみなして全 worker で共有する。
_SSL_CONTEXT: ssl.SSLContext = ssl.create_default_context()


@dataclass(frozen=True, slots=True, kw_only=True)
class Repo:
    """APT リポジトリ 1 件を表す。"""

    # ベース URL (末尾の `/` は parse 時に正規化済み)。 例: `http://ports.ubuntu.com/ubuntu-ports`
    url: str
    # suite 一覧。 1 つ以上の非空配列。 例: `["jammy"]`
    suites: tuple[str, ...]
    # component 一覧。 1 つ以上の非空配列。 例: `["main", "universe"]`
    components: tuple[str, ...]
    # GPG 検証を行わないかどうか。 現時点では sysroot.py の挙動には影響しないが、
    # 将来 GPG 検証を導入する際の拡張点として保持する。
    allow_insecure: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class PostInstallSymlink:
    """`.deb` 展開後に補完するシンボリックリンク 1 件。"""

    # `<dest>` 相対の symlink パス。 絶対パス / `..` を含む値は CRITICAL abort で弾く。
    link: str
    # symlink target の basename。 `link` と同じディレクトリの実体を指す。
    file: str


@dataclass(frozen=True, slots=True, kw_only=True)
class SysrootConfig:
    """JSON で表現される 1 つの sysroot ターゲット。"""

    # ログ / stamp 表示用の名前。 例: `ubuntu-22.04_armv8`
    name: str
    # ターゲットアーキテクチャ。 `arm64` を想定。 他値は警告ログを出してそのまま使う。
    arch: str
    # 依存解決の roots となるパッケージ名の集合。
    packages: tuple[str, ...]
    # APT リポジトリ一覧。
    repos: tuple[Repo, ...]
    # 任意。 `.deb` 展開後に補完する symlink 一覧。
    post_install_symlinks: tuple[PostInstallSymlink, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True, kw_only=True)
class PackageMeta:
    """Packages インデックスから読み取った 1 パッケージ分のメタ情報。"""

    # パッケージ名 (`Package:` フィールド)。
    name: str
    # バージョン文字列 (`Version:` フィールド)。 現状はバージョン制約評価をしないため記録のみ。
    version: str
    # アーキテクチャ (`Architecture:` フィールド)。
    architecture: str
    # `.deb` 取得 URL。 repo の base url + Filename の連結。
    url: str
    # `.deb` の SHA256 (`SHA256:` フィールド)。 download 時の整合性検証に使う。
    sha256: str
    # 通常依存 (`Depends:` フィールドの右辺)。 OR 依存ごとに 1 要素 (OR は内側のリスト)。
    depends: tuple[tuple[str, ...], ...]
    # 事前依存 (`Pre-Depends:` フィールドの右辺)。 形式は depends と同じ。
    pre_depends: tuple[tuple[str, ...], ...]
    # 仮想パッケージ宣言 (`Provides:` フィールド)。 バージョン部分は捨てて名前だけ保持する。
    provides: tuple[str, ...]
    # `Essential: yes` かどうか。 yes なら cross-compile 用 sysroot には不要なので依存集合に含めない。
    essential: bool


# ---------- JSON パース ----------


def _ensure(condition: bool, message: str) -> None:
    """assert の代わりに本番不変条件をチェックし、 失敗時は SysrootError を投げる。

    shiguredo-python 規約「assert を本番不変条件チェックに使わない」に従う。
    """
    if not condition:
        raise SysrootError(message)


def _normalize_url(url: str) -> str:
    """末尾の `/` を 1 個に正規化 (`Packages` URL 組み立て時の二重 `/` を防ぐ)。"""
    return url.rstrip("/")


def _parse_repo(raw: object, index: int) -> Repo:
    """JSON の repos[i] エントリ 1 件を Repo に変換する。"""
    _ensure(isinstance(raw, dict), f"repos[{index}] must be an object, got {type(raw).__name__}")
    repo = cast("Mapping[str, object]", raw)

    url_raw = repo.get("url")
    _ensure(
        isinstance(url_raw, str) and bool(url_raw),
        f"repos[{index}].url must be a non-empty string",
    )
    url = cast(str, url_raw)
    _ensure(
        url.startswith("http://") or url.startswith("https://"),
        f"repos[{index}].url must start with http:// or https://, got {url!r}",
    )

    suites_raw = repo.get("suites")
    _ensure(
        isinstance(suites_raw, list) and len(suites_raw) > 0,
        f"repos[{index}].suites must be a non-empty array",
    )
    suites = cast("list[object]", suites_raw)
    for j, s in enumerate(suites):
        _ensure(
            isinstance(s, str) and bool(s),
            f"repos[{index}].suites[{j}] must be a non-empty string",
        )

    components_raw = repo.get("components")
    _ensure(
        isinstance(components_raw, list) and len(components_raw) > 0,
        f"repos[{index}].components must be a non-empty array",
    )
    components = cast("list[object]", components_raw)
    for j, c in enumerate(components):
        _ensure(
            isinstance(c, str) and bool(c),
            f"repos[{index}].components[{j}] must be a non-empty string",
        )

    allow_insecure_raw = repo.get("allow_insecure", False)
    _ensure(
        isinstance(allow_insecure_raw, bool),
        f"repos[{index}].allow_insecure must be a bool, got {type(allow_insecure_raw).__name__}",
    )

    # 真の未知フィールドは警告ログ。 webrtc-rs / momo 互換の任意フィールドは黙って無視する。
    known_keys = frozenset(["url", "suites", "components"]) | _KNOWN_OPTIONAL_REPO_KEYS
    for key in repo:
        if key not in known_keys:
            logger.warning("%s: unknown field %r in repos[%d], ignoring", _LOG_PREFIX, key, index)

    return Repo(
        url=_normalize_url(url),
        suites=tuple(cast("list[str]", suites)),
        components=tuple(cast("list[str]", components)),
        allow_insecure=cast(bool, allow_insecure_raw),
    )


def _parse_post_install_symlink(raw: object, index: int) -> PostInstallSymlink:
    """JSON の post_install_symlinks[i] エントリ 1 件を PostInstallSymlink に変換する。"""
    _ensure(
        isinstance(raw, dict),
        f"post_install_symlinks[{index}] must be an object, got {type(raw).__name__}",
    )
    entry = cast("Mapping[str, object]", raw)

    link_raw = entry.get("link")
    _ensure(
        isinstance(link_raw, str) and bool(link_raw),
        f"post_install_symlinks[{index}].link must be a non-empty string",
    )
    link = cast(str, link_raw)
    file_raw = entry.get("file")
    _ensure(
        isinstance(file_raw, str) and bool(file_raw),
        f"post_install_symlinks[{index}].file must be a non-empty string",
    )
    file_value = cast(str, file_raw)

    # link は <dest> 相対パスに限る。 絶対パス・先頭 / ・.. の混入はパストラバーサル防止のため CRITICAL abort。
    _ensure(
        not link.startswith("/") and not link.startswith(".."),
        f"post_install_symlinks[{index}].link must be a relative path without leading / or .., "
        f"got {link!r}",
    )
    _ensure(
        ".." not in Path(link).parts,
        f"post_install_symlinks[{index}].link must not contain '..', got {link!r}",
    )

    # file は basename に限る (link と同一ディレクトリの実体名)。
    _ensure(
        "/" not in file_value and ".." not in file_value,
        f"post_install_symlinks[{index}].file must be a basename without / or .., got {file_value!r}",
    )

    return PostInstallSymlink(link=link, file=file_value)


def parse_config(path: Path) -> SysrootConfig:
    """JSON 設定ファイルを読み込み、 バリデーション後に SysrootConfig に変換する。"""
    text = path.read_text(encoding="utf-8")
    try:
        data: object = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SysrootError(f"failed to parse {path} as JSON: {exc}") from exc

    _ensure(
        isinstance(data, dict),
        f"top-level JSON must be an object, got {type(data).__name__}",
    )
    obj = cast("Mapping[str, object]", data)

    name_raw = obj.get("name")
    _ensure(
        isinstance(name_raw, str) and bool(name_raw) and bool(_NAME_PATTERN.match(name_raw)),
        f"name must be a non-empty string matching {_NAME_PATTERN.pattern}, got {name_raw!r}",
    )
    name = cast(str, name_raw)

    arch_raw = obj.get("arch")
    _ensure(
        isinstance(arch_raw, str) and bool(arch_raw),
        f"arch must be a non-empty string, got {arch_raw!r}",
    )
    arch = cast(str, arch_raw)
    if arch != "arm64":
        logger.warning(
            "%s: arch %r is not 'arm64'; proceeding but unverified",
            _LOG_PREFIX,
            arch,
        )

    packages_raw = obj.get("packages")
    _ensure(
        isinstance(packages_raw, list) and len(packages_raw) > 0,
        "packages must be a non-empty array",
    )
    packages = cast("list[object]", packages_raw)
    for i, p in enumerate(packages):
        _ensure(
            isinstance(p, str) and bool(p),
            f"packages[{i}] must be a non-empty string",
        )

    repos_raw = obj.get("repos")
    _ensure(
        isinstance(repos_raw, list) and len(repos_raw) > 0,
        "repos must be a non-empty array",
    )
    repos_list = cast("list[object]", repos_raw)
    repos = tuple(_parse_repo(r, i) for i, r in enumerate(repos_list))

    post_install_raw = obj.get("post_install_symlinks", [])
    _ensure(
        isinstance(post_install_raw, list),
        "post_install_symlinks must be an array when present",
    )
    post_install_list = cast("list[object]", post_install_raw)
    post_install_symlinks = tuple(
        _parse_post_install_symlink(e, i) for i, e in enumerate(post_install_list)
    )

    # 真の未知フィールドのみ警告。 webrtc-rs / momo 互換の任意フィールド (rust_target 等) は黙って無視する。
    known_keys = (
        frozenset(["name", "arch", "packages", "repos", "post_install_symlinks"])
        | _KNOWN_OPTIONAL_KEYS
    )
    for key in obj:
        if key not in known_keys:
            logger.warning("%s: unknown top-level field %r, ignoring", _LOG_PREFIX, key)

    return SysrootConfig(
        name=name,
        arch=arch,
        packages=tuple(cast("list[str]", packages)),
        repos=repos,
        post_install_symlinks=post_install_symlinks,
    )


# ---------- HTTP 取得とリトライ ----------


def _http_get(url: str, timeout: float = 60.0) -> bytes:
    """単発 GET。 404 は urllib.error.HTTPError をそのまま raise する。

    proxies は urllib のデフォルト (`urllib.request.getproxies()`) を尊重する。
    """
    req = urllib.request.Request(url, headers={"User-Agent": "sora-sysroot/1"})
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CONTEXT) as resp:
        return resp.read()


def _http_get_with_retry(url: str, max_attempts: int = 3, base_sleep: float = 1.0) -> bytes:
    """5xx / network error 時に最大 `max_attempts` 回まで `base_sleep` 秒間隔でリトライ。

    404 等の 4xx は永続失敗扱いで即 raise (リトライしない)。
    """
    last_exc: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return _http_get(url)
        except urllib.error.HTTPError as exc:
            if 500 <= exc.code < 600:
                last_exc = exc
                logger.warning(
                    "%s: HTTP %d on %s (attempt %d/%d), retrying",
                    _LOG_PREFIX,
                    exc.code,
                    url,
                    attempt,
                    max_attempts,
                )
                time.sleep(base_sleep)
                continue
            raise
        except urllib.error.URLError as exc:
            last_exc = exc
            logger.warning(
                "%s: network error on %s (attempt %d/%d): %s",
                _LOG_PREFIX,
                url,
                attempt,
                max_attempts,
                exc,
            )
            time.sleep(base_sleep)
            continue
    # ループは必ず 1 回以上回り、 成功時は return / 永続失敗時は raise / 5xx・network 時は last_exc を残す。
    # そのため、 ここに到達するのは「max_attempts 回すべて 5xx / network failure」のときのみ。
    if last_exc is None:
        raise SysrootError(f"unexpected retry loop exit with no exception for {url}")
    raise last_exc


# ---------- Packages インデックスの取得・解析 ----------


def _packages_url(repo: Repo, suite: str, component: str, arch: str, ext: str) -> str:
    """APT 正規 layout の Packages インデックス URL を組み立てる。"""
    return f"{repo.url}/dists/{suite}/{component}/binary-{arch}/Packages.{ext}"


def _decompress_packages(payload: bytes, ext: str) -> str:
    """`.xz` または `.gz` 圧縮の Packages バイト列を UTF-8 テキストに展開する。"""
    if ext == "xz":
        return lzma.decompress(payload).decode("utf-8", errors="replace")
    if ext == "gz":
        return gzip.decompress(payload).decode("utf-8", errors="replace")
    raise SysrootError(f"unsupported Packages compression: {ext!r}")


def _fetch_packages_for_repo_unit(repo: Repo, suite: str, component: str, arch: str) -> str:
    """1 つの (repo, suite, component) について Packages を取得し UTF-8 テキストで返す。

    `.xz` を優先し、 404 (= 未配布) なら `.gz` にフォールバックする (NVIDIA / RPi 対応)。
    両方とも 404 なら CRITICAL abort。
    """
    for ext in ("xz", "gz"):
        url = _packages_url(repo, suite, component, arch, ext)
        try:
            payload = _http_get_with_retry(url)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                logger.debug("%s: %s not found (404), trying next compression", _LOG_PREFIX, url)
                continue
            raise SysrootError(f"failed to fetch {url}: HTTP {exc.code}") from exc
        logger.info("%s: fetched %s (%d bytes compressed)", _LOG_PREFIX, url, len(payload))
        return _decompress_packages(payload, ext)
    raise SysrootError(
        f"no Packages index found for {repo.url} {suite}/{component} binary-{arch} "
        f"(tried .xz and .gz)"
    )


def _parse_packages_text(text: str, base_url: str) -> list[PackageMeta]:
    """1 つの Packages テキストを `Package:` ブロックごとに分割してパースする。"""
    result: list[PackageMeta] = []
    block_lines: list[str] = []

    def flush_block() -> None:
        if not block_lines:
            return
        fields = _parse_control_block(block_lines)
        block_lines.clear()
        name = fields.get("Package")
        version = fields.get("Version")
        architecture = fields.get("Architecture")
        filename = fields.get("Filename")
        sha256 = fields.get("SHA256")
        # Packages ブロックは仕様上これらが揃っている前提だが、 1 つでも欠ければそのブロックは捨てる。
        if not (name and version and architecture and filename and sha256):
            logger.debug(
                "%s: skip Packages block lacking required fields (Package=%r)",
                _LOG_PREFIX,
                name,
            )
            return
        depends = _parse_relations(fields.get("Depends", ""))
        pre_depends = _parse_relations(fields.get("Pre-Depends", ""))
        provides = _parse_provides(fields.get("Provides", ""))
        essential = fields.get("Essential", "no").lower() == "yes"
        url = f"{base_url}/{filename.lstrip('/')}"
        result.append(
            PackageMeta(
                name=name,
                version=version,
                architecture=architecture,
                url=url,
                sha256=sha256,
                depends=depends,
                pre_depends=pre_depends,
                provides=provides,
                essential=essential,
            )
        )

    for raw_line in text.splitlines():
        if raw_line == "":
            flush_block()
        else:
            block_lines.append(raw_line)
    flush_block()
    return result


def _parse_control_block(lines: list[str]) -> dict[str, str]:
    """RFC822 風の Debian control ブロックを `dict[str, str]` にパースする。

    継続行 (先頭が空白の行) は直前フィールド値の続きとして半角スペースで連結する。
    `Depends:` などの relations は仕様上複数行に折り返されることがあるため、
    `Description:` のような multi-line 整形フィールドの改行表現は再現しない。
    """
    fields: dict[str, str] = {}
    current_key: str | None = None
    for line in lines:
        if line.startswith((" ", "\t")):
            if current_key is None:
                continue
            fields[current_key] = fields[current_key] + " " + line.strip()
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        current_key = key.strip()
        fields[current_key] = value.strip()
    return fields


def _parse_relations(raw: str) -> tuple[tuple[str, ...], ...]:
    """`Depends:` / `Pre-Depends:` 右辺をパースして「OR 候補のリスト」のタプルに変換する。

    例: `a, b | c (>= 1.0)` -> ((a,), (b, c))
    """
    if not raw:
        return ()
    items: list[tuple[str, ...]] = []
    for part in raw.split(","):
        candidates: list[str] = []
        for alt in part.split("|"):
            name = _strip_version_constraint(alt.strip())
            if name:
                candidates.append(name)
        if candidates:
            items.append(tuple(candidates))
    return tuple(items)


def _parse_provides(raw: str) -> tuple[str, ...]:
    """`Provides:` 右辺を名前のリストに変換する。 バージョン制約は捨てる。"""
    if not raw:
        return ()
    names: list[str] = []
    for part in raw.split(","):
        name = _strip_version_constraint(part.strip())
        if name:
            names.append(name)
    return tuple(names)


_VERSION_CONSTRAINT_RE = re.compile(r"\s*\([^)]*\)\s*$")
_ARCH_QUALIFIER_RE = re.compile(r":[A-Za-z0-9_\-]+$")


def _strip_version_constraint(token: str) -> str:
    """`pkg (>= 1.0)` や `pkg:any` を `pkg` に正規化する。"""
    token = _VERSION_CONSTRAINT_RE.sub("", token).strip()
    token = _ARCH_QUALIFIER_RE.sub("", token).strip()
    return token


@dataclass(frozen=True, slots=True, kw_only=True)
class _PackagesIndex:
    """全 repo の Packages を統合したインデックス。"""

    # 実パッケージ: name -> PackageMeta (同名は後勝ち、 repo 配列順は呼び出し側で制御済み)。
    packages: dict[str, PackageMeta]
    # 仮想パッケージ: provides 名 -> 実 provider 名のリスト (重複・順序維持)。
    provides: dict[str, list[str]]


def _fetch_all_packages_indexes(
    config: SysrootConfig,
    jobs: int,
) -> _PackagesIndex:
    """全 repo × suite × component の Packages を並列取得して 1 つに統合する。"""
    units: list[tuple[Repo, str, str]] = []
    for repo in config.repos:
        for suite in repo.suites:
            for component in repo.components:
                units.append((repo, suite, component))

    # 並列取得。 結果は (repo, suite, component, text) の順序保存で返す。
    indexed_results: dict[int, str] = {}
    with cf.ThreadPoolExecutor(max_workers=jobs) as pool:
        futures: dict[cf.Future[str], int] = {
            pool.submit(_fetch_packages_for_repo_unit, repo, suite, component, config.arch): i
            for i, (repo, suite, component) in enumerate(units)
        }
        try:
            for fut in cf.as_completed(futures):
                indexed_results[futures[fut]] = fut.result()
        except BaseException:
            # fail-fast: 1 つでも例外が起きたら残りを cancel してから raise。
            for pending in futures:
                pending.cancel()
            raise

    packages: dict[str, PackageMeta] = {}
    provides: dict[str, list[str]] = {}
    # 統合順序は repos -> suites -> components の順。
    # 同一 repo 内は配列末尾を後勝ちにすることで apt の updates 反映と同等にする。
    for i, (repo, _suite, _component) in enumerate(units):
        text = indexed_results[i]
        for meta in _parse_packages_text(text, repo.url):
            packages[meta.name] = meta
            for virtual in meta.provides:
                provides.setdefault(virtual, []).append(meta.name)
    return _PackagesIndex(packages=packages, provides=provides)


# ---------- 依存解決 ----------


def _resolve_candidate(
    candidate: str,
    index: _PackagesIndex,
) -> str | None:
    """単一の依存名候補について、 実パッケージ採用 / 仮想 provider 採用 / None を返す。"""
    if candidate in index.packages:
        return candidate
    providers = index.provides.get(candidate)
    if providers:
        # Packages ファイル内出現順は repo mirror で安定しないため、 sorted で決定的に。
        return sorted(providers)[0]
    return None


def _resolve_dependencies(
    config: SysrootConfig,
    index: _PackagesIndex,
) -> tuple[list[PackageMeta], dict[str, list[str]]]:
    """roots から `Depends` + `Pre-Depends` を辿り、 採用パッケージと依存マップを返す。

    第 1 戻り値は採用順 (発見順) を保つ list。 第 2 戻り値は
    「meta.name -> その meta が依存する採用候補名の list」 (essential も含めて記録)。
    依存マップは `_topological_order` が同じ採用候補で辺を張るために使う。

    Essential: yes が選ばれた場合、 satisfaction として扱い install 集合には追加しない
    (cross-compile 用 sysroot に dpkg / apt 等は不要)。
    """
    selected: dict[str, PackageMeta] = {}
    visit_order: list[str] = []
    queue: list[str] = []
    prerequisites: dict[str, list[str]] = {}
    for root in config.packages:
        chosen = _resolve_candidate(root, index)
        if chosen is None:
            raise SysrootError(
                f"root package {root!r} is not provided by any repository "
                f"(neither as a real package nor as a virtual package)"
            )
        if chosen not in selected:
            meta = index.packages[chosen]
            if not meta.essential:
                selected[chosen] = meta
                visit_order.append(chosen)
                queue.append(chosen)
    while queue:
        current = queue.pop(0)
        meta = selected[current]
        for relation in (*meta.depends, *meta.pre_depends):
            resolved: str | None = None
            for cand in relation:
                chosen = _resolve_candidate(cand, index)
                if chosen is None:
                    continue
                resolved = chosen
                break
            if resolved is None:
                # 単独 / OR 全候補が「未提供」 = MTA / cron 系の意図せぬ混入を防ぐため CRITICAL abort。
                raise SysrootError(
                    f"unresolved dependency {list(relation)!r} required by {current!r} "
                    f"(no real package or virtual provider found)"
                )
            # current -> resolved を依存マップに記録するのは BFS forward edge のみ。
            # 既に selected に入っているノードへの back-edge は dpkg-deb の unpack 順序では
            # 問題にならず、 graphlib の CycleError を回避するため除外する
            # (Debian / Ubuntu の libc6 <-> libgcc-s1 のような相互依存が現実に存在する)。
            if resolved in selected:
                continue
            resolved_meta = index.packages[resolved]
            if resolved_meta.essential:
                continue
            prerequisites.setdefault(current, []).append(resolved)
            selected[resolved] = resolved_meta
            visit_order.append(resolved)
            queue.append(resolved)
    return [selected[name] for name in visit_order], prerequisites


def _topological_order(
    selected: list[PackageMeta],
    prerequisites: Mapping[str, list[str]],
) -> list[PackageMeta]:
    """採用済みパッケージを `_resolve_dependencies` の依存マップから topological order に並べる。

    同レベルのノード間は selected の出現順 (= JSON packages 順 + transitive 発見順)
    を tie-breaker とする。 `graphlib.TopologicalSorter.static_order()` は
    Python 3.9 以降で同レベル順序として `add()` 呼び出し順を保つ。
    """
    name_to_meta = {meta.name: meta for meta in selected}
    sorter: graphlib.TopologicalSorter[str] = graphlib.TopologicalSorter()
    for meta in selected:
        prereqs: list[str] = []
        for name in prerequisites.get(meta.name, ()):
            if name in name_to_meta and name != meta.name and name not in prereqs:
                prereqs.append(name)
        sorter.add(meta.name, *prereqs)
    ordered_names = list(sorter.static_order())
    return [name_to_meta[name] for name in ordered_names]


# ---------- .deb ダウンロードと展開 ----------


def _deb_cache_name(meta: PackageMeta) -> str:
    """キャッシュ内の `.deb` ファイル名 (`<pkg>_<ver>_<arch>_<sha[:12]>.deb`)。"""
    safe_version = meta.version.replace(":", "%3a").replace("/", "_")
    return f"{meta.name}_{safe_version}_{meta.architecture}_{meta.sha256[:12]}.deb"


def _sha256_of_file(path: Path) -> str:
    """ファイルの SHA256 を 1 MiB チャンクで計算する。"""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _download_single_deb(meta: PackageMeta, cache_dir: Path) -> Path:
    """1 つの `.deb` を取得・整合性検証して cache_dir に置く。 既にあれば再利用する。"""
    target = cache_dir / _deb_cache_name(meta)
    if target.exists():
        if _sha256_of_file(target) == meta.sha256:
            logger.debug("%s: cache hit %s", _LOG_PREFIX, target.name)
            return target
        # SHA256 が一致しなければ壊れキャッシュとして削除して再取得する。
        logger.warning("%s: cached %s has wrong SHA256; re-downloading", _LOG_PREFIX, target.name)
        target.unlink()
    logger.info("%s: downloading %s", _LOG_PREFIX, meta.url)
    payload = _http_get_with_retry(meta.url)
    actual = hashlib.sha256(payload).hexdigest()
    if actual != meta.sha256:
        raise SysrootError(
            f"SHA256 mismatch for {meta.name} from {meta.url}: expected {meta.sha256}, got {actual}"
        )
    # 同じ cache_dir に並列書き込みが入る可能性を考慮し、 一時ファイル経由で原子的に置く。
    tmp = cache_dir / (target.name + ".part")
    tmp.write_bytes(payload)
    tmp.replace(target)
    return target


def _download_all_debs(
    metas: Iterable[PackageMeta],
    cache_dir: Path,
    jobs: int,
) -> dict[str, Path]:
    """`.deb` を並列ダウンロードして name -> Path のマッピングで返す。

    エラー伝播は fail-fast (1 つでも失敗したら残りを cancel してから raise)。
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    metas_list = list(metas)
    result: dict[str, Path] = {}
    with cf.ThreadPoolExecutor(max_workers=jobs) as pool:
        futures: dict[cf.Future[Path], PackageMeta] = {
            pool.submit(_download_single_deb, meta, cache_dir): meta for meta in metas_list
        }
        try:
            for fut in cf.as_completed(futures):
                meta = futures[fut]
                result[meta.name] = fut.result()
        except BaseException:
            for pending in futures:
                pending.cancel()
            raise
    return result


def _extract_debs_sequential(
    ordered_metas: list[PackageMeta],
    debs: Mapping[str, Path],
    dest: Path,
) -> None:
    """`.deb` を topological order でシーケンシャル展開する (同名ファイル衝突の決定性を保つ)。"""
    for meta in ordered_metas:
        deb_path = debs[meta.name]
        logger.info("%s: extracting %s", _LOG_PREFIX, deb_path.name)
        try:
            subprocess.run(
                ["dpkg-deb", "-x", str(deb_path), str(dest)],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            raise SysrootError(
                f"dpkg-deb -x failed for {deb_path.name} (exit={exc.returncode}): {exc.stderr}"
            ) from exc
        except FileNotFoundError as exc:
            raise SysrootError(
                "dpkg-deb command not found; build requires dpkg (ubuntu-24.04 host)"
            ) from exc


# ---------- symlink 後処理 ----------


def _ensure_usrmerge_symlinks(dest: Path) -> None:
    """`<dest>` 直下に usrmerge 用の lib / bin / sbin -> usr/lib / usr/bin / usr/sbin を作る。

    transitional package が `/lib/...` 直下にファイルを置いても symlink 経由で `/usr/lib/...` に
    集約されるようにする (aarch64 では lib64 不要)。
    """
    dest.mkdir(parents=True, exist_ok=True)
    for name in ("lib", "bin", "sbin"):
        link = dest / name
        target = Path("usr") / name
        if link.is_symlink():
            continue
        if link.exists():
            # 何らかの理由で実体ディレクトリが先にできているなら触らない (上書きは危険)。
            logger.warning(
                "%s: %s already exists as a real entry; skipping usrmerge symlink",
                _LOG_PREFIX,
                link,
            )
            continue
        (dest / "usr" / name).mkdir(parents=True, exist_ok=True)
        link.symlink_to(target)


def _fix_absolute_symlinks(root: Path) -> None:
    """`<root>` 内の絶対パス symlink を相対パスに置き換える。

    buildbase.py:install_rootfs の挙動を機能等価で移植する。 ターゲットが root 内に
    実体として存在しない broken symlink はそのまま残す (元実装と同じ)。
    """
    for dirpath, _dirnames, filenames in os.walk(root):
        for filename in filenames:
            link_path = Path(dirpath) / filename
            if not link_path.is_symlink():
                continue
            target = os.readlink(link_path)
            if not os.path.isabs(target):
                continue
            # 絶対パス target の先頭 `/` を剥がして root 配下のパスを組み立てる。
            target_path = Path(root, target.lstrip("/"))
            if not target_path.exists():
                continue
            relpath = os.path.relpath(target_path, dirpath)
            try:
                rel_link = link_path.relative_to(root)
            except ValueError:
                rel_link = link_path
            logger.debug(
                "%s: rewriting symlink %s: %s -> %s",
                _LOG_PREFIX,
                rel_link,
                target,
                relpath,
            )
            link_path.unlink()
            link_path.symlink_to(relpath)


def _apply_post_install_symlinks(
    root: Path,
    symlinks: Iterable[PostInstallSymlink],
) -> None:
    """JSON の post_install_symlinks を冪等に適用する。"""
    for entry in symlinks:
        link_path = root / entry.link
        target_file = link_path.parent / entry.file
        if not target_file.exists():
            logger.debug(
                "%s: post_install_symlinks target %s does not exist; skipping",
                _LOG_PREFIX,
                target_file,
            )
            continue
        if link_path.exists() or link_path.is_symlink():
            logger.debug(
                "%s: post_install_symlinks link %s already exists; skipping",
                _LOG_PREFIX,
                link_path,
            )
            continue
        link_path.parent.mkdir(parents=True, exist_ok=True)
        link_path.symlink_to(entry.file)


# ---------- stamp ----------


def _stamp_path(dest: Path) -> Path:
    """stamp ファイルのパス。"""
    return dest / ".sysroot.stamp"


def _compute_stamp(config_path: Path, script_path: Path) -> str:
    """JSON 設定ファイルと本スクリプト自身の SHA256 を連結したハッシュを stamp 値とする。

    sysroot.py 自身の空白・コメント変更でも stamp が変わるが、 再現性を優先して許容する。
    """
    h = hashlib.sha256()
    h.update(config_path.read_bytes())
    h.update(script_path.read_bytes())
    return h.hexdigest()


def _read_stamp(dest: Path) -> str | None:
    """既存 stamp 値を読む。 存在しなければ None。"""
    path = _stamp_path(dest)
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8").strip()


def _write_stamp(dest: Path, stamp: str) -> None:
    """stamp を書き込む。"""
    _stamp_path(dest).write_text(stamp + "\n", encoding="utf-8")


# ---------- 公開 API: build / clean ----------


def build_rootfs(
    config_path: Path,
    dest: Path,
    *,
    cache_dir: Path | None = None,
    jobs: int = 4,
    force: bool = False,
    script_path: Path | None = None,
) -> None:
    """sysroot を構築する。 stamp 一致 + `force=False` なら全処理 skip する。

    `script_path` は stamp 計算用の本スクリプト位置。 未指定なら本ファイルを使う。
    """
    if script_path is None:
        script_path = Path(__file__).resolve()
    config = parse_config(config_path)
    dest = dest.resolve()
    if cache_dir is None:
        cache_dir = dest / ".debs"
    cache_dir = cache_dir.resolve()

    stamp = _compute_stamp(config_path, script_path)
    existing = _read_stamp(dest) if dest.exists() else None
    if not force and existing == stamp:
        logger.info(
            "%s: stamp hit for %s; skipping (use --force to override)", _LOG_PREFIX, config.name
        )
        return

    dest.mkdir(parents=True, exist_ok=True)
    _ensure_usrmerge_symlinks(dest)

    logger.info("%s: fetching Packages indexes for %s", _LOG_PREFIX, config.name)
    index = _fetch_all_packages_indexes(config, jobs=jobs)

    logger.info("%s: resolving dependencies (%d roots)", _LOG_PREFIX, len(config.packages))
    selected, prerequisites = _resolve_dependencies(config, index)
    logger.info("%s: selected %d packages", _LOG_PREFIX, len(selected))

    ordered = _topological_order(selected, prerequisites)

    cache_dir.mkdir(parents=True, exist_ok=True)
    logger.info("%s: downloading %d .deb files", _LOG_PREFIX, len(ordered))
    debs = _download_all_debs(ordered, cache_dir, jobs=jobs)

    logger.info("%s: extracting %d .deb files (sequential)", _LOG_PREFIX, len(ordered))
    _extract_debs_sequential(ordered, debs, dest)

    logger.info("%s: fixing absolute symlinks", _LOG_PREFIX)
    _fix_absolute_symlinks(dest)

    if config.post_install_symlinks:
        logger.info(
            "%s: applying %d post_install_symlinks", _LOG_PREFIX, len(config.post_install_symlinks)
        )
        _apply_post_install_symlinks(dest, config.post_install_symlinks)

    _write_stamp(dest, stamp)
    logger.info("%s: build complete for %s at %s", _LOG_PREFIX, config.name, dest)


def _clean(dest: Path) -> None:
    """`<dest>` ディレクトリと stamp / cache をまるごと削除する。 不在時は no-op。"""
    dest = dest.resolve()
    if not dest.exists():
        logger.info("%s: %s does not exist; nothing to clean", _LOG_PREFIX, dest)
        return
    logger.info("%s: removing %s", _LOG_PREFIX, dest)
    # `<dest>/.debs` と `<dest>/.sysroot.stamp` も dest 配下なので rmtree でまとめて消える。
    shutil.rmtree(dest)


# ---------- CLI ----------


def _default_jobs() -> int:
    """`--jobs` のデフォルト値 `min(8, os.cpu_count() or 4)`。"""
    return min(8, os.cpu_count() or 4)


def _build_argparser() -> argparse.ArgumentParser:
    """sub-parser 構成の argparse を組み立てる。"""
    parser = argparse.ArgumentParser(
        prog="sysroot.py",
        description="Build a cross-compile sysroot from APT Packages indexes.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="Build a sysroot at --dest from --config")
    build.add_argument("--config", required=True, type=Path, help="path to the JSON config file")
    build.add_argument("--dest", required=True, type=Path, help="destination directory")
    build.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help="directory to cache downloaded .deb files (default: <dest>/.debs)",
    )
    build.add_argument(
        "--jobs",
        type=int,
        default=None,
        help=f"parallelism for downloads (1-32, default: {_default_jobs()})",
    )
    build.add_argument("--force", action="store_true", help="rebuild even if stamp matches")
    build.add_argument("--verbose", action="store_true", help="enable DEBUG level logging")

    clean = sub.add_parser("clean", help="Remove --dest along with stamp and .debs cache")
    clean.add_argument("--dest", required=True, type=Path, help="destination directory to remove")
    clean.add_argument("--verbose", action="store_true", help="enable DEBUG level logging")

    return parser


def _configure_logging(verbose: bool) -> None:
    """ロガーを stderr 出力で初期化する。 INFO / DEBUG をプロセス全体に伝播させる。"""
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False


def main(argv: list[str] | None = None) -> int:
    """CLI エントリポイント。 終了コードを int で返す。"""
    parser = _build_argparser()
    args = parser.parse_args(argv)
    _configure_logging(args.verbose)
    try:
        if args.command == "build":
            jobs = args.jobs if args.jobs is not None else _default_jobs()
            if not (1 <= jobs <= 32):
                raise SysrootError(f"--jobs must be in range 1-32, got {jobs}")
            build_rootfs(
                config_path=args.config,
                dest=args.dest,
                cache_dir=args.cache_dir,
                jobs=jobs,
                force=args.force,
            )
            return 0
        if args.command == "clean":
            _clean(args.dest)
            return 0
        # argparse の required=True により未到達。
        raise SysrootError(f"unknown command: {args.command!r}")
    except SysrootError as exc:
        logger.critical("%s: %s", _LOG_PREFIX, exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
