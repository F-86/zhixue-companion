#pragma once

#include <string>

// 向指定文件追加一行 [ISO8601 时间] [级别] 消息
// level 必须是 INFO / WARN / ERROR，否则抛 ValueError
// 父目录不存在时自动创建，文件无写入权限时抛 RuntimeError
void write_log(const std::string& log_path,
               const std::string& level,
               const std::string& message);
