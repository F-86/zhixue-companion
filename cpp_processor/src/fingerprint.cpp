#include "fingerprint.h"

#include <sstream>
#include <stdexcept>

// FNV-1a 确定性哈希函数。
// 使用固定的 offset basis 和 prime，保证不同编译/运行环境结果一致。
// 这是本模块的核心假设: 同文本必须产出同指纹，否则粗筛逻辑失效。
static uint64_t fnv1a(const std::string& s) {
    uint64_t hash = 14695981039346656037ULL;
    for (unsigned char c : s) {
        hash = (hash ^ static_cast<uint64_t>(c)) * 1099511628211ULL;
    }
    return hash;
}

std::vector<uint64_t> compute_fingerprint(const std::string& text,
                                          int window_size) {
    if (text.empty()) {
        throw std::invalid_argument("input text is empty");
    }
    if (window_size < 2 || window_size > 20) {
        throw std::invalid_argument("window_size must be between 2 and 20");
    }

    // 空白符分词
    std::vector<std::string> words;
    std::istringstream stream(text);
    std::string word;
    while (stream >> word) {
        words.push_back(std::move(word));
    }

    // 词数不足一个窗口，返回空
    if (words.size() < static_cast<size_t>(window_size)) {
        return {};
    }

    // 滑动窗口: 每次取 window_size 个词，合并 FNV-1a
    std::vector<uint64_t> fingerprints;
    fingerprints.reserve(words.size() - static_cast<size_t>(window_size) + 1);

    for (size_t i = 0; i + static_cast<size_t>(window_size) <= words.size(); ++i) {
        uint64_t hash = 14695981039346656037ULL;
        for (int k = 0; k < window_size; ++k) {
            hash = (hash ^ fnv1a(words[i + static_cast<size_t>(k)])) * 1099511628211ULL;
        }
        fingerprints.push_back(hash);
    }

    return fingerprints;
}
