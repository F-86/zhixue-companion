from pybind11.setup_helpers import Pybind11Extension, build_ext
from setuptools import setup

# pybind11 扩展构建配置
# 编译命令: cd cpp_processor && python setup.py build_ext --inplace
# 产出: cpp_processor/file_processor.pyd (Windows) / .so (Linux/macOS)
# 部署: 将 .pyd 复制到 backend/app/ 下供 import
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
    libraries=["poppler-cpp"],          # PDF 解析依赖
)

setup(
    name="file_processor",
    ext_modules=[ext],
    cmdclass={"build_ext": build_ext},
)
