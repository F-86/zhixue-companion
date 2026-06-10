#include "extractor.h"

#include <algorithm>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <stdexcept>

#include <poppler/cpp/poppler-document.h>
#include <poppler/cpp/poppler-page.h>

// 提取文件扩展名并转为小写
static std::string get_extension(const std::string& path) {
    auto pos = path.find_last_of('.');
    if (pos == std::string::npos) return "";
    std::string ext = path.substr(pos + 1);
    for (auto& c : ext) {
        c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    }
    return ext;
}

// 读取 .txt 文件（二进制模式避免编码转换），跳过 UTF-8 BOM 头
static std::string read_txt(const std::string& path) {
    std::ifstream file(path, std::ios::binary);
    if (!file.is_open()) {
        throw std::runtime_error("cannot open file: " + path);
    }
    std::stringstream buf;
    buf << file.rdbuf();
    std::string content = buf.str();

    if (content.size() >= 3 &&
        static_cast<unsigned char>(content[0]) == 0xEF &&
        static_cast<unsigned char>(content[1]) == 0xBB &&
        static_cast<unsigned char>(content[2]) == 0xBF) {
        content = content.substr(3);
    }
    return content;
}

// 通过 poppler-cpp 逐页提取 PDF 文本，每页后追加换行
static std::string read_pdf(const std::string& path) {
    auto doc = poppler::document::load_from_file(path);
    if (!doc) {
        throw std::runtime_error("failed to parse PDF: " + path);
    }
    if (doc->is_encrypted()) {
        throw std::runtime_error("PDF is encrypted: " + path);
    }

    std::string result;
    for (int i = 0; i < doc->pages(); ++i) {
        auto page = doc->create_page(i);
        if (page) {
            // page->text() 返回 poppler::ustring，需转 UTF-8
            result += page->text().to_utf8();
            result += '\n';
        }
    }
    return result;
}

std::string extract_text(const std::string& file_path) {
    if (!std::filesystem::exists(file_path)) {
        throw std::runtime_error("file not found: " + file_path);
    }

    std::string ext = get_extension(file_path);
    if (ext == "txt") {
        return read_txt(file_path);
    } else if (ext == "pdf") {
        return read_pdf(file_path);
    } else {
        throw std::invalid_argument("unsupported file extension: " + ext);
    }
}
