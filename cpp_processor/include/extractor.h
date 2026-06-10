#pragma once

#include <string>

// 从本地文件中提取纯文本，支持 .txt 和 .pdf。
// .txt: 直接字节读取，跳过 UTF-8 BOM。
// .pdf: 通过 poppler-cpp 逐页提取 text()，转 UTF-8 后拼接。
// 文件不存在抛 RuntimeError，格式不识别抛 ValueError，PDF 损坏/加密抛 RuntimeError。
std::string extract_text(const std::string& file_path);
