import unittest
from unittest.mock import patch, MagicMock
import subprocess
import time
from collections import deque
import supervisor  # import ไฟล์ที่แก้แล้ว

class TestTerminateProcessFix(unittest.TestCase):
    """เทสบั๊ก 1: terminate_process ไม่ค้างเมื่อ process เป็น zombie"""

    @patch('supervisor.subprocess.Popen')
    def test_kill_then_wait_timeout(self, mock_popen):
        """จำลองกรณี proc.wait(timeout=5) หลัง kill แล้ว TimeoutExpired (zombie) — ต้องไม่ raise"""
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.terminate.return_value = None
        mock_proc.kill.return_value = None
        # จำลองว่า terminate แล้ว wait(timeout=10) timeout → ไป kill
        mock_proc.wait.side_effect = [
            subprocess.TimeoutExpired('terminate', 10),  # terminate wait timeout
            subprocess.TimeoutExpired('kill', 5)         # kill wait timeout (zombie)
        ]
        supervisor.terminate_process(mock_proc)
        # ต้องไม่ raise exception — ผ่าน

    @patch('supervisor.subprocess.Popen')
    def test_kill_then_process_gone(self, mock_popen):
        """จำลองกรณี process ตายไปแล้วก่อน wait หลัง kill — ต้องไม่ raise ProcessLookupError"""
        mock_proc = MagicMock()
        mock_proc.pid = 12346
        mock_proc.terminate.return_value = None
        mock_proc.kill.return_value = None
        mock_proc.wait.side_effect = [
            subprocess.TimeoutExpired('terminate', 10),  # terminate wait timeout
            ProcessLookupError()                          # process ตายไปแล้ว
        ]
        supervisor.terminate_process(mock_proc)
        # ต้องไม่ raise exception — ผ่าน

class TestRateLimitLogic(unittest.TestCase):
    """เทสบั๊ก 2: rate limit ทำงานถูกต้อง (ใช้ deque ไม่ใช่ตัวนับที่รีเซ็ต)"""

    def setUp(self):
        supervisor.restart_timestamps.clear()

    def test_rate_limit_not_exceeded(self):
        """restart น้อยกว่า MAX_RESTARTS — ต้องไม่ rate limited"""
        now = time.time()
        supervisor.restart_timestamps.extend([now - 100, now - 200])  # 2 ครั้งใน 1 ชม.
        self.assertFalse(supervisor._is_rate_limited())

    def test_rate_limit_exceeded(self):
        """restart เกิน MAX_RESTARTS — ต้อง rate limited"""
        now = time.time()
        timestamps = [now - i * 100 for i in range(supervisor.MAX_RESTARTS + 2)]  # 12 ครั้ง
        supervisor.restart_timestamps.extend(timestamps)
        self.assertTrue(supervisor._is_rate_limited())

    def test_old_timestamps_cleaned(self):
        """timestamp ที่เก่ากว่า window ต้องถูกลบออก"""
        now = time.time()
        old = now - supervisor.RATE_LIMIT_WINDOW - 100  # เก่าเกิน window
        recent = now - 100
        supervisor.restart_timestamps.extend([old, recent])
        supervisor._is_rate_limited()  # เรียกเพื่อ trigger cleanup
        self.assertEqual(len(supervisor.restart_timestamps), 1)
        self.assertAlmostEqual(supervisor.restart_timestamps[0], recent, delta=1)

if __name__ == '__main__':
    unittest.main()
