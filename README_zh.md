# Telegram 密码生成器 Bot

一个私人使用的 Telegram Bot，用于生成随机密码并记录历史。

## 功能

- 自定义字符类型：a-z、A-Z、0-9、!@#$%
- 排除易混淆字符：iIl10oO
- 快速生成 16/20/24 位密码
- **手动保存**：生成的密码默认不保存，点击按钮确认后记录
- **即时刷新**：不满意当前密码可点击刷新重新生成
- 密码历史记录保存
- 用户权限控制
- 提供 systemd 部署示例，适合长期运行

## 部署效果示例

![部署效果示例](./deployment-demo.png)

## 安装

建议使用虚拟环境：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 配置

复制示例配置文件：

```bash
cp config.example.json config.json
```

`config.json` 格式：

```json
{
  "bot_token": "YOUR_BOT_TOKEN_HERE",
  "allowed_users": [123456789]
}
```

- `bot_token`: 从 [@BotFather](https://t.me/BotFather) 获取
- `allowed_users`: 允许使用的用户 ID 列表

获取用户 ID：向 Bot 发送 `/start`，未授权用户会收到自己的用户 ID。

默认情况下，Bot 会基于 `bot.py` 所在目录读取和写入文件，不依赖当前 shell 工作目录：

- 配置文件：`config.json`
- 保存数据：`passwords.json`

也可以通过环境变量覆盖路径，方便 systemd 按标准 Linux 目录部署：

```bash
BOT_CONFIG_FILE=/etc/random-generate-bot/config.json \
BOT_DATA_FILE=/var/lib/random-generate-bot/passwords.json \
python bot.py
```

## 本地运行

适合开发和测试：

```bash
python bot.py
```

如果要长期稳定运行，不建议直接把进程挂在终端里，请使用 systemd。

## systemd 部署

项目提供了 systemd 示例文件：

```text
deploy/systemd/random-generate-bot.service.example
```

一种推荐的部署目录结构：

```text
/opt/random_generate_bot                # 项目目录
/opt/random_generate_bot/.venv/bin/python
/etc/systemd/system/random-generate-bot.service
```

安装服务文件：

```bash
sudo cp deploy/systemd/random-generate-bot.service.example \
  /etc/systemd/system/random-generate-bot.service
sudo nano /etc/systemd/system/random-generate-bot.service
```

根据服务器实际情况修改：

- `WorkingDirectory`
- `ExecStart`
- `User`
- `Group`

启用并启动：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now random-generate-bot
sudo systemctl status random-generate-bot
```

查看实时日志：

```bash
sudo journalctl -u random-generate-bot -f
```

重启或停止服务：

```bash
sudo systemctl restart random-generate-bot
sudo systemctl stop random-generate-bot
```

示例服务使用 `Restart=on-failure`，因此异常退出会自动重启，但手动 `systemctl stop` 不会被立即拉起。

## 安全说明

- 不要提交真实 `config.json`，请使用 `config.example.json` 作为模板。
- `config.json` 包含 Telegram Bot Token。
- `passwords.json` 包含保存过的密码历史，属于敏感文件。
- 生产环境建议限制文件权限：

```bash
chmod 600 config.json passwords.json
```

- 如果需要保留密码历史，请定期备份 `passwords.json`。
- 如果真实 Bot Token 曾经进入 git 历史，建议到 BotFather 重新生成 token。

## 命令

- `/start` - 显示主界面
- `/list` - 查看保存的密码记录
- `/clear` - 清除所有记录
