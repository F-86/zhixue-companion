#pragma once

#include <string>
#include <vector>

// 对文本进行去噪和分段，返回按段落切分的字符串列表。
// 处理步骤: \r\n 归一化 → 去除控制字符 → 压缩连续空行 → 按 \n\n 切分 → 过滤长度小于 10 的短段
// 输入为空时抛 ValueError。
std::vector<std::string> preprocess_segments(const std::string& text);
