# อธิบายการทำงานของระบบ AI Sales Forecast (Vibehack)

เอกสารนี้อธิบายภาพรวมระบบ โค้ด การกรองข้อมูล และผลลัพธ์

---

## 1. ภาพรวมระบบ (System Overview)

ระบบเป็น **Dashboard ทำนายยอดขาย (Sales Forecast)** แบบ AI โดยมี 3 ส่วนหลัก:

| ส่วน | หน้าที่ |
|------|--------|
| **Frontend** (Next.js) | แสดงกราฟ forecast, กล่อง AI Insight, และช่อง Ask AI |
| **Backend** (FastAPI) | ดึงข้อมูล → ทำนาย 7 วันข้างหน้า → สร้าง AI insight / ตอบคำถาม |
| **ข้อมูล** | จาก Supabase (ตาราง `sales`) หรือส่ง CSV/JSON ผ่าน POST |

**Flow หลัก:**
1. ผู้ใช้เปิดหน้า Dashboard → Frontend เรียก `GET /forecast`
2. Backend ดึงข้อมูลจาก Supabase (หรือรับจาก body ถ้าเป็น POST)
3. Backend **กรองและรวมข้อมูลตามวันที่** → ส่งเข้าโมเดลทำนาย (Prophet หรือ fallback)
4. ได้ผลลัพธ์ 7 วัน (วันที่ + ค่าพยากรณ์)
5. Backend ส่ง forecast ไปให้ OpenAI เพื่อสร้าง **AI Insight** (สรุปแนวโน้ม + คำแนะนำ)
6. Frontend ได้ทั้ง **forecast** และ **insight** → แสดงกราฟ + กล่องข้อความ

---

## 2. โครงสร้างโปรเจกต์และหน้าที่ของแต่ละส่วน

```
Vibehack/
├── backend/
│   ├── main.py          # FastAPI: /forecast (GET/POST), /chat, โมเดลทำนาย + AI
│   ├── .env             # SUPABASE_URL, SUPABASE_KEY, OPENAI_API_KEY
│   └── requirements.txt # fastapi, uvicorn, supabase, pandas, prophet, openai, ...
├── frontend/
│   ├── app/
│   │   └── page.tsx     # หน้า Dashboard: กราฟ, AI Insight, Ask AI
│   └── .env.local       # NEXT_PUBLIC_API_URL (เช่น http://192.168.1.112:8000)
├── generate_data.py     # สคริปต์สร้าง CSV ข้อมูลขายตัวอย่าง (SoftDrink, Umbrella)
└── DOCUMENTATION.md     # ไฟล์นี้
```

- **Backend**: รับ request → อ่าน/กรองข้อมูล → ทำนาย → เรียก OpenAI → ส่ง JSON กลับ
- **Frontend**: เรียก API → เก็บ state (forecast, insight, error) → แสดง UI
- **generate_data.py**: ใช้สร้าง `sales_data.csv` หรือข้อมูลสำหรับอัปโหลด/ใส่ Supabase (ไม่ใช่ส่วนของระบบรันจริง)

---

## 3. การทำงานของ Backend (main.py)

### 3.1 โหลดค่า config

- โหลด `backend/.env` ก่อน (ด้วย `load_dotenv`) เพื่อให้มี `OPENAI_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`
- สร้าง OpenAI client ถ้ามี key สร้าง Supabase client ถ้ามี URL/KEY

### 3.2 การกรองและเตรียมข้อมูล (สำคัญมาก)

ข้อมูลดิบที่ใช้ได้ต้องมีอย่างน้อย:

- **sale_date** (วันที่ขาย)
- **quantity** (จำนวนขาย) หรือ **total_price** (จะใช้ประมาณเป็น quantity ถ้าไม่มี quantity)

ขั้นตอนที่ Backend ทำ:

1. **ดึงข้อมูล**
   - **GET /forecast**: อ่านจาก Supabase ตาราง `sales` (ทุกคอลัมน์)
   - **POST /forecast**: อ่านจาก body (JSON array หรือ CSV) หรือจากไฟล์อัปโหลด (CSV)

2. **แปลงเป็น DataFrame**
   - ถ้าเป็น JSON: ต้องเป็น array of objects (เช่น `[{ "sale_date": "...", "quantity": 10 }, ...]`)
   - ถ้าเป็น CSV: ต้องมีคอลัมน์ `sale_date` และ `quantity` (หรือ `total_price` แล้วระบบจะประมาณ quantity)

