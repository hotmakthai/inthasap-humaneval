import unittest
from core.memory import _our_context, est_tokens, memory  # แก้: import memory จาก core

# ใช้ getattr เพื่อ fallback ค่า default หาก attribute ไม่มีใน core.memory
MAX_EACH = getattr(memory, 'MAX_EACH', 2000)
COMPRESS_AT = getattr(memory, 'COMPRESS_AT', 18)
KEEP_RECENT = getattr(memory, 'KEEP_RECENT', 6)

class TestOurContext(unittest.TestCase):
    def test_summary_text_length(self):
        """ทดสอบว่า summary_text มีความยาวตามที่คาด"""
        # สร้าง entries มากกว่า COMPRESS_AT (18) เพื่อ trigger การสร้าง summary
        entries = [("user", "hello world")] * 25
        result = _our_context(entries)
        
        # แยกส่วน summary และ recent
        lines = result.split("\n")
        summary_line = lines[0]
        recent_lines = lines[1:]
        
        # summary_line ควรเป็นข้อความจำลองยาว (ไม่ใช่ "[summary ~... tokens]")
        self.assertGreater(len(summary_line), 50, 
                          "summary_text ควรยาวพอสมควร ไม่ใช่ข้อความสั้นๆ")
        
        # ตรวจสอบว่า recent lines มี 6 บรรทัด (KEEP_RECENT = 6)
        self.assertEqual(len(recent_lines), 6,
                        "ควรมี recent lines 6 บรรทัด")
        
        # ตรวจสอบว่า est_tokens ของ summary_line ใกล้เคียง summary_tok
        # summary_tok = min(600, est_tokens(fmt(old)) // 4)
        # โดย old = 19 entries (25-6), แต่ละ entry "hello world" ~3 token
        # fmt(old) ~ 19 * (3 + 3) = 114 token → //4 = 28
        # ดังนั้น summary_tok = 28, summary_text = "x" * 112 → est_tokens = 112/4 = 28
        summary_tok_est = est_tokens(summary_line)
        self.assertAlmostEqual(summary_tok_est, 28, delta=5,
                              "summary_tok ควรใกล้เคียงค่าที่คำนวณ")

if __name__ == "__main__":
    unittest.main()
