#!/usr/bin/env python

import logging
import shutil
import subprocess

from setuptools import setup, Extension
from setuptools.command.build_ext import build_ext
from setuptools.command.install import install
from wheel.bdist_wheel import bdist_wheel
import sys
import os
import platform

STPYV8_HOME = os.path.dirname(os.path.realpath(__file__))
DEPOT_HOME = os.environ.get("DEPOT_HOME", os.path.join(STPYV8_HOME, "depot_tools"))
V8_HOME = os.environ.get("V8_HOME", os.path.join(STPYV8_HOME, "v8"))

V8_GIT_URL = "https://chromium.googlesource.com/v8/v8.git"
V8_GIT_TAG_STABLE = "13.1.201.22"
V8_GIT_TAG_MASTER = "master"
V8_GIT_TAG = V8_GIT_TAG_STABLE
DEPOT_GIT_URL = "https://chromium.googlesource.com/chromium/tools/depot_tools.git"

STPYV8_VERSION = V8_GIT_TAG_STABLE

v8_deps_linux = os.environ.get("V8_DEPS_LINUX", "1") in ("1",)

os.environ["PATH"] = f"{os.environ.get('PATH', '')}:{DEPOT_HOME}"

gn_args = {
    "dcheck_always_on": "false",
    "is_component_build": "false",
    "is_debug": "true" if os.environ.get("STPYV8_DEBUG") else "false",
    "treat_warnings_as_errors": "false",
    "use_custom_libcxx": "false",
    "v8_deprecation_warnings": "true",
    "v8_enable_disassembler": "false",
    "v8_enable_i18n_support": "true",
    "v8_enable_pointer_compression": "false",
    "v8_enable_31bit_smis_on_64bit_arch": "false",
    "v8_imminent_deprecation_warnings": "true",
    "v8_monolithic": "true",
    "v8_use_external_startup_data": "false",
}

source_files = [
    "Exception.cpp",
    "Platform.cpp",
    "Isolate.cpp",
    "Context.cpp",
    "Engine.cpp",
    "Wrapper.cpp",
    "Locker.cpp",
    "Utils.cpp",
    "STPyV8.cpp",
]


macros = [("BOOST_PYTHON_STATIC_LIB", None)]
include_dirs = set()
library_dirs = set()
libraries = []
extra_compile_args = []
extra_link_args = []

include_dirs.add(os.path.join(V8_HOME, "include"))
library_dirs.add(
    os.path.join(V8_HOME, os.path.join("out.gn", "x64.release.sample", "obj"))
)

BOOST_PYTHON_LIB_SHORT = f"boost_python{sys.version_info.major}"
BOOST_PYTHON_LIB_LONG = f"boost_python{sys.version_info.major}{sys.version_info.minor}"

BOOST_PYTHON_UBUNTU_MATRIX = {
    "default": BOOST_PYTHON_LIB_LONG,
    "18.04": BOOST_PYTHON_LIB_SHORT,
    "20.04": f"{BOOST_PYTHON_LIB_SHORT}8",
    "22.04": f"{BOOST_PYTHON_LIB_SHORT}10",
}


def get_libboost_python_name():
    if not os.path.exists("/etc/lsb-release"):
        return BOOST_PYTHON_UBUNTU_MATRIX["default"]

    platform_info = {}

    with open("/etc/lsb-release", encoding="utf-8", mode="r") as fd:
        for line in fd.readlines():
            s = line.strip()
            p = s.split("=")

            if len(p) < 2:
                continue

            platform_info[p[0]] = p[1]

    if "DISTRIB_ID" not in platform_info:
        return BOOST_PYTHON_UBUNTU_MATRIX["default"]

    if platform_info["DISTRIB_ID"].lower() not in ("ubuntu",):
        return BOOST_PYTHON_UBUNTU_MATRIX["default"]

    release = platform_info["DISTRIB_RELEASE"]

    if release not in BOOST_PYTHON_UBUNTU_MATRIX:
        return BOOST_PYTHON_UBUNTU_MATRIX["default"]

    return BOOST_PYTHON_UBUNTU_MATRIX[release]


STPYV8_BOOST_PYTHON = os.getenv(
    "STPYV8_BOOST_PYTHON", default=get_libboost_python_name()
)

