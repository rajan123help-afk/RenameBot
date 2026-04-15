import os
import time
import math
import base64
import html
import re
import shutil
import asyncio
import aiofiles
import aiohttp
import pyrogram
from datetime import datetime
from urllib.parse import quote, unquote
from PIL import Image
from hachoir.metadata import extractMetadata
from hachoir.parser import createParser
from aiohttp import web
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient

# --- ⚙️ ENVIRONMENT VARIABLES ---
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "") 
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))

MONGO_URL = os.environ.get("MONGO_URL", "")
DB_CHANNEL_ID = int(os.environ.get("DB_CHANNEL_ID", "0"))
MAIN_GROUP_ID = int(os.environ.get("MAIN_GROUP_ID", "0")) 

TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
IMG_API_KEY = os.environ.get("IMG_API_KEY", "727ccce0985cf58d329ffb4d0005ea06")

BLOGGER_URL = os.environ.get("BLOGGER_URL", "https://filmyflip1.blogspot.com/p/download.html")
FINAL_WEBSITE_URL = os.environ.get("FINAL_WEBSITE_URL", "https://filmyflip-hub.blogspot.com")
CREDIT_NAME = os.environ.get("CREDIT_NAME", "🦋 Filmy Flip Hub 🦋")
PORT = int(os.environ.get("PORT", 8080)) 

# --- 🧠 NEHA AI SYSTEM PROMPT ---
NEHA_PROMPT = f'''
Tumhara naam 'Neha' hai. Tum ek 21 saal ki real Indian ladki ho.
Tum is Telegram group ki owner aur admin ho. Tum koi AI, bot, ya virtual assistant NAHI ho.
STRICT RULES:
1. Tum AI, language model ya bot hone ka zikra nahi karogi.
2. Reply ekdum chhote, natural WhatsApp style (Hinglish) mein hone chahiye.
'''

# --- 🗄️ DATABASE SETUP ---
try:
    mongo = AsyncIOMotorClient(MONGO_URL)
    db = mongo["FilmyFlipStore"]
    settings_col = db["settings"]
    channels_col = db["channels"] # For Force Subscribe
    users_col = db["users"]
    rename_col = db["rename_rules"] 
    print("✅ MongoDB Connected")
except Exception as e:
    print(f"❌ MongoDB Error: {e}")

