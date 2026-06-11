#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# 智学伴侣后端控制脚本
# 用法：
#   ./server.sh start    后台启动后端服务
#   ./server.sh stop     关闭后端服务
#   ./server.sh restart  重启后端服务
#   ./server.sh status   查看运行状态
#   ./server.sh log      实时跟踪日志输出
# ─────────────────────────────────────────────────────────────

set -euo pipefail

# ── 路径配置 ──────────────────────────────────────────────────
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="${ROOT_DIR}/backend"
LOG_DIR="${ROOT_DIR}/logs"
PID_DIR="${ROOT_DIR}/pids"

LOG_FILE="${LOG_DIR}/backend.log"
PID_FILE="${PID_DIR}/backend.pid"

# ── 服务配置 ──────────────────────────────────────────────────
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

# ── 颜色输出 ──────────────────────────────────────────────────
GREEN="\033[0;32m"
YELLOW="\033[0;33m"
RED="\033[0;31m"
CYAN="\033[0;36m"
RESET="\033[0m"

info()    { echo -e "${GREEN}[INFO]${RESET}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*"; }
section() { echo -e "${CYAN}$*${RESET}"; }

# ── 工具函数 ──────────────────────────────────────────────────

_read_pid() {
    [[ -f "${PID_FILE}" ]] && cat "${PID_FILE}" || echo ""
}

_is_running() {
    local pid="$1"
    [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null
}

# ── 子命令 ────────────────────────────────────────────────────

cmd_start() {
    local pid
    pid="$(_read_pid)"

    if _is_running "${pid}"; then
        warn "后端服务已在运行 (PID: ${pid})，如需重启请使用 restart"
        return 0
    fi

    mkdir -p "${LOG_DIR}" "${PID_DIR}"

    if [[ ! -f "${BACKEND_DIR}/.env" ]]; then
        warn ".env 文件不存在，请先执行: cp backend/.env.example backend/.env 并填写配置"
    fi

    section "► 启动后端服务 (${HOST}:${PORT})..."

    # 在 backend/ 目录下启动，确保 sqlite:///./zhixue.db 落在 backend/ 内
    nohup uv run --project "${BACKEND_DIR}" \
        --directory "${BACKEND_DIR}" \
        uvicorn app.main:app \
        --host "${HOST}" \
        --port "${PORT}" \
        --no-access-log \
        >> "${LOG_FILE}" 2>&1 &

    local new_pid=$!
    echo "${new_pid}" > "${PID_FILE}"

    # 最多等待 5 秒确认进程存活
    local waited=0
    while ! _is_running "${new_pid}"; do
        sleep 0.5
        waited=$((waited + 1))
        if [[ ${waited} -ge 10 ]]; then
            error "进程启动失败，请检查日志: ${LOG_FILE}"
            rm -f "${PID_FILE}"
            return 1
        fi
    done

    info "后端服务已启动"
    info "  PID      : ${new_pid}"
    info "  地址     : http://${HOST}:${PORT}"
    info "  健康检查 : http://localhost:${PORT}/api/health"
    info "  API 文档 : http://localhost:${PORT}/docs"
    info "  日志文件 : ${LOG_FILE}"
    info "  PID 文件 : ${PID_FILE}"
}

cmd_stop() {
    local pid
    pid="$(_read_pid)"

    if ! _is_running "${pid}"; then
        warn "后端服务未在运行"
        rm -f "${PID_FILE}"
        return 0
    fi

    section "► 停止后端服务 (PID: ${pid})..."
    kill "${pid}"

    # 最多等待 10 秒，超时后强制终止
    local waited=0
    while _is_running "${pid}"; do
        sleep 0.5
        waited=$((waited + 1))
        if [[ ${waited} -ge 20 ]]; then
            warn "进程未响应 SIGTERM，强制终止..."
            kill -9 "${pid}" 2>/dev/null || true
            break
        fi
    done

    rm -f "${PID_FILE}"
    info "后端服务已停止"
}

cmd_restart() {
    section "► 重启后端服务..."
    cmd_stop
    sleep 1
    cmd_start
}

cmd_status() {
    local pid
    pid="$(_read_pid)"

    section "─── 智学伴侣后端状态 ───────────────────────────"

    if _is_running "${pid}"; then
        info "状态     : 运行中 ✓"
        info "PID      : ${pid}"
        info "地址     : http://${HOST}:${PORT}"

        local start_time
        start_time="$(ps -o lstart= -p "${pid}" 2>/dev/null | xargs || echo '未知')"
        info "启动时间 : ${start_time}"

        if [[ -f "${LOG_FILE}" ]]; then
            local log_size
            log_size="$(du -sh "${LOG_FILE}" 2>/dev/null | cut -f1)"
            info "日志大小 : ${log_size}  (${LOG_FILE})"
        fi

        if command -v curl &>/dev/null; then
            local http_status
            http_status="$(curl -s -o /dev/null -w '%{http_code}' \
                --connect-timeout 2 "http://localhost:${PORT}/api/health" 2>/dev/null || echo '无响应')"
            if [[ "${http_status}" == "200" ]]; then
                info "健康检查 : HTTP ${http_status} ✓"
            else
                warn "健康检查 : HTTP ${http_status} (服务可能正在启动)"
            fi
        fi
    else
        error "状态     : 未运行 ✗"
        if [[ -f "${PID_FILE}" ]]; then
            warn "PID 文件残留 (${PID_FILE})，已清理"
            rm -f "${PID_FILE}"
        fi
    fi

    section "──────────────────────────────────────────────"
}

cmd_log() {
    if [[ ! -f "${LOG_FILE}" ]]; then
        warn "日志文件不存在: ${LOG_FILE}"
        warn "请先启动服务: ./server.sh start"
        return 1
    fi
    section "► 实时日志 (Ctrl+C 退出)..."
    tail -f "${LOG_FILE}"
}

cmd_help() {
    cat <<EOF

${CYAN}智学伴侣后端控制脚本${RESET}

用法：
  ./server.sh <命令>

命令：
  start    后台启动后端服务
  stop     停止后端服务
  restart  重启后端服务
  status   查看运行状态（含健康检查）
  log      实时跟踪日志输出
  help     显示此帮助信息

环境变量（可在执行前覆盖）：
  HOST     监听地址（默认 0.0.0.0）
  PORT     监听端口（默认 8000）

示例：
  ./server.sh start
  PORT=9000 ./server.sh start
  ./server.sh status
  ./server.sh log
  ./server.sh stop

EOF
}

# ── 入口 ──────────────────────────────────────────────────────
case "${1:-help}" in
    start)          cmd_start   ;;
    stop)           cmd_stop    ;;
    restart)        cmd_restart ;;
    status)         cmd_status  ;;
    log)            cmd_log     ;;
    help|--help|-h) cmd_help    ;;
    *)
        error "未知命令: $1"
        cmd_help
        exit 1
        ;;
esac
