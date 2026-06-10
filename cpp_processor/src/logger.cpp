#include "logger.h"

#include <chrono>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <stdexcept>

void write_log(const std::string& log_path,
               const std::string& level,
               const std::string& message) {
    if (level != "INFO" && level != "WARN" && level != "ERROR") {
        throw std::invalid_argument("level must be INFO / WARN / ERROR");
    }

    // 确保日志目录存在
    std::filesystem::path p(log_path);
    std::filesystem::create_directories(p.parent_path());

    std::ofstream file(log_path, std::ios_base::app);
    if (!file.is_open()) {
        throw std::runtime_error("cannot open log file: " + log_path);
    }

    // ISO 8601 时间戳
    auto now = std::chrono::system_clock::now();
    auto tt = std::chrono::system_clock::to_time_t(now);
    std::tm tm = *std::localtime(&tt);

    file << "[" << std::put_time(&tm, "%Y-%m-%dT%H:%M:%S") << "] "
         << "[" << level << "] " << message << "\n";
}
