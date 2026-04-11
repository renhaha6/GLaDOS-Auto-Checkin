import os
import json
import time
import random
import requests
from pypushdeer import PushDeer
from urllib.parse import quote


CHECKIN_URL = "https://glados.cloud/api/user/checkin"
STATUS_URL = "https://glados.cloud/api/user/status"

HEADERS_BASE = {
    "origin": "https://glados.cloud",
    "referer": "https://glados.cloud/console/checkin",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "content-type": "application/json;charset=UTF-8",
}

PAYLOAD = {"token": "glados.cloud"}
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


def push_all(sendkey_deer: str, sendkey_sc: str, bark_key: str, title: str, content: str):
    """推送到所有配置的服务"""
    # PushDeer 推送
    if sendkey_deer:
        push_deer(sendkey_deer, title, content)
    
    # Server 酱推送
    if sendkey_sc:
        push_serverchan(sendkey_sc, title, content)

    # Bark 推送
    if bark_key:
        push_bark(bark_key, title, content)
    
    # 如果都没有配置，打印提醒
    if not sendkey_deer and not sendkey_sc and not bark_key:
        print("⚠️ 未配置任何推送服务，请在 Secrets 中配置 SENDKEY / SERVERCHAN_KEY / BARK_KEY")


def safe_json(resp):
    try:
        return resp.json()
    except Exception:
        return {}


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

        try:
            r = session.post(
                CHECKIN_URL,
                headers=headers,
                data=json.dumps(PAYLOAD),
                timeout=TIMEOUT,
            )

            j = safe_json(r)
            msg = j.get("message", "")
            msg_lower = msg.lower()

            if "got" in msg_lower:
                ok += 1
                points = j.get("points", "-")
                status = "✅ 成功"
            elif "repeat" in msg_lower or "already" in msg_lower:
                repeat += 1
                status = "🔁 已签到"
            else:
                fail += 1
                status = "❌ 失败"

            # 状态接口（允许失败）
            s = session.get(STATUS_URL, headers=headers, timeout=TIMEOUT)
            sj = safe_json(s).get("data") or {}
            email = sj.get("email", email)
            if sj.get("leftDays") is not None:
                days = f"{int(float(sj['leftDays']))} 天"

        except Exception:
            fail += 1
            status = "❌ 异常"

        lines.append(f"{idx}. {email} | {status} | P:{points} | 剩余:{days}")
        time.sleep(random.uniform(1, 2))

    title = f"GLaDOS 签到完成 ✅{ok} ❌{fail} 🔁{repeat}"
    content = "\n".join(lines)

    print(content)
    
    # 推送消息到所有服务
    push_all(sendkey_deer, sendkey_sc, bark_key, title, content)


if __name__ == "__main__":
    main()
