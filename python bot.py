""" Full Advanced Telegram Bot (Python, aiogram) Features:

/start with referral tracking

/review -> generates review texts via OpenAI

/ask -> general Q&A powered by OpenAI

Referral earnings (balance), withdraw requests

Admin commands: /broadcast, /users, /refstats, /setprice, /withdraws

SQLite (aiosqlite) to persist data


Fill .env with: TELEGRAM_BOT_TOKEN=your_telegram_token OPENAI_API_KEY=your_openai_key ADMIN_IDS=123456789,987654321      # comma separated admin telegram user ids REF_BONUS=10                       # amount (units) credited per successful referral CURRENCY=BDT                        # optional label for currency

Run: python telegram_review_bot.py Requires: aiogram, aiosqlite, openai, python-dotenv

"""

import os import asyncio import logging from aiogram import Bot, Dispatcher, types from aiogram.contrib.fsm_storage.memory import MemoryStorage from aiogram.types import ParseMode from aiogram.dispatcher import FSMContext from aiogram.dispatcher.filters.state import State, StatesGroup from aiogram.utils import executor import aiosqlite from dotenv import load_dotenv import openai from datetime import datetime

load config

load_dotenv() TELEGRAM_BOT_TOKEN = os.getenv('8333558740:AAHoXqa8V0E-NAbYxbYU4y15yrBTQzr4QHc') OPENAI_API_KEY = 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 ADMIN_IDS = [int(x.strip()) for x in os.getenv('t.me/AfMdshakil','').split(',') if x.strip().isdigit()] REF_BONUS = float(os.getenv('REF_BONUS','10')) CURRENCY = os.getenv('CURRENCY','BDT')

if not TELEGRAM_BOT_TOKEN or not OPENAI_API_KEY: raise Exception("Please set TELEGRAM_BOT_TOKEN and OPENAI_API_KEY in .env")

openai.api_key = OPENAI_API_KEY

logging.basicConfig(level=logging.INFO) logger = logging.getLogger(name)

bot = Bot(token=TELEGRAM_BOT_TOKEN, parse_mode=ParseMode.HTML) storage = MemoryStorage() dp = Dispatcher(bot, storage=storage) DB_PATH = 'bot_data.db'

States for FSM

class ReviewStates(StatesGroup): waiting_for_details = State() waiting_for_count = State()

class AskStates(StatesGroup): waiting_for_question = State()

DB init

async def init_db(): async with aiosqlite.connect(DB_PATH) as db: await db.execute(''' CREATE TABLE IF NOT EXISTS users ( id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, referrer INTEGER, joined_at TEXT, balance REAL DEFAULT 0 ) ''') await db.execute(''' CREATE TABLE IF NOT EXISTS referrals ( id INTEGER PRIMARY KEY AUTOINCREMENT, referrer INTEGER, referee INTEGER, at TEXT ) ''') await db.execute(''' CREATE TABLE IF NOT EXISTS withdraws ( id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount REAL, method TEXT, note TEXT, status TEXT DEFAULT 'pending', requested_at TEXT ) ''') await db.commit()

Helpers

async def add_user(user: types.User, referrer: int | None): async with aiosqlite.connect(DB_PATH) as db: cur = await db.execute('SELECT id FROM users WHERE id = ?', (user.id,)) row = await cur.fetchone() if row: return False await db.execute('INSERT INTO users (id, username, first_name, referrer, joined_at) VALUES (?,?,?,?,?)', (user.id, user.username or '', user.first_name or '', referrer, datetime.utcnow().isoformat())) if referrer: # credit referrer await db.execute('INSERT INTO referrals (referrer, referee, at) VALUES (?,?,?)', (referrer, user.id, datetime.utcnow().isoformat())) await db.execute('UPDATE users SET balance = balance + ? WHERE id = ?', (REF_BONUS, referrer)) await db.commit() return True

async def get_user_count(): async with aiosqlite.connect(DB_PATH) as db: cur = await db.execute('SELECT COUNT(*) FROM users') r = await cur.fetchone() return r[0]

