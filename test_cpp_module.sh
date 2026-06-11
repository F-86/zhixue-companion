#!/usr/bin/env bash
# 快速测试 C++ file_processor 扩展的所有函数
# 用法: cd backend && uv run python test_cpp_module.py

cd "$(dirname "${BASH_SOURCE[0]}")/backend"

uv run python -c "
import os, tempfile

# ── 1. 导入 ──────────────────────────────────────────
try:
    import file_processor as fp
    print('✓ [1/5] 导入成功:', fp.__doc__.strip())
except ImportError as e:
    print('✗ [1/5] 导入失败:', e)
    exit(1)

# ── 2. extract_text ──────────────────────────────────
print()
try:
    # 2a. 测试 .txt 提取
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write('这是第一行测试文本。\n这是第二行，包含中文和 English 混合。\n')
        txt_path = f.name
    text = fp.extract_text(txt_path)
    os.unlink(txt_path)
    assert '第一行测试文本' in text, f'unexpected content: {text[:50]}'
    print(f'✓ [2/5] extract_text (.txt): {len(text)} chars')
except Exception as e:
    print(f'✗ [2/5] extract_text (.txt): {e}')

# ── 3. preprocess_segments ───────────────────────────
print()
try:
    sample = '  第一段内容。\n\n\n第二段，带有  多余空格  。\n\n第三段。  '
    segs = fp.preprocess_segments(sample)
    assert len(segs) >= 1, 'no segments returned'
    print(f'✓ [3/5] preprocess_segments: {len(segs)} segments -> {segs[:3]}')
except Exception as e:
    print(f'✗ [3/5] preprocess_segments: {e}')

# ── 4. compute_fingerprint ───────────────────────────
print()
try:
    sample = 'AI is changing education and helping teachers understand students learning needs better than ever before'
    fp_vals = fp.compute_fingerprint(sample, window_size=3)
    assert len(fp_vals) > 0, 'no fingerprint values'
    print(f'✓ [4/5] compute_fingerprint: {len(fp_vals)} hash values -> {fp_vals[:5]}...')
except Exception as e:
    print(f'✗ [4/5] compute_fingerprint: {e}')

# ── 5. batch_compare ─────────────────────────────────
print()
try:
    texts = [
        'AI is changing education and helping teachers understand students learning needs',
        'AI is changing education and assisting teachers to understand students learning needs',
        'Today is sunny and perfect for outdoor sports and picnics',
    ]
    pairs = fp.batch_compare(texts, threshold=0.0)  # 0.0 查看全量
    print(f'✓ [5/5] batch_compare: {len(pairs)} pairs total')
    for i, j, sim in pairs:
        label = '★ 高度相似' if sim > 0.05 else '  无关'
        print(f'       [{i}][{j}] similarity={sim:.4f} {label}')
except Exception as e:
    print(f'✗ [5/5] batch_compare: {e}')

print()
print('─── 测试完毕 ───')
"
