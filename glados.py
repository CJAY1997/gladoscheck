#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import os
import sys
import time
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 解决 Windows 控制台输出 Emoji 时报 UnicodeEncodeError (GBK) 的问题
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DEBUG = False
ACCOUNTS_LOCAL = Path(__file__).with_name("accounts.local.json")
ACCOUNTS_FILE = Path(__file__).with_name("accounts.json")

def load_accounts():
    """
    优先从环境变量 GLaDOS_COOKIES_JSON / GLADOS_COOKIES_JSON 读取（Actions/CI）
    本地运行优先读取 accounts.local.json（防泄露），其次 accounts.json
    """
    raw = (os.getenv("GLaDOS_COOKIES_JSON") or os.getenv("GLADOS_COOKIES_JSON") or "").strip()
    if raw:
        try:
            accounts = json.loads(raw)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"GLaDOS_COOKIES_JSON is not valid JSON: {e}") from e
        source = "env:GLaDOS_COOKIES_JSON"
    else:
        target_file = ACCOUNTS_LOCAL if ACCOUNTS_LOCAL.exists() else ACCOUNTS_FILE
        if not target_file.exists():
            raise RuntimeError(
                "Missing accounts source.\n"
                f"- For local: create {ACCOUNTS_LOCAL} or {ACCOUNTS_FILE}\n"
                "- For CI: set env GLaDOS_COOKIES_JSON / GLADOS_COOKIES_JSON"
            )
        try:
            raw = target_file.read_text(encoding="utf-8").strip()
            accounts = json.loads(raw)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"{target_file} is not valid JSON: {e}") from e
        source = f"file:{target_file.name}"

    if not isinstance(accounts, list) or not accounts:
        raise RuntimeError(f"Accounts from {source} must be a non-empty JSON array")

    for idx, a in enumerate(accounts, 1):
        if not isinstance(a, dict):
            raise RuntimeError(f"Account #{idx} must be an object")
        if not a.get("name"):
            raise RuntimeError(f"Account #{idx} missing field: name")
        # 支持整段 cookie 或分开的字段
        has_full_cookie = bool(a.get("cookie"))
        has_koa = bool(a.get("koa_sess") and a.get("koa_sess_sig"))
        has_gld = bool(a.get("gld_sess"))
        if not (has_full_cookie or has_koa or has_gld):
            raise RuntimeError(
                f"Account #{idx} ({a.get('name')}) 缺少 Cookie。\n"
                "可直接提供完整的 'cookie' 字符串，或分别提供 'gld_sess', 'gld_sess_sig', 'koa_sess', 'koa_sess_sig'。"
            )

    return accounts, source

def format_traffic(traffic):
    if traffic is None:
        return "未知"
    # 按照从大到小的顺序判断
    if traffic >= 1024 ** 3:
        return f"{traffic / (1024 ** 3):.2f} GB"
    elif traffic >= 1024 ** 2:
        return f"{traffic / (1024 ** 2):.2f} MB"
    elif traffic >= 1024:
        return f"{traffic / 1024:.2f} KB"
    else:
        return f"{traffic} B"

def notify_telegram(title: str, text: str) -> bool:
    token = os.getenv("TG_BOT_TOKEN")
    chat_id = os.getenv("TG_CHAT_ID")
    if not token or not chat_id:
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": f"{title}\n\n{text}",
        "disable_web_page_preview": True,
    }
    try:
        r = requests.post(url, json=payload, timeout=30)
        return r.status_code == 200
    except requests.RequestException:
        return False

def notify_serverchan(title: str, markdown: str) -> bool:
    key = os.getenv("SERVERCHAN_KEY")
    if not key:
        return False
    url = f"https://sctapi.ftqq.com/{key}.send"
    try:
        r = requests.post(url, data={"title": title, "desp": markdown}, timeout=30)
        return r.status_code == 200
    except requests.RequestException:
        return False

def notify(title: str, text: str):
    if notify_telegram(title, text):
        return
    notify_serverchan(title, text)