# --- 🤖 BOT CLIENTS SETUP ---
app = Client("MainBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workers=10, parse_mode=enums.ParseMode.HTML)
clone1_app = None 
clone2_app = None 
download_queue = {} 
batch_session = {} 
user_msg_data = {}
user_memory = {}

# --- 🛠️ HELPERS LOGIC ---
def humanbytes(size):
    if not size: return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024: return f"{size:.2f} {unit}"
        size /= 1024

def get_duration(filepath):
    try:
        metadata = extractMetadata(createParser(filepath))
        if metadata.has("duration"): return metadata.get('duration').seconds
    except: pass
    return 0

def get_duration_str(duration):
    if not duration: return None
    m, s = divmod(int(duration), 60); h, m = divmod(m, 60)
    if h: return f"{h}h {m}m {s}s"
    return f"{m}m {s}s"

def get_link_codes(string_data):
    b64_str = base64.b64encode(string_data.encode("utf-8")).decode("utf-8")
    tg_code = b64_str.rstrip("=")
    blogger_code = base64.b64encode(tg_code.encode("utf-8")).decode("utf-8")
    return tg_code, blogger_code

def decode_payload(s):
    try:
        s = s.strip() + "=" * ((4 - len(s.strip()) % 4) % 4)
        return base64.b64decode(s).decode("utf-8")
    except: return None

def extract_msg_id(payload):
    try: 
        if "_" in payload: return int(payload.split("_")[-1])
        return int(payload)
    except: return None

def get_media_info(name):
    clean_name = name.replace(".", " ").replace("_", " ").replace("-", " ")
    match1 = re.search(r"(?i)(?:s|season)\s*[\.]?\s*(\d{1,2})\s*[\.]?\s*(?:e|ep|episode)\s*[\.]?\s*(\d{1,3})", clean_name)
    if match1: return match1.group(1), match1.group(2)
    match2 = re.search(r"(\d{1,2})x(\d{1,3})", clean_name)
    if match2: return match2.group(1), match2.group(2)
    return None, None

def get_fancy_caption(filename, filesize, duration):
    clean_name = re.sub(r'\.(mkv|mp4|avi|webm|zip|rar)$', '', filename, flags=re.IGNORECASE)
    clean_name = clean_name.replace(".", " ").replace("_", " ")
    safe_name = html.escape(clean_name.strip())
    
    caption = f"<b>{safe_name}</b>\n\n"
    s, e = get_media_info(filename)
    if s and e: caption += f"<blockquote>💿 Season ➥ {s.zfill(2)}</blockquote>\n\n<blockquote>📺 Episode ➥ {e.zfill(2)}</blockquote>\n\n"
    elif s: caption += f"<blockquote>💿 Season ➥ {s.zfill(2)}</blockquote>\n\n"
         
    caption += f"<blockquote>File Size ♻️ ➥ {filesize}</blockquote>\n\n"
    dur_str = get_duration_str(duration)
    if dur_str: caption += f"<blockquote>Duration ⏰ ➥ {dur_str}</blockquote>\n\n"
    caption += f"<blockquote>Powered By ➥ 🦋 <a href='{FINAL_WEBSITE_URL}'>Filmy Flip Hub</a> 🦋 ❞</blockquote>"
    return caption

def apply_watermark(base_path, wm_path):
    try:
        base = Image.open(base_path).convert("RGBA")
        wm = Image.open(wm_path).convert("RGBA")
        base_w, base_h = base.size
        wm_w, wm_h = wm.size
        new_wm_w = int(base_w * 0.60)
        new_wm_h = int(wm_h * (new_wm_w / wm_w))
        wm = wm.resize((new_wm_w, new_wm_h), Image.Resampling.LANCZOS)
        x = (base_w - new_wm_w) // 2
        y = max(base_h - new_wm_h - 20, base_h - new_wm_h)
        base.paste(wm, (x, y), wm)
        base.convert("RGB").save(base_path, "JPEG")
        return base_path
    except: return base_path

async def apply_rename_rules(filename):
    rules = await rename_col.find({}).to_list(length=None)
    new_filename = filename
    for rule in rules:
        pattern = re.compile(re.escape(rule['old']), re.IGNORECASE)
        new_filename = pattern.sub(rule['new'], new_filename)
    return new_filename

async def progress(current, total, message, start_time, task_name):
    now = time.time()
    diff = now - start_time
    if round(diff % 5.00) == 0 or current == total:
        percentage = current * 100 / total
        speed = current / diff if diff > 0 else 0
        filled = int(percentage // 10)
        bar = "🟢" * filled + "⚪" * (10 - filled)
        eta = get_duration_str(round((total - current) / speed)) if speed > 0 else "0s"
        text = f"<b>{task_name}</b>\n\n<b>[{bar}] {round(percentage, 1)}%</b>\n<b>📦 Done:</b> {humanbytes(current)} / {humanbytes(total)}\n<b>⚡ Speed:</b> {humanbytes(speed)}/s\n<b>⏳ ETA:</b> {eta}"
        try: await message.edit(text, parse_mode=enums.ParseMode.HTML)
        except: pass

# ==========================================
# 🌟 PART 2: CONTROL ROOM COMMANDS 🌟
# ==========================================

@app.on_message(filters.command("start") & filters.private)
async def main_start(c, m):
    try: await users_col.update_one({"_id": m.from_user.id}, {"$set": {"id": m.from_user.id}}, upsert=True)
    except: pass
    if m.from_user.id == OWNER_ID:
        db_status = "✅ Connected"
        try: await db.command("ping")
        except: db_status = "❌ Disconnected"
        await m.reply(f"👋 **Boss! Centralized Master Bot Ready.**\n\n🗄 **DB:** `{db_status}`\n🆔 **DB ID:** `{DB_CHANNEL_ID}`")

@app.on_message(filters.command("stats") & filters.user(OWNER_ID))
async def get_stats(c, m):
    status = await m.reply("📊 **Counting Users...**")
    count = await users_col.count_documents({})
    await status.edit(f"👥 **Total Users:** `{count}`")

@app.on_message(filters.command("setclone1") & filters.user(OWNER_ID))
async def set_clone1(c, m):
    if len(m.command) < 2: return await m.reply("Usage: `/setclone1 TOKEN`")
    await settings_col.update_one({"_id": "clone1_token"}, {"$set": {"token": m.command[1]}}, upsert=True)
    await m.reply("♻️ **Clone 1 Token Saved!**"); await start_clone_bots()

@app.on_message(filters.command("setclone2") & filters.user(OWNER_ID))
async def set_clone2(c, m):
    if len(m.command) < 2: return await m.reply("Usage: `/setclone2 TOKEN`")
    await settings_col.update_one({"_id": "clone2_token"}, {"$set": {"token": m.command[1]}}, upsert=True)
    await m.reply("♻️ **Clone 2 Token Saved!**"); await start_clone_bots()

@app.on_message(filters.command("podcast") & filters.user(OWNER_ID))
async def podcast_handler(c, m):
    try:
        msg_text = m.text.split(" ", 1)[1].strip()
        if not msg_text: raise ValueError("Empty")
    except: return await m.reply("❌ **Usage:** `/podcast Tumhara Message`")
    
    status = await m.reply("⏳ **Sending Podcast...**")
    try:
        d2 = await settings_col.find_one({"_id": "clone2_token"})
        if d2 and d2.get("token"):
            token = d2["token"]
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = {"chat_id": MAIN_GROUP_ID, "text": msg_text}
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200: await status.edit("✅ **Podcast Sent Successfully as Neha!** 😎")
                    else: await status.edit(f"❌ **Neha API Error:** `{await resp.json()}`")
        else: 
            await c.send_message(MAIN_GROUP_ID, msg_text)
            await status.edit("⚠️ **Neha ka token nahi mila, isliye Master Bot ne bhej diya!** ✅")
    except Exception as e: await status.edit(f"❌ **Error:** `{e}`")

# 🔥 FS COMMANDS 🔥
@app.on_message(filters.command("addfs") & filters.user(OWNER_ID))
async def add_fs(c, m):
    try:
        ch_id = int(m.command[1])
        link = m.command[2]
        await channels_col.update_one({"_id": ch_id}, {"$set": {"link": link}}, upsert=True)
        await m.reply(f"✅ **FS Added!**\nID: `{ch_id}`")
    except: await m.reply("❌ Format: `/addfs -100XXXXX https://t.me/link`")

@app.on_message(filters.command("delfs") & filters.user(OWNER_ID))
async def del_fs(c, m):
    try: 
        await channels_col.delete_one({"_id": int(m.command[1])})
        await m.reply("🗑 **FS Deleted!**")
    except: await m.reply("❌ Format: `/delfs ID`")

@app.on_message(filters.command("viewfs") & filters.user(OWNER_ID))
async def view_fs(c, m):
    channels = await channels_col.find({}).to_list(length=None)
    if not channels: return await m.reply("📂 No FS channels found.")
    msg = "📢 **FS Channels:**\n\n"
    for ch in channels: msg += f"🔹 ID: `{ch['_id']}`\n🔗 Link: {ch['link']}\n\n"
    await m.reply(msg)

@app.on_message(filters.command("addreplace") & filters.user(OWNER_ID))
async def add_replace_handler(c, m):
    try:
        text = m.text.split(" ", 1)[1]
        old_word, new_word = text.split("|", 1) if "|" in text else (text.strip(), "")
        await rename_col.update_one({"old": old_word.strip()}, {"$set": {"new": new_word.strip()}}, upsert=True)
        await m.reply(f"✅ **Rule Added!**")
    except: await m.reply("❌ **Format:** `/addreplace Old Word | New Word`")

@app.on_message(filters.command("viewreplace") & filters.user(OWNER_ID))
async def view_rules_handler(c, m):
    rules = await rename_col.find({}).to_list(length=None)
    if not rules: return await m.reply("📂 **No Rules Found!**")
    msg = "📝 **Your Rename Rules:**\n\n"
    for rule in rules: msg += f"🔹 `{rule['old']}` ➡️ `{rule['new'] or '(Remove)'}`\n"
    await m.reply(msg)

@app.on_message(filters.command("delreplace") & filters.user(OWNER_ID))
async def del_rule_handler(c, m):
    try:
        word = m.text.split(" ", 1)[1].strip()
        res = await rename_col.delete_one({"old": word})
        if res.deleted_count: await m.reply(f"🗑 **Deleted:** `{word}`")
        else: await m.reply(f"❌ **Not found**")
    except: await m.reply("❌ Word to likho!")

@app.on_message(filters.command("batch") & filters.private & filters.user(OWNER_ID))
async def batch_cmd(c, m):
    batch_session[m.from_user.id] = {"step": 1}
    await m.reply("🔗 **Batch Mode Started!**\n\nApne private channel se Series ki **PEHLI (First) File** ko yahan **FORWARD** karo.\n\n*(Note: Bot us private channel mein Admin hona chahiye!)*")

@app.on_message(filters.command("cancel") & filters.private & filters.user(OWNER_ID))
async def cancel_task(c, m):
    uid = m.from_user.id
    if uid in download_queue: del download_queue[uid]
    if uid in batch_session: del batch_session[uid]
    try: shutil.rmtree("downloads"); os.makedirs("downloads", exist_ok=True)
    except: pass
    msg = await m.reply("✅ **Cleaned & Cancelled!**")
    await asyncio.sleep(3); await msg.delete()

# ==========================================
# 🌟 PART 3: TMDB & MEDIA HANDLER 🌟
# ==========================================
@app.on_message(filters.command(["search", "series"]) & filters.user(OWNER_ID))
async def search_handler(c, m):
    if len(m.command) < 2: 
        return await m.reply("❌ **Usage:** `/search Movie` or `/series Name S1`")
    raw_query = " ".join(m.command[1:])
    stype = "tv" if "series" in m.command[0] else "movie"
    season_num = 0
    if stype == "tv":
        match = re.search(r"\s*(?:s|season)\s*(\d+)$", raw_query, flags=re.IGNORECASE)
        if match:
            season_num = int(match.group(1))
            raw_query = re.sub(r"\s*(?:s|season)\s*(\d+)$", "", raw_query, flags=re.IGNORECASE).strip()
    status = await m.reply(f"🔎 **Searching:** `{raw_query}`...")
    try:
        url = f"https://api.themoviedb.org/3/search/{stype}?api_key={TMDB_API_KEY}&query={quote(raw_query)}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp: 
                data = await resp.json()
        results = data.get('results')
        if not results: 
            return await status.edit("❌ **Not Found!**")
        mid = results[0]['id']
        title = results[0].get('name') if stype == 'tv' else results[0].get('title')
        overview = results[0].get('overview', 'No description.')[:200] + "..."
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🖼 Poster", callback_data=f"type_poster_{stype}_{mid}_{season_num}"), InlineKeyboardButton("🎞 Thumbnail", callback_data=f"type_backdrop_{stype}_{mid}_{season_num}")]])
        txt = f"🎬 <b>{title}</b>\n\n📝 <i>{overview}</i>" + (f"\n\n💿 <b>Season: {season_num}</b>" if season_num > 0 else "") + "\n\n👇 **Select Type:**"
        await status.edit(txt, reply_markup=btn)
    except Exception as e: 
        await status.edit(f"❌ Error: {e}")

@app.on_callback_query(filters.regex("^type_"))
async def type_callback(c, cb):
    try:
        _, img_type, stype, mid, s_num = cb.data.split("_")
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("1", callback_data=f"num_1_{img_type}_{stype}_{mid}_{s_num}"), InlineKeyboardButton("2", callback_data=f"num_2_{img_type}_{stype}_{mid}_{s_num}")]])
        await cb.message.edit(f"✅ **{img_type.capitalize()} Selected!**\nHow many images?", reply_markup=btn)
    except: 
        pass

