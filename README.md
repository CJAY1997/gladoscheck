# GLaDOS 自动签到

GLaDOS 网络自动签到脚本，支持多账号和微信推送通知。

支持GithubAction和本地运行,GithubAction就用下面的环境变量,本地运行把cookie填入accounts.json中,脚本会自适应执行,优先环境变量

## 功能特性

- 🚀 自动每日签到
- 👥 支持多账号（通过cookies）
- 📱 微信推送通知（Server酱）
- 🤖 GitHub Actions 自动运行
- 📊 签到状态检查
- 🔒 安全的账号信息管理

## 使用方法

### 1. Fork 本仓库

点击右上角的 `Fork` 按钮，将仓库 fork 到你的账号下。

### 2. 获取 Cookies

1. 登录 [GLaDOS](https://glados.network/console)
2. 打开浏览器开发者工具 (F12)
3. 切换到 Network 标签页
4. 刷新页面，找到任意请求
5. 在请求头中找到 Cookie 字段，复制其中的 `koa:sess` 和 `koa:sess.sig` 值

### 3. 配置 Secrets

在你 fork 的仓库中，进入 `Settings` -> `Secrets and variables` -> `Actions`，添加以下 secrets：

#### 必需配置

- `COOKIES`: GLaDOS cookies 信息，格式为 JSON 字符串：
  ```json
  [
    {
      "name": "账号1",
      "koa_sess": "your_koa_sess_value",
      "koa_sess_sig": "your_koa_sess_sig_value"
    },
    {
      "name": "账号2", 
      "koa_sess": "another_koa_sess_value",
      "koa_sess_sig": "another_koa_sess_sig_value"
    }
  ]
  ```

#### 可选配置

- `SERVERCHAN_KEY`: Server酱推送 Key（用于微信通知）

### 4. 启用 GitHub Actions

进入 `Actions` 页面，启用 GitHub Actions。

### 5. 测试运行

可以手动触发 workflow 测试是否配置正确。

## 自动运行时间

默认配置为每天北京时间 9:00 AM 自动运行，你可以在 `.github/workflows/checkin.yml` 中修改运行时间。

## 注意事项

- Cookies 有效期较长，但建议定期更新
- 如果签到失败，请检查 cookies 是否过期
- 支持多账号同时签到

## 免责声明

本项目仅供学习交流使用，请遵守相关服务条款。使用本项目所产生的任何后果由使用者自行承担。

## License

MIT License
