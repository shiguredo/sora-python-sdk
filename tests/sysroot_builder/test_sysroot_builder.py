from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

import pytest

from sysroot_builder import (
    MANIFEST_NAME,
    MANIFEST_VERSION,
    SysrootBuildError,
    SysrootConfig,
    SysrootConfigError,
    _apt_options,
    _build_argument_parser,
    _collect_pin_stanzas,
    _ensure_usrmerge_symlinks,
    _file_sha256,
    _fix_absolute_symlinks,
    _install_completed_sysroot,
    _link_pkgconfig_files,
    _postprocess_sysroot,
    _write_apt_files,
    build_sysroot,
    load_sysroot_config,
    main,
    sysroot_config_fingerprint,
)

# ---------------------------------------------------------------------------
# 設定 JSON 生成のヘルパー
# ---------------------------------------------------------------------------


def _write_keyring(path: Path, *, content: bytes = b"dummy-keyring") -> None:
    """署名鍵をテスト用に作成する（内容はダミーだが SHA-256 計算は通る）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _base_config(
    name: str = "raspberry-pi-os_armv8",
    *,
    with_pin: bool = False,
) -> dict[str, object]:
    """テスト全体で共有する最小 JSON 設定を生成する。"""
    debian_repository: dict[str, object] = {
        "url": "https://deb.debian.org/debian",
        "suite": "trixie",
        "components": ["main"],
        "signed_by": "keyrings/debian-archive-keyring.gpg",
    }
    raspberrypi_repository: dict[str, object] = {
        "url": "https://archive.raspberrypi.com/debian",
        "suite": "trixie",
        "components": ["main"],
        "signed_by": "keyrings/raspberrypi-archive-keyring.asc",
    }
    if with_pin:
        raspberrypi_repository["pin_priority"] = 990
    return {
        "name": name,
        "arch": "arm64",
        "triplet": "aarch64-linux-gnu",
        "packages": ["libc6-dev", "libstdc++-14-dev"],
        "repositories": [debian_repository, raspberrypi_repository],
    }


def _write_full_config(
    config_dir: Path,
    *,
    name: str = "raspberry-pi-os_armv8",
    with_pin: bool = False,
    overrides: dict[str, object] | None = None,
) -> Path:
    """設定ファイルと keyring を config_dir に生成し、設定ファイルパスを返す。"""
    config_dir.mkdir(parents=True, exist_ok=True)
    _write_keyring(config_dir / "keyrings" / "debian-archive-keyring.gpg")
    _write_keyring(config_dir / "keyrings" / "raspberrypi-archive-keyring.asc")
    config_data = _base_config(name=name, with_pin=with_pin)
    if overrides is not None:
        config_data.update(overrides)
    config_path = config_dir / f"{name}.json"
    config_path.write_text(json.dumps(config_data), encoding="utf-8")
    return config_path


# ---------------------------------------------------------------------------
# load_sysroot_config の正常系
# ---------------------------------------------------------------------------


def test_load_sysroot_config_resolves_relative_keyring(tmp_path: Path) -> None:
    # 署名鍵は設定ファイルの配置場所を基準に解決し、実行時の cwd に依存させない
    config_path = _write_full_config(tmp_path)

    config = load_sysroot_config(config_path)

    assert config.name == "raspberry-pi-os_armv8"
    assert config.arch == "arm64"
    assert config.triplet == "aarch64-linux-gnu"
    assert config.packages == ("libc6-dev", "libstdc++-14-dev")
    assert config.repositories[0].signed_by == (
        tmp_path / "keyrings" / "debian-archive-keyring.gpg"
    )
    # hostname が RepositoryConfig に固定化されていることを確認する
    assert config.repositories[0].hostname == "deb.debian.org"
    assert config.repositories[1].hostname == "archive.raspberrypi.com"
    # pin_priority を指定しない場合はデフォルト値の None が入っていることを確認する
    assert all(repository.pin_priority is None for repository in config.repositories)


def test_load_sysroot_config_reads_pin_priority(tmp_path: Path) -> None:
    # pin_priority を指定した repository は値が保持され、他は None のままとなる
    config_path = _write_full_config(tmp_path, with_pin=True)

    config = load_sysroot_config(config_path)

    assert config.repositories[0].pin_priority is None
    assert config.repositories[1].pin_priority == 990


def test_load_sysroot_config_accepts_absolute_signed_by(tmp_path: Path) -> None:
    # 絶対パスの signed_by が受容され、resolve 済みの Path として保存される
    config_path = _write_full_config(tmp_path)
    abs_key = tmp_path / "abs-keyring.gpg"
    _write_keyring(abs_key)
    raw_config = json.loads(config_path.read_text(encoding="utf-8"))
    raw_config["repositories"][0]["signed_by"] = str(abs_key)
    config_path.write_text(json.dumps(raw_config), encoding="utf-8")

    config = load_sysroot_config(config_path)

    assert config.repositories[0].signed_by == abs_key


# ---------------------------------------------------------------------------
# load_sysroot_config の異常系（必須値・重複・スキーマ）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", ""),
        ("arch", ""),
        ("triplet", ""),
        ("packages", []),
        ("repositories", []),
    ],
    ids=["empty-name", "empty-arch", "empty-triplet", "empty-packages", "empty-repositories"],
)
def test_load_sysroot_config_rejects_empty_required_values(
    tmp_path: Path, field: str, value: object
) -> None:
    # 不完全な設定で APT を実行せず、読み込み時点で明確に失敗させる
    config_path = _write_full_config(tmp_path)
    raw_config = json.loads(config_path.read_text(encoding="utf-8"))
    raw_config[field] = value
    config_path.write_text(json.dumps(raw_config), encoding="utf-8")

    with pytest.raises(SysrootConfigError):
        load_sysroot_config(config_path)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("packages", "libc6-dev"),
        ("repositories", {}),
        ("name", 42),
        ("arch", ["arm64"]),
    ],
    ids=[
        "packages-not-array",
        "repositories-not-array",
        "name-not-string",
        "arch-not-string",
    ],
)
def test_load_sysroot_config_rejects_type_mismatch(
    tmp_path: Path, field: str, value: object
) -> None:
    # 型不整合（配列であるべき箇所が文字列、文字列であるべき箇所が数値等）を早期に弾く
    config_path = _write_full_config(tmp_path)
    raw_config = json.loads(config_path.read_text(encoding="utf-8"))
    raw_config[field] = value
    config_path.write_text(json.dumps(raw_config), encoding="utf-8")

    with pytest.raises(SysrootConfigError):
        load_sysroot_config(config_path)


def test_load_sysroot_config_rejects_duplicate_packages(tmp_path: Path) -> None:
    # 重複した package 指定は誤設定の兆候として拒否する
    config_path = _write_full_config(
        tmp_path,
        overrides={"packages": ["libc6-dev", "libc6-dev"]},
    )

    with pytest.raises(SysrootConfigError):
        load_sysroot_config(config_path)


def test_load_sysroot_config_rejects_missing_signed_by(tmp_path: Path) -> None:
    # 相対パスで指定された signed_by の実体が無ければ、生成前にエラーにする
    config_path = _write_full_config(tmp_path)
    (tmp_path / "keyrings" / "debian-archive-keyring.gpg").unlink()

    with pytest.raises(SysrootConfigError):
        load_sysroot_config(config_path)


def test_load_sysroot_config_rejects_signed_by_with_forbidden_chars(tmp_path: Path) -> None:
    # 解決後の絶対パスに空白を含む配置を作り、CONFIG_TOKEN_PATTERN の拒否経路を通す
    config_dir = tmp_path / "has space"
    config_path = _write_full_config(config_dir)

    with pytest.raises(SysrootConfigError):
        load_sysroot_config(config_path)


def test_load_sysroot_config_rejects_unknown_arch(tmp_path: Path) -> None:
    # arch は arm64 のみの whitelist で運用し、amd64 / aarch64 等の別表記を拒否する
    config_path = _write_full_config(
        tmp_path,
        overrides={"arch": "amd64"},
    )

    with pytest.raises(SysrootConfigError):
        load_sysroot_config(config_path)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", "raspberry-pi;os"),
        ("triplet", "aarch64-linux-gnu$"),
    ],
    ids=["name-with-semicolon", "triplet-with-dollar"],
)
def test_load_sysroot_config_rejects_token_forbidden_chars(
    tmp_path: Path, field: str, value: str
) -> None:
    # token 文字集合 CONFIG_TOKEN_PATTERN を破る値は APT 実行前に拒否する
    config_path = _write_full_config(tmp_path)
    raw_config = json.loads(config_path.read_text(encoding="utf-8"))
    raw_config[field] = value
    config_path.write_text(json.dumps(raw_config), encoding="utf-8")

    with pytest.raises(SysrootConfigError):
        load_sysroot_config(config_path)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("suite", "trixie main"),
        ("components", ["main;evil"]),
    ],
    ids=["suite-with-space", "component-with-semicolon"],
)
def test_load_sysroot_config_rejects_repository_token_forbidden_chars(
    tmp_path: Path, field: str, value: object
) -> None:
    # repositories 内の suite / components も token 制限を通り、
    # sources.list の区切りを壊す文字を弾く
    config_path = _write_full_config(tmp_path)
    raw_config = json.loads(config_path.read_text(encoding="utf-8"))
    raw_config["repositories"][0][field] = value
    config_path.write_text(json.dumps(raw_config), encoding="utf-8")

    with pytest.raises(SysrootConfigError):
        load_sysroot_config(config_path)


def test_load_sysroot_config_rejects_package_with_forbidden_chars(tmp_path: Path) -> None:
    # packages 内の値も同じ token 制限を通り、sources.list / コマンドラインへの
    # インジェクションを構文レベルで防ぐ
    config_path = _write_full_config(
        tmp_path,
        overrides={"packages": ["libc6-dev$"]},
    )

    with pytest.raises(SysrootConfigError):
        load_sysroot_config(config_path)


# ---------------------------------------------------------------------------
# load_sysroot_config の異常系（URL バリデーション）
# ---------------------------------------------------------------------------


def test_load_sysroot_config_rejects_insecure_repository_url(tmp_path: Path) -> None:
    # 署名検証だけでなく通信経路も保護し、HTTP への意図しない後退を拒否する
    config_path = _write_full_config(tmp_path)
    raw_config = json.loads(config_path.read_text(encoding="utf-8"))
    raw_config["repositories"][0]["url"] = "http://deb.debian.org/debian"
    config_path.write_text(json.dumps(raw_config), encoding="utf-8")

    with pytest.raises(SysrootConfigError):
        load_sysroot_config(config_path)


@pytest.mark.parametrize(
    "url",
    [
        "https://user:secret@deb.debian.org/debian",
        "https://deb.debian.org/debian?arch=arm64",
        "https://deb.debian.org/debian#section",
    ],
    ids=["userinfo", "query", "fragment"],
)
def test_load_sysroot_config_rejects_url_with_forbidden_parts(tmp_path: Path, url: str) -> None:
    # userinfo / query / fragment を含む URL は pin 対象特定を曖昧にするため拒否する
    config_path = _write_full_config(tmp_path)
    raw_config = json.loads(config_path.read_text(encoding="utf-8"))
    raw_config["repositories"][0]["url"] = url
    config_path.write_text(json.dumps(raw_config), encoding="utf-8")

    with pytest.raises(SysrootConfigError):
        load_sysroot_config(config_path)


def test_load_sysroot_config_rejects_url_without_hostname(tmp_path: Path) -> None:
    # netloc は非空だが hostname が抽出できない URL を hostname バリデーションで弾く
    config_path = _write_full_config(tmp_path)
    raw_config = json.loads(config_path.read_text(encoding="utf-8"))
    raw_config["repositories"][0]["url"] = "https://:8080/debian"
    config_path.write_text(json.dumps(raw_config), encoding="utf-8")

    with pytest.raises(SysrootConfigError):
        load_sysroot_config(config_path)


@pytest.mark.parametrize(
    "url",
    [
        "https://deb.debian.org/deb ian",
        "https://deb.debian.org/[trixie]",
        "https://deb.debian.org/]hack[",
    ],
    ids=["url-with-space", "url-with-bracket-open", "url-with-bracket-close"],
)
def test_load_sysroot_config_rejects_url_with_shell_hostile_chars(tmp_path: Path, url: str) -> None:
    # sources.list への埋め込みを壊す空白と角括弧を含む URL は拒否する
    config_path = _write_full_config(tmp_path)
    raw_config = json.loads(config_path.read_text(encoding="utf-8"))
    raw_config["repositories"][0]["url"] = url
    config_path.write_text(json.dumps(raw_config), encoding="utf-8")

    with pytest.raises(SysrootConfigError):
        load_sysroot_config(config_path)


def test_load_sysroot_config_rejects_unknown_repository_key(tmp_path: Path) -> None:
    # 未知キーは pin_priority などの綴り違いを黙って無視しないための保険として拒否する
    config_path = _write_full_config(tmp_path)
    raw_config = json.loads(config_path.read_text(encoding="utf-8"))
    raw_config["repositories"][0]["pin_priorty"] = 990
    config_path.write_text(json.dumps(raw_config), encoding="utf-8")

    with pytest.raises(SysrootConfigError):
        load_sysroot_config(config_path)


# ---------------------------------------------------------------------------
# pin_priority のバリデーション
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [0, 1001, -1],
    ids=["below-min", "above-max", "negative"],
)
def test_load_sysroot_config_rejects_pin_priority_out_of_range(tmp_path: Path, value: int) -> None:
    # pin_priority は 1..1000 の範囲外なら明示的にエラーとし、暗黙の解釈を避ける
    config_path = _write_full_config(tmp_path, with_pin=True)
    raw_config = json.loads(config_path.read_text(encoding="utf-8"))
    raw_config["repositories"][1]["pin_priority"] = value
    config_path.write_text(json.dumps(raw_config), encoding="utf-8")

    with pytest.raises(SysrootConfigError):
        load_sysroot_config(config_path)


@pytest.mark.parametrize("value", [1, 1000], ids=["min", "max"])
def test_load_sysroot_config_accepts_pin_priority_boundary(tmp_path: Path, value: int) -> None:
    # 境界値 (min / max) が受容されることを担保し、比較演算の off-by-one を防ぐ
    config_path = _write_full_config(tmp_path, with_pin=True)
    raw_config = json.loads(config_path.read_text(encoding="utf-8"))
    raw_config["repositories"][1]["pin_priority"] = value
    config_path.write_text(json.dumps(raw_config), encoding="utf-8")

    config = load_sysroot_config(config_path)

    assert config.repositories[1].pin_priority == value


@pytest.mark.parametrize("value", [True, False], ids=["true", "false"])
def test_load_sysroot_config_rejects_pin_priority_bool(tmp_path: Path, value: bool) -> None:
    # bool は int のサブクラスなので数値扱いされる。設定ファイルでの True/False は意図と外れる
    config_path = _write_full_config(tmp_path, with_pin=True)
    raw_config = json.loads(config_path.read_text(encoding="utf-8"))
    raw_config["repositories"][1]["pin_priority"] = value
    config_path.write_text(json.dumps(raw_config), encoding="utf-8")

    with pytest.raises(SysrootConfigError):
        load_sysroot_config(config_path)


def test_load_sysroot_config_rejects_conflicting_pin_priority(tmp_path: Path) -> None:
    # 同一 hostname に対して異なる pin_priority を与えても片方しか効かず、意図しない優先付けになる
    config_path = _write_full_config(tmp_path, with_pin=True)
    raw_config = json.loads(config_path.read_text(encoding="utf-8"))
    raw_config["repositories"].append(
        {
            "url": "https://archive.raspberrypi.com/debian",
            "suite": "trixie",
            "components": ["contrib"],
            "signed_by": "keyrings/raspberrypi-archive-keyring.asc",
            "pin_priority": 500,
        }
    )
    config_path.write_text(json.dumps(raw_config), encoding="utf-8")

    with pytest.raises(SysrootConfigError):
        load_sysroot_config(config_path)


def test_load_sysroot_config_rejects_mixed_none_and_priority(tmp_path: Path) -> None:
    # 同一 hostname の一方に pin_priority を指定し、もう一方に指定しないのも混在扱いにする
    config_path = _write_full_config(tmp_path, with_pin=False)
    raw_config = json.loads(config_path.read_text(encoding="utf-8"))
    raw_config["repositories"].append(
        {
            "url": "https://deb.debian.org/debian",
            "suite": "trixie",
            "components": ["contrib"],
            "signed_by": "keyrings/debian-archive-keyring.gpg",
            "pin_priority": 700,
        }
    )
    config_path.write_text(json.dumps(raw_config), encoding="utf-8")

    with pytest.raises(SysrootConfigError):
        load_sysroot_config(config_path)


# ---------------------------------------------------------------------------
# fingerprint の挙動
# ---------------------------------------------------------------------------


def test_sysroot_config_fingerprint_is_independent_of_config_path(tmp_path: Path) -> None:
    # 同一内容なら checkout の場所が異なっても同じ sysroot と判定できるようにする
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    for config_dir in (first_dir, second_dir):
        _write_full_config(config_dir)

    first = load_sysroot_config(first_dir / "raspberry-pi-os_armv8.json")
    second = load_sysroot_config(second_dir / "raspberry-pi-os_armv8.json")

    assert sysroot_config_fingerprint(first) == sysroot_config_fingerprint(second)


def test_sysroot_config_fingerprint_stable_without_pin(tmp_path: Path) -> None:
    # pin_priority を指定しない設定の fingerprint は、
    # pin_priority キー導入前と同じ payload になっている（余計な null を含めない）
    config_path = _write_full_config(tmp_path)
    config = load_sysroot_config(config_path)

    fingerprint = sysroot_config_fingerprint(config)

    expected_payload = {
        "name": config.name,
        "arch": config.arch,
        "triplet": config.triplet,
        "packages": list(config.packages),
        "repositories": [
            {
                "url": repository.url,
                "suite": repository.suite,
                "components": list(repository.components),
                "signed_by_sha256": _file_sha256(repository.signed_by),
            }
            for repository in config.repositories
        ],
    }
    expected_encoded = json.dumps(
        expected_payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    )
    expected = hashlib.sha256(expected_encoded.encode("utf-8")).hexdigest()
    assert fingerprint == expected


def test_sysroot_config_fingerprint_changes_with_pin(tmp_path: Path) -> None:
    # pin_priority を追加すると fingerprint が変わり、既存 sysroot は再利用されない
    without_pin_dir = tmp_path / "without"
    with_pin_dir = tmp_path / "with"
    _write_full_config(without_pin_dir, with_pin=False)
    _write_full_config(with_pin_dir, with_pin=True)

    without_pin = load_sysroot_config(without_pin_dir / "raspberry-pi-os_armv8.json")
    with_pin = load_sysroot_config(with_pin_dir / "raspberry-pi-os_armv8.json")

    assert sysroot_config_fingerprint(without_pin) != sysroot_config_fingerprint(with_pin)


def test_sysroot_config_fingerprint_changes_with_keyring_bytes(tmp_path: Path) -> None:
    # 同じ設定でも keyring バイト列が異なれば fingerprint は変わる
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    _write_full_config(first_dir)
    _write_full_config(second_dir)
    # 片方の keyring 内容だけ書き換える
    _write_keyring(
        second_dir / "keyrings" / "debian-archive-keyring.gpg", content=b"different-content"
    )

    first = load_sysroot_config(first_dir / "raspberry-pi-os_armv8.json")
    second = load_sysroot_config(second_dir / "raspberry-pi-os_armv8.json")

    assert sysroot_config_fingerprint(first) != sysroot_config_fingerprint(second)


# ---------------------------------------------------------------------------
# APT オプションと sources.list / preferences 生成
# ---------------------------------------------------------------------------


def test_apt_options_isolates_state_and_preferences(tmp_path: Path) -> None:
    # ホストの /var/lib/apt / /etc/apt を参照しないように、
    # 主要な Dir::* が work_dir 配下か /dev/null を向いていることを確認する
    config_path = _write_full_config(tmp_path)
    config = load_sysroot_config(config_path)
    work_dir = tmp_path / "work"
    work_dir.mkdir()

    layout = _write_apt_files(config, work_dir)
    options = _apt_options(layout)

    joined = " ".join(options)
    assert f"Dir::State={work_dir / 'state'}" in joined
    assert f"Dir::State::status={work_dir / 'state' / 'status'}" in joined
    assert f"Dir::Cache={work_dir / 'state' / 'cache'}" in joined
    assert f"Dir::Etc::sourcelist={work_dir / 'sources.list'}" in joined
    assert "Dir::Etc::sourceparts=/dev/null" in joined
    assert f"Dir::Etc::preferences={layout.preferences}" in joined
    assert f"Dir::Etc::preferencesparts={work_dir / 'preferencesparts'}" in joined
    assert "Debug::NoLocking=true" in joined


def test_apt_options_reflects_pinned_preferences(tmp_path: Path) -> None:
    # pin_priority を持つ設定では Dir::Etc::preferences が /dev/null ではなく
    # work_dir 配下の preferences ファイルを指す
    config_path = _write_full_config(tmp_path, with_pin=True)
    config = load_sysroot_config(config_path)
    work_dir = tmp_path / "work"
    work_dir.mkdir()

    layout = _write_apt_files(config, work_dir)
    options = _apt_options(layout)

    joined = " ".join(options)
    assert f"Dir::Etc::preferences={work_dir / 'preferences'}" in joined
    assert "Dir::Etc::preferences=/dev/null" not in joined


def test_write_apt_files_creates_state_dirs_and_status(tmp_path: Path) -> None:
    # apt-get update / install が期待する state ディレクトリと空の status ファイルを担保する
    config_path = _write_full_config(tmp_path)
    config = load_sysroot_config(config_path)
    work_dir = tmp_path / "work"
    work_dir.mkdir()

    _write_apt_files(config, work_dir)

    assert (work_dir / "state" / "lists" / "partial").is_dir()
    assert (work_dir / "state" / "cache" / "archives" / "partial").is_dir()
    assert (work_dir / "state" / "status").is_file()


def test_write_apt_files_generates_apt_conf_with_isolation_directives(tmp_path: Path) -> None:
    # apt.conf にホスト /etc/apt 隔離指示と APT::Architecture などが確実に書かれる
    config_path = _write_full_config(tmp_path)
    config = load_sysroot_config(config_path)
    work_dir = tmp_path / "work"
    work_dir.mkdir()

    _write_apt_files(config, work_dir)
    apt_conf = (work_dir / "apt.conf").read_text(encoding="utf-8")

    assert 'Dir::Etc::main "/dev/null";' in apt_conf
    assert 'Dir::Etc::parts "/dev/null";' in apt_conf
    assert 'APT::Architecture "arm64";' in apt_conf
    assert 'APT::Architectures { "arm64"; };' in apt_conf
    assert 'Acquire::Languages "none";' in apt_conf
    assert 'APT::Install-Recommends "false";' in apt_conf
    assert 'APT::Install-Suggests "false";' in apt_conf


def test_write_apt_files_sources_list_line_format(tmp_path: Path) -> None:
    # sources.list の各行が deb [arch=... signed-by=絶対パス] url suite components の完全一致
    config_path = _write_full_config(tmp_path)
    config = load_sysroot_config(config_path)
    work_dir = tmp_path / "work"
    work_dir.mkdir()

    _write_apt_files(config, work_dir)
    lines = (work_dir / "sources.list").read_text(encoding="utf-8").splitlines()

    for line, repository in zip(lines, config.repositories, strict=True):
        expected = (
            f"deb [arch=arm64 signed-by={repository.signed_by}] "
            f"{repository.url} {repository.suite} {' '.join(repository.components)}"
        )
        assert line == expected


def test_write_apt_files_generates_https_sources_and_preferencesparts(tmp_path: Path) -> None:
    # sources.list が HTTPS + signed-by で書かれ、preferencesparts の隔離ディレクトリが作成される
    config_path = _write_full_config(tmp_path)
    config = load_sysroot_config(config_path)
    work_dir = tmp_path / "work"
    work_dir.mkdir()

    layout = _write_apt_files(config, work_dir)

    sources = (work_dir / "sources.list").read_text(encoding="utf-8")
    assert "https://deb.debian.org/debian" in sources
    assert "signed-by=" in sources
    assert "http://" not in sources
    parts = work_dir / "preferencesparts"
    assert parts.is_dir()
    assert not any(parts.iterdir())
    # pin 未指定のため preferences は /dev/null を指す
    assert layout.preferences == Path("/dev/null")


def test_write_apt_files_generates_pin_preferences(tmp_path: Path) -> None:
    # pin_priority が指定された repository の hostname に対して pin stanza が生成される
    config_path = _write_full_config(tmp_path, with_pin=True)
    config = load_sysroot_config(config_path)
    work_dir = tmp_path / "work"
    work_dir.mkdir()

    layout = _write_apt_files(config, work_dir)

    assert layout.preferences == work_dir / "preferences"
    content = layout.preferences.read_text(encoding="utf-8")
    assert "Package: *" in content
    assert 'Pin: origin "archive.raspberrypi.com"' in content
    assert "Pin-Priority: 990" in content
    # Debian 側は pin を持たないため Pin 行に含まれない
    assert 'Pin: origin "deb.debian.org"' not in content


def test_collect_pin_stanzas_returns_empty_when_no_pin(tmp_path: Path) -> None:
    # pin 無し設定では stanza が 1 件も生成されない
    config_path = _write_full_config(tmp_path)
    config = load_sysroot_config(config_path)

    assert _collect_pin_stanzas(config) == []


def test_collect_pin_stanzas_deduplicates_same_hostname(tmp_path: Path) -> None:
    # 同一 hostname / 同一 priority を持つ repository が 2 件あっても stanza は 1 件に集約する
    config_path = _write_full_config(tmp_path, with_pin=True)
    raw_config = json.loads(config_path.read_text(encoding="utf-8"))
    raw_config["repositories"].append(
        {
            "url": "https://archive.raspberrypi.com/debian",
            "suite": "trixie",
            "components": ["contrib"],
            "signed_by": "keyrings/raspberrypi-archive-keyring.asc",
            "pin_priority": 990,
        }
    )
    config_path.write_text(json.dumps(raw_config), encoding="utf-8")
    config = load_sysroot_config(config_path)

    stanzas = _collect_pin_stanzas(config)

    assert len(stanzas) == 1
    assert 'Pin: origin "archive.raspberrypi.com"' in stanzas[0]


# ---------------------------------------------------------------------------
# 後処理（symlink・pkg-config・usrmerge）
# ---------------------------------------------------------------------------


def test_ensure_usrmerge_symlinks_creates_missing_links(tmp_path: Path) -> None:
    # dpkg-deb --extract で作られない usr* -> legacy の互換リンクを 4 対全て補う
    for merged in ("usr/bin", "usr/sbin", "usr/lib", "usr/lib64"):
        (tmp_path / merged).mkdir(parents=True)

    _ensure_usrmerge_symlinks(tmp_path)

    for legacy, merged in (
        ("bin", "usr/bin"),
        ("sbin", "usr/sbin"),
        ("lib", "usr/lib"),
        ("lib64", "usr/lib64"),
    ):
        link = tmp_path / legacy
        assert link.is_symlink()
        assert os.readlink(link) == merged


def test_ensure_usrmerge_symlinks_respects_existing(tmp_path: Path) -> None:
    # 既に実体（ディレクトリ / symlink）が居る legacy は上書きしない
    (tmp_path / "usr" / "lib").mkdir(parents=True)
    (tmp_path / "lib").mkdir()

    _ensure_usrmerge_symlinks(tmp_path)

    assert not (tmp_path / "lib").is_symlink()
    assert (tmp_path / "lib").is_dir()


def test_ensure_usrmerge_symlinks_skips_when_target_missing(tmp_path: Path) -> None:
    # マージ先が無い状態で legacy を作ってしまうと壊れた symlink が残る。作らない挙動を担保する
    _ensure_usrmerge_symlinks(tmp_path)

    for legacy in ("bin", "sbin", "lib", "lib64"):
        assert not (tmp_path / legacy).exists()


def test_postprocess_sysroot_applies_all_steps(tmp_path: Path) -> None:
    # 後処理 3 段（usrmerge / 絶対 symlink 相対化 / pkg-config link）が合成される
    # usr/lib を用意して usrmerge / pkg-config link を有効化する
    (tmp_path / "usr" / "lib").mkdir(parents=True)
    (tmp_path / "usr" / "bin").mkdir(parents=True)
    (tmp_path / "usr" / "sbin").mkdir(parents=True)
    (tmp_path / "usr" / "lib64").mkdir(parents=True)
    pkgconfig = tmp_path / "usr" / "lib" / "aarch64-linux-gnu" / "pkgconfig"
    pkgconfig.mkdir(parents=True)
    (pkgconfig / "example.pc").touch()
    target = tmp_path / "usr" / "lib" / "aarch64-linux-gnu" / "libexample.so.1"
    target.touch()
    link = target.parent / "libexample.so"
    link.symlink_to("/usr/lib/aarch64-linux-gnu/libexample.so.1")

    _postprocess_sysroot(tmp_path, "aarch64-linux-gnu")

    assert (tmp_path / "lib").is_symlink()
    assert not os.readlink(link).startswith("/")
    share_link = tmp_path / "usr" / "share" / "pkgconfig" / "example.pc"
    assert share_link.is_symlink()


def test_fix_absolute_symlinks_makes_existing_target_relative(tmp_path: Path) -> None:
    # sysroot の移動後もリンクがホスト側の /usr/lib を参照しないことを確認する
    target = tmp_path / "usr" / "lib" / "aarch64-linux-gnu" / "libexample.so.1"
    target.parent.mkdir(parents=True)
    target.touch()
    link = target.parent / "libexample.so"
    link.symlink_to("/usr/lib/aarch64-linux-gnu/libexample.so.1")

    _fix_absolute_symlinks(tmp_path)

    assert link.is_symlink()
    assert not os.readlink(link).startswith("/")
    assert link.resolve() == target


def test_fix_absolute_symlinks_keeps_unresolved_target(tmp_path: Path) -> None:
    # alternatives など展開だけでは解決しないリンクを誤った相対リンクへ変更しない
    link = tmp_path / "usr" / "bin" / "example"
    link.parent.mkdir(parents=True)
    link.symlink_to("/etc/alternatives/example")

    _fix_absolute_symlinks(tmp_path)

    assert os.readlink(link) == "/etc/alternatives/example"


def test_fix_absolute_symlinks_ignores_regular_files(tmp_path: Path) -> None:
    # 通常ファイルは対象外。ここを緩めて symlink 化してしまうと sysroot が壊れる
    regular = tmp_path / "usr" / "lib" / "regular.txt"
    regular.parent.mkdir(parents=True)
    regular.write_text("keep", encoding="utf-8")

    _fix_absolute_symlinks(tmp_path)

    assert regular.is_file()
    assert regular.read_text(encoding="utf-8") == "keep"


def test_fix_absolute_symlinks_keeps_relative_symlinks(tmp_path: Path) -> None:
    # もともと相対 symlink になっているものは書き換えない
    real = tmp_path / "usr" / "lib" / "real.so"
    real.parent.mkdir(parents=True)
    real.touch()
    link = real.parent / "alias.so"
    link.symlink_to("real.so")

    _fix_absolute_symlinks(tmp_path)

    assert os.readlink(link) == "real.so"


def test_fix_absolute_symlinks_rejects_traversal_target(tmp_path: Path) -> None:
    # 絶対 symlink のターゲットが `..` を含み sysroot 境界を越える場合、書き換えない
    outside = tmp_path / "outside" / "marker"
    outside.parent.mkdir(parents=True)
    outside.write_text("host", encoding="utf-8")
    root = tmp_path / "root"
    link_dir = root / "usr" / "lib"
    link_dir.mkdir(parents=True)
    link = link_dir / "escape"
    # /../outside/marker は root からは root/../outside/marker = tmp_path/outside/marker で
    # ホスト側に到達してしまう構成
    link.symlink_to("/../outside/marker")

    _fix_absolute_symlinks(root)

    assert link.is_symlink()
    assert os.readlink(link) == "/../outside/marker"


def test_link_pkgconfig_files_creates_compatibility_links(tmp_path: Path) -> None:
    # WebRTC の pkg-config 探索が従来と同じ場所からターゲット用定義を発見できるようにする
    source_dir = tmp_path / "usr" / "lib" / "aarch64-linux-gnu" / "pkgconfig"
    source_dir.mkdir(parents=True)
    (source_dir / "example.pc").touch()

    _link_pkgconfig_files(tmp_path, "aarch64-linux-gnu")

    link = tmp_path / "usr" / "share" / "pkgconfig" / "example.pc"
    assert link.is_symlink()
    assert os.readlink(link) == "../../lib/aarch64-linux-gnu/pkgconfig/example.pc"


def test_link_pkgconfig_files_keeps_existing_destination(tmp_path: Path) -> None:
    # パッケージが既に usr/share/pkgconfig へ配置した定義を上書きしない
    source_dir = tmp_path / "usr" / "lib" / "aarch64-linux-gnu" / "pkgconfig"
    source_dir.mkdir(parents=True)
    (source_dir / "example.pc").write_text("triplet", encoding="utf-8")
    destination_dir = tmp_path / "usr" / "share" / "pkgconfig"
    destination_dir.mkdir(parents=True)
    original = destination_dir / "example.pc"
    original.write_text("original", encoding="utf-8")

    _link_pkgconfig_files(tmp_path, "aarch64-linux-gnu")

    assert original.read_text(encoding="utf-8") == "original"
    assert not original.is_symlink()


def test_link_pkgconfig_files_no_op_when_source_absent(tmp_path: Path) -> None:
    # triplet 固有ディレクトリが無ければ何もしない（Jetson 以外の safety net）
    _link_pkgconfig_files(tmp_path, "aarch64-linux-gnu")

    assert not (tmp_path / "usr" / "share" / "pkgconfig").exists()


def test_link_pkgconfig_files_ignores_non_pc_entries(tmp_path: Path) -> None:
    # .pc 以外のファイルには互換 link を張らない
    source_dir = tmp_path / "usr" / "lib" / "aarch64-linux-gnu" / "pkgconfig"
    source_dir.mkdir(parents=True)
    (source_dir / "example.pc").touch()
    (source_dir / "README").touch()

    _link_pkgconfig_files(tmp_path, "aarch64-linux-gnu")

    destination_dir = tmp_path / "usr" / "share" / "pkgconfig"
    assert (destination_dir / "example.pc").is_symlink()
    assert not (destination_dir / "README").exists()


# ---------------------------------------------------------------------------
# _install_completed_sysroot
# ---------------------------------------------------------------------------


def test_install_completed_sysroot_installs_when_no_previous(tmp_path: Path) -> None:
    # 初回ビルド相当。output_dir が存在しない状態から single rename で配置する
    output_dir = tmp_path / "rootfs"
    new_root = tmp_path / "new"
    new_root.mkdir()
    (new_root / "new.txt").write_text("new", encoding="utf-8")

    _install_completed_sysroot(new_root, output_dir)

    assert output_dir.is_dir()
    assert (output_dir / "new.txt").read_text(encoding="utf-8") == "new"
    # backup 側のパスは残らない
    assert not (tmp_path / ".rootfs.previous").exists()


def test_install_completed_sysroot_rejects_stale_backup(tmp_path: Path) -> None:
    # 前回失敗の残骸が backup 位置にあると次回以降が silently 詰まる。
    # 明示的に SysrootBuildError で拒否し、人手対応へ倒す
    output_dir = tmp_path / "rootfs"
    output_dir.mkdir()
    stale = tmp_path / ".rootfs.previous"
    stale.mkdir()
    (stale / "leftover.txt").write_text("old", encoding="utf-8")
    new_root = tmp_path / "new"
    new_root.mkdir()

    with pytest.raises(SysrootBuildError, match="Stale backup"):
        _install_completed_sysroot(new_root, output_dir)

    # 拒否した以上、既存 output_dir と stale backup はそのまま残す
    assert output_dir.is_dir()
    assert stale.is_dir()


def test_install_completed_sysroot_replaces_existing(tmp_path: Path) -> None:
    # 既存の出力を退避してから新規を配置することで、途中状態が可視化されない
    output_dir = tmp_path / "rootfs"
    output_dir.mkdir()
    (output_dir / "old.txt").write_text("old", encoding="utf-8")
    new_root = tmp_path / "new"
    new_root.mkdir()
    (new_root / "new.txt").write_text("new", encoding="utf-8")

    _install_completed_sysroot(new_root, output_dir)

    assert (output_dir / "new.txt").read_text(encoding="utf-8") == "new"
    assert not (output_dir / "old.txt").exists()


def test_install_completed_sysroot_replaces_symlink(tmp_path: Path) -> None:
    # 既存が symlink のときは unlink 経由で退避し、正しく新規で置き換える
    target = tmp_path / "target"
    target.mkdir()
    (target / "old.txt").write_text("old", encoding="utf-8")
    output_dir = tmp_path / "rootfs"
    output_dir.symlink_to(target)
    new_root = tmp_path / "new"
    new_root.mkdir()
    (new_root / "new.txt").write_text("new", encoding="utf-8")

    _install_completed_sysroot(new_root, output_dir)

    assert output_dir.is_dir()
    assert not output_dir.is_symlink()
    assert (output_dir / "new.txt").read_text(encoding="utf-8") == "new"
    # symlink 越しの target 自体は影響を受けない
    assert target.is_dir()


def test_install_completed_sysroot_restores_on_failure(tmp_path: Path) -> None:
    # 新規配置に失敗したら既存出力を元へ戻し、呼び出し側にエラーを伝える
    output_dir = tmp_path / "rootfs"
    output_dir.mkdir()
    (output_dir / "old.txt").write_text("old", encoding="utf-8")
    new_root = tmp_path / "missing"

    with pytest.raises(FileNotFoundError):
        _install_completed_sysroot(new_root, output_dir)

    assert (output_dir / "old.txt").read_text(encoding="utf-8") == "old"


# ---------------------------------------------------------------------------
# build_sysroot の manifest 判定
# ---------------------------------------------------------------------------


def _place_manifest(output_dir: Path, config: SysrootConfig, *, version: int) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "format_version": version,
        "fingerprint": sysroot_config_fingerprint(config),
    }
    (output_dir / MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")


def test_build_sysroot_reuses_matching_manifest(tmp_path: Path) -> None:
    # 一致する manifest があれば APT を再実行せず、既存 sysroot を再利用する
    config_path = _write_full_config(tmp_path / "config")
    config = load_sysroot_config(config_path)
    output_dir = tmp_path / "rootfs"
    _place_manifest(output_dir, config, version=MANIFEST_VERSION)

    built = build_sysroot(config, output_dir)

    assert built is False


def test_build_sysroot_rejects_old_manifest_without_force(tmp_path: Path) -> None:
    # 生成形式が変わった sysroot を再利用せず、明示的な再生成を要求する
    config_path = _write_full_config(tmp_path / "config")
    config = load_sysroot_config(config_path)
    output_dir = tmp_path / "rootfs"
    _place_manifest(output_dir, config, version=0)

    with pytest.raises(SysrootBuildError):
        build_sysroot(config, output_dir)


def test_build_sysroot_rejects_stale_directory_without_force(tmp_path: Path) -> None:
    # 設定由来か不明な既存ディレクトリを黙って削除または再利用しない
    config_path = _write_full_config(tmp_path / "config")
    config = load_sysroot_config(config_path)
    output_dir = tmp_path / "rootfs"
    output_dir.mkdir()

    with pytest.raises(SysrootBuildError):
        build_sysroot(config, output_dir)


def test_build_sysroot_rejects_broken_manifest_without_force(tmp_path: Path) -> None:
    # manifest が壊れて読めない既存 rootfs は「由来不明」として拒否する
    config_path = _write_full_config(tmp_path / "config")
    config = load_sysroot_config(config_path)
    output_dir = tmp_path / "rootfs"
    output_dir.mkdir()
    (output_dir / MANIFEST_NAME).write_text("{ broken json", encoding="utf-8")

    with pytest.raises(SysrootBuildError):
        build_sysroot(config, output_dir)


def test_build_sysroot_rejects_mismatched_fingerprint_without_force(tmp_path: Path) -> None:
    # fingerprint が一致しない manifest は format_version が最新でも再利用せず拒否する
    config_path = _write_full_config(tmp_path / "config")
    config = load_sysroot_config(config_path)
    output_dir = tmp_path / "rootfs"
    output_dir.mkdir()
    manifest = {
        "format_version": MANIFEST_VERSION,
        "fingerprint": "0" * 64,
    }
    (output_dir / MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(SysrootBuildError):
        build_sysroot(config, output_dir)


def test_build_sysroot_rejects_stale_symlink_without_force(tmp_path: Path) -> None:
    # 壊れたリンクも既存出力として扱い、利用者の明示なしに置き換えない
    config_path = _write_full_config(tmp_path / "config")
    config = load_sysroot_config(config_path)
    output_dir = tmp_path / "rootfs"
    output_dir.symlink_to(tmp_path / "missing")

    with pytest.raises(SysrootBuildError):
        build_sysroot(config, output_dir)


def test_build_sysroot_force_bypasses_stale_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # --force を渡すと stale 判定を通り抜けて apt-get 依存段階まで進む。
    # PATH を空にして apt-get 自体を見つからない状態にすると、
    # _require_command 経由で SysrootBuildError が上がることで通過を確認できる。
    monkeypatch.setenv("PATH", "")
    config_path = _write_full_config(tmp_path / "config")
    config = load_sysroot_config(config_path)
    output_dir = tmp_path / "rootfs"
    output_dir.mkdir()

    with pytest.raises(SysrootBuildError, match="apt-get"):
        build_sysroot(config, output_dir, force=True)


def test_build_sysroot_force_bypasses_matching_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # --force を渡すと fingerprint が一致する既存 rootfs すら再利用せず apt-get 段階へ進む。
    # 依存更新後に開発者が明示的に作り直す典型シナリオを担保する
    monkeypatch.setenv("PATH", "")
    config_path = _write_full_config(tmp_path / "config")
    config = load_sysroot_config(config_path)
    output_dir = tmp_path / "rootfs"
    _place_manifest(output_dir, config, version=MANIFEST_VERSION)

    with pytest.raises(SysrootBuildError, match="apt-get"):
        build_sysroot(config, output_dir, force=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_argument_parser_recognizes_force() -> None:
    # --force が正しく解釈され、既定は False であることを確認する
    parser = _build_argument_parser()

    without_force = parser.parse_args(["--config", "a.json", "--dest", "b"])
    with_force = parser.parse_args(["--config", "a.json", "--dest", "b", "--force"])

    assert without_force.force is False
    assert with_force.force is True


def test_argument_parser_requires_config_and_dest() -> None:
    # --config と --dest は必須引数で、片方でも欠けたらパーサが SystemExit で失敗する
    parser = _build_argument_parser()

    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_main_rejects_config_name_stem_mismatch(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # 設定ファイル名と config.name の不一致は他ターゲットの設定を渡した典型的な誤りとして拒否する
    config_path = _write_full_config(tmp_path, name="raspberry-pi-os_armv8")
    raw_config = json.loads(config_path.read_text(encoding="utf-8"))
    raw_config["name"] = "ubuntu-24.04_armv8"
    config_path.write_text(json.dumps(raw_config), encoding="utf-8")
    dest_dir = tmp_path / "dest"

    return_code = main(["--config", str(config_path), "--dest", str(dest_dir)])

    assert return_code == 1
    error_output = capsys.readouterr().err
    assert "does not match file stem" in error_output


def test_main_returns_1_on_config_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # 設定エラーは英語メッセージを標準エラーへ出し、終了コード 1 で返す
    config_path = _write_full_config(tmp_path)
    raw_config = json.loads(config_path.read_text(encoding="utf-8"))
    raw_config["arch"] = "amd64"
    config_path.write_text(json.dumps(raw_config), encoding="utf-8")
    dest_dir = tmp_path / "dest"

    return_code = main(["--config", str(config_path), "--dest", str(dest_dir)])

    assert return_code == 1
    error_output = capsys.readouterr().err
    assert re.search(r"^error: ", error_output, re.MULTILINE)
    # メッセージは英語で書かれ、日本語（ひらがな / カタカナ / 漢字）を含まない
    assert not re.search(r"[぀-ヿ一-鿿]", error_output)


def test_main_returns_0_when_manifest_matches(tmp_path: Path) -> None:
    # 既存 rootfs に一致する manifest を置いた場合、main は生成を skip して 0 を返す
    config_path = _write_full_config(tmp_path)
    config = load_sysroot_config(config_path)
    dest = tmp_path / "dest" / "rootfs"
    _place_manifest(dest, config, version=MANIFEST_VERSION)

    return_code = main(["--config", str(config_path), "--dest", str(dest)])

    assert return_code == 0


# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------


def test_manifest_name_is_stable() -> None:
    # cross repository 互換の恒久名として値をロックする
    assert MANIFEST_NAME == ".webrtc-build-sysroot.json"