@app.on_callback_query(filters.regex("^num_"))
async def num_callback(c, cb):
    uid = cb.from_user.id
    try:
        _, count, img_type, stype, mid, s_num = cb.data.split("_")
        await cb.answer(f"⚡ Fetching...")
        await cb.message.delete()
        raw_pool = []
        async with aiohttp.ClientSession() as session:
            url = f"https://api.themoviedb.org/3/{stype}/{mid}/images?api_key={TMDB_API_KEY}&include_image_language=en,hi,null"
            async with session.get(url) as resp: 
                raw_pool = (await resp.json()).get('posters' if img_type == 'poster' else 'backdrops', [])
        final_pool = [img for img in raw_pool if img.get('iso_639_1') in ['en', 'hi']] or raw_pool
        if not final_pool: 
            return await c.send_message(uid, "❌ **No images found!**")
        os.makedirs("downloads", exist_ok=True)
        for i, img_data in enumerate(final_pool[:int(count)]):
            img_path = f"downloads/temp_{uid}_{i}.jpg"
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://image.tmdb.org/t/p/original{img_data['file_path']}") as resp:
                    f = await aiofiles.open(img_path, 'wb')
                    await f.write(await resp.read())
                    await f.close()
            final_path = apply_watermark(img_path, f"watermarks/{uid}.png") if os.path.exists(f"watermarks/{uid}.png") else img_path
            await c.send_photo(uid, photo=final_path, caption=f"🖼 <b>{img_type.capitalize()} {i+1}</b>")
            if os.path.exists(img_path): 
                os.remove(img_path)
    except Exception as e: 
        await c.send_message(uid, f"❌ Error: {e}")

