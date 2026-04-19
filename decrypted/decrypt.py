import lzma
import zlib
import bz2
import base64
import re

# 读取加密文件
with open('routes_encrypted.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 提取加密信息
def extract_encryption_info(code):
    """从代码中提取加密方式和 base64 字符串"""
    # 尝试匹配各种加密方式 + base64
    patterns = [
        (r"bz2\.decompress\(base64\.b64decode\('([^']+)'\)\)", 'bz2'),
        (r"lzma\.decompress\(base64\.b64decode\('([^']+)'\)\)", 'lzma'),
        (r"zlib\.decompress\(base64\.b64decode\('([^']+)'\)\)", 'zlib'),
        (r"base64\.b64decode\('([^']+)'\)", 'base64'),
    ]

    for pattern, method in patterns:
        match = re.search(pattern, code)
        if match:
            return method, match.group(1)

    return None, None

# 解码函数
def decode_layer(encoded_str, method):
    """解码一层：根据不同的加密方式"""
    try:
        # 首先进行 base64 解码
        decoded_bytes = base64.b64decode(encoded_str)

        # 根据加密方式进一步解密
        if method == 'lzma':
            decompressed = lzma.decompress(decoded_bytes)
        elif method == 'zlib':
            decompressed = zlib.decompress(decoded_bytes)
        elif method == 'bz2':
            decompressed = bz2.decompress(decoded_bytes)
        elif method == 'base64':
            decompressed = decoded_bytes  # 仅仅 base64，无需进一步解密
        else:
            return None

        # 尝试用 UTF-8 解码
        return decompressed.decode('utf-8')
    except Exception as e:
        print(f"  解码失败 ({method}): {e}")
        return None

# 循环解密直到没有更多层
current_code = content
layer = 0
max_layers = 200  # 增加最大层数

print("开始多层解密...\n")

while layer < max_layers:
    layer += 1
    print(f"第 {layer} 层解密：")

    # 提取加密信息和 base64 字符串
    method, encoded_str = extract_encryption_info(current_code)
    if not encoded_str:
        print("  未找到加密代码，解密结束")
        break

    print(f"  加密方式: {method}")
    print(f"  Base64 字符串长度: {len(encoded_str)}")

    # 解码
    decoded_code = decode_layer(encoded_str, method)
    if not decoded_code:
        print("  解码失败，停止解密")
        break

    print(f"  解码后长度: {len(decoded_code)} 字符")

    # 检查是否还有嵌套的加密
    if "base64.b64decode" not in decoded_code:
        print("  未发现更多加密层，解密完成！")
        current_code = decoded_code
        break

    current_code = decoded_code
    print(f"  发现更多加密层，继续解密...\n")

# 保存最终解密的代码
with open('routes_decrypted.py', 'w', encoding='utf-8') as f:
    f.write(current_code)

print("\n" + "="*60)
print(f"解密完成！共 {layer} 层加密")
print("="*60 + "\n")

# 检查解密后的代码是否仍然是混淆的
print("检查解密后的代码...")
print(f"  是否包含 import: {'import' in current_code}")
print(f"  是否包含 def: {'def ' in current_code}")
print(f"  是否包含 class: {'class ' in current_code}")
print(f"  是否包含 @app: {'@app' in current_code}")
print(f"  是否包含 exec: {'exec' in current_code}")
print(f"  是否包含 base64: {'base64' in current_code}")
print(f"  是否包含 lzma: {'lzma' in current_code}")

# 显示解密后的代码前 1000 字符
print(f"\n解密后的代码前 1000 字符:")
print(current_code[:1000])
print("\n... (完整代码已保存到 routes_decrypted.py)")
