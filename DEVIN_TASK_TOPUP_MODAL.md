# DEVIN TASK — เพิ่มปุ่ม "เติมเงิน" + Modal ใน terminal.html

**ไฟล์ที่แก้:** `web/terminal.html` เท่านั้น
**backup ก่อนแก้:** `web/terminal.html.bak_topup`
**ห้ามแตะ:** `council_web.py` · `web/profile.html` · `core/*` · `.env`

> ⚠️ `web/profile.html` มีอยู่แล้ว เป็นหน้าจำแนกหมวดงาน ห้ามแตะเด็ดขาด

---

## Context

บรรทัด 275 ใน terminal.html:
```html
<div class="tb-cost credit-display" id="costBadge"
     onclick="window.location.href='/profile'"
     title="ไปหน้าโปรไฟล์/เติมเงิน">💳 —</div>
```

ปัจจุบัน `onclick` พา user ออกไปหน้าอื่น — พ่อต้องการให้เพิ่มปุ่ม "เติมเงิน" ข้างๆ แทน กดแล้วเปิด modal ในหน้าเดิม

---

## งานที่ต้องทำ

### 1. เปลี่ยน costBadge — เอา onclick ออก

```html
<!-- เดิม -->
<div class="tb-cost credit-display" id="costBadge"
     onclick="window.location.href='/profile'"
     title="ไปหน้าโปรไฟล์/เติมเงิน">💳 —</div>

<!-- ใหม่ — เอา onclick ออก เพิ่มปุ่มข้างๆ -->
<div class="tb-cost credit-display" id="costBadge" title="ยอดเครดิตคงเหลือ">💳 —</div>
<button class="topup-btn" onclick="openTopupModal()" title="เติมเงิน">เติมเงิน</button>
```

### 2. CSS ปุ่มเติมเงิน (ใส่ใน `<style>`)

```css
.topup-btn {
  background: #7c3aed;
  color: #fff;
  border: none;
  border-radius: 6px;
  padding: 4px 10px;
  font-size: 12px;
  cursor: pointer;
  margin-left: 6px;
}
.topup-btn:hover { background: #6d28d9; }
```

### 3. Modal เติมเงิน (ใส่ก่อน `</body>`)

```html
<div id="topupModal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:9999;display:flex;align-items:center;justify-content:center">
  <div style="background:#1a1d27;border:1px solid #7c3aed;border-radius:12px;padding:28px;width:340px;max-width:95vw">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
      <b style="font-size:16px;color:#a78bfa">💳 เติมเงิน</b>
      <button onclick="closeTopupModal()" style="background:none;border:none;color:#888;font-size:20px;cursor:pointer">✕</button>
    </div>
    <!-- ยอดปัจจุบัน -->
    <div style="text-align:center;margin-bottom:16px">
      <div style="font-size:13px;color:#888">ยอดคงเหลือ</div>
      <div id="topupBalance" style="font-size:2rem;color:#a78bfa;font-weight:bold">฿—</div>
    </div>
    <!-- ปุ่มจำนวนสำเร็จรูป -->
    <div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap">
      <button onclick="setTopupAmt(50)"  class="amt-btn">฿50</button>
      <button onclick="setTopupAmt(100)" class="amt-btn">฿100</button>
      <button onclick="setTopupAmt(200)" class="amt-btn">฿200</button>
      <button onclick="setTopupAmt(500)" class="amt-btn">฿500</button>
    </div>
    <!-- ช่องกรอกเอง -->
    <input id="topupAmt" type="number" min="1" placeholder="หรือพิมพ์จำนวน (บาท)"
           style="width:100%;box-sizing:border-box;padding:8px;border-radius:6px;border:1px solid #333;background:#0d0f14;color:#eee;margin-bottom:12px">
    <!-- ปุ่มส่งคำขอ -->
    <button id="topupSubmitBtn" onclick="submitTopup()"
            style="width:100%;padding:10px;background:#7c3aed;color:#fff;border:none;border-radius:8px;font-size:15px;cursor:pointer;font-weight:bold">
      🏧 ขอเติมเงิน
    </button>
    <!-- QR + ref (ซ่อนก่อน) -->
    <div id="topupQRArea" style="display:none;text-align:center;margin-top:16px">
      <img id="topupQR" src="" style="width:200px;height:200px;border-radius:8px">
      <div style="margin-top:8px;font-size:13px;color:#888">เลขอ้างอิง</div>
      <div id="topupRef" style="font-size:1.5rem;font-weight:bold;color:#a78bfa;letter-spacing:4px"></div>
      <div style="margin-top:8px;font-size:12px;color:#888">โอนแล้วรอ admin อนุมัติ (ปกติภายใน 24 ชม.)</div>
    </div>
    <!-- ประวัติ -->
    <div style="margin-top:16px;border-top:1px solid #222;padding-top:12px">
      <div style="font-size:12px;color:#888;margin-bottom:6px">ประวัติการเติมเงิน</div>
      <div id="topupHistory" style="font-size:12px;color:#aaa;max-height:120px;overflow-y:auto"></div>
    </div>
  </div>
</div>
```