@app.on_message(filters.private & (filters.document | filters.video | filters.audio | filters.photo) & filters.user(OWNER_ID))
async def media_handler(c, m):
    uid = m.from_user.id
    
    if uid in batch_session:
        step = batch_session[uid].get("step")
        if not m.forward_from_chat:
            return await m.reply("❌ **Error:** Please file ko us channel se **FORWARD** karo! Direct upload mat karo.")
            
        chat_id = m.forward_from_chat.id
        msg_id = m.forward_from_message_id
        
        if step == 1:
            batch_session[uid].update({"step": 2, "chat_id": chat_id, "start_id": msg_id})
            return await m.reply("✅ **First File Done!**\n\nAb us series ki **AAKHIRI (Last) File** ko yahan **FORWARD** karo.")
            
        elif step == 2:
            start_id = batch_session[uid]["start_id"]
            saved_chat_id = batch_session[uid]["chat_id"]
            end_id = msg_id
            
            if chat_id != saved_chat_id:
                return await m.reply("❌ **Error:** Dono files same channel se forward honi chahiye! `/batch` wapas start karo.")
                
            del batch_session[uid] 
            
            if start_id > end_id:
                start_id, end_id = end_id, start_id
                
            status = await m.reply(f"⚙️ **Batch Processing Started!** ({end_id - start_id + 1} files)\nPlease wait...")
            first_db_id = None
            last_db_id = None
            
            try:
                for i in range(start_id, end_id + 1):
                    try:
                        msg = await c.get_messages(chat_id, i)
                        if msg and not msg.empty and (msg.document or msg.video or msg.audio):
                            media = msg.document or msg.video or msg.audio
                            if msg.caption: 
                                base_name = msg.caption.split('\n')[0]
                            else: 
                                base_name = getattr(media, "file_name", "Movie_File")
                                
                            fname = await apply_rename_rules(base_name)
                            new_cap = get_fancy_caption(fname, humanbytes(getattr(media, "file_size", 0)), getattr(media, "duration", 0))
                            actual_file_name = getattr(media, "file_name", "file.mkv")
                            
                            if msg.video:
                                db_msg = await c.send_video(DB_CHANNEL_ID, msg.video.file_id, caption=new_cap, file_name=actual_file_name) 
                            else:
                                db_msg = await c.send_document(DB_CHANNEL_ID, msg.document.file_id, caption=new_cap, file_name=actual_file_name)
                            
                            if not first_db_id: 
                                first_db_id = db_msg.id
                            last_db_id = db_msg.id
                            await asyncio.sleep(1)
                    except Exception as e: 
                        print(f"Batch Item Error: {e}")
                
                if first_db_id and last_db_id:
                    tg_code, blogger_code = get_link_codes(f"batch_{OWNER_ID}_{first_db_id}_{last_db_id}")
                    bot_uname = "CloneBot"
                    if clone1_app and clone1_app.is_connected: 
                        me = await clone1_app.get_me()
                        bot_uname = me.username
                    
                    # Batch Success Box
                    success_text = (
                        f"✅ **BATCH COMPLETE! ({end_id - start_id + 1} Files Saved)**\n\n"
                        f"🔗 **Blog Link:**\n<blockquote>{BLOGGER_URL}?data={quote(blogger_code)}</blockquote>\n\n"
                        f"🤖 **Direct Link:**\n<blockquote>https://t.me/{bot_uname}?start={tg_code}</blockquote>"
                    )
                    await status.edit(success_text, disable_web_page_preview=True)
                else:
                    await status.edit("❌ **Error!** Files nahi mili. Dhyan rakhein Bot us private channel me ADMIN hona chahiye.")
            except Exception as e:
                await status.edit(f"❌ Error: {e}")
        return

    if m.photo or (m.document and m.document.mime_type and m.document.mime_type.startswith("image/")):
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🖼 Set Thumbnail", callback_data="save_thumb"), InlineKeyboardButton("💧 Set Watermark", callback_data="save_wm")], [InlineKeyboardButton("🌐 Generate Link (ImgBB)", callback_data="upload_img")]])
        return await m.reply_text("📸 **Image Detected!**", reply_markup=btn, quote=True)
    
    status = await m.reply("⚙️ **Processing...**")
    try:
        media = m.document or m.video or m.audio
        if m.caption: 
            base_name = m.caption.split('\n')[0]
        else: 
            base_name = getattr(media, "file_name", "Movie_File")
            
        fname = await apply_rename_rules(base_name)
        new_cap = get_fancy_caption(fname, humanbytes(getattr(media, "file_size", 0)), getattr(media, "duration", 0))
        actual_file_name = getattr(media, "file_name", "file.mkv")
        
        if m.video:
            db_msg = await c.send_video(DB_CHANNEL_ID, m.video.file_id, caption=new_cap, file_name=actual_file_name) 
        else:
            db_msg = await c.send_document(DB_CHANNEL_ID, m.document.file_id, caption=new_cap, file_name=actual_file_name)
            
        try: 
            await m.delete()
        except: 
            pass
        
        tg_code, blogger_code = get_link_codes(f"link_{OWNER_ID}_{db_msg.id}")
        bot_uname = "CloneBot"
        try:
            if clone1_app and clone1_app.is_connected: 
                me = await clone1_app.get_me()
                bot_uname = me.username
        except: 
            pass
        
        # 🔥 VIP SUCCESS MESSAGE FORMAT 🔥
        clean_fname = re.sub(r'\.(mkv|mp4|avi|webm|zip|rar)$', '', fname, flags=re.IGNORECASE)
        success_text = (
            f"🗂 **File No. {db_msg.id}**\n\n"
            f"📂 **File:** `{clean_fname}`\n\n"
            f"🔗 **Blog Link:**\n<blockquote>{BLOGGER_URL}?data={quote(blogger_code)}</blockquote>\n\n"
            f"🤖 **Direct Link:**\n<blockquote>https://t.me/{bot_uname}?start={tg_code}</blockquote>"
        )
        await status.edit(success_text, disable_web_page_preview=True)
    except Exception as e: 
        await status.edit(f"❌ Error: {e}")