class GLaDOS:
    def __init__(self):
        self.s = requests.Session()
        self.s.trust_env = True

        retry = Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.s.mount("https://", adapter)
        self.s.mount("http://", adapter)

        # 对齐浏览器关键头
        self.s.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36 Edg/143.0.0.0",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://glados.cloud",
            "Referer": "https://glados.cloud/console/checkin",
        })

    def set_cookies_from_account(self, acc: dict):
        # 1. 优先使用整段 cookie 字符串
        if acc.get("cookie"):
            raw_cookie = acc["cookie"].strip()
            for part in raw_cookie.split(";"):
                if "=" in part:
                    k, v = part.strip().split("=", 1)
                    self.s.cookies.set(k.strip(), v.strip())
            return

        # 2. 字段式注入
        cookies = {}
        if acc.get("gld_sess"):
            cookies["gld:sess"] = acc["gld_sess"]
        if acc.get("gld_sess_sig"):
            cookies["gld:sess.sig"] = acc["gld_sess_sig"]
        if acc.get("koa_sess"):
            cookies["koa:sess"] = acc["koa_sess"]
        if acc.get("koa_sess_sig"):
            cookies["koa:sess.sig"] = acc["koa_sess_sig"]

        self.s.cookies.update(cookies)

    def get_status(self):
        url = "https://glados.cloud/api/user/status"
        try:
            r = self.s.get(url, timeout=30)
        except requests.RequestException as e:
            return None, f"网络请求失败: {e}"

        if r.status_code != 200:
            return None, f"HTTP {r.status_code}"

        try:
            data = r.json()
        except Exception:
            return None, f"响应解析失败: {r.text[:100]}"

        if data.get("code") != 0:
            msg = data.get("message", "status error")
            if "没有权限" in msg or data.get("code") == -2:
                msg = f"{msg} (Cookie 已过期或无效，请重新抓取填入 accounts.json)"
            return None, msg

        u = data.get("data", {}) or {}
        if DEBUG:
            safe_keys = ["email", "vip", "days", "leftDays", "traffic", "cakeCount", "site", "expired", "system_date"]
            print("调试返回(脱敏)：", json.dumps({k: u.get(k) for k in safe_keys}, ensure_ascii=False, indent=2))

        return {
            "email": u.get("email"),
            "vip": u.get("vip"),
            "leftDays": int(float(u.get("leftDays", 0))),
            "days": u.get("days"),
            "traffic": u.get("traffic"),
            "cakeCount": u.get("cakeCount"),
        }, None

    def checkin(self):
        try:
            # 先 GET 页面（有些站依赖初始化）
            self.s.get("https://glados.cloud/console/checkin", timeout=30)

            # 关键：按抓包 payload
            url = "https://glados.cloud/api/user/checkin"
            r = self.s.post(url, json={"token": "glados.cloud"}, timeout=30)
        except requests.RequestException as e:
            return {"code": -1, "message": f"网络请求失败: {e}"}

        if r.status_code != 200:
            return {"code": -1, "message": f"HTTP {r.status_code}"}
        try:
            return r.json()
        except Exception:
            return {"code": -1, "message": f"响应解析失败: {r.text[:100]}"}

def main():
    accounts, source = load_accounts()
    print(f"Loaded {len(accounts)} account(s) from {source}")

    results = []
    for i, acc in enumerate(accounts, 1):
        name = acc["name"]
        print(f"\n===== 账号 {i}: {name} =====")

        g = GLaDOS()
        g.set_cookies_from_account(acc)

        st, err = g.get_status()
        if err:
            print("❌ 获取状态失败：", err)
            results.append((name, "失败", err, None, None, None))
            continue

        print("账号状态详情：")
        print(f"  邮箱: {st['email']}")
        print(f"  VIP等级: {st['vip']}")
        print(f"  剩余天数: {st['leftDays']}")
        print(f"  已用流量: {format_traffic(st.get('traffic'))}")
        print(f"  Cake数: {st.get('cakeCount', 0)}")

        res = g.checkin()
        msg = res.get("message", "Unknown")
        points_today = res.get("points")

        msg_lower = str(msg).lower()
        is_repeat = any(k in msg_lower for k in ("repeat", "return tomorrow", "already", "logged"))

        if res.get("code") == 0:
            print(f"✅ 签到成功：{msg}，获得点数：{points_today}")
            results.append((name, "成功", msg, points_today, st["leftDays"], st.get("traffic")))
        elif is_repeat:
            print("ℹ️ 今日已签到：", msg)
            results.append((name, "已签到", msg, points_today, st["leftDays"], st.get("traffic")))
        else:
            print("❌ 签到失败：", msg)
            results.append((name, "失败", msg, points_today, st["leftDays"], st.get("traffic")))

        time.sleep(2)

    ok = sum(1 for _, st, *_ in results if st in ("成功", "已签到"))
    total = len(results)

    # CI 用 SGT，本地也不影响
    now_sgt = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S (SGT)")
    report = f"时间：{now_sgt}\n结果：{ok}/{total}\n\n"
    for name, st, msg, points_today, leftDays, traffic in results:
        icon = "✅" if st == "成功" else ("ℹ️" if st == "已签到" else "❌")
        report += f"{icon} {name}：{st} - {msg}"
        if points_today is not None:
            report += f" (今日点数: {points_today})"
        report += f" (剩余天数: {leftDays})"
        if traffic is not None:
            report += f" (已用流量: {format_traffic(traffic)})"
        report += "\n"

    print("\n--- 汇总 ---\n" + report)
    notify("GLaDOS 签到报告", report)

if __name__ == "__main__":
    main()
