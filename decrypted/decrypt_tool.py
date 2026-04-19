"""递归解密 routes_decrypted.py - 直到得到真正的源码"""
import builtins
import sys
import os

original_exec = builtins.exec
original_getattr = builtins.getattr

def decrypt_one_layer(code_text):
    """解密一层混淆代码，返回解密后的bytes/str或None"""
    captured = None

    def capture_exec(code, *args, **kwargs):
        nonlocal captured
        captured = code

    def smart_getattr(obj, name, *default):
        if obj is builtins and name == 'exec':
            return capture_exec
        return original_getattr(obj, name, *default)

    builtins.getattr = smart_getattr

    try:
        original_exec(code_text)
    except SystemExit:
        pass
    except Exception as e:
        print(f"  [!] 执行出错: {type(e).__name__}: {e}")

    builtins.getattr = original_getattr
    return captured

def is_obfuscated(code_text):
    """判断是否还是混淆代码（以 import lzma,base64 开头）"""
    if isinstance(code_text, bytes):
        return code_text.startswith(b'import lzma,base64')
    if isinstance(code_text, str):
        return code_text.startswith('import lzma,base64')
    return False

# 读取原始文件
print("=== 递归解密 routes_decrypted.py ===\n")
with open('routes_decrypted.py', 'r', encoding='utf-8') as f:
    current = f.read()

layer = 0
while True:
    layer += 1
    length = len(current)
    print(f"[第{layer}层] 长度: {length} 字符")

    if not is_obfuscated(current):
        print(f"  -> 不再是混淆代码，解密完成！")
        break

    print(f"  -> 检测到混淆代码，开始解密...")
    result = decrypt_one_layer(current)

    if result is None:
        print(f"  [!] 解密返回None，停止")
        break

    # 转换为str
    if isinstance(result, bytes):
        try:
            result = result.decode('utf-8')
        except:
            print(f"  [!] bytes无法UTF-8解码，保存为二进制")
            with open('routes_decrypted_final.bin', 'wb') as f:
                f.write(result)
            print(f"  已保存到 routes_decrypted_final.bin")
            break

    current = result

# 保存最终结果
if isinstance(current, str):
    out_path = 'routes_decrypted_final.py'
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(current)
    print(f"\n=== 最终结果 ===")
    print(f"解密层数: {layer}")
    print(f"最终长度: {len(current)} 字符")
    print(f"保存到: {out_path}")
    print(f"\n--- 前1000字符 ---")
    print(current[:1000])