CSS เพิ่มเติม:
```css
.amt-btn {
  flex:1;min-width:60px;padding:6px;border-radius:6px;
  background:#2a2d3a;border:1px solid #444;color:#eee;cursor:pointer;
}
.amt-btn:hover { background:#7c3aed; }
```

### 4. JavaScript (ใส่ในกลุ่ม script เดิม)

```javascript
function openTopupModal() {
  document.getElementById('topupModal').style.display = 'flex';
  document.getElementById('topupQRArea').style.display = 'none';
  document.getElementById('topupAmt').value = '';
  // โหลดยอดคงเหลือ
  fetch('/api/me/credit').then(r => r.json()).then(d => {
    document.getElementById('topupBalance').textContent = '฿' + Number(d.credit_thb||0).toFixed(2);
  });
  // โหลดประวัติ
  fetch('/api/topup/history').then(r => r.json()).then(d => {
    var h = d.history || [];
    var icons = {approved:'✅',pending:'⏳',rejected:'❌',cancelled:'🚫'};
    document.getElementById('topupHistory').innerHTML = h.length
      ? h.slice(0,10).map(r =>
          '<div style="display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px solid #222">'
          + '<span>' + r.created_at.slice(0,10) + '</span>'
          + '<span>฿' + Number(r.amount).toFixed(0) + '</span>'
          + '<span>' + (icons[r.status]||'') + ' ' + r.status + '</span></div>'
        ).join('')
      : '<div style="color:#555">ยังไม่มีประวัติ</div>';
  });
}

function closeTopupModal() {
  document.getElementById('topupModal').style.display = 'none';
}

function setTopupAmt(n) {
  document.getElementById('topupAmt').value = n;
}

function submitTopup() {
  var amt = parseFloat(document.getElementById('topupAmt').value);
  if (!amt || amt <= 0) { alert('กรุณาระบุจำนวนเงิน'); return; }
  document.getElementById('topupSubmitBtn').disabled = true;
  document.getElementById('topupSubmitBtn').textContent = 'กำลังสร้าง QR…';
  fetch('/api/topup/request', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({amount: amt})
  }).then(r => r.json()).then(d => {
    document.getElementById('topupSubmitBtn').disabled = false;
    document.getElementById('topupSubmitBtn').textContent = '🏧 ขอเติมเงิน';
    if (!d.ok) { alert(d.error || 'เกิดข้อผิดพลาด'); return; }
    document.getElementById('topupQR').src = 'data:image/png;base64,' + d.qr;
    document.getElementById('topupRef').textContent = d.ref;
    document.getElementById('topupQRArea').style.display = 'block';
  }).catch(() => {
    document.getElementById('topupSubmitBtn').disabled = false;
    document.getElementById('topupSubmitBtn').textContent = '🏧 ขอเติมเงิน';
    alert('เชื่อมต่อ server ไม่ได้');
  });
}

// ปิด modal เมื่อกดนอก
document.getElementById('topupModal').addEventListener('click', function(e) {
  if (e.target === this) closeTopupModal();
});
```

---

## Definition of Done

เปิด `http://127.0.0.1:8091/terminal` แล้วทดสอบด้วยตา:

- [ ] มีปุ่ม "เติมเงิน" ข้างๆ ยอดเครดิต `💳 ฿79.29`
- [ ] กดปุ่ม → modal เปิดในหน้าเดิม (ไม่ redirect)
- [ ] ยอดเครดิตในกล่อง modal แสดงถูกต้อง
- [ ] กดปุ่ม ฿50/100/200/500 → ตัวเลขเข้าช่องอัตโนมัติ
- [ ] กด "ขอเติมเงิน" → QR + เลข ref ปรากฏ
- [ ] ประวัติแสดงรายการ
- [ ] กด ✕ หรือกดนอก modal → ปิด
- [ ] `web/profile.html` ไม่ถูกแตะ (ตรวจด้วย git diff)

---

## ห้ามทำ

- ห้ามแตะ `web/profile.html` เด็ดขาด (เป็นหน้าจำแนกหมวดงาน คนละเรื่อง)
- ห้ามแตะ `council_web.py` (backend ครบแล้ว)
- ห้ามแตะ `core/*` · `.env`
- ห้ามลบ backup
