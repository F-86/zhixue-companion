import subprocess
import sys

from pybind11.setup_helpers import Pybind11Extension, build_ext
from setuptools import setup


def _pkg_config(*args: str) -> list[str]:
    """调用 pkg-config 并返回拆分的编译/链接参数。"""
    try:
        out = subprocess.check_output(["pkg-config", *args], text=True).strip()
        return out.split()
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("WARNING: pkg-config 不可用，跳过系统库检测", file=sys.stderr)
        return []


# pybind11 扩展构建配置
# 编译命令: cd cpp_processor && python setup.py build_ext --inplace
# 产出: cpp_processor/file_processor.pyd (Windows) / .so (Linux/macOS)
# 部署: 将 .pyd / .so 复制到 backend/app/ 下供 import

extra_compile_args = ["-g0", "-mmacosx-version-min=10.15"]  # 去除调试符号，减小 .so 体积
extra_link_args = []

# 通过 pkg-config 获取 poppler-cpp 的编译和链接参数
poppler_cflags = _pkg_config("--cflags", "poppler-cpp")
poppler_libs = _pkg_config("--libs", "poppler-cpp")

# pkg-config --cflags poppler-cpp 返回形如 -I.../include/poppler/cpp 的路径，
# 但源码使用 #include <poppler/cpp/...>，需要额外加入 -I.../include
if poppler_cflags:
    # 从第一个 -I 路径推导父目录
    for flag in poppler_cflags:
        if flag.startswith("-I"):
            inc = flag[2:]
            # 去掉末尾的 /poppler/cpp 得到 .../include
            if inc.endswith("/poppler/cpp"):
                poppler_cflags.insert(0, "-I" + inc[:-len("/poppler/cpp")])
            break

ext = Pybind11Extension(
    "file_processor",
    sources=[
        "src/bindings.cpp",
        "src/logger.cpp",
        "src/preprocessor.cpp",
        "src/extractor.cpp",
        "src/fingerprint.cpp",
        "src/comparator.cpp",
    ],
    include_dirs=["include"],
    cxx_std=17,
    extra_compile_args=extra_compile_args + poppler_cflags,
    extra_link_args=extra_link_args + poppler_libs,
)

setup(
    name="file_processor",
    ext_modules=[ext],
    cmdclass={"build_ext": build_ext},
)
