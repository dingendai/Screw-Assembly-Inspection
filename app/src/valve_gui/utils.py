import hashlib

DECISION_OPERATORS = ("<", ">", "=", "<=", ">=")


def hex_to_bgr(value):
    text = str(value).strip().lstrip("#")
    if len(text) != 6:
        text = "22c55e"
    try:
        red = int(text[0:2], 16)
        green = int(text[2:4], 16)
        blue = int(text[4:6], 16)
    except ValueError:
        red, green, blue = 34, 197, 94
    return blue, green, red


def decision_rule_key(slot, model_name):
    return f"{slot}::{model_name}"


def normalise_decision_operator(value, fallback=">="):
    operator = str(value).strip()
    return operator if operator in DECISION_OPERATORS else fallback


def compare_decision_value(actual, operator, expected):
    if operator == "<":
        return actual < expected
    if operator == ">":
        return actual > expected
    if operator == "=":
        return actual == expected
    if operator == "<=":
        return actual <= expected
    return actual >= expected


def hash_password(password: str) -> str:
    if not password:
        return ""
    return "sha256:" + hashlib.sha256(password.encode("utf-8")).hexdigest()


def verify_password(input_password: str, stored: str) -> bool:
    """Accepts both plain-text (legacy) and sha256-prefixed stored passwords."""
    if not stored:
        return True
    if stored.startswith("sha256:"):
        return hash_password(input_password) == stored
    return input_password == stored


def process_barcode_text(value, config) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if not getattr(config, "enabled", False):
        return text
    rules = list(getattr(config, "rules", []) or [])
    barcode_count = max(1, int(getattr(config, "barcode_count", len(rules) or 1)))
    if rules:
        rebuilt_parts = []
        cursor = 0
        for rule in rules[:barcode_count]:
            if not getattr(rule, "enabled", True):
                continue
            start_token = str(getattr(rule, "start_token", "")).strip()
            length = max(0, int(getattr(rule, "length", 0)))
            if not start_token or length <= 0:
                continue
            start_index = text.find(start_token, cursor)
            if start_index < 0:
                continue
            end_index = start_index + length
            if end_index > len(text):
                continue
            segment = text[start_index:end_index]
            rebuilt_parts.append(
                f"{getattr(rule, 'prefix', '')}{segment}{getattr(rule, 'suffix', '')}"
            )
            cursor = end_index
        if rebuilt_parts:
            return "".join(rebuilt_parts)
    trim_count = max(0, int(getattr(config, "trim_leading_chars", 0)))
    if trim_count:
        text = text[trim_count:]
    prefix = str(getattr(config, "prefix", ""))
    suffix = str(getattr(config, "suffix", ""))
    return f"{prefix}{text}{suffix}"
