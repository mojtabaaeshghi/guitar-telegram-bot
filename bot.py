import os
import sqlite3
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta
import logging

# تنظیم لاگ‌گذاری
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# اتصال به پایگاه داده SQLite
def init_db():
    conn = sqlite3.connect('guitar_classes.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS students (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    phone TEXT NOT NULL,
                    term_start TEXT,
                    sessions_left INTEGER,
                    excused_absence INTEGER DEFAULT 1,
                    location TEXT,
                    days TEXT,
                    time TEXT,
                    fee INTEGER,
                    paid INTEGER DEFAULT 0,
                    account TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS attendance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id INTEGER,
                    date TEXT,
                    present INTEGER,
                    FOREIGN KEY(student_id) REFERENCES students(id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id INTEGER,
                    amount INTEGER,
                    date TEXT,
                    account TEXT,
                    FOREIGN KEY(student_id) REFERENCES students(id))''')
    conn.commit()
    conn.close()

# تابع شروع بات
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('سلام! به بات مدیریت کلاس‌های گیتار خوش آمدید.\nدستورات:\n/register - ثبت شاگرد\n/class - ثبت کلاس\n/attendance - حضور و غیاب\n/payment - ثبت پرداخت\n/reminders - تنظیم یادآورها\n/report - گزارش هفتگی')

# ثبت شاگرد
async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 6:
        await update.message.reply_text('لطفاً اطلاعات را به این شکل وارد کنید:\n/register نام شماره_تلفن روز_شروع_ترم مکان روزها ساعت')
        return
    name, phone, term_start, location, days, time = args[:6]
    conn = sqlite3.connect('guitar_classes.db')
    c = conn.cursor()
    c.execute('INSERT INTO students (name, phone, term_start, sessions_left, location, days, time, fee) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
              (name, phone, term_start, 8, location, days, time, 800000))  # شهریه پیش‌فرض 800,000 تومان
    conn.commit()
    conn.close()
    await update.message.reply_text(f'شاگرد {name} با موفقیت ثبت شد.')

# ثبت حضور و غیاب
async def attendance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text('لطفاً اطلاعات را به این شکل وارد کنید:\n/attendance نام وضعیت (حاضر/غایب/غایب_موجه)')
        return
    name, status = args
    conn = sqlite3.connect('guitar_classes.db')
    c = conn.cursor()
    c.execute('SELECT id, sessions_left, excused_absence FROM students WHERE name=?', (name,))
    student = c.fetchone()
    if not student:
        await update.message.reply_text('شاگرد یافت نشد.')
        return
    student_id, sessions_left, excused_absence = student
    today = datetime.now().strftime('%Y-%m-%d')
    if status == 'حاضر':
        c.execute('INSERT INTO attendance (student_id, date, present) VALUES (?, ?, ?)', (student_id, today, 1))
    elif status == 'غایب':
        if sessions_left > 0:
            c.execute('UPDATE students SET sessions_left=? WHERE id=?', (sessions_left - 1, student_id))
    elif status == 'غایب_موجه' and excused_absence > 0:
        c.execute('UPDATE students SET excused_absence=? WHERE id=?', (excused_absence - 1, student_id))
    c.execute('INSERT INTO attendance (student_id, date, present) VALUES (?, ?, ?)', (student_id, today, 0 if status != 'حاضر' else 1))
    conn.commit()
    conn.close()
    await update.message.reply_text(f'وضعیت {name} به‌عنوان {status} ثبت شد.')

# ثبت پرداخت
async def payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 3:
        await update.message.reply_text('لطفاً اطلاعات را به این شکل وارد کنید:\n/payment نام مبلغ حساب (نقد/کارت)')
        return
    name, amount, account = args
    conn = sqlite3.connect('guitar_classes.db')
    c = conn.cursor()
    c.execute('SELECT id, paid, fee FROM students WHERE name=?', (name,))
    student = c.fetchone()
    if not student:
        await update.message.reply_text('شاگرد یافت نشد.')
        return
    student_id, paid, fee = student
    new_paid = paid + int(amount)
    c.execute('INSERT INTO payments (student_id, amount, date, account) VALUES (?, ?, ?, ?)', 
              (student_id, int(amount), datetime.now().strftime('%Y-%m-%d'), account))
    c.execute('UPDATE students SET paid=? WHERE id=?', (new_paid, student_id))
    conn.commit()
    conn.close()
    await update.message.reply_text(f'پرداخت {amount} تومان برای {name} در حساب {account} ثبت شد. مانده: {fee - new_paid} تومان')

# یادآورها
async def send_reminders(context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('guitar_classes.db')
    c = conn.cursor()
    c.execute('SELECT name, phone, days, time, sessions_left, fee, paid FROM students')
    students = c.fetchall()
    today = datetime.now().strftime('%A')
    for student in students:
        name, phone, days, time, sessions_left, fee, paid = student
        if today in days.split(','):
            await context.bot.send_message(chat_id=phone, text=f'یادآوری: امروز ساعت {time} کلاس گیتار دارید.')
        if sessions_left == 1:
            await context.bot.send_message(chat_id=phone, text=f'{name} عزیز، جلسه بعدی آخرین جلسه ترم شماست. لطفاً برای تمدید اقدام کنید.')
        if fee - paid > 0 and (datetime.now() + timedelta(days=2)).day == 1:
            await context.bot.send_message(chat_id=phone, text=f'یادآوری: شهریه شما {fee - paid} تومان باقی مانده است.')

# گزارش هفتگی
async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('guitar_classes.db')
    c = conn.cursor()
    c.execute('SELECT name, sessions_left, fee, paid FROM students')
    students = c.fetchall()
    report_text = 'گزارش هفتگی:\n'
    for student in students:
        name, sessions_left, fee, paid = student
        report_text += f'{name}: جلسات باقی‌مانده: {sessions_left}، مانده شهریه: {fee - paid} تومان\n'
    conn.close()
    await update.message.reply_text(report_text)

def main():
    init_db()
    token = os.getenv('TELEGRAM_TOKEN')
    application = Application.builder().token(token).build()

    # ثبت دستورات
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('register', register))
    application.add_handler(CommandHandler('attendance', attendance))
    application.add_handler(CommandHandler('payment', payment))
    application.add_handler(CommandHandler('report', report))

    # تنظیم یادآورها
    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_reminders, 'interval', hours=24, args=[application])
    scheduler.start()

    # شروع بات
    application.run_polling()

if __name__ == '__main__':
    main()