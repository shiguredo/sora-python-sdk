import os

from setup import (PlatformTarget, download, extract, get_build_platform,
                   install_deps, mkdir_p, rm_rf, versioned)


def get_nanobind_version() -> str:
    lines = open("pyproject.toml").readlines()
    for line in lines:
        line = line.strip('" ,\r\n')

        if not line.startswith("nanobind"):
            continue

        return line.rsplit("=", 1)[1]


@versioned
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
    build_platform = get_build_platform()

    target = os.getenv('SORA_SDK_TARGET')
    if target is None:
        target_platform = build_platform
    elif target == 'ubuntu-20.04_armv8_jetson':
        target_platform = PlatformTarget('jetson', None, 'armv8')
    else:
        raise Exception(f'Unknown target {target}')

    base_dir = os.getcwd()
    source_dir = os.path.join(base_dir, '_source', target_platform.package_name)
    build_dir = os.path.join(base_dir, '_build', target_platform.package_name)
    install_dir = os.path.join(base_dir, '_install', target_platform.package_name)
    mkdir_p(source_dir)
    mkdir_p(build_dir)
    mkdir_p(install_dir)

    install_deps(build_platform, target_platform, source_dir, build_dir, install_dir)

    # nanobind
    install_nanobind_args = {
        'version': get_nanobind_version(),
        'version_file': os.path.join(install_dir, 'nanobind.version'),
        'source_dir': source_dir,
        'install_dir': install_dir,
        'platform': build_platform.package_name,
    }
    install_nanobind(**install_nanobind_args)


if __name__ == '__main__':
    main()
