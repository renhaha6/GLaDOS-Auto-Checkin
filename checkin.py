import os
import json
import time
import random
import hashlib
import requests
from pypushdeer import PushDeer
from decimal import Decimal, InvalidOperation
from urllib.parse import quote


CHECKIN_URL = "https://glados.network/api/user/checkin"
CHALLENGE_URL = "https://glados.network/api/user/checkin/challenge"
STATUS_URL = "https://glados.network/api/user/status"
POINTS_URL = "https://glados.network/api/user/points"

# 前端校验：nonce 下发后至少 2.5 秒才允许提交，否则按未验证签到只给 1 分
PROOF_SALT = "glados-observe-v1"
MIN_CHALLENGE_AGE = 2.6

HEADERS_BASE = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "zh-CN,zh;q=0.9",
    "sec-ch-ua": '"Not:A-Brand";v="8", "Chromium";v="156", "Google Chrome";v="156"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "origin": "https://glados.network",
    "referer": "https://glados.network/console/checkin",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/156.0.0.0 Safari/537.36"
    ),
    "content-type": "application/json;charset=UTF-8",
}

PAYLOAD = {"token": "glados.network"}
TIMEOUT = 10


def push_deer(sckey: str, title: str, text: str):
    """推送消息到 PushDeer"""
    if sckey:
        PushDeer(pushkey=sckey).send_text(title, desp=text)


def push_serverchan(sendkey: str, title: str, content: str):
    """推送消息到 Server 酱 (Turbo 版)"""
    if not sendkey:
        return
    
    # Server 酱 Turbo 版 API
    url = f"https://sctapi.ftqq.com/{sendkey}.send"
    
    data = {
        "title": title,
        "desp": content
    }
    
    try:
        resp = requests.post(url, data=data, timeout=TIMEOUT)
        if resp.status_code == 200:
            result = resp.json()
            if result.get("code") == 0:
                print("✅ Server 酱推送成功")
            else:
                print(f"⚠️ Server 酱推送失败: {result.get('message')}")
        else:
            print(f"⚠️ Server 酱推送失败: HTTP {resp.status_code}")
    except Exception as e:
        print(f"⚠️ Server 酱推送异常: {e}")


def push_bark(bark_key: str, title: str, content: str):
    """推送消息到 Bark"""
    if not bark_key:
        return

    url = f"https://api.day.app/{quote(bark_key)}/{quote(title)}/{quote(content)}"
    params = {
        "icon": "https://glados.rocks/assets/favicon.ico",
        "group": "GLaDOS-Auto-Checkin",
        "level": "active",
        "isArchive": "1",
    }

    try:
        resp = requests.get(url, params=params, timeout=TIMEOUT)
        if resp.status_code == 200:
            result = resp.json()
            if result.get("code") == 200:
                print("✅ Bark 推送成功")
            else:
                print(f"⚠️ Bark 推送失败: {result.get('message')}")
        else:
            print(f"⚠️ Bark 推送失败: HTTP {resp.status_code}")
    except Exception as e:
        print(f"⚠️ Bark 推送异常: {e}")


def push_all(
    sendkey_deer: str,
    sendkey_sc: str,
    bark_key: str,
    title: str,
    content: str,
    bark_content: str = "",
):
    """推送到所有配置的服务"""
    # PushDeer 推送
    if sendkey_deer:
        push_deer(sendkey_deer, title, content)
    
    # Server 酱推送
    if sendkey_sc:
        push_serverchan(sendkey_sc, title, content)

    # Bark 推送
    if bark_key:
        push_bark(bark_key, title, bark_content or content)
    
    # 如果都没有配置，打印提醒
    if not sendkey_deer and not sendkey_sc and not bark_key:
        print("⚠️ 未配置任何推送服务，请在 Secrets 中配置 SENDKEY / SERVERCHAN_KEY / BARK_KEY")


def safe_json(resp):
    try:
        return resp.json()
    except Exception:
        return {}


def get_challenge(session: requests.Session, headers: dict):
    """获取签到 nonce，接口不可用时返回 None（退化为旧版未验证签到）"""
    try:
        r = session.get(CHALLENGE_URL, headers=headers, timeout=TIMEOUT)
        j = safe_json(r)
        if r.ok and j.get("code") == 0 and j.get("nonce"):
            return {
                "nonce": str(j["nonce"]),
                "ttl": j.get("ttl"),
                "received_at": time.monotonic(),
            }
        print(f"⚠️ 获取 challenge 失败: HTTP {r.status_code}, code={j.get('code')}, message={j.get('message')}")
    except Exception as e:
        print(f"⚠️ 获取 challenge 异常: {e}")
    return None