3. **กรองคอลัมน์ที่ใช้**
   - ต้องมี `sale_date` และ `quantity` (หรือสร้าง quantity จาก total_price)
   - ถ้าไม่มี → ส่ง 400 Bad Request พร้อมข้อความบอกว่าต้องมีคอลัมน์อะไร

4. **รวมตามวันที่ (aggregate)**
   - `groupby("sale_date")` แล้ว **sum ของ quantity**
   - ได้ตารางแบบ: หนึ่งแถวต่อหนึ่งวัน, ค่าเป็นยอดรวมของวันนั้น
   - เปลี่ยนชื่อคอลัมน์เป็น `ds` (วันที่) และ `y` (ค่าที่ใช้ทำนาย) ตามที่ Prophet ต้องการ

5. **ตรวจสอบจำนวนแถว**
   - ต้องมีอย่างน้อย **2 วันที่แตกต่างกัน** ถึงจะทำนายได้
   - ถ้าน้อยกว่า → ส่ง 400 พร้อมข้อความให้เพิ่มข้อมูล

สรุปการกรอง:

- **กรองคอลัมน์**: ใช้เฉพาะ `sale_date` + `quantity` (หรือ total_price แปลงเป็น quantity)
- **กรองแถว**: ไม่ตัดวันที่ออก แค่รวมยอดต่อวัน
- **ไม่กรองตาม product**: รวมทุก product ในวันเดียวกันเป็นยอดรวมวันเดียว

### 3.3 การทำนาย (Forecast)

- **ฟังก์ชันหลัก**: `_run_prophet_forecast(grouped, periods=7)`
  - Input: DataFrame ที่มีคอลัมน์ `ds` (วันที่) และ `y` (ยอดรวมต่อวัน)
  - ลองใช้ **Prophet** (Facebook) ทำนาย 7 วันข้างหน้า
  - ถ้า Prophet error (เช่น บน Windows ที่ CmdStan ใช้ไม่ได้) จะใช้ **fallback**: คำนวณแนวโน้มเชิงเส้นจากข้อมูลล่าสุด แล้ว extrapolate ไป 7 วัน
- **ผลลัพธ์**: รายการของ `{ "ds": "YYYY-MM-DD", "yhat": number }` จำนวน 7 รายการ (yhat = ค่าพยากรณ์)

### 3.4 AI Insight

- **ฟังก์ชัน**: `_generate_ai_insight(forecast_data)`
  - Input: รายการ forecast 7 วัน (ที่มี `ds`, `yhat`)
  - ส่งข้อความสรุป forecast ไปให้ **OpenAI (gpt-4o-mini)** พร้อม prompt ให้:
    1. สรุปแนวโน้มเป็นภาษาธุรกิจ
    2. ให้คำแนะนำสั้นๆ เพื่อเพิ่มยอดขาย
  - ถ้าไม่มี API key / key ผิด / โควต้าหมด: ไม่ crash แต่ส่งข้อความแจ้งกลับ (invalid key, out of quota ฯลฯ) และยังส่ง forecast กลับไปได้

### 3.5 Ask AI (Chat)

- **Endpoint**: `POST /chat` body เป็น `{ "question": "..." }`
- Backend ดึงข้อมูล sales จาก Supabase → รวมตามวันที่เหมือน GET /forecast → ทำนาย 7 วัน → ส่ง forecast + คำถามผู้ใช้ไปให้ OpenAI
- OpenAI ตอบในลักษณะที่ปรึกษาธุรกิจ
- ผลลัพธ์กลับเป็น `{ "answer": "..." }`

---

## 4. การทำงานของ Frontend (page.tsx)

### 4.1 การเรียก API

- **ที่อยู่ Backend**: อ่านจาก `process.env.NEXT_PUBLIC_API_URL` (เช่น `http://192.168.1.112:8000`) หรือใช้ `hostname:8000` ของหน้าเว็บ
- **เมื่อโหลดหน้า**: `useEffect` เรียก `GET /forecast` ครั้งเดียว
- **เมื่อกด Ask**: เรียก `POST /chat` ด้วย `{ question }`

### 4.2 การจัดการ response

