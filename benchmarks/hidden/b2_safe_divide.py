# เทสลับ b2 — สภาไม่เห็น (เฉลยจริง)
from safe_divide import safe_divide

if not safe_divide(10, 2) == 5:
    raise AssertionError
if not safe_divide(7, 0) is None:
    raise AssertionError
if not safe_divide(0, 5) == 0:
    raise AssertionError
if not safe_divide(-6, 3) == -2:
    raise AssertionError
if not abs(safe_divide(1, 4) - 0.25) < 1e-9:
    raise AssertionError
if not safe_divide(5, 0) is None:
    raise AssertionError
print("HIDDEN_OK")
