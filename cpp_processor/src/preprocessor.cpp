#include "preprocessor.h"

#include <stdexcept>

// 将 \r\n 和单独 \r 都归一化为 \n
static std::string normalize_line_endings(const std::string& text) {
    std::string result;
    result.reserve(text.size());
    for (size_t i = 0; i < text.size(); ++i) {
        if (text[i] == '\r') {
            result += '\n';
            if (i + 1 < text.size() && text[i + 1] == '\n') {
                ++i;  // 跳过 \n 避免重复
            }
        } else {
            result += text[i];
        }
    }
    return result;
}

// 剔除控制字符（< 0x20 且不是 \n / \t / \r）和 DEL(0x7F)
// CJK 汉字 UTF-8 编码的后续字节均在 0x80~0xBF 范围，不会被误删
static std::string remove_control_chars(const std::string& text) {
    std::string result;
    result.reserve(text.size());
    for (char c : text) {
        unsigned char uc = static_cast<unsigned char>(c);
        if (uc == '\n' || uc == '\t' || uc == '\r' || (uc >= 0x20 && uc != 0x7F)) {
            result += c;
        }
    }
    return result;
}

// 将连续多个空行压缩为单个空行（即 \n\n... → \n\n）
// blank_line_emitted 保证多空行只产出一个 \n\n
static std::string collapse_blank_lines(const std::string& text) {
    std::string result;
    result.reserve(text.size());
    bool consecutive_newline = false;
    bool blank_line_emitted = false;
    for (char c : text) {
        if (c == '\n') {
            if (consecutive_newline) {
                if (!blank_line_emitted) {
                    result += c;
                    blank_line_emitted = true;
                }
            } else {
                result += c;
                consecutive_newline = true;
            }
        } else {
            consecutive_newline = false;
            blank_line_emitted = false;
            result += c;
        }
    }
    return result;
}

std::vector<std::string> preprocess_segments(const std::string& text) {
    if (text.empty()) {
        throw std::invalid_argument("input text is empty");
    }

    // 三步流水线处理
    std::string s = normalize_line_endings(text);
    s = remove_control_chars(s);
    s = collapse_blank_lines(s);

    // 按双换行切段落，过滤短段
    std::vector<std::string> segments;
    size_t start = 0;
    while (start < s.size()) {
        size_t end = s.find("\n\n", start);
        if (end == std::string::npos) {
            end = s.size();
        }
        std::string seg = s.substr(start, end - start);
        seg.erase(0, seg.find_first_not_of(" \t\n\r"));
        seg.erase(seg.find_last_not_of(" \t\n\r") + 1);
        if (seg.size() >= 10) {
            segments.push_back(std::move(seg));
        }
        if (end >= s.size()) break;
        start = end + 2;
    }

    return segments;
}