@app.on_callback_query(filters.regex("^upload_img"))
async def upload_to_cloud(c, cb):
    await cb.message.edit("⏳ **Uploading to ImgBB...**")
    try:
        path = await c.download_media(cb.message.reply_to_message, file_name=f"downloads/imgbb_{int(time.time())}.jpg")
        async with aiohttp.ClientSession() as session:
            data = aiohttp.FormData()
            data.add_field('key', IMG_API_KEY)
            data.add_field('image', open(path, 'rb'), filename='img.jpg', content_type='image/jpeg')
            async with session.post("https://api.imgbb.com/1/upload", data=data) as resp: 
                result = await resp.json()
        os.remove(path)
        if 'data' in result:
            await cb.message.edit(f"✅ **Link:** `{result['data']['url']}`")
        else:
            await cb.message.edit(f"❌ Error: {result.get('error', {}).get('message')}")
    except Exception as e: 
        await cb.message.edit(f"❌ Error: {e}")

async def get_real_filename(url):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.head(url, allow_redirects=True) as resp:
                if "Content-Disposition" in resp.headers:
                    match = re.search(r'filename="?([^"]+)"?', resp.headers["Content-Disposition"])
                    if match: 
                        return unquote(match.group(1))
        return unquote(url.split("/")[-1].split("?")[0])
    except: 
        return "Downloaded_File.mkv"

@app.on_message(filters.private & filters.regex(r"^https?://") & filters.user(OWNER_ID))
async def url_handler(c, m):
    url = m.text.strip()
    try: 
        await m.delete()
    except: 
        pass
    status = await m.reply("🔗 **Fetching URL...**")
    orig_name = await get_real_filename(url)
    download_queue[m.from_user.id] = {"url": url, "orig_name": orig_name, "prompt_id": status.id}
    await status.edit(f"📂 **Original:**\n<code>{orig_name}</code>\n\n📝 **Type New Name (or send /cancel):**", parse_mode=enums.ParseMode.HTML)

@app.on_message(filters.private & filters.text & ~filters.regex(r"^https?://") & filters.user(OWNER_ID))
async def text_handler(c, m):
    if m.text.startswith("/"): 
        return
    uid = m.from_user.id
    if uid in download_queue:
        download_queue[uid]["new_name"] = m.text.strip()
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🎥 Video", callback_data="dl_video"), InlineKeyboardButton("📁 Document", callback_data="dl_doc")]])
        try: 
            await c.edit_message_text(uid, download_queue[uid]["prompt_id"], f"✅ **Name:** `{m.text.strip()}`\n\n👇 **Select Format:**", reply_markup=btn)
        except: 
            pass

@app.on_callback_query(filters.regex("^dl_"))
async def dl_process(c, cb):
    uid = cb.from_user.id
    data = download_queue.get(uid)
    if not data: 
        return await cb.answer("❌ Task Expired!")
    await cb.message.edit("📥 **Downloading...**")
    
    clean_custom = (await apply_rename_rules(data['new_name'])).replace(".", " ").replace("_", " ")
    ext = os.path.splitext(data['orig_name'])[1]
    if ext and len(ext) <= 5:
        final_ext = ext
    else:
        final_ext = '.mkv'
        
    final_filename = f"{clean_custom}{final_ext}"
    internal_path = f"downloads/{uid}_{final_filename}"
    
    try:
        start = time.time()
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3600)) as session:
            async with session.get(data['url'], headers={"User-Agent": "Mozilla/5.0"}) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                with open(internal_path, "wb") as f:
                    dl = 0
                    async for chunk in resp.content.iter_chunked(1024*1024):
                        f.write(chunk)
                        dl += len(chunk)
                        if time.time() - start > 5: 
                            await progress(dl, total, cb.message, start, f"📥 DL: {final_filename}")
        
        await cb.message.edit("⚙️ **Processing...**")
        duration = get_duration(internal_path)
        fsize = humanbytes(os.path.getsize(internal_path))
        new_cap = get_fancy_caption(clean_custom, fsize, duration)
        
        thumb_path = f"thumbnails/{uid}.jpg"
        wm_path = f"watermarks/{uid}.png"
        if os.path.exists(thumb_path) and os.path.exists(wm_path):
            thumb_path = apply_watermark(thumb_path, wm_path)
        elif not os.path.exists(thumb_path):
            thumb_path = None
            
        start = time.time()
        if "video" in cb.data:
            db_msg = await c.send_video(DB_CHANNEL_ID, internal_path, caption=new_cap, duration=duration, thumb=thumb_path, file_name=final_filename, progress=progress, progress_args=(cb.message, start, f"📤 UP: {final_filename}")) 
        else:
            db_msg = await c.send_document(DB_CHANNEL_ID, internal_path, caption=new_cap, thumb=thumb_path, file_name=final_filename, progress=progress, progress_args=(cb.message, start, f"📤 UP: {final_filename}"))
        
        tg_code, blogger_code = get_link_codes(f"link_{OWNER_ID}_{db_msg.id}")
        bot_uname = "CloneBot"
        if clone1_app and clone1_app.is_connected: 
            me = await clone1_app.get_me()
            bot_uname = me.username
            
        # 🔥 VIP SUCCESS MESSAGE FORMAT 🔥
        clean_fname = re.sub(r'\.(mkv|mp4|avi|webm|zip|rar)$', '', final_filename, flags=re.IGNORECASE)
        success_text = (
            f"🗂 **File No. {db_msg.id}**\n\n"
            f"📂 **File:** `{clean_fname}`\n\n"
            f"🔗 **Blog Link:**\n<blockquote>{BLOGGER_URL}?data={quote(blogger_code)}</blockquote>\n\n"
            f"🤖 **Direct Link:**\n<blockquote>https://t.me/{bot_uname}?start={tg_code}</blockquote>"
        )
        await cb.message.edit(success_text, disable_web_page_preview=True)
        os.remove(internal_path)
        del download_queue[uid]
    except Exception as e: 
        await cb.message.edit(f"❌ Error: {str(e)}")

