# Telegram 密码生成器 Bot

一个私人使用的 Telegram Bot，用于生成随机密码并记录历史。

## 功能

- 自定义字符类型：a-z、A-Z、0-9、!@#$%
- 排除易混淆字符：iIl10oO
- 快速生成 16/20/24 位密码
- 密码历史记录保存
- 用户权限控制

## 安装

```bash
pip install -r requirements.txt
```

## 配置

创建 `config.json` 文件：

```json
{
  "bot_token": "YOUR_BOT_TOKEN_HERE",
  "allowed_users": [123456789]
}
```

- `bot_token`: 从 [@BotFather](https://t.me/BotFather) 获取
- `allowed_users`: 允许使用的用户 ID 列表

获取用户 ID：向 Bot 发送 `/start`，未授权用户会收到自己的用户 ID。

## 运行

```bash
python bot.py
```

## 命令

- `/start` - 显示主界面
- `/list` - 查看保存的密码记录
- `/clear` - 清除所有记录
