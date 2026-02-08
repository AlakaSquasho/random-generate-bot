import os
import json
import secrets
import string
from datetime import datetime
from functools import wraps
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# 配置文件路径
CONFIG_FILE = "config.json"
DATA_FILE = "passwords.json"


def load_config() -> dict:
    """加载配置文件"""
    if not os.path.exists(CONFIG_FILE):
        print(f"Error: {CONFIG_FILE} not found")
        print("Please create config.json with the following format:")
        print(json.dumps({
            "bot_token": "YOUR_BOT_TOKEN_HERE",
            "allowed_users": [123456789]
        }, indent=2))
        exit(1)

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


# 加载配置
CONFIG = load_config()
ALLOWED_USERS = set(CONFIG.get("allowed_users", []))


def authorized_only(func):
    """装饰器：仅允许授权用户访问"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id not in ALLOWED_USERS:
            if update.callback_query:
                await update.callback_query.answer("⛔ 无权限访问", show_alert=True)
            else:
                await update.message.reply_text(
                    f"⛔ 无权限访问此Bot\n\n您的用户ID: `{user_id}`",
                    parse_mode="Markdown"
                )
            return
        return await func(update, context)
    return wrapper

# 默认字符集配置
DEFAULT_CHAR_SETS = {
    "lowercase": True,   # a-z
    "uppercase": True,   # A-Z
    "digits": True,      # 0-9
    "symbols": True,     # !@#$%
}

# 排除字符配置
DEFAULT_EXCLUSIONS = {
    "ambiguous": False,  # iIl10oO
}

# 字符集定义
CHAR_SETS = {
    "lowercase": string.ascii_lowercase,
    "uppercase": string.ascii_uppercase,
    "digits": string.digits,
    "symbols": "!@#$%",
}

# 易混淆字符
AMBIGUOUS_CHARS = "iIl10oO"


def load_data() -> dict:
    """加载保存的数据"""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"users": {}}


def save_data(data: dict):
    """保存数据"""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_user_config(user_id: str, data: dict) -> dict:
    """获取用户配置"""
    if user_id not in data["users"]:
        data["users"][user_id] = {
            "char_sets": DEFAULT_CHAR_SETS.copy(),
            "exclusions": DEFAULT_EXCLUSIONS.copy(),
            "saved_passwords": [],
        }
    return data["users"][user_id]


def generate_password(length: int, char_sets: dict, exclusions: dict) -> str:
    """生成密码"""
    chars = ""
    for key, enabled in char_sets.items():
        if enabled:
            chars += CHAR_SETS[key]

    if not chars:
        chars = string.ascii_lowercase

    if exclusions.get("ambiguous", False):
        for c in AMBIGUOUS_CHARS:
            chars = chars.replace(c, "")

    if not chars:
        return "Error: No characters available"

    return "".join(secrets.choice(chars) for _ in range(length))


def build_main_keyboard(user_config: dict) -> InlineKeyboardMarkup:
    """构建主键盘"""
    char_sets = user_config["char_sets"]
    exclusions = user_config["exclusions"]

    keyboard = [
        [InlineKeyboardButton("━━ 包含字符类型 ━━", callback_data="noop")],
        [
            InlineKeyboardButton(
                f"{'✅' if char_sets['lowercase'] else '❌'} a-z",
                callback_data="toggle_lowercase"
            ),
            InlineKeyboardButton(
                f"{'✅' if char_sets['uppercase'] else '❌'} A-Z",
                callback_data="toggle_uppercase"
            ),
        ],
        [
            InlineKeyboardButton(
                f"{'✅' if char_sets['digits'] else '❌'} 0-9",
                callback_data="toggle_digits"
            ),
            InlineKeyboardButton(
                f"{'✅' if char_sets['symbols'] else '❌'} !@#$%",
                callback_data="toggle_symbols"
            ),
        ],
        [InlineKeyboardButton("━━ 排除字符 ━━", callback_data="noop")],
        [
            InlineKeyboardButton(
                f"{'✅' if exclusions['ambiguous'] else '❌'} 排除 iIl10oO",
                callback_data="toggle_ambiguous"
            ),
        ],
        [InlineKeyboardButton("━━ 生成密码 ━━", callback_data="noop")],
        [
            InlineKeyboardButton("🔐 16位", callback_data="gen_16"),
            InlineKeyboardButton("🔐 20位", callback_data="gen_20"),
            InlineKeyboardButton("🔐 24位", callback_data="gen_24"),
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /start 命令"""
    user_id = update.effective_user.id

    # 未授权用户显示其ID以便添加
    if user_id not in ALLOWED_USERS:
        await update.message.reply_text(
            f"⛔ 无权限访问此Bot\n\n您的用户ID: `{user_id}`\n\n"
            f"请将此ID添加到配置文件的 allowed_users 中",
            parse_mode="Markdown"
        )
        return

    data = load_data()
    user_config = get_user_config(str(user_id), data)
    save_data(data)

    await update.message.reply_text(
        "🔑 **密码生成器**\n\n"
        "选择要包含的字符类型，然后点击生成按钮。\n"
        "生成的密码会自动保存，可通过 /list 查看历史记录。",
        reply_markup=build_main_keyboard(user_config),
        parse_mode="Markdown"
    )


