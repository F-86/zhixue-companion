#include <pybind11/pybind11.h>
#include <pybind11/stl.h>       // vector / string / tuple 自动类型转换

#include "comparator.h"
#include "extractor.h"
#include "fingerprint.h"
#include "logger.h"
#include "preprocessor.h"

namespace py = pybind11;

// pybind11 模块注册入口。编译后生成 file_processor.pyd / .so，
// Python 端通过 import file_processor 直接调用这里的 5 个函数。
// 异常自动映射: std::invalid_argument → ValueError, std::runtime_error → RuntimeError
PYBIND11_MODULE(file_processor, m) {
    m.doc() = "智学伴侣 C++ 文件处理模块（pybind11）";

    m.def("extract_text", &extract_text, py::arg("file_path"),
        "从本地文件中提取纯文本。\n\n"
        "Args:\n    file_path (str): 待提取文件的绝对路径，支持 .txt / .pdf。\n\n"
        "Returns:\n    str: 提取的纯文本内容。\n\n"
        "Raises:\n    ValueError: 文件格式不支持。\n    RuntimeError: 文件不存在、无权限或解析失败。");

    m.def("preprocess_segments", &preprocess_segments, py::arg("text"),
        "对输入文本进行去噪和分段。\n\n"
        "Args:\n    text (str): 原始文本。\n\n"
        "Returns:\n    list[str]: 按段落切分的字符串列表。\n\n"
        "Raises:\n    ValueError: 输入为空字符串。");

    m.def("compute_fingerprint", &compute_fingerprint,
        py::arg("text"), py::arg("window_size") = 5,
        "使用滑动窗口哈希计算文本指纹。\n\n"
        "Args:\n    text (str): 待计算指纹的文本。\n    window_size (int): 滑动窗口大小（词数），默认 5，范围 2~20。\n\n"
        "Returns:\n    list[int]: 哈希值列表。\n\n"
        "Raises:\n    ValueError: 输入文本为空或 window_size 越界。");

    m.def("batch_compare", &batch_compare,
        py::arg("texts"), py::arg("threshold") = 0.8,
        "对多份文本进行两两指纹相似度粗筛。\n\n"
        "Args:\n    texts (list[str]): 参与比对的文本列表。\n    threshold (float): 相似度阈值，默认 0.8。\n\n"
        "Returns:\n    list[tuple[int, int, float]]: 超过阈值的 (i, j, similarity) 三元组列表。\n\n"
        "Raises:\n    ValueError: texts 少于两个元素或 threshold 越界。");

    m.def("write_log", &write_log,
        py::arg("log_path"), py::arg("level"), py::arg("message"),
        "向指定日志文件追加一条日志。\n\n"
        "Args:\n    log_path (str): 日志文件绝对路径。\n    level (str): 日志级别，INFO / WARN / ERROR。\n    message (str): 日志消息内容。\n\n"
        "Returns:\n    None\n\n"
        "Raises:\n    ValueError: level 不合法。\n    RuntimeError: 日志文件无写入权限。");
}