def build_proof(nonce: str) -> str:
    """proof = SHA256(nonce + '.' + salt) 的小写十六进制"""
    return hashlib.sha256(f"{nonce}.{PROOF_SALT}".encode()).hexdigest()


def get_total_points(session: requests.Session, headers: dict):
    """获取账户当前总积分，失败时返回 None"""
    try:
        r = session.get(POINTS_URL, headers=headers, timeout=TIMEOUT)
        j = safe_json(r)
        if j.get("code") != 0:
            return None
        points = j.get("points")
        if points is None:
            return None
        return Decimal(str(points))
    except (InvalidOperation, TypeError, ValueError):
        return None
    except Exception:
        return None


def format_points(value):
    """格式化积分，只去掉小数部分无意义的尾随 0"""
    if isinstance(value, Decimal):
        text = format(value, "f")
    else:
        text = str(value)
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def main():
    # 获取推送密钥
    sendkey_deer = os.getenv("SENDKEY", "")
    sendkey_sc = os.getenv("SERVERCHAN_KEY", "")
    bark_key = os.getenv("BARK_KEY", "")
    cookies_env = os.getenv("COOKIES", "")
    cookies = [c.strip() for c in cookies_env.split("&") if c.strip()]

    if not cookies:
        push_all(sendkey_deer, sendkey_sc, bark_key, "GLaDOS 签到", "❌ 未检测到 COOKIES")
        return

    session = requests.Session()
    ok = fail = repeat = 0
    lines = []

    for idx, cookie in enumerate(cookies, 1):
        headers = dict(HEADERS_BASE)
        headers["cookie"] = cookie

        email = "unknown"
        points = "-"
        days = "-"
        gained = "?"
        proof_tag = "none"

        try:
            before_points = get_total_points(session, headers)

            payload = dict(PAYLOAD)
            challenge = get_challenge(session, headers)
            if challenge:
                elapsed = time.monotonic() - challenge["received_at"]
                if elapsed < MIN_CHALLENGE_AGE:
                    time.sleep(MIN_CHALLENGE_AGE - elapsed)
                payload["nonce"] = challenge["nonce"]
                payload["proof"] = build_proof(challenge["nonce"])

            r = session.post(
                CHECKIN_URL,
                headers=headers,
                data=json.dumps(payload),
                timeout=TIMEOUT,
            )

            j = safe_json(r)
            msg = str(j.get("message") or "")
            msg_lower = msg.lower()
            repeated = bool(j.get("repeated")) or any(
                word in msg_lower
                for word in ("repeat", "already checked", "already check", "已签到", "重复签到", "已经签到")
            )
            proof_tag = "proof" if challenge else "none"

            if repeated:
                repeat += 1
                status = "🔁 已签到"
            elif r.ok and j.get("code") == 0:
                ok += 1
                status = "✅ 成功"
            elif r.ok and j.get("code") == 4 and j.get("reason") == "device-mismatch":
                fail += 1
                status = "❌ 设备不匹配，请在浏览器重新登录后更新 COOKIES"
            else:
                fail += 1
                status = (
                    f"❌ 失败(HTTP {r.status_code}, code={j.get('code')}, "
                    f"reason={j.get('reason') or '-'}: {msg or '接口未返回 message'})"
                )

            # 状态接口（允许失败）
            s = session.get(STATUS_URL, headers=headers, timeout=TIMEOUT)
            sj = safe_json(s).get("data") or {}
            email = sj.get("email", email)
            if sj.get("leftDays") is not None:
                days = f"{int(float(sj['leftDays']))} 天"

            after_points = get_total_points(session, headers)
            if before_points is not None and after_points is not None:
                gained = format_points(after_points - before_points)
                points = format_points(after_points)

        except Exception:
            fail += 1
            status = "❌ 异常"

        lines.append(
            f"{idx}. {email} | {status} | 总积分:{points} | 本次+{gained} | 剩余:{days} | 验证:{proof_tag}"
        )
        time.sleep(random.uniform(1, 2))

    title = f"GLaDOS 签到完成 ✅{ok} ❌{fail} 🔁{repeat}"
    content = "\n".join(lines)
    bark_content = "📊 签到结果明细\n\n" + content

    print(content)
    
    # 推送消息到所有服务
    push_all(sendkey_deer, sendkey_sc, bark_key, title, content, bark_content=bark_content)


if __name__ == "__main__":
    main()