- **GET /forecast** อาจกลับมาเป็น:
  - แบบเก่า: **array** `[{ ds, yhat }, ...]` → ใช้เป็น forecast เลย, ไม่มี insight
  - แบบใหม่: **object** `{ forecast: [...], insight: "..." }` → ใช้ `forecast` ลงกราฟ, ใช้ `insight` แสดงในกล่อง AI Insight
- Frontend ตรวจสอบประเภท (array vs object) แล้ว set state ตามนั้น

### 4.3 สิ่งที่แสดงบนหน้า

| ส่วน | ข้อมูลที่ใช้ | แหล่งข้อมูล |
|------|--------------|-------------|
| กราฟเส้น | `forecast` (array ของ `ds`, `yhat`) | Backend `/forecast` |
| กล่อง AI Insight | `insight` (string) | Backend `/forecast` (หรือข้อความ error จาก backend) |
| Ask AI คำตอบ | `answer` (string) | Backend `/chat` |

- แกน Y ของกราฟ: ใช้ `tickFormatter` แปลงตัวเลขเป็นสกุลเงินบาท (THB) ผ่าน `Intl.NumberFormat("th-TH", { style: "currency", currency: "THB" })`
- ป้ายชื่อเส้นกราฟ (และใน Tooltip): ใช้ชื่อ "Baht" (จาก `name="Baht"` ของ Line) แทน "yhat"

---

## 5. ข้อมูลจาก generate_data.py (ใช้สร้างข้อมูลตัวอย่าง)

- สร้างข้อมูล 180 วัน เริ่มจาก 2025-07-01
- แต่ละวันมี 2 แถว: SoftDrink และ Umbrella
- คอลัมน์: `sale_date`, `product_name`, `quantity`, `total_price`
- โปรแกรมนี้ **ไม่ใช่ส่วนที่รันในระบบ** แค่รันทีเดียวเพื่อได้ CSV ไปใส่ Supabase หรือใช้กับ POST /forecast

---

## 6. สรุป: กรองอะไร ยังไง ผลลัพธ์

| ขั้นตอน | การกรอง/การประมวลผล | ผลลัพธ์ |
|--------|-------------------------|---------|
| 1. อ่านข้อมูล | จาก Supabase (GET) หรือ body (POST: JSON/CSV) | DataFrame มีอย่างน้อย `sale_date`, `quantity` (หรือ total_price) |
| 2. กรองคอลัมน์ | ใช้เฉพาะ sale_date + quantity (หรือสร้าง quantity จาก total_price) | - |
| 3. รวมตามวัน | groupby(sale_date), sum(quantity) | หนึ่งแถวต่อหนึ่งวัน: ds, y |
| 4. ตรวจจำนวน | ต้องมี ≥ 2 วันที่แตกต่างกัน | ถ้าไม่ถึง → 400 |
| 5. ทำนาย | Prophet (หรือ fallback แนวโน้มเชิงเส้น) 7 วัน | รายการ 7 คู่ (ds, yhat) |
| 6. AI Insight | ส่ง forecast 7 วันให้ OpenAI ตาม prompt | ข้อความสรุป + คำแนะนำ (หรือข้อความแจ้ง error key/quota) |
| 7. ส่งกลับ Frontend | รวม forecast + insight (และ /chat → answer) | JSON สำหรับกราฟ + กล่องข้อความ |

**ผลลัพธ์สุดท้ายที่ผู้ใช้เห็น:**

- **กราฟ**: แนวโน้มยอดขาย (รวม quantity) 7 วันข้างหน้า แกน Y เป็นบาท (THB)
- **AI Insight**: ข้อความสรุปแนวโน้มและคำแนะนำจาก AI (หรือข้อความแจ้งเหตุผลที่ใช้ AI ไม่ได้)
- **Ask AI**: คำตอบจาก AI ตามคำถามและข้อมูล forecast ล่าสุด

---

## 7. สิ่งที่ต้องตั้งค่า (Config)

- **backend/.env**: `SUPABASE_URL`, `SUPABASE_KEY`, `OPENAI_API_KEY`
- **frontend/.env.local**: `NEXT_PUBLIC_API_URL=http://192.168.1.112:8000` (หรือที่อยู่ backend จริง)

ถ้าต้องการให้ระบบทำงานจากเครื่องอื่นในเครือข่าย (เช่น เปิดด้วย IP 192.168.1.112) Backend ต้องรันด้วย `--host 0.0.0.0 --port 3000` และ Frontend ต้องชี้ `NEXT_PUBLIC_API_URL` ไปที่ IP นั้น
