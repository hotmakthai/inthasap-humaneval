# เทสลับ b3 — สภาไม่เห็น (เฉลยจริง)
from roman import int_to_roman
cases = {1: "I", 3: "III", 4: "IV", 9: "IX", 14: "XIV", 40: "XL",
         58: "LVIII", 90: "XC", 400: "CD", 900: "CM",
         1994: "MCMXCIV", 2023: "MMXXIII", 3999: "MMMCMXCIX"}
for n, r in cases.items():
    got = int_to_roman(n)
    if got != r:
        raise AssertionError(f"int_to_roman({n}) = {got!r} แต่ควรเป็น {r!r}")
print("HIDDEN_OK")