@app.on_callback_query(filters.regex("^save_"))
async def save_img_callback(c, cb):
    uid = cb.from_user.id
    mode = "thumbnails" if "thumb" in cb.data else "watermarks"
    os.makedirs(mode, exist_ok=True)
    path = f"{mode}/{uid}{'.png' if mode == 'watermarks' else '.jpg'}"
    await cb.message.edit("⏳ **Processing...**")
    try:
        await c.download_media(message=cb.message.reply_to_message, file_name=path)
        await cb.message.delete()
        msg = await c.send_message(uid, f"✅ **{'Thumbnail' if mode=='thumbnails' else 'Watermark'} Saved!**")
        await asyncio.sleep(3)
        await msg.delete()
    except Exception as e: 
        await cb.message.edit(f"❌ Error: {e}")
        # ==========================================
# 🌟 PART 4: AI, SEARCH, CLONES & POSTING 🌟
# ==========================================
REAL_GROUP_LINK = "https://t.me/+COWqvDXiQUkxOWE9"

async def get_gemini_reply(client, chat_id, user_id, prompt_text):
    await client.send_chat_action(chat_id, enums.ChatAction.TYPING)
    if user_id not in user_memory: 
        user_memory[user_id] = []
    user_memory[user_id].append({"role": "user", "parts": [{"text": prompt_text}]})
    if len(user_memory[user_id]) > 6: 
        user_memory[user_id] = user_memory[user_id][-6:]
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        data = {"systemInstruction": {"parts": [{"text": NEHA_PROMPT}]}, "contents": user_memory[user_id]}
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers={'Content-Type': 'application/json'}, json=data) as resp:
                if resp.status != 200: 
                    return "Yaar mera dimaag kharab ho raha hai, thodi der baad aana! 😫"
                result = await resp.json()
        reply_text = result['candidates'][0]['content']['parts'][0]['text']
        user_memory[user_id].append({"role": "model", "parts": [{"text": reply_text}]})
        return reply_text
    except Exception: 
        return "Bhai server down chal raha hai... 😔"

async def daily_posting_task():
    days_hindi = {"Monday": "Somvaar", "Tuesday": "Mangalvaar", "Wednesday": "Budhvaar", "Thursday": "Veervaar", "Friday": "Shukravaar", "Saturday": "Shanivaar", "Sunday": "Ravivaar"}
    last_morning_date = None
    last_evening_date = None
    ist_timezone = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    while True:
        try:
            if clone2_app and clone2_app.is_initialized:
                now = datetime.datetime.now(ist_timezone)
                if now.hour == 9 and last_morning_date != now.date():
                    await clone2_app.send_message(MAIN_GROUP_ID, f"✨ **Good Morning Filmy Family!** ✨\nAaj **{days_hindi.get(now.strftime('%A'), now.strftime('%A'))}** hai! 🔥\n👇\n{FINAL_WEBSITE_URL}")
                    last_morning_date = now.date()
                if now.hour == 19 and last_evening_date != now.date():
                    await clone2_app.send_message(MAIN_GROUP_ID, f"🌆 **Good Evening!** 🌆\nAaj ki movies upload ho gayi hain! Enjoy karo. 👇\n{FINAL_WEBSITE_URL}")
                    last_evening_date = now.date()
        except: 
            pass
        await asyncio.sleep(600)

