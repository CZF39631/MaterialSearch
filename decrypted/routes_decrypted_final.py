import socket
import struct
import time
from functools import wraps
from flask import jsonify, request
from config import *
from database import get_pexels_video_count
from models import DatabaseSessionPexelsVideo
from routes import login_required
from scan import scanner
from search import clean_cache

FORBIDDEN = ('', 403)


def verify_checksum(time_cookie, checksum_b64, max_diff=20) -> bool:
    """验证请求的时间戳和校验和是否合法"""
    try:
        if len(checksum_b64) <= 4:
            return False
        trimmed = checksum_b64[2:]       # 去掉前2字符
        suffix = trimmed[-2:]             # 取末尾2字符
        main_part = trimmed[:-2]          # 剩余部分
        # 每4个字符取第4个（索引3），再拼上suffix
        extracted = ''.join([main_part[i + 3] for i in range(0, len(main_part), 4) if i + 3 < len(main_part)])
        real_b64 = extracted + suffix
        decoded = base64.b64decode(real_b64)
        if len(decoded) != 4:
            return False
        checksum_int = int.from_bytes(decoded, byteorder='big')
        real_timestamp = time_cookie ^ checksum_int
        now = int(time.time())
        return abs(now - real_timestamp) <= max_diff
    except Exception:
        return False


def checksum_required(view_func):
    """装饰器：要求请求携带有效的时间校验和"""
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        time_cookie = request.cookies.get('time')
        if not time_cookie or not time_cookie.isdigit():
            return FORBIDDEN
        time_cookie = int(time_cookie)
        checksum = request.headers.get('X-Checksum') or request.values.get('checksum')
        if not checksum:
            return FORBIDDEN
        try:
            valid = verify_checksum(time_cookie, checksum)
            if not valid:
                return FORBIDDEN
        except Exception:
            return FORBIDDEN
        return view_func(*args, **kwargs)
    return wrapper


@app.route("/time", methods=["GET"])
@login_required
def get_timestamp():
    """返回时间戳，并用客户端IP加密后写入cookie"""
    client_ip = request.environ.get("HTTP_X_FORWARDED_FOR", request.remote_addr)
    try:
        ip_int = struct.unpack("!I", socket.inet_aton(client_ip))[0]
    except Exception:
        ip_int = 0
    timestamp = int(time.time())
    encrypted = ip_int ^ timestamp
    resp = jsonify({"timestamp": timestamp})
    resp.set_cookie("time", str(encrypted))
    return resp


@app.route("/api/scan", methods=["GET"])
@login_required
@checksum_required
def start_scan():
    global scanner
    if not scanner.is_scanning:
        import threading
        t = threading.Thread(target=scanner.scan)
        t.start()
        return jsonify({"status": "start scanning"})
    return jsonify({"status": "already scanning"})


@app.route("/api/status", methods=["GET"])
@login_required
@checksum_required
def get_status():
    global scanner
    status = scanner.get_status()
    with DatabaseSessionPexelsVideo() as session:
        status["total_pexels_videos"] = get_pexels_video_count(session)
    return jsonify(status)


@app.route("/api/clean_cache", methods=["GET", "POST"])
@login_required
@checksum_required
def clean_cache_route():
    clean_cache()
    return "", 204
