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
