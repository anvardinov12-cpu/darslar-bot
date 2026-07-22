# Darslar Eslatuvchi Telegram Bot (Multi-Group)

Ushbu bot guruhlar ochish, dars jadvallarini tuzish va obunachilarga darsdan oldin (1 kun, 12 soat, 6 soat, 1 soat va dars boshlanganda) O'zbekiston vaqti bilan avtomatik eslatmalar yuborish uchun mo'ljallangan.

---

## 🚀 Xususiyatlari:
1. **O'zbekiston vaqti (Asia/Tashkent / UTC+5):** Eslatmalar xatosiz va o'z vaqtida boradi.
2. **O'tib ketgan darslarni avto-o'chirish:** Vaqti o'tib bo me'yordan oshgan darslar bazada turmaydi, avtomatik tozalanadi.
3. **Xavfsiz va xususiy guruhlar:** Begona adminlar sizning guruhingizga dars qo'sha yoki uni o'chira olmaydi.
4. **Qulay interfeys:** Pastki menu tugmalari va qulay buyruqlar kiritish tizimi.

---

## 📌 Buyruqlar Ro'yxati

### 👤 Oddiy foydalanuvchilar uchun:
* `/start` - Botni ishga tushirish hamda guruh havolasi orqali kirilganda obuna bo'lish.
* `/lessons` - Siz obuna bo'lgan guruhlarning yaqin darslarini ko'rish.
* `/stop <guruh_id>` - Muayyan guruhdan obunani bekor qilish.
* `/help` - Yordam menyusi.

### 👑 Guruh egalari va Adminlar uchun:
* `/create_group <guruh_nomi>` - Yangi guruh va taklif havolasini (link) yaratish.
* `/my_groups` - Egalik qiladigan guruhlaringiz ro'yxati, havolalari va ID lari.
* `/edit_group <guruh_id> <yangi_nom>` - Guruh nomini o'zgartirish.
* `/delete_group <guruh_id>` - Guruh va unga tegishli barcha darslarni o'chirib tashlash.
* `/add_lessons <guruh_id>` - Guruhga yangi darslarni ommaviy qo'shish.
* `/delete_lesson <dars_id>` - Xato qo'shilgan darsni o'chirish.

---

## 📝 Dars Qo'shish Qoidasi (`/add_lessons`)

`/add_lessons` buyrug'idan keyin joy tashlab **bitta xabarda** darslarni quyidagi **5 qatordan iborat** shablon bilan yuborasiz:

`/add_lessons 1`
`O'qituvchi Ismi`
`Учитель`
`Dars Mavzusi`
`Fan Nomi`
`YYYY-MM-DD HH:MM`

### 💡 Misol:
```text
/add_lessons 1
Anvar Ahmad
Учитель
Tazkiya - Qalb kasalliklari
Aqida
2026-08-10 20:00
