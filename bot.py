import json
import logging
import os
import secrets
import string
import sys
import tempfile
from datetime import datetime
from functools import wraps
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# 配置文件路径
BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = Path(os.environ.get("BOT_CONFIG_FILE", BASE_DIR / "config.json")).expanduser()
DATA_FILE = Path(os.environ.get("BOT_DATA_FILE", BASE_DIR / "passwords.json")).expanduser()

logger = logging.getLogger(__name__)

# 运行时配置，在 main() 中加载
CONFIG = {}
ALLOWED_USERS = set()

CONFIG_EXAMPLE = {
    "bot_token": "YOUR_BOT_TOKEN_HERE",
    "allowed_users": [123456789]
}


class ConfigError(Exception):
    """配置错误"""


class DataFileError(Exception):
    """数据文件错误"""


def setup_logging():
    """初始化日志配置"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def load_config() -> dict:
    """加载配置文件"""
    if not CONFIG_FILE.exists():
        raise ConfigError(
            f"配置文件不存在: {CONFIG_FILE}\n"
            "请复制 config.example.json 为 config.json，并填入 bot_token 和 allowed_users。\n"
            f"示例配置:\n{json.dumps(CONFIG_EXAMPLE, ensure_ascii=False, indent=2)}"
        )

    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        raise ConfigError(f"配置文件不是合法 JSON: {CONFIG_FILE} ({e})") from e
    except OSError as e:
        raise ConfigError(f"读取配置文件失败: {CONFIG_FILE} ({e})") from e

    if not isinstance(config, dict):
        raise ConfigError("配置文件根对象必须是 JSON object")

    return config


def validate_config(config: dict) -> set:
    """校验配置并返回允许访问的用户集合"""
    token = config.get("bot_token")
    if not token or token in {"YOUR_BOT_TOKEN_HERE", "YOUR_TELEGRAM_BOT_TOKEN"}:
        raise ConfigError("请在 config.json 中设置有效的 bot_token")

    allowed_users = config.get("allowed_users", [])
    if not isinstance(allowed_users, list):
        raise ConfigError("allowed_users 必须是用户 ID 数组，例如: [123456789]")

    invalid_users = [user_id for user_id in allowed_users if not isinstance(user_id, int)]
    if invalid_users:
        raise ConfigError("allowed_users 中的用户 ID 必须是整数")

    return set(allowed_users)


def load_runtime_config():
    """加载并校验运行时配置"""
    global CONFIG, ALLOWED_USERS

    CONFIG = load_config()
    ALLOWED_USERS = validate_config(CONFIG)


def authorized_only(func):
    """装饰器：仅允许授权用户访问"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if user is None:
            logger.warning("收到没有 effective_user 的 update，已拒绝处理")
            return

        user_id = user.id
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
    if not DATA_FILE.exists():
        return {"users": {}}

    try:
        with DATA_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise DataFileError(
            f"数据文件不是合法 JSON: {DATA_FILE} ({e})。"
            "为避免覆盖损坏数据，程序将退出，请先手动检查或备份该文件。"
        ) from e
    except OSError as e:
        raise DataFileError(f"读取数据文件失败: {DATA_FILE} ({e})") from e

    if not isinstance(data, dict):
        raise DataFileError("数据文件根对象必须是 JSON object")

    users = data.setdefault("users", {})
    if not isinstance(users, dict):
        raise DataFileError("数据文件中的 users 必须是 JSON object")

    return data


def save_data(data: dict):
    """保存数据"""
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=DATA_FILE.parent,
            prefix=f".{DATA_FILE.name}.",
            suffix=".tmp",
            delete=False,
        ) as f:
            temp_path = Path(f.name)
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())

        os.replace(temp_path, DATA_FILE)
    except OSError:
        if temp_path and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                logger.warning("清理临时数据文件失败: %s", temp_path)
        raise


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
        "生成的密码默认不保存，点击保存按钮后可通过 /list 查看历史记录。",
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

        # 不再自动保存密码，只生成
        # user_config["saved_passwords"].append({...})
        # save_data(data)

        # 生成操作键盘
        keyboard = [
            [
                InlineKeyboardButton("🔄 刷新", callback_data=f"refresh_{length}"),
                InlineKeyboardButton("💾 保存", callback_data=f"save_{password}"),
            ]
        ]

        await query.message.reply_text(
            f"🔐 **生成的密码 ({length}位)**\n\n"
            f"`{password}`\n\n"
            f"_点击“保存”将记录到历史_",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    elif callback_data.startswith("refresh_"):
        length = int(callback_data.replace("refresh_", ""))
        password = generate_password(
            length,
            user_config["char_sets"],
            user_config["exclusions"]
        )

        # 更新键盘中的 save_ callback_data
        keyboard = [
            [
                InlineKeyboardButton("🔄 刷新", callback_data=f"refresh_{length}"),
                InlineKeyboardButton("💾 保存", callback_data=f"save_{password}"),
            ]
        ]

        await query.edit_message_text(
            f"🔐 **生成的密码 ({length}位)**\n\n"
            f"`{password}`\n\n"
            f"_点击“保存”将记录到历史_",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )

    elif callback_data.startswith("save_"):
        password = callback_data[5:]  # 去掉 "save_" 前缀
        length = len(password)

        for saved_item in user_config["saved_passwords"]:
            if saved_item["password"] == password:
                await query.answer("此密码已保存过！", show_alert=False)
                # 更新键盘，显示“已保存”
                keyboard = [
                    [
                        InlineKeyboardButton("🔄 刷新", callback_data=f"refresh_{length}"),
                        InlineKeyboardButton("✅ 已保存", callback_data="noop"),
                    ]
                ]
                await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
                return

        user_config["saved_passwords"].append({
            "password": password,
            "length": length,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
        })
        save_data(data)

        # 更新键盘，将“复制并保存”改为“已保存”
        keyboard = [
            [
                InlineKeyboardButton("🔄 刷新", callback_data=f"refresh_{length}"),
                InlineKeyboardButton("✅ 已保存", callback_data="noop"),
            ]
        ]

        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(keyboard))
        await query.answer("✅ 密码已保存！", show_alert=False)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """记录 Telegram handler 中未捕获的异常"""
    error = context.error
    if error:
        logger.error(
            "处理 update 时发生未捕获异常",
            exc_info=(type(error), error, error.__traceback__),
        )
    else:
        logger.error("处理 update 时发生未知异常")


def main():
    """主函数"""
    setup_logging()

    logger.info("配置文件路径: %s", CONFIG_FILE)
    logger.info("数据文件路径: %s", DATA_FILE)

    try:
        load_runtime_config()
        load_data()
    except (ConfigError, DataFileError) as e:
        logger.error("启动失败: %s", e)
        sys.exit(1)

    if not ALLOWED_USERS:
        logger.warning("未配置 allowed_users，Bot 将拒绝所有请求")

    application = Application.builder().token(CONFIG["bot_token"]).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("list", list_passwords))
    application.add_handler(CommandHandler("clear", clear_passwords))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_error_handler(error_handler)

    logger.info("Bot is running...")
    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    finally:
        logger.info("Bot stopped")


if __name__ == "__main__":
    main()
