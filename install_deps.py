import os
from setup import (
    download,
    extract,
    get_build_platform,
    install_deps,
    mkdir_p,
    rm_rf
)


def get_nanobind_version() -> str:
    lines = open("pyproject.toml").readlines()
    for line in lines:
        line = line.strip('" ,\r\n')

        if not line.startswith("nanobind"):
            continue

        return line.rsplit("=", 1)[1]


def install_nanobind(version, source_dir, install_dir, platform: str):
    win = platform.startswith("windows_")
    filename = f'v{version}.{"zip" if win else "tar.gz"}'
    rm_rf(os.path.join(source_dir, filename))
    archive = download(
        f'https://github.com/wjakob/nanobind/archive/refs/tags/{filename}',
        output_dir=source_dir)
    rm_rf(os.path.join(install_dir, 'nanobind'))
    extract(archive, output_dir=install_dir, output_dirname='nanobind')


def main():
    platform = get_build_platform()

    base_dir = os.getcwd()
    source_dir = os.path.join(base_dir, '_source')
    build_dir = os.path.join(base_dir, '_build')
    install_dir = os.path.join(base_dir, '_install')
    mkdir_p(source_dir)
    mkdir_p(build_dir)
    mkdir_p(install_dir)

    install_deps(platform, source_dir, build_dir, install_dir)

    # nanobind
    install_nanobind_args = {
        'version': get_nanobind_version(),
        'source_dir': source_dir,
        'install_dir': install_dir,
        'platform': platform.package_name,
    }
    install_nanobind(**install_nanobind_args)


if __name__ == '__main__':
    main()
