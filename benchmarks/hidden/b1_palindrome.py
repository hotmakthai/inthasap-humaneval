# เทสลับ b1 — สภาไม่เห็น (เฉลยจริง)
from palindrome import is_palindrome

def _check(condition, msg=None):
    if not condition:
        raise AssertionError(msg or "Assertion failed")

_check(is_palindrome("aba") is True)
_check(is_palindrome("abc") is False)
_check(is_palindrome("") is True)
_check(is_palindrome("a") is True)
_check(is_palindrome("A man a plan a canal Panama") is True)
_check(is_palindrome("Was it a car or a cat I saw") is True)
_check(is_palindrome("hello world") is False)
print("HIDDEN_OK")