if os.name in ("nt",):
    include_dirs.add(os.path.join(V8_HOME, "include"))
    library_dirs.add(os.path.join(V8_HOME, "out.gn", "x64.release.sample", "obj"))

    if "BOOST_ROOT" in os.environ:
        include_dirs.add(os.environ.get("BOOST_ROOT"))
        library_dirs.add(os.path.join(os.environ["BOOST_ROOT"], "stage", "lib"))

    if "Python_ROOT_DIR" in os.environ:
        include_dirs.add(os.path.join(os.environ["Python_ROOT_DIR"], "include"))
        library_dirs.add(os.path.join(os.environ["Python_ROOT_DIR"], "libs"))

    libraries += ["winmm", "ws2_32", "Advapi32", "dbghelp", "v8_monolith"]
    extra_compile_args += ["/O2", "/GL", "/MT", "/EHsc", "/Gy", "/Zi", "/std:c++20", "/Zc:__cplusplus"]
    extra_link_args += ["/DLL", "/OPT:REF", "/OPT:ICF", "/MACHINE:X64"]
    macros += [
        ("HAVE_SNPRINTF", None),
    ]

    os.environ["DEPOT_TOOLS_WIN_TOOLCHAIN"] = "0"

elif os.name in ("posix",):
    libraries = [
        "boost_system",
        "boost_iostreams",
        "boost_filesystem",
        "v8_monolith",
        STPYV8_BOOST_PYTHON.replace(".", ""),
    ]

    extra_compile_args.append("-Wno-strict-aliasing")
    extra_compile_args.append("-Wno-array-bounds")

    if platform.system() in ("Linux",):
        libraries.append("rt")
        extra_compile_args.append("-std=c++2a")
    else:
        extra_compile_args.append("-std=c++20")
        extra_link_args.append("-headerpad_max_install_names")


GN_ARGS = " ".join(f"{key}={value}" for key, value in gn_args.items())

include_dirs = list(include_dirs)
library_dirs = list(library_dirs)
log = logging.getLogger()

ICU_DATA_PACKAGE_FOLDER = os.path.join(os.pardir, os.pardir, "stpyv8-icu")
ICU_DATA_V8_FILE_PATH = os.path.join("v8", "out.gn", "x64.release.sample", "icudtl.dat")


def exec_cmd(cmdline, *args, **kwargs):
    msg = kwargs.get("msg")
    cwd = kwargs.get("cwd", ".")
    output = kwargs.get("output")

    if msg:
        print(msg)

    cmdline = " ".join([cmdline] + list(args))

    proc = subprocess.Popen(
        cmdline,  # pylint:disable=consider-using-with
        shell=kwargs.get("shell", True),
        cwd=cwd,
        env=kwargs.get("env"),
        stdout=subprocess.PIPE if output else None,
        stderr=subprocess.PIPE if output else None,
    )

    stdout, stderr = proc.communicate()

    succeeded = proc.returncode == 0

    if not succeeded:
        log.error("%s failed: code = %d", msg or "Execute command", proc.returncode)

        if output:
            log.debug(stderr)

    return succeeded, stdout, stderr if output else succeeded


def install_depot():
    if not os.path.exists(DEPOT_HOME):
        exec_cmd(
            "git clone --depth 1",
            DEPOT_GIT_URL,
            DEPOT_HOME,
            cwd=os.path.dirname(DEPOT_HOME),
            msg="Cloning depot tools",
        )

        return

    # depot_tools updates itself automatically when running gclient tool
    if os.path.isfile(os.path.join(DEPOT_HOME, "gclient")):
        success, stdout, __ = exec_cmd(
            os.path.join(DEPOT_HOME, "gclient"),  # pylint:disable=unused-variable
            "--version",
            cwd=DEPOT_HOME,
            output=True,
            msg="Found depot tools",
        )

        if not success:
            exit(1)


def checkout_v8():
    install_depot()

    if not os.path.exists(V8_HOME):
        success, _, __ = exec_cmd(
            os.path.join(DEPOT_HOME, "fetch"),
            "--no-history",
            "v8",
            cwd=os.path.dirname(V8_HOME),
            msg="Fetching Google V8 code",
        )

        if not success:
            exit(1)

    success, _, __ = exec_cmd(
        "git fetch --tags --quiet",
        cwd=V8_HOME,
        msg="Fetching the release tag information",
    )

    if not success:
        exit(1)

    success, _, __ = exec_cmd(
        "git checkout", V8_GIT_TAG, cwd=V8_HOME, msg=f"Checkout Google V8 v{V8_GIT_TAG}"
    )

    if not success:
        exit(1)

    success, _, __ = exec_cmd(
        os.path.join(DEPOT_HOME, "gclient"),
        "sync",
        "-D",
        "-j8",
        cwd=os.path.dirname(V8_HOME),
        msg="Syncing Google V8 code",
    )

    if not success:
        exit(1)

    # On Linux, install additional dependencies, per
    # https://v8.dev/docs/build step 4
    if (
        sys.platform
        in (
            "linux",
            "linux2",
        )
        and v8_deps_linux
    ):
        success, _, __ = exec_cmd(
            "./v8/build/install-build-deps.sh",
            cwd=os.path.dirname(V8_HOME),
            msg="Installing additional linux dependencies",
        )

        if not success:
            exit(1)


