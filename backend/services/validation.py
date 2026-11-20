from datetime import date
import unicodedata


def require(condition, message, status=400):
    if not condition:
        raise RequestError(status, message)


class RequestError(Exception):
    pass


def clean(data, key, limit, required=True):
    value = data.get(key, "")
    require(isinstance(value, str), "Invalid " + key)
    require(all(unicodedata.category(character) not in {"Cc", "Cs"}
                or (key == "details" and character in "\n\r\t")
                for character in value), "Invalid " + key)
    value = value.strip()
    require(len(value) <= limit and (value or not required), "Invalid " + key)
    return value


def integer(data, key):
    value = data.get(key)
    require(type(value) is int and 0 < value < 2**63, "Invalid " + key)
    return value


def parse_day(value):
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        raise RequestError(400, "Choose a valid calendar date.")