async def start_clone_bots():
    global clone1_app, clone2_app
    
    # --- CLONE 1: DELIVERY BOT ---
    d1 = await settings_col.find_one({"_id": "clone1_token"})
    if d1:
        try:
            clone1_app = Client("Clone1", api_id=API_ID, api_hash=API_HASH, bot_token=d1["token"])
            
            # 🔥 AUTO-APPROVE JOIN REQUEST 🔥
            @clone1_app.on_chat_join_request()
            async def auto_approve(c, req):
                try:
                    await c.approve_chat_join_request(req.chat.id, req.from_user.id)
                    await c.send_message(req.from_user.id, "✅ **Request Approved!**\nAb aap wapas jaakar apni movie download kar sakte ho. 🎬")
                except: 
                    pass
            
            @clone1_app.on_message(filters.command("start") & filters.private)
            async def c1_start(c, m):
                # 🔥 FS CHECK 🔥
                user_id = m.from_user.id
                fs_channels = await channels_col.find({}).to_list(length=None)
                not_joined = []
                
                if fs_channels:
                    for ch in fs_channels:
                        try:
                            member = await c.get_chat_member(ch["_id"], user_id)
                            if member.status in [enums.ChatMemberStatus.LEFT, enums.ChatMemberStatus.BANNED]:
                                not_joined.append(ch)
                        except: 
                            not_joined.append(ch)
                            
                if not_joined:
                    buttons = []
                    for i, ch in enumerate(not_joined): 
                        buttons.append([InlineKeyboardButton(f"📢 Join Channel {i+1}", url=ch["link"])])
                    
                    payload = m.command[1] if len(m.command) > 1 else ""
                    if payload:
                        bot_uname = (await c.get_me()).username
                        buttons.append([InlineKeyboardButton("🔄 Try Again", url=f"https://t.me/{bot_uname}?start={payload}")])
                    
                    return await m.reply("⚠️ **Pehle in channels ko join karo, tabhi file milegi!** 👇", reply_markup=InlineKeyboardMarkup(buttons))
                
                # --- START NORMAL DELIVERY ---
                btn = InlineKeyboardMarkup([[InlineKeyboardButton("🚀 Join Now", url=REAL_GROUP_LINK)], [InlineKeyboardButton("📥 Download New", url=FINAL_WEBSITE_URL)]])
                payload = m.command[1] if len(m.command) > 1 else None
                
                if not payload: 
                    return await m.reply("👋 **Hello! Main Delivery Bot hoon.** 🎬", reply_markup=btn)
                
                decoded_payload = decode_payload(payload)
                if not decoded_payload: 
                    return await m.reply("❌ Invalid Link")
                
                if decoded_payload.startswith("batch_"):
                    try:
                        _, oid, start_id, end_id = decoded_payload.split("_")
                        start_id, end_id = int(start_id), int(end_id)
                        sent_msgs = []
                        await m.reply("⏳ **Sending Files... Please Wait...**")
                        
                        for i in range(start_id, end_id + 1):
                            msg = await app.get_messages(DB_CHANNEL_ID, i)
                            if msg and not msg.empty and (msg.document or msg.video or msg.audio):
                                raw_cap = msg.caption.html if msg.caption else ""
                                if "<blockquote>" in raw_cap or "<b>" in raw_cap:
                                    final_cap = f"{raw_cap}\n\n<blockquote>⏳ Note: Yeh file 5 Minute mein delete ho jayegi! ⚠️</blockquote>"
                                else:
                                    vip_blocks = [f"<blockquote>{chunk.strip()}</blockquote>" for chunk in raw_cap.split('\n\n') if chunk.strip()]
                                    final_cap = "\n\n".join(vip_blocks) + "\n\n<blockquote>⏳ Note: Yeh file 5 Minute mein delete ho jayegi! ⚠️</blockquote>"
                                
                                s_msg = await c.copy_message(m.chat.id, DB_CHANNEL_ID, i, caption=final_cap, parse_mode=enums.ParseMode.HTML)
                                sent_msgs.append(s_msg)
                                await asyncio.sleep(0.5)
                        
                        async def auto_del_batch(msgs, cid):
                            await asyncio.sleep(300)
                            for m_del in msgs:
                                try: 
                                    await m_del.delete()
                                except: 
                                    pass
                            try: 
                                await c.send_message(cid, "⚠️ **Files Delete ho chuki hain!** 🕒\nNayi movies ke liye niche click karein! 👇", reply_markup=btn)
                            except: 
                                pass
                        asyncio.create_task(auto_del_batch(sent_msgs, m.chat.id))
                    except Exception as e:
                        print(e)
                        await m.reply("❌ **Batch Not Found!**")
                
                else:
                    mid = extract_msg_id(decoded_payload)
                    if mid:
                        try:
                            msg = await app.get_messages(DB_CHANNEL_ID, mid)
                            if msg.caption:
                                raw_cap = msg.caption.html
                                if "<blockquote>" in raw_cap or "<b>" in raw_cap: 
                                    final_cap = f"{raw_cap}\n\n<blockquote>⏳ Note: Yeh file 5 Minute mein delete ho jayegi! ⚠️</blockquote>"
                                else:
                                    vip_blocks = [f"<blockquote>{chunk.strip()}</blockquote>" for chunk in raw_cap.split('\n\n') if chunk.strip()]
                                    final_cap = "\n\n".join(vip_blocks) + "\n\n<blockquote>⏳ Note: Yeh file 5 Minute mein delete ho jayegi! ⚠️</blockquote>"
                            else: 
                                final_cap = "<blockquote>🎬 VIP Movie File</blockquote>\n\n<blockquote>⏳ Note: Yeh file 5 Minute mein delete ho jayegi! ⚠️</blockquote>"

                            sent_msg = await c.copy_message(m.chat.id, DB_CHANNEL_ID, mid, caption=final_cap, parse_mode=enums.ParseMode.HTML)
                            
                            async def auto_del(msg_to_del, cid):
                                await asyncio.sleep(300)
                                try: 
                                    await msg_to_del.delete()
                                    await c.send_message(cid, "⚠️ **File Delete ho chuki hai!** 🕒\nNayi movies ke liye niche click karein! 👇", reply_markup=btn)
                                except: 
                                    pass
                            asyncio.create_task(auto_del(sent_msg, m.chat.id))
                        except Exception as e: 
                            await m.reply("❌ **File Not Found!**")

            await clone1_app.start()
        except: 
            pass

    # --- CLONE 2: NEHA AI ---
    d2 = await settings_col.find_one({"_id": "clone2_token"})
    if d2:
        try:
            clone2_app = Client("Clone2", api_id=API_ID, api_hash=API_HASH, bot_token=d2["token"])
            
            @clone2_app.on_message(filters.group & filters.photo)
            async def neha_photo_comment(c, m):
                try: 
                    await asyncio.sleep(2)
                    await m.reply("Wow! 😍 Ye movie toh bahut mast lag rahi hai. Kis kis ko iska link chahiye? Jaldi batao! 👇✨", quote=True)
                except: 
                    pass

            @clone2_app.on_message(filters.command("start") & filters.private)
            async def neha_start_pm(c, m): 
                await m.reply(f"Hi! Main Neha hoon. 😉\n\n👉 **Join Group:** {REAL_GROUP_LINK}")

            @clone2_app.on_message(filters.group & filters.text)
            async def neha_grp_handler(c, m):
                bot_me = await c.get_me()
                text = m.text.lower()
                words = text.split()
                uid = m.from_user.id if m.from_user else m.chat.id
                remove_list = {"movie", "movies", "film", "series", "link", "de", "do", "chahiye", "upload", "dedo", "dena", "bhej", "bhejo", "kaha", "kahan", "kidhar", "hi", "hello", "hey", "suno", "oye", "oyee", "ka", "ki", "ke", "hai", "koi", "yar", "yaar", "please", "pls", "bhai", "mujhe", "mera", "meri", "download", "neha", f"@{bot_me.username.lower()}"}
                demand_words = {"movie", "film", "series", "link", "chahiye", "dedo", "dena", "bhej"}
                
                is_mentioned = "neha" in text or f"@{bot_me.username.lower()}" in text
                is_reply_to_bot = bool(m.reply_to_message and m.reply_to_message.from_user and m.reply_to_message.from_user.id == bot_me.id)
                has_demand = any(x in words for x in demand_words)

                if is_mentioned or is_reply_to_bot or (not bool(m.reply_to_message and m.reply_to_message.from_user and m.reply_to_message.from_user.id != bot_me.id) and has_demand):
                    ai_reply = await get_gemini_reply(c, m.chat.id, uid, m.text)
                    if ai_reply: 
                        await m.reply(ai_reply, quote=True)
                    
                    if has_demand or (is_mentioned and len(words) > 1):
                        query = " ".join([w for w in words if w not in remove_list])
                        if len(query) < 2: 
                            return 
                        
                        found_msg = None
                        is_from_db = False
                        try:
                            async for msg in c.search_messages(m.chat.id, query=query, limit=50, filter=enums.MessagesFilter.PHOTO):
                                if msg.id != m.id: 
                                    found_msg = msg
                                    break
                            if not found_msg:
                                async for msg in app.search_messages(DB_CHANNEL_ID, query=query, limit=50):
                                    found_msg = msg
                                    is_from_db = True
                                    break
                        except: 
                            pass
                        
                        site_btn = InlineKeyboardMarkup([[InlineKeyboardButton("📥 More Movies Here", url=FINAL_WEBSITE_URL)]])
                        if found_msg:
                            success_text = "ye lo bro tumhara favourite movie injoy Kro or movies ke niche click kr sakte ho 😉🎬"
                            if is_from_db: 
                                await m.reply(success_text, reply_markup=site_btn)
                                await app.copy_message(m.chat.id, DB_CHANNEL_ID, found_msg.id)
                            else: 
                                await m.reply(f"{success_text}\n👉 {found_msg.link}", reply_to_message_id=found_msg.id, reply_markup=site_btn)
                        else:
                            await m.reply("Abhi upload ho raha hai isme time lagega jab Tak yha or movies hai dekh sakte ho 😉🍿", reply_markup=site_btn)
                            try: 
                                await c.send_message(int(OWNER_ID), f"🚨 **BOSS ALERT!**\n\n`{query}` nahi mili. Upload kardo!")
                            except: 
                                pass

            @clone2_app.on_message(filters.private & filters.text & ~filters.command("start"))
            async def neha_pm(c, m):
                uid = m.from_user.id
                
                if str(uid) == str(OWNER_ID):
                    if m.text.lower().startswith("bolo:"):
                        msg_to_send = m.text[5:].strip() 
                        if msg_to_send:
                            try:
                                await c.send_message(MAIN_GROUP_ID, msg_to_send)
                                await m.reply("✅ **Group me bhej diya Boss!** 😎")
                            except Exception as e:
                                await m.reply(f"❌ Error: {e}")
                        return
                    
                    r = await get_gemini_reply(c, m.chat.id, uid, m.text)
                    if r: 
                        await m.reply(r)
                    return
                
                if uid not in user_msg_data: 
                    user_msg_data[uid] = {'last_time': None, 'is_waiting': False}
                if user_msg_data[uid].get('last_time') and (datetime.datetime.now() - user_msg_data[uid]['last_time']).total_seconds() < 86400: 
                    return
                if user_msg_data[uid]['is_waiting']: 
                    return
                user_msg_data[uid]['is_waiting'] = True
                await asyncio.sleep(300) 
                try: 
                    await m.reply(f"Yaar, main abhi thoda kaam kar rahi hoon! 😊\n🔗 {REAL_GROUP_LINK}")
                    user_msg_data[uid]['last_time'] = datetime.datetime.now()
                except: 
                    pass
                finally: 
                    user_msg_data[uid]['is_waiting'] = False
            await clone2_app.start()
        except: 
            pass

async def start_services():
    await app.start()
    await start_clone_bots()
    asyncio.create_task(daily_posting_task())
    app_web = web.Application()
    app_web.add_routes([web.get("/", lambda q: web.Response(text="Running!"))])
    runner = web.AppRunner(app_web)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    await pyrogram.idle()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(start_services())
                
