#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import os
import time
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

DEBUG = False
ACCOUNTS_FILE = Path(__file__).with_name("accounts.json")

def load_accounts():
    """
    优先从环境变量 GLaDOS_COOKIES_JSON 读取（Actions/CI）
    否则从本地 accounts.json 读取（本地运行）
    """
    raw = os.getenv("GLaDOS_COOKIES_JSON", "").strip()
    if raw:
        try:
            accounts = json.loads(raw)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"GLaDOS_COOKIES_JSON is not valid JSON: {e}") from e
        source = "env:GLaDOS_COOKIES_JSON"
    else:
        if not ACCOUNTS_FILE.exists():
            raise RuntimeError(
                "Missing accounts source.\n"
                f"- For local: create {ACCOUNTS_FILE}\n"
                "- For CI: set env GLaDOS_COOKIES_JSON"
            )
        try:
            raw = ACCOUNTS_FILE.read_text(encoding="utf-8").strip()
            accounts = json.loads(raw)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"{ACCOUNTS_FILE} is not valid JSON: {e}") from e
        source = f"file:{ACCOUNTS_FILE}"

    if not isinstance(accounts, list) or not accounts:
        raise RuntimeError(f"Accounts from {source} must be a non-empty JSON array")

    for idx, a in enumerate(accounts, 1):
        if not isinstance(a, dict):
            raise RuntimeError(f"Account #{idx} must be an object")
        for k in ("name", "koa_sess", "koa_sess_sig"):
            if not a.get(k):
                raise RuntimeError(f"Account #{idx} missing field: {k}")

    return accounts, source

def format_traffic(traffic):
    if traffic is None:
        return "未知"
    gb = traffic / (1024**3)
    mb = traffic / (1024**2)
    return f"{gb:.2f} GB" if gb >= 1 else f"{mb:.2f} MB"

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

    def set_cookies(self, koa_sess: str, koa_sess_sig: str):
        self.s.cookies.update({
            "koa:sess": koa_sess,
            "koa:sess.sig": koa_sess_sig,
        })

    def get_status(self):
        url = "https://glados.cloud/api/user/status"
        r = self.s.get(url, timeout=30)
        if r.status_code != 200:
            return None, f"HTTP {r.status_code}"

        data = r.json()
        if data.get("code") != 0:
            return None, data.get("message", "status error")

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
        # 先 GET 页面（有些站依赖初始化）
        self.s.get("https://glados.cloud/console/checkin", timeout=30)

        # 关键：按抓包 payload
        url = "https://glados.cloud/api/user/checkin"
        r = self.s.post(url, json={"token": "glados.cloud"}, timeout=30)

        if r.status_code != 200:
            return {"code": -1, "message": f"HTTP {r.status_code}"}
        return r.json()

def main():
    accounts, source = load_accounts()
    print(f"Loaded {len(accounts)} account(s) from {source}")

    results = []
    for i, acc in enumerate(accounts, 1):
        name = acc["name"]
        print(f"\n===== 账号 {i}: {name} =====")

        g = GLaDOS()
        g.set_cookies(acc["koa_sess"], acc["koa_sess_sig"])

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

        if res.get("code") == 0:
            print(f"✅ 签到成功：{msg}，获得点数：{points_today}")
            results.append((name, "成功", msg, points_today, st["leftDays"], st.get("traffic")))
        elif "repeat" in str(msg).lower():
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
