#pragma once

#include <cstdint>
#include <string>
#include <vector>

// 使用滑动窗口 FNV-1a 哈希算法计算文本指纹。
// 每个窗口覆盖 window_size 个词（空白分隔），产出 1 个 uint64_t 哈希。
// 返回值长度约为 词数 - window_size + 1，词数不足时返回空列表。
// 注意: 使用确定性 FNV-1a 而非 std::hash，确保跨平台/跨运行可复现。
// text 为空或 window_size 不在 2~20 范围时抛 ValueError。
std::vector<uint64_t> compute_fingerprint(const std::string& text,
                                          int window_size = 5);
