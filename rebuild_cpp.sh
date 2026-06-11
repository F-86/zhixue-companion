#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# C++ pybind11 扩展编译 & 部署脚本
# 用法: ./rebuild_cpp.sh
# ─────────────────────────────────────────────────────────────
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend"
CPP_DIR="${ROOT_DIR}/cpp_processor"
DEPLOY_DIR="${BACKEND_DIR}"

GREEN="\033[0;32m"
RED="\033[0;31m"
CYAN="\033[0;36m"
RESET="\033[0m"

info()  { echo -e "${GREEN}[INFO]${RESET}  $*"; }
error() { echo -e "${RED}[ERROR]${RESET} $*"; }
step()  { echo -e "${CYAN}──►${RESET} $*"; }

# ── 1. 检查系统依赖 ────────────────────────────────────────
step "检查 poppler-cpp..."
if ! pkg-config --exists poppler-cpp 2>/dev/null; then
    error "poppler-cpp 未安装，请先执行: brew install poppler"
    exit 1
fi
info "poppler-cpp 已就绪: $(pkg-config --modversion poppler-cpp)"

# ── 2. 同步 uv 依赖（确保 pybind11 可用） ──────────────────
step "同步 uv 依赖..."
cd "${BACKEND_DIR}"
uv sync --dev
info "依赖同步完成"

# ── 3. 编译 C++ 扩展 ───────────────────────────────────────
step "编译 C++ 扩展..."
cd "${CPP_DIR}"

# 清理旧产物
rm -rf ./*.so build/

uv run --project "${BACKEND_DIR}" --with setuptools python setup.py build_ext --inplace

# 查找编译产物
SO_FILE=$(ls ./*.so 2>/dev/null | head -1)
if [[ -z "${SO_FILE}" ]]; then
    error "编译失败：未找到 .so 文件"
    exit 1
fi
info "编译产出: ${SO_FILE}"

# ── 4. 部署到 backend/ ─────────────────────────────────
step "部署到 backend/..."
cp "${SO_FILE}" "${DEPLOY_DIR}/"
info "已部署: ${DEPLOY_DIR}/$(basename "${SO_FILE}")"

# ── 5. 验证 ────────────────────────────────────────────────
step "验证导入..."
cd "${BACKEND_DIR}"
if uv run python -c "import file_processor; print('版本:', file_processor.__doc__)" 2>&1; then
    info "导入验证成功 ✓"
else
    error "导入验证失败，请检查编译日志"
    exit 1
fi

echo ""
info "编译部署完成！可以运行 ./server.sh start 启动后端"
