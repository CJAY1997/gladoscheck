# 详细配置说明

由于 GLaDOS 官方安全升级，目前每次请求必须携带 **4 个 Cookie 字段** 才能通过身份验证。

---

## 1. Cookies 获取方法

### 方法一：开发者工具 Application 面板（最直观）
1. 打开浏览器并登录 [GLaDOS 控制台](https://glados.cloud/console/checkin)。
2. 按 `F12` 打开开发者工具。
3. 点击顶部的 **应用 (Application)** 标签页（如未显示，可点击 `>>` 展开）。
4. 在左侧面板展开 **存储 (Storage)** -> **Cookie** -> 点击 `https://glados.cloud`。
5. 在右侧列表中找到以下 **4 个名称**，分别点击并复制其值：
   - `gld:sess`
   - `gld:sess.sig`
   - `koa:sess`
   - `koa:sess.sig`

### 方法二：开发者工具 Network 面板（最快捷）
1. 打开开发者工具并切换到 **网络 (Network)** 标签页。
2. 刷新页面，在列表中点击任意以 `status` 或 `checkin` 结尾的请求。
3. 在右侧 **标头 (Headers)** -> **请求标头 (Request Headers)** 中找到 **`cookie:`**。
4. 复制整行 Cookie 内容，可直接作为 `"cookie": "..."` 填入配置。

---

## 2. GitHub Secrets 配置

在 GitHub 仓库中点击 `Settings` -> `Secrets and variables` -> `Actions`。

### `GLADOS_COOKIES_JSON`（必需）

格式为 JSON 数组，支持任意数量的多账号：

#### 格式 A：标准 4 字段格式（推荐）
```json
[
  {
    "name": "账号1",
    "gld_sess": "你的 gld:sess",
    "gld_sess_sig": "你的 gld:sess.sig",
    "koa_sess": "你的 koa:sess",
    "koa_sess_sig": "你的 koa:sess.sig"
  },
  {
    "name": "账号2",
    "gld_sess": "账号2的 gld:sess",
    "gld_sess_sig": "账号2的 gld:sess.sig",
    "koa_sess": "账号2的 koa:sess",
    "koa_sess_sig": "账号2的 koa:sess.sig"
  }
]
```

#### 格式 B：整串 Cookie 格式
```json
[
  {
    "name": "账号1",
    "cookie": "gld:sess=...; gld:sess.sig=...; koa:sess=...; koa:sess.sig=..."
  }
]
```

---

## 3. 推送通知配置（可选）

### Telegram 推送
- `TG_BOT_TOKEN`：在 Telegram 中与 `@BotFather` 对话创建机器人后获取的 HTTP API Token。
- `TG_CHAT_ID`：你的 Telegram 用户 ID 或群组 ID（可通过 `@userinfobot` 获取）。

### 微信推送（Server酱）
- `SERVERCHAN_KEY`：Server酱 SendKey。
  1. 访问 https://sct.ftqq.com/ 微信扫码登录。
  2. 点击“发送消息”获取 SendKey。
  3. 设置为 `SERVERCHAN_KEY`。

---

## 4. 本地安全测试与运行

为了避免本地提交代码时不慎将真实 Cookie 上传到 GitHub，本地采用安全文件分离机制：

1. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```
2. 在本地创建 `accounts.local.json`（该文件已写入 `.gitignore`，不会被 Git 提交）：
   ```json
   [
     {
       "name": "账号1",
       "gld_sess": "...",
       "gld_sess_sig": "...",
       "koa_sess": "...",
       "koa_sess_sig": "..."
     }
   ]
   ```
3. 执行测试：
   ```bash
   python checkin.py
   ```
   程序会自动优先读取 `accounts.local.json`，确保本地测试正常且绝不泄露凭据。