async def get_ref_stats(admin=False): async with aiosqlite.connect(DB_PATH) as db: cur = await db.execute('''SELECT u.id,u.username,u.first_name, COUNT(r.id) as refs, u.balance FROM users u LEFT JOIN referrals r ON u.id=r.referrer GROUP BY u.id ORDER BY refs DESC LIMIT 50''') rows = await cur.fetchall() return rows

OpenAI call (run in thread to avoid blocking)

async def openai_chat(prompt, system_prompt=None, max_tokens=300): def call(): messages = [] if system_prompt: messages.append({"role":"system","content":system_prompt}) messages.append({"role":"user","content":prompt}) res = openai.ChatCompletion.create(model='gpt-4o-mini', messages=messages, max_tokens=max_tokens, temperature=0.7) return res loop = asyncio.get_event_loop() res = await loop.run_in_executor(None, call) return res['choices'][0]['message']['content']

Handlers

@dp.message_handler(commands=['start']) async def cmd_start(message: types.Message): # check for referral parameter args = message.get_args() ref = None if args and args.isdigit(): ref = int(args) if ref == message.from_user.id: ref = None created = await add_user(message.from_user, ref) text = f"প্রিয় {message.from_user.first_name or ''}, স্বাগতম!\n\n" text += "এই বট দিয়ে তুমি রিভিউ টেক্সট জেনারেট করতে পারো এবং রেফারাল সিস্টেম থেকে আয় করতে পারো.\n" text += "কমান্ডগুলো: /review, /ask, /balance, /withdraw, /profile\n" # make invite link invite = f"https://t.me/{(await bot.get_me()).username}?start={message.from_user.id}" text += f"তোমার রেফারাল লিংক: <code>{invite}</code> (শেয়ার করো)\n" await message.reply(text)

@dp.message_handler(commands=['review']) async def cmd_review(message: types.Message): await ReviewStates.waiting_for_details.set() await message.reply("রিভিউ তৈরি করার জন্য অ্যাপ/প্রোডাক্টের নাম ও টোন (উদাহরণ: 'MyApp, professional, 15 words each') লিখুন:\n(নাম, টোন, প্রতিটি রিভিউয়ের শব্দসংখ্যা) — আপনি শুধু নাম লিখলেও হবে")

@dp.message_handler(state=ReviewStates.waiting_for_details) async def process_review_details(message: types.Message, state: FSMContext): text = message.text.strip() # parse simple: name[, tone][, words] parts = [p.strip() for p in text.split(',')] name = parts[0] tone = parts[1] if len(parts) > 1 else 'positive' words = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 20 await state.update_data(name=name, tone=tone, words=words) await message.reply('এখন কয়টা রিভিউ লাগবে লিখুন (উদাহরণ: 5)') await ReviewStates.next()

@dp.message_handler(state=ReviewStates.waiting_for_count) async def process_review_count(message: types.Message, state: FSMContext): try: count = int(message.text.strip()) except: await message.reply('সংখ্যা লিখুন, যেমন: 5') return data = await state.get_data() name = data['name'] tone = data['tone'] words = data['words'] await message.reply('রিভিউ তৈরি করা হচ্ছে... একটু অপেক্ষা করুন') # build prompt prompt = f"Generate {count} distinct {tone} review texts in Bengali for product/app named '{name}'. Each review about {words} words. No numbering, each on separate line." try: resp = await openai_chat(prompt, system_prompt='You are a helpful assistant generating short product reviews in Bengali.') except Exception as e: await message.reply('OpenAI তে সমস্যা হয়েছে: ' + str(e)) await state.finish() return await message.reply(resp) await state.finish()

@dp.message_handler(commands=['ask']) async def cmd_ask(message: types.Message): await AskStates.waiting_for_question.set() await message.reply('আপনার প্রশ্ন লিখুন — আমি OpenAI ব্যবহার করে উত্তর দিবো।')

@dp.message_handler(state=AskStates.waiting_for_question) async def process_ask(message: types.Message, state: FSMContext): q = message.text.strip() await message.reply('উত্তর তৈরি করা হচ্ছে...') try: resp = await openai_chat(q, system_prompt='You are a helpful assistant answering in Bengali where appropriate.') except Exception as e: await message.reply('OpenAI তে সমস্যা হয়েছে: ' + str(e)) await state.finish() return await message.reply(resp) await state.finish()

