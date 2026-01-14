#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import time
import requests
from datetime import datetime, timezone, timedelta
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def load_accounts_from_secret_env() -> list[dict]:
    raw = os.getenv("GLaDOS_COOKIES_JSON", "").strip()
    if not raw:
        raise RuntimeError("Missing secret env: GLaDOS_COOKIES_JSON")

    try:
        accounts = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"GLaDOS_COOKIES_JSON is not valid JSON: {e}") from e

    if not isinstance(accounts, list) or not accounts:
        raise RuntimeError("GLaDOS_COOKIES_JSON must be a non-empty JSON array")

    for idx, a in enumerate(accounts, 1):
        if not isinstance(a, dict):
            raise RuntimeError(f"Account #{idx} must be an object")
        for k in ("name", "koa_sess", "koa_sess_sig"):
            if not a.get(k):
                raise RuntimeError(f"Account #{idx} missing field: {k}")

    return accounts


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
    # 不配置就不会发；优先 Telegram，其次 Server酱
    if notify_telegram(title, text):
        return
    notify_serverchan(title, text)


class GLaDOS:
    def __init__(self):
        self.s = requests.Session()
        self.s.trust_env = True  # 允许使用 runner 的代理环境（可选）

        retry = Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.s.mount("https://", adapter)
        self.s.mount("http://", adapter)

        self.s.headers.update({
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://glados.rocks",
            "Referer": "https://glados.rocks/console/checkin",
        })

    def set_cookies(self, koa_sess: str, koa_sess_sig: str):
        # 注意：绝不打印 cookie
        self.s.cookies.update({
            "koa:sess": koa_sess,
            "koa:sess.sig": koa_sess_sig,
        })

    def get_status(self):
        url = "https://glados.rocks/api/user/status"
        r = self.s.get(url, timeout=30)
        if r.status_code != 200:
            return None, f"HTTP {r.status_code}"

        data = r.json()
        if data.get("code") != 0:
            return None, data.get("message", "status error")

        u = data.get("data", {}) or {}
        return {
            "email": u.get("email", "Unknown"),
            "days": u.get("leftDays", "Unknown"),
        }, None

    def checkin(self):
        url = "https://glados.rocks/api/user/checkin"
        r = self.s.post(url, json={"token": "glados.one"}, timeout=30)
        if r.status_code != 200:
            return {"code": -1, "message": f"HTTP {r.status_code}"}
        return r.json()


def main():
    accounts = load_accounts_from_secret_env()
    results = []

    for i, acc in enumerate(accounts, 1):
        name = acc["name"]
        print(f"\n===== 账号 {i}: {name} =====")

        g = GLaDOS()
        g.set_cookies(acc["koa_sess"], acc["koa_sess_sig"])

        st, err = g.get_status()
        if err:
            print("❌ 获取状态失败：", err)
            results.append((name, "失败", err))
            continue

        print("邮箱：", st["email"])
        print("剩余天数：", st["days"])

        res = g.checkin()
        msg = res.get("message", "Unknown")
        points = res.get("points")  # 新增


        if res.get("code") == 0:
            print(f"✅ 签到成功：{msg}，获得点数：{points}")
            results.append((name, "成功", f"{msg} (点数: {points})"))
        elif "repeat" in msg.lower():
            print("ℹ️ 今日已签到：", msg)
            results.append((name, "已签到", msg))
        else:
            print("❌ 签到失败：", msg)
            results.append((name, "失败", msg))

        time.sleep(2)

    ok = sum(1 for _, st, _ in results if st == "成功")
    total = len(results)
    now_sgt = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S (SGT)")

    report = f"时间：{now_sgt}\n结果：{ok}/{total}\n\n"
    for name, st, msg in results:
        icon = "✅" if st == "成功" else ("ℹ️" if st == "已签到" else "❌")
        report += f"{icon} {name}：{st} - {msg}\n"

    print("\n--- 汇总 ---\n" + report)
    notify("GLaDOS 签到报告", report)


if __name__ == "__main__":
    main()
