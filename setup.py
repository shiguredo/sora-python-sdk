import os
import sys

from setuptools import setup
from wheel.bdist_wheel import bdist_wheel as _bdist_wheel


BASE_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, BASE_DIR)


from run import get_build_platform, PlatformTarget, cd  # noqa: E402


def run_setup(build_platform, target_platform):
    plat_name = None
    if target_platform.os == 'jetson':
        plat_name = 'linux-aarch64'

    class bdist_wheel(_bdist_wheel):
        def finalize_options(self):
            self.plat_name = plat_name
            super().finalize_options()
            self.root_is_pure = False

    setup(
        name="sora_sdk",
        version="2023.0.1",
        description="WebRTC SFU Sora Python SDK",
        url="https://github.com/shiguredo/sora-python-sdk",
        license="Apache License 2.0",
        packages=['sora_sdk', 'sora_sdk.model_coeffs'],
        package_dir={'': 'src'},
        package_data={
            'sora_sdk': ['sora_sdk_ext.*', 'model_coeffs/*'],
        },
        include_package_data=True,
        cmdclass={
            'bdist_wheel': bdist_wheel,
        },
    )


def main():
    build_platform = get_build_platform()

    target = os.getenv('SORA_SDK_TARGET')
    if target is None:
        target_platform = build_platform
    elif target == 'ubuntu-20.04_armv8_jetson':
        target_platform = PlatformTarget('jetson', None, 'armv8')
    else:
        raise Exception(f'Unknown target {target}')

    with cd(BASE_DIR):
        run_setup(build_platform, target_platform)


if __name__ == '__main__':
    main()
