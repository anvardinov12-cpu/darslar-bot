# Darslar Eslatma Boti

Bu bot foydalanuvchilarga darslar boshlanishidan oldin avtomatik eslatma yuboradi:
**1 kun, 12 soat, 6 soat, 1 soat oldin** va **dars boshlanganda**.

Bot **bir marta** yaratiladi va doim ishlab turadi — har oy yangi bot ochish shart
emas, shunchaki yangi darslarni qo'shib turasiz.

---

## 1-QADAM: Bot yaratish (5 daqiqa, bir martalik)

1. Telegram'da **@BotFather** ni toping va `/start` yozing
2. `/newbot` buyrug'ini yuboring
3. Botga nom bering (masalan: `Darslar Eslatma Bot`)
4. Username bering — oxiri `bot` bilan tugashi kerak (masalan: `darslarim_eslatma_bot`)
5. BotFather sizga **token** beradi — bunday ko'rinishda:
   `7123456789:AAHk3xxxxxxxxxxxxxxxxxxxxxxxxxxxx`
   **Bu tokenni saqlab qo'ying, hech kimga bermang.**

6. O'zingizning Telegram ID raqamingizni bilib oling: **@userinfobot** ga `/start`
   yozing — u sizga ID raqamingizni beradi (masalan: `123456789`). Bu sizni
   **admin** qiladi — faqat siz darslarni qo'sha olasiz.

---

## 2-QADAM: Botni joylashtirish (deploy)

Ikkita oson yo'l bor. **Railway** eng sodda va bepul boshlanadi.

### A) Railway orqali (tavsiya etiladi, brauzerdan, kodlash shart emas)

1. [railway.app](https://railway.app) saytida ro'yxatdan o'ting (GitHub akkaunt bilan kirish qulay)
2. Loyihadagi barcha fayllarni (bot.py, database.py, parser.py, requirements.txt,
   Procfile) o'z GitHub repository'ingizga yuklang
   - GitHub'da yangi repository yarating (masalan `darslar-bot`)
   - Fayllarni "Add file" → "Upload files" orqali yuklang
3. Railway'da **"New Project"** → **"Deploy from GitHub repo"** → repository'ingizni tanlang
4. Railway loyihani avtomatik aniqlaydi. **"Variables"** bo'limiga o'ting va qo'shing:
   - `BOT_TOKEN` = (BotFather bergan token)
   - `ADMIN_IDS` = (sizning Telegram ID raqamingiz)
5. **Deploy** tugmasini bosing — bir necha daqiqada bot ishga tushadi
6. Telegram'da botingizga `/start` yozib tekshiring

### B) O'z kompyuteringizda ishga tushirish (test qilish uchun)

```bash
# 1) Papkaga kiring
cd telegram_bot

# 2) Kerakli kutubxonalarni o'rnating
pip install -r requirements.txt

# 3) .env.example faylini .env deb nomlang va tokeningizni yozing
cp .env.example .env
# .env faylini oching va BOT_TOKEN, ADMIN_IDS ni to'ldiring

# 4) Botni ishga tushiring
python bot.py
```

**Eslatma:** kompyuteringizda ishga tushirsangiz, kompyuter o'chsa yoki dastur
yopilsa, bot ham to'xtaydi. Doim ishlashi uchun Railway kabi xizmat kerak.

---

## 3-QADAM: Darslarni qo'shish

Botga (admin sifatida) quyidagi formatda yozing — `/add_lessons` buyrug'idan keyin,
xuddi shu qatorda emas, **keyingi qatorlarga** darslarni joylashtiring:

```
/add_lessons
Анвар Ахмад
Учитель
Tazkiya - Qalb va Nafs kasalliklari (Anvar Ahmad Hazratlari)
Основы Ислама
2026-07-24 20:30
Анвар Ахмад
Учитель
Asoslar - Shariat va Aqiyda asoslari (Hasanxon Hazratlari)
Основы Ислама
2026-07-25 18:00
```

Har bir dars **aynan 5 qatordan** iborat bo'lishi kerak:
1. O'qituvchi ismi
2. "Учитель" so'zi (shunchaki belgi, bot buni o'qimaydi)
3. Dars nomi
4. Fan nomi
5. Sana va vaqt — aynan `YYYY-MM-DD SS:DD` formatida (masalan `2026-08-03 20:00`)

Istalgancha darsni bitta xabarda joylashtirishingiz mumkin — 20 ta, 50 ta, farqi yo'q.
Bot barchasini bir zumda qo'shib, nechta dars qo'shilganini yozib beradi.

---

## Boshqa buyruqlar

| Buyruq | Kim uchun | Nima qiladi |
|---|---|---|
| `/start` | Hammaga | Obuna bo'lish |
| `/stop` | Hammaga | Obunani bekor qilish |
| `/lessons` | Hammaga | Yaqin 20 ta darsni ko'rsatadi |
| `/help` | Hammaga | Yordam va format namunasi |
| `/add_lessons` | Faqat admin | Darslarni ommaviy qo'shish |
| `/delete_lesson <id>` | Faqat admin | Bitta darsni o'chirish |
| `/stats` | Faqat admin | Obunachilar va darslar soni |

---

## Tez-tez so'raladigan savollar

**Har oy yangi bot yaratishim kerakmi?**
Yo'q. Bot bir marta yaratiladi va doim ishlab turadi. Har oy shunchaki yangi
darslarni `/add_lessons` orqali qo'shib turasiz — eskisi ustiga qo'shiladi, hech
narsa o'chmaydi.

**Necha kishi obuna bo'la oladi?**
Cheklov yo'q — 10 kishi ham, 10 000 kishi ham obuna bo'la oladi, bot hammasiga
bir xilda xabar yuboradi.

**Eslatmalar aniq vaqtida keladimi?**
Ha, bot har daqiqada tekshirib turadi, shuning uchun eslatmalar bir daqiqalik
aniqlik bilan keladi.

**Agar bot biroz vaqt o'chib qolsa (masalan qayta ishga tushirilsa) nima bo'ladi?**
Yuborilgan eslatmalar bazada saqlanadi, shuning uchun qayta ishga tushganda
eski eslatmalar takror yuborilmaydi, faqat navbatdagilar to'g'ri vaqtida ketadi.