@authorized_only
async def list_passwords(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /list 命令 - 显示保存的密码"""
    user_id = str(update.effective_user.id)
    data = load_data()
    user_config = get_user_config(user_id, data)

    saved = user_config.get("saved_passwords", [])

    if not saved:
        await update.message.reply_text("📭 暂无保存的密码记录")
        return

    text = "📋 **保存的密码记录**\n\n"
    for i, item in enumerate(saved[-10:], 1):
        text += f"{i}. `{item['password']}`\n"
        text += f"   📅 {item['time']} | 📏 {item['length']}位\n\n"

    if len(saved) > 10:
        text += f"_（仅显示最近10条，共{len(saved)}条）_"

    await update.message.reply_text(text, parse_mode="Markdown")


@authorized_only
async def clear_passwords(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /clear 命令 - 清除保存的密码"""
    user_id = str(update.effective_user.id)
    data = load_data()
    user_config = get_user_config(user_id, data)

    user_config["saved_passwords"] = []
    save_data(data)

    await update.message.reply_text("🗑️ 已清除所有保存的密码记录")


@authorized_only
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理按钮回调"""
    query = update.callback_query
    await query.answer()

    user_id = str(update.effective_user.id)
    data = load_data()
    user_config = get_user_config(user_id, data)

    callback_data = query.data

    if callback_data == "noop":
        return

    if callback_data.startswith("toggle_"):
        key = callback_data.replace("toggle_", "")
        if key in user_config["char_sets"]:
            user_config["char_sets"][key] = not user_config["char_sets"][key]
        elif key in user_config["exclusions"]:
            user_config["exclusions"][key] = not user_config["exclusions"][key]

        save_data(data)
        await query.edit_message_reply_markup(
            reply_markup=build_main_keyboard(user_config)
        )

    elif callback_data.startswith("gen_"):
        length = int(callback_data.replace("gen_", ""))
        password = generate_password(
            length,
            user_config["char_sets"],
            user_config["exclusions"]
        )

        user_config["saved_passwords"].append({
            "password": password,
            "length": length,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        })
        save_data(data)

        await query.message.reply_text(
            f"🔐 **生成的密码 ({length}位)**\n\n"
            f"`{password}`\n\n"
            f"_点击上方密码即可复制_",
            parse_mode="Markdown"
        )


def main():
    """主函数"""
    token = CONFIG.get("bot_token")
    if not token or token == "YOUR_BOT_TOKEN_HERE":
        print("Error: Please set bot_token in config.json")
        return

    if not ALLOWED_USERS:
        print("Warning: No allowed_users configured, bot will reject all requests")

    application = Application.builder().token(token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("list", list_passwords))
    application.add_handler(CommandHandler("clear", clear_passwords))
    application.add_handler(CallbackQueryHandler(button_callback))

    print("Bot is running...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
