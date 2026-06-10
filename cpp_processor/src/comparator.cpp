#include "comparator.h"
#include "fingerprint.h"

#include <algorithm>
#include <stdexcept>
#include <unordered_set>

// 计算两个指纹集合的 Jaccard 相似度 |A ∩ B| / |A ∪ B|
// 先去重（指纹可能有重复窗口值），再计算交并比。
// 两份空指纹返回 0.0 而非除零崩溃。
static double jaccard(const std::vector<uint64_t>& a,
                      const std::vector<uint64_t>& b) {
    std::unordered_set<uint64_t> set_a(a.begin(), a.end());
    std::unordered_set<uint64_t> set_b(b.begin(), b.end());

    if (set_a.empty() && set_b.empty()) {
        return 0.0;
    }

    size_t intersection = 0;
    for (uint64_t h : set_a) {
        if (set_b.count(h)) {
            ++intersection;
        }
    }

    size_t uni = set_a.size() + set_b.size() - intersection;
    return static_cast<double>(intersection) / static_cast<double>(uni);
}

std::vector<std::tuple<int, int, double>> batch_compare(
    const std::vector<std::string>& texts,
    double threshold) {

    if (texts.size() < 2) {
        throw std::invalid_argument("texts must contain at least 2 elements");
    }
    if (threshold < 0.0 || threshold > 1.0) {
        throw std::invalid_argument("threshold must be between 0.0 and 1.0");
    }

    // 预计算所有文本的指纹，避免重复遍历
    std::vector<std::vector<uint64_t>> fingerprints;
    fingerprints.reserve(texts.size());
    for (const auto& text : texts) {
        if (text.empty()) {
            fingerprints.emplace_back();  // 空指纹，不调用 compute_fingerprint
        } else {
            fingerprints.push_back(compute_fingerprint(text));
        }
    }

    // 两两比较，只保留高于 threshold 的对
    std::vector<std::tuple<int, int, double>> results;
    for (size_t i = 0; i < texts.size(); ++i) {
        for (size_t j = i + 1; j < texts.size(); ++j) {
            double sim = jaccard(fingerprints[i], fingerprints[j]);
            if (sim >= threshold) {
                results.emplace_back(static_cast<int>(i),
                                     static_cast<int>(j),
                                     sim);
            }
        }
    }

    // 相似度降序排列，最可疑的对排最前面
    std::sort(results.begin(), results.end(),
              [](const auto& a, const auto& b) {
                  return std::get<2>(a) > std::get<2>(b);
              });

    return results;
}
