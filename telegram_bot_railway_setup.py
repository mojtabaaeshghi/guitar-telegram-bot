import telegram
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
import sqlite3
from datetime import datetime, timedelta
import schedule
import time
import threading

# توکن بات خود را اینجا وارد کنید
TOKEN = "YOUR_BOT_TOKEN"

# اتصال به پایگاه داده SQLite
conn = sqlite3.connect("guitar_classes.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    phone TEXT,
    term_start TEXT,
    sessions_left INTEGER,
    allowed_absence INTEGER,
    paid_amount INTEGER,
    payment_account TEXT,
    payment_history TEXT
)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS classes (
    student_id INTEGER,
    date TEXT,
    time TEXT,
    location TEXT,
    attendance TEXT
)''')
conn.commit()

# دستور شروع
def start(update, context):
    update.message.reply_text("به بات مدیریت کلاس گیتار خوش آمدید!\nدستورات:\n/add_student - ثبت شاگرد\n/add_class - ثبت کلاس\n/check_attendance - حضور و غیاب")

# ثبت شاگرد
def add_student(update, context):
    msg = update.message.text.split()
    if len(msg) < 3:
        update.message.reply_text("لطفاً نام و شماره تلفن را وارد کنید: /add_student نام شماره")
        return
    name, phone = msg[1], msg[2]
    cursor.execute("INSERT INTO students (name, phone, term_start, sessions_left, allowed_absence, paid_amount, payment_account, payment_history) VALUES (?, ?, ?, 8, 1, 0, '', '')",
                   (name, phone, datetime.now().strftime("%Y-%m-%d")))
    conn.commit()
    update.message.reply_text(f"شاگرد {name} با موفقیت ثبت شد.")

# ثبت کلاس
def add_class(update, context):
    msg = update.message.text.split()
    if len(msg) < 5:
        update.message.reply_text("لطفاً اطلاعات کلاس را وارد کنید: /add_class نام_شاگرد تاریخ ساعت مکان")
        return
    name, date, time_, location = msg[1], msg[2], msg[3], msg[4]
    cursor.execute("SELECT id FROM students WHERE name=?", (name,))
    student_id = cursor.fetchone()
    if student_id:
        cursor.execute("INSERT INTO classes (student_id, date, time, location, attendance) VALUES (?, ?, ?, ?, 'pending')",
                       (student_id[0], date, time_, location))
        conn.commit()
        update.message.reply_text(f"کلاس برای {name} ثبت شد.")
    else:
        update.message.reply_text("شاگرد یافت نشد.")

# حضور و غیاب
def check_attendance(update, context):
    msg = update.message.text.split()
    if len(msg) < 3:
        update.message.reply_text("لطفاً نام و وضعیت را وارد کنید: /check_attendance نام حضور/غیاب_موجه/غیاب_غیرموجه")
        return
    name, status = msg[1], msg[2]
    cursor.execute("SELECT id, sessions_left, allowed_absence FROM students WHERE name=?", (name,))
    student = cursor.fetchone()
    if student:
        student_id, sessions_left, allowed_absence = student
        if status == "حضور":
            cursor.execute("UPDATE classes SET attendance='present' WHERE student_id=? AND date=?", (student_id, datetime.now().strftime("%Y-%m-%d")))
        elif status == "غیاب_موجه" and allowed_absence > 0:
            cursor.execute("UPDATE classes SET attendance='excused' WHERE student_id=? AND date=?", (student_id, datetime.now().strftime("%Y-%m-%d")))
            cursor.execute("UPDATE students SET allowed_absence=? WHERE id=?", (allowed_absence - 1, student_id))
        elif status == "غیاب_غیرموجه":
            cursor.execute("UPDATE classes SET attendance='absent' WHERE student_id=? AND date=?", (student_id, datetime.now().strftime("%Y-%m-%d")))
            cursor.execute("UPDATE students SET sessions_left=? WHERE id=?", (sessions_left - 1, student_id))
        conn.commit()
        update.message.reply_text(f"وضعیت {name} ثبت شد.")
    else:
        update.message.reply_text("شاگرد یافت نشد.")

# یادآور خودکار
def send_reminders():
    bot = telegram.Bot(TOKEN)
    now = datetime.now()
    cursor.execute("SELECT s.name, c.date, c.time, c.location FROM students s JOIN classes c ON s.id = c.student_id WHERE c.date=?", 
                   (now.strftime("%Y-%m-%d"),))
    classes = cursor.fetchall()
    for name, date, time_, location in classes:
        reminder_time = datetime.strptime(f"{date} {time_}", "%Y-%m-%d %H:%M") - timedelta(hours=1)
        if now >= reminder_time and now < datetime.strptime(f"{date} {time_}", "%Y-%m-%d %H:%M"):
            bot.send_message(chat_id="YOUR_CHAT_ID", text=f"یادآور: کلاس {name} امروز ساعت {time_} در {location}")

# زمان‌بندی یادآورها
def run_scheduler():
    schedule.every(10).minutes.do(send_reminders)
    while True:
        schedule.run_pending()
        time.sleep(1)

# راه‌اندازی بات
updater = Updater(TOKEN, use_context=True)
dp = updater.dispatcher
dp.add_handler(CommandHandler("start", start))
dp.add_handler(CommandHandler("add_student", add_student))
dp.add_handler(CommandHandler("add_class", add_class))
dp.add_handler(CommandHandler("check_attendance", check_attendance))

# اجرای زمان‌بندی در یک رشته جداگانه
threading.Thread(target=run_scheduler, daemon=True).start()

updater.start_polling()
updater.idle()
