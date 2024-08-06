import os
import sys
import sysconfig

from setuptools import setup
from wheel.bdist_wheel import bdist_wheel as _bdist_wheel

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, BASE_DIR)


from buildbase import PlatformTarget, cd, get_build_platform  # noqa: E402


def run_setup(build_platform, target_platform):
    plat = None
    if target_platform.os == "jetson":
        plat = "manylinux_2_17_aarch64.manylinux2014_aarch64"
    elif target_platform.os == "ubuntu" and target_platform.arch == "x86_64":
        if target_platform.osver == "22.04":
            plat = "manylinux_2_17_x86_64.manylinux2014_x86_64"
        if target_platform.osver == "24.04":
            plat = "manylinux_2_17_x86_64.manylinux2014_x86_64"

    class bdist_wheel(_bdist_wheel):
        def finalize_options(self):
            _bdist_wheel.finalize_options(self)
            self.root_is_pure = False

        def get_tag(self):
            _, _, plat2 = super().get_tag()
            impl = "cp" + sysconfig.get_config_var("py_version_nodot")
            return impl, impl, plat if plat is not None else plat2

    setup(
        url="https://github.com/shiguredo/sora-python-sdk",
        packages=["sora_sdk"],
        package_dir={"": "src"},
        package_data={
            "sora_sdk": ["sora_sdk_ext.*"],
        },
        include_package_data=True,
        cmdclass={
            "bdist_wheel": bdist_wheel,
        },
    )


def main():
    build_platform = get_build_platform()

    target = os.getenv("SORA_SDK_TARGET")
    if target is None:
        target_platform = build_platform
    elif target == "ubuntu-22.04_armv8_jetson":
        target_platform = PlatformTarget("jetson", None, "armv8", "ubuntu-22.04")
    else:
        raise Exception(f"Unknown target {target}")

    with cd(BASE_DIR):
        run_setup(build_platform, target_platform)


if __name__ == "__main__":
    main()
