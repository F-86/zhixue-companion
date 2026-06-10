#pragma once

#include <string>
#include <tuple>
#include <vector>

// 对多份文本进行两两指纹相似度粗筛，返回相似度 >= threshold 的 (i, j, similarity) 三元组。
// 内部调用 compute_fingerprint 计算每份文本的指纹，再两两算 Jaccard 相似度。
// 结果按 similarity 降序排列。
// texts 少于 2 个元素 或 threshold 不在 [0.0, 1.0] 时抛 ValueError。
std::vector<std::tuple<int, int, double>> batch_compare(
    const std::vector<std::string>& texts,
    double threshold = 0.8);