def build_v8():
    args = f"gen {os.path.join('out.gn', 'x64.release.sample')} --args=\"{GN_ARGS}\""
    success, _, __ = exec_cmd(
        os.path.join(DEPOT_HOME, "gn"),
        args,
        cwd=V8_HOME,
        msg=f"Generate build scripts for V8 (v{V8_GIT_TAG})",
    )

    if not success:
        exit(1)

    success, _, __ = exec_cmd(
        os.path.join(DEPOT_HOME, "ninja"),
        f"-C {os.path.join('out.gn', 'x64.release.sample')} v8_monolith",
        cwd=V8_HOME,
        msg="Build V8 with ninja",
    )

    if not success:
        exit(1)


def clean_stpyv8():
    build_folder = os.path.join(STPYV8_HOME, "build")

    if os.path.exists(os.path.join(build_folder)):
        shutil.rmtree(build_folder)


def prepare_v8():
    try:
        checkout_v8()
        build_v8()
        # clean_stpyv8()
    except Exception as e:  # pylint:disable=broad-except
        log.error("Fail to checkout and build v8, %s", str(e))


class stpyv8_bdist_wheel(bdist_wheel):
    user_options = bdist_wheel.user_options + [
        ("skip-build-v8", None, "don't build v8")
    ]

    def initialize_options(self) -> None:
        bdist_wheel.initialize_options(self)

        self.skip_build_v8 = None

    def run(self):
        if not self.skip_build_v8:
            prepare_v8()

        bdist_wheel.run(self)


class stpyv8_build(build_ext):
    def run(self):
        V8_GIT_TAG = V8_GIT_TAG_STABLE  # pylint:disable=redefined-outer-name,unused-variable

        build_ext.run(self)


class stpyv8_develop(build_ext):
    def run(self):
        V8_GIT_TAG = V8_GIT_TAG_MASTER  # pylint:disable=redefined-outer-name,unused-variable
        prepare_v8()
        build_ext.run(self)


class stpyv8_install_v8(build_ext):
    def run(self):
        V8_GIT_TAG = V8_GIT_TAG_MASTER  # pylint:disable=redefined-outer-name,unused-variable
        prepare_v8()


class stpyv8_build_no_v8(build_ext):
    def run(self):
        clean_stpyv8()
        build_ext.run(self)


class stpyv8_install(install):
    def run(self):
        self.skip_build = True  # pylint:disable=attribute-defined-outside-init
        install.run(self)


class stpyv8_checkout_v8(build_ext):
    def run(self):
        checkout_v8()


stpyv8 = Extension(
    name="_STPyV8",
    sources=[os.path.join("src", source) for source in source_files],
    define_macros=macros,
    include_dirs=include_dirs,
    library_dirs=library_dirs,
    libraries=libraries,
    extra_compile_args=extra_compile_args,
    extra_link_args=extra_link_args,
)

setup(
    name="stpyv8",
    version=STPYV8_VERSION,
    description="Python Wrapper for Google V8 Engine",
    long_description=open("README.md").read(),
    platforms=["Linux", "MacOS", "Windows"],
    author="Philip Syme, Angelo Dell'Aera",
    url="https://github.com/cloudflare/stpyv8",
    license="Apache License 2.0",
    py_modules=["STPyV8"],
    ext_modules=[stpyv8],
    install_requires=["importlib_resources; python_version < '3.10'"],
    setup_requires=["wheel"],
    data_files=[
        (ICU_DATA_PACKAGE_FOLDER, [ICU_DATA_V8_FILE_PATH]),
    ],
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Environment :: Plugins",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: Apache Software License",
        "Natural Language :: English",
        "Programming Language :: C++",
        "Programming Language :: Python",
        "Topic :: Internet",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Software Development",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Utilities",
        "Operating System :: POSIX :: Linux",
        "Operating System :: MacOS :: MacOS X",
        "Operating System :: Microsoft :: Windows",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    long_description_content_type="text/markdown",
    cmdclass=dict(
        bdist_wheel=stpyv8_bdist_wheel,
        build_ext=stpyv8_build,
        develop=stpyv8_develop,
        v8=stpyv8_install_v8,
        stpyv8=stpyv8_build_no_v8,
        install=stpyv8_install,
        checkout_v8=stpyv8_checkout_v8,
    ),
)