@dp.message_handler(commands=['balance']) async def cmd_balance(message: types.Message): async with aiosqlite.connect(DB_PATH) as db: cur = await db.execute('SELECT balance FROM users WHERE id = ?', (message.from_user.id,)) r = await cur.fetchone() bal = r[0] if r else 0 await message.reply(f'তোমার ব্যাল্যান্স: {bal} {CURRENCY}\nরেফারাল বোনাস প্রতি জন: {REF_BONUS} {CURRENCY}')

@dp.message_handler(commands=['withdraw']) async def cmd_withdraw(message: types.Message): parts = message.get_args() if not parts: await message.reply('উদাহরণ: /withdraw 100 bkash (নোটল: আপনার পেমেন্ট তথ্য লিখুন পাশাপাশি)') return try: tokens = parts.split() amount = float(tokens[0]) method = ' '.join(tokens[1:]) or 'unknown' except Exception: await message.reply('সঠিক ফরম্যাট ব্যবহার করুন: /withdraw <amount> <method>') return async with aiosqlite.connect(DB_PATH) as db: await db.execute('INSERT INTO withdraws (user_id, amount, method, note, status, requested_at) VALUES (?,?,?,?,?,?)', (message.from_user.id, amount, method, '', 'pending', datetime.utcnow().isoformat())) await db.commit() await message.reply('আপনার withdraw অনুরোধ দাখিল করা হয়েছে। অ্যাডমিন পর্যালোচনা করবেন।') # notify admins for aid in ADMIN_IDS: try: await bot.send_message(aid, f'নতুন withdraw অনুরোধ: User: {message.from_user.id}\nAmount: {amount} {CURRENCY}\nMethod: {method}') except Exception: pass

Admin commands

@dp.message_handler(commands=['users']) async def cmd_users(message: types.Message): if message.from_user.id not in ADMIN_IDS: await message.reply('You are not admin') return cnt = await get_user_count() await message.reply(f'Total users: {cnt}')

@dp.message_handler(commands=['refstats']) async def cmd_refstats(message: types.Message): if message.from_user.id not in ADMIN_IDS: await message.reply('You are not admin') return rows = await get_ref_stats() txt = '<b>Top Referrers</b>\n' for r in rows[:20]: uid, uname, fname, refs, balance = r txt += f"{fname or uname} (id:{uid}) — refs: {refs} — bal: {balance} {CURRENCY}\n" await message.reply(txt)

@dp.message_handler(commands=['broadcast']) async def cmd_broadcast(message: types.Message): if message.from_user.id not in ADMIN_IDS: await message.reply('You are not admin') return parts = message.get_args() if not parts: await message.reply('Use: /broadcast Your message here') return async with aiosqlite.connect(DB_PATH) as db: cur = await db.execute('SELECT id FROM users') rows = await cur.fetchall() count = 0 for row in rows: uid = row[0] try: await bot.send_message(uid, parts) count += 1 except Exception: pass await message.reply(f'Broadcast sent to {count} users')

@dp.message_handler(commands=['withdraws']) async def cmd_withdraws(message: types.Message): if message.from_user.id not in ADMIN_IDS: await message.reply('You are not admin') return async with aiosqlite.connect(DB_PATH) as db: cur = await db.execute('SELECT id,user_id,amount,method,status,requested_at FROM withdraws WHERE status = "pending"') rows = await cur.fetchall() if not rows: await message.reply('No pending withdraws') return txt = 'Pending withdraws:\n' for r in rows: txt += f'#{r[0]} user:{r[1]} amount:{r[2]} method:{r[3]} at:{r[5]}\n' await message.reply(txt)

fallback

@dp.message_handler() async def echo_all(message: types.Message): await message.reply('কমান্ড পাওয়া যায়নি। ব্যবহার করুন /review বা /ask বা /balance')

startup

async def on_startup(dp): await init_db() logger.info('Bot started')

if name == 'main': executor.start_polling(dp, on_startup=on_startup)
