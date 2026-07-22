# DEVIN TASK — สร้าง web/profile.html (หน้าเติมเงิน/ยอดเครดิต)

**ไฟล์ที่สร้างใหม่:** `web/profile.html`
**ห้ามแตะ:** `council_web.py` · `core/*` · `.env` · `terminal.html`
**backup:** ไม่จำเป็น (สร้างใหม่)

---

## Context

- กดปุ่ม `💳 ฿79.29` ใน terminal.html → `window.location.href='/profile'` → ปัจจุบัน 404 เพราะ `web/profile.html` ไม่มีไฟล์
- Backend ครบแล้วทุก endpoint ไม่ต้องแก้ council_web.py เลย

## Endpoints ที่ใช้ได้ (อ่าน code จริงก่อนเรียก)

| Endpoint | Method | ทำอะไร |
|---|---|---|
| `/api/me/credit` | GET | `{"credit_thb": 79.29, "username": "...", "display_name": "..."}` |
| `/api/topup/request` | POST `{"amount": 50}` | ส่งคำขอเติมเงิน → คืน `{"ok": true, "ref": "1234", "qr": "<base64>", "amount": 50}` |
| `/api/topup/mystatus` | GET | สถานะคำขอล่าสุด `{"status": "pending"/"approved"/"none", ...}` |
| `/api/topup/history` | GET | `{"history": [{id, amount, status, created_at}, ...]}` |

---

## UI ที่ต้องสร้าง

### Layout
- Header: ← กลับ (ไปที่ `/terminal`) + ชื่อหน้า "กระเป๋าเงิน"
- Section 1: **ยอดคงเหลือ** — ตัวเลขใหญ่ `฿79.29`
- Section 2: **เติมเงิน** — ปุ่มเติมเงินชัดเจน แยกออกมา (ไม่ซ่อน)
- Section 3: **ประวัติ** — รายการ topup history

### Section เติมเงิน (สำคัญที่สุด — แยกชัดเจน)

```
[ ฿50 ] [ ฿100 ] [ ฿200 ] [ ฿500 ]   ← ปุ่มจำนวนสำเร็จรูป
หรือพิมพ์จำนวน: [ ______ บาท ]
[ 🏧 ขอเติมเงิน ]                      ← ปุ่มหลัก
```

เมื่อกด "ขอเติมเงิน":
1. POST `/api/topup/request` พร้อม `{"amount": N}`
2. แสดง QR Code PromptPay (base64 image จาก `res.qr`)
3. แสดงเลขอ้างอิง `ref` ขนาดใหญ่ให้ชัดเจน
4. ข้อความ: "โอนแล้วรอ admin อนุมัติ (ปกติภายใน 24 ชม.)"

### Section ประวัติ

แสดง `/api/topup/history` เป็นตาราง:
```
วันที่          จำนวน    สถานะ
2026-07-20     ฿100     ✅ อนุมัติแล้ว
2026-07-18     ฿50      ⏳ รออนุมัติ
2026-07-15     ฿200     ❌ ปฏิเสธ
```

---

## สไตล์

- ใช้ CSS เดียวกับ terminal.html: dark theme (`#0d0f14` bg, `#8b5cf6` accent)
- ตัวเลขยอดเครดิต: font-size ใหญ่ (`2.5rem`) สี `#a78bfa`
- ปุ่ม "ขอเติมเงิน": สีม่วง เด่นชัด ไม่เล็ก
- Responsive: ใช้งานมือถือได้

---

## Definition of Done

รัน server แล้วเปิด `http://127.0.0.1:8091/profile` หรือกดปุ่ม `💳` ใน terminal ต้องเห็น:

- [ ] หน้าโหลดได้ ไม่ 404
- [ ] ยอดเครดิตปัจจุบันแสดงถูกต้อง
- [ ] ปุ่มจำนวนสำเร็จรูป (50/100/200/500) กดแล้วใส่ค่าในช่อง
- [ ] กด "ขอเติมเงิน" → QR + เลข ref ปรากฏ
- [ ] ประวัติรายการแสดงถูกต้อง
- [ ] ปุ่มกลับ `/terminal` ทำงาน

**ไม่ต้องเทสอัตโนมัติ** — หน้า HTML ทดสอบด้วยตาใน browser เพียงพอ
