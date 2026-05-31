from urllib.parse import urlparse


SUPPORTED_FORMATS = {
    "openai_chat_completion",
    "openai_response",
    "anthropic_message",
}
FORMAT_ALIASES = {"openai_chat": "openai_chat_completion"}


def require_text(value, field_name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name}不能为空")
    return value.strip()


def validate_password(password):
    if not isinstance(password, str) or password == "":
        raise ValueError("主密码不能为空")
    return password


def validate_url(value):
    url = require_text(value, "API端点")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("API端点必须是合法的 http 或 https 地址")
    return url.rstrip("/")


def normalize_formats(value):
    if isinstance(value, list):
        formats = [FORMAT_ALIASES.get(str(item).strip(), str(item).strip()) for item in value if str(item).strip()]
    elif isinstance(value, str):
        formats = [FORMAT_ALIASES.get(item.strip(), item.strip()) for item in value.split(",") if item.strip()]
    else:
        formats = []
    unknown = [item for item in formats if item not in SUPPORTED_FORMATS]
    if unknown:
        raise ValueError(f"不支持的API格式：{', '.join(unknown)}")
    if not formats:
        raise ValueError("至少需要选择一种API格式")
    return ",".join(dict.fromkeys(formats))


def parse_formats(value):
    if not value:
        return []
    return [FORMAT_ALIASES.get(item.strip(), item.strip()) for item in value.split(",") if item.strip()]


def mask_secret(value):
    if not value:
        return ""
    if len(value) <= 8:
        return value[:2] + "***"
    return value[:4] + "..." + value[-4:]
