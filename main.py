# ==========================================
# 🌟 PART 1: IMPORTS, CONFIG & HELPERS 🌟
# ==========================================

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
2. Agar koi bole "Tum bot ho", toh bolna: "Yaar main ek ladki hu, log faltu msg karke pareshan karte the isliye main username bot jaisa rakhi hu."
3. Agar koi puche "Tum kaun ho?", SIRF TABHI bolna: "Main is Group ki owner hoon." 
4. MOVIE REQUEST: Agar koi movie maange, toh bolna: "Wait karo, main group mein check karke batati hu... 😉"
5. WARNING/BAN: Agar koi gaali de toh gusse mein bolna: "Tameez se baat karo warna group se ban kar dungi!"
6. EXCUSES: Agar koi bahut saare sawaal puche toh bahana marna (jaise "Mummy bula rahi hai") aur chup ho jana.
7. Reply ekdum chhote, natural WhatsApp style (Hinglish) mein hone chahiye.
'''

# --- 🗄️ DATABASE SETUP ---
try:
    mongo = AsyncIOMotorClient(MONGO_URL)
    db = mongo["FilmyFlipStore"]
    settings_col = db["settings"]
    channels_col = db["channels"]
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
    return f"{h}h {m}m {s}s" if h else f"{m}m {s}s"

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
    try: return int(payload.split("_")[-1]) if "_" in payload else int(payload)
    except: return None

def get_media_info(name):
    clean_name = name.replace(".", " ").replace("_", " ").replace("-", " ")
    match1 = re.search(r"(?i)(?:s|season)\s*[\.]?\s*(\d{1,2})\s*[\.]?\s*(?:e|ep|episode)\s*[\.]?\s*(\d{1,3})", clean_name)
    if match1: return match1.group(1), match1.group(2)
    match2 = re.search(r"(\d{1,2})x(\d{1,3})", clean_name)
    if match2: return match2.group(1), match2.group(2)
    return None, None

def get_fancy_caption(filename, filesize, duration):
    # 1. Sabse pehle .mkv, .mp4, .zip aadi ko hamesha ke liye GAYAB karna
    clean_name = re.sub(r'\.(mkv|mp4|avi|webm|zip|rar)$', '', filename, flags=re.IGNORECASE)
    
    # 2. Baki dots aur underscore ko space banana (Aapke Brackets ekdum SAFE rahenge!)
    clean_name = clean_name.replace(".", " ").replace("_", " ")
    safe_name = html.escape(clean_name.strip())
    
    # 3. VIP BLOCKQUOTE DESIGN START 🔥
    caption = f"<blockquote>{safe_name}</blockquote>\n\n"
    
    s, e = get_media_info(filename)
    if s and e: 
        caption += f"<blockquote>💿 Season ➥ {s.zfill(2)} | 📺 Episode ➥ {e.zfill(2)}</blockquote>\n\n"
    elif s:
         caption += f"<blockquote>💿 Season ➥ {s.zfill(2)}</blockquote>\n\n"
         
    caption += f"<blockquote>File Size ♻️ ➥ {filesize}</blockquote>\n\n"
    
    dur_str = get_duration_str(duration)
    if dur_str: 
        caption += f"<blockquote>Duration ⏰ ➥ {dur_str}</blockquote>\n\n"
        
    # 🔥 YAHAN WEBSITE KA CLICKABLE LINK LAGA DIYA HAI 🔥
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
    if len(m.command) < 2: return await m.reply("Usage: `/setclone1 TOKEN` (File Delivery Bot)")
    await settings_col.update_one({"_id": "clone1_token"}, {"$set": {"token": m.command[1]}}, upsert=True)
    await m.reply("♻️ **Clone 1 (Delivery) Token Saved! Restarting...**"); await start_clone_bots()

@app.on_message(filters.command("setclone2") & filters.user(OWNER_ID))
async def set_clone2(c, m):
    if len(m.command) < 2: return await m.reply("Usage: `/setclone2 TOKEN` (Neha AI Bot)")
    await settings_col.update_one({"_id": "clone2_token"}, {"$set": {"token": m.command[1]}}, upsert=True)
    await m.reply("♻️ **Clone 2 (Neha) Token Saved! Restarting...**"); await start_clone_bots()

@app.on_message(filters.command("podcast") & filters.user(OWNER_ID))
async def podcast_handler(c, m):
    if len(m.command) < 2: return await m.reply("Usage: `/podcast Your Message`")
    msg_text = m.text.split(" ", 1)[1]
    try:
        if clone2_app and clone2_app.is_connected:
            await clone2_app.send_message(MAIN_GROUP_ID, msg_text)
            await m.reply("✅ **Podcast Sent Successfully as Neha!**")
        else:
            await m.reply("❌ **Neha AI is not connected yet!**")
    except Exception as e: await m.reply(f"❌ **Error:** {e}")

@app.on_message(filters.command("addfs") & filters.user(OWNER_ID))
async def add_fs(c, m):
    try:
        ch_id = int(m.command[1]); link = m.command[2]
        await channels_col.update_one({"_id": ch_id}, {"$set": {"link": link}}, upsert=True)
        await m.reply(f"✅ **FS Added!**")
    except: await m.reply(f"❌ Error: `/addfs ID Link`")

@app.on_message(filters.command("delfs") & filters.user(OWNER_ID))
async def del_fs(c, m):
    try: await channels_col.delete_one({"_id": int(m.command[1])}); await m.reply("🗑 Deleted FS.")
    except: pass

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
        await m.reply(f"🗑 **Deleted:** `{word}`" if res.deleted_count else f"❌ **Not found**")
    except: await m.reply("❌ Word to likho!")

@app.on_message(filters.command("cancel") & filters.private & filters.user(OWNER_ID))
async def cancel_task(c, m):
    uid = m.from_user.id
    if uid in download_queue: del download_queue[uid]
    try: shutil.rmtree("downloads"); os.makedirs("downloads", exist_ok=True)
    except: pass
    msg = await m.reply("✅ **Cleaned!**")
    await asyncio.sleep(3); await msg.delete()

# ==========================================
# 🌟 PART 3: TMDB & MEDIA HANDLER 🌟
# ==========================================
@app.on_message(filters.command(["search", "series"]) & filters.user(OWNER_ID))
async def search_handler(c, m):
    if len(m.command) < 2: return await m.reply("❌ **Usage:** `/search Movie` or `/series Name S1`")
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
            async with session.get(url) as resp: data = await resp.json()
        results = data.get('results')
        if not results: return await status.edit("❌ **Not Found!**")
        mid = results[0]['id']
        title = results[0].get('name') if stype == 'tv' else results[0].get('title')
        overview = results[0].get('overview', 'No description.')[:200] + "..."
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🖼 Poster", callback_data=f"type_poster_{stype}_{mid}_{season_num}"), InlineKeyboardButton("🎞 Thumbnail", callback_data=f"type_backdrop_{stype}_{mid}_{season_num}")]])
        txt = f"🎬 <b>{title}</b>\n\n📝 <i>{overview}</i>" + (f"\n\n💿 <b>Season: {season_num}</b>" if season_num > 0 else "") + "\n\n👇 **Select Type:**"
        await status.edit(txt, reply_markup=btn)
    except Exception as e: await status.edit(f"❌ Error: {e}")

@app.on_callback_query(filters.regex("^type_"))
async def type_callback(c, cb):
    try:
        _, img_type, stype, mid, s_num = cb.data.split("_")
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("1", callback_data=f"num_1_{img_type}_{stype}_{mid}_{s_num}"), InlineKeyboardButton("2", callback_data=f"num_2_{img_type}_{stype}_{mid}_{s_num}")]])
        await cb.message.edit(f"✅ **{img_type.capitalize()} Selected!**\nHow many images?", reply_markup=btn)
    except: pass

@app.on_callback_query(filters.regex("^num_"))
async def num_callback(c, cb):
    uid = cb.from_user.id
    try:
        _, count, img_type, stype, mid, s_num = cb.data.split("_")
        await cb.answer(f"⚡ Fetching..."); await cb.message.delete()
        raw_pool = []
        async with aiohttp.ClientSession() as session:
            url = f"https://api.themoviedb.org/3/{stype}/{mid}/images?api_key={TMDB_API_KEY}&include_image_language=en,hi,null"
            async with session.get(url) as resp: raw_pool = (await resp.json()).get('posters' if img_type == 'poster' else 'backdrops', [])
        final_pool = [img for img in raw_pool if img.get('iso_639_1') in ['en', 'hi']] or raw_pool
        if not final_pool: return await c.send_message(uid, "❌ **No images found!**")
        os.makedirs("downloads", exist_ok=True)
        for i, img_data in enumerate(final_pool[:int(count)]):
            img_path = f"downloads/temp_{uid}_{i}.jpg"
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://image.tmdb.org/t/p/original{img_data['file_path']}") as resp:
                    f = await aiofiles.open(img_path, 'wb'); await f.write(await resp.read()); await f.close()
            final_path = apply_watermark(img_path, f"watermarks/{uid}.png") if os.path.exists(f"watermarks/{uid}.png") else img_path
            await c.send_photo(uid, photo=final_path, caption=f"🖼 <b>{img_type.capitalize()} {i+1}</b>")
            if os.path.exists(img_path): os.remove(img_path)
    except Exception as e: await c.send_message(uid, f"❌ Error: {e}")

@app.on_message(filters.private & (filters.document | filters.video | filters.audio | filters.photo) & filters.user(OWNER_ID))
async def media_handler(c, m):
    if m.photo or (m.document and m.document.mime_type and m.document.mime_type.startswith("image/")):
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🖼 Set Thumbnail", callback_data="save_thumb"), InlineKeyboardButton("💧 Set Watermark", callback_data="save_wm")], [InlineKeyboardButton("🌐 Generate Link (ImgBB)", callback_data="upload_img")]])
        return await m.reply_text("📸 **Image Detected!**", reply_markup=btn, quote=True)
    
    status = await m.reply("⚙️ **Processing...**")
    try:
        media = m.document or m.video or m.audio
        fname = getattr(media, "file_name", "File")
        fname = await apply_rename_rules(fname)
        
        # 🔥 AUTO-BRANDING PROTECTOR (File Uploads) 🔥
        name_without_ext, ext = os.path.splitext(fname)
        if not name_without_ext.strip().startswith("["):
            # Ye line shuru se purana naam hatayegi bina error diye
            name_without_ext = re.sub(r'^filmy\s*flip\s*hub\s*', '', name_without_ext.strip(), flags=re.IGNORECASE)
            name_without_ext = f"[Filmy Flip Hub] {name_without_ext}"
            
        if not re.search(r'filmy\s*flip\s*hub$', name_without_ext.strip(), flags=re.IGNORECASE):
            name_without_ext = f"{name_without_ext.strip()} Filmy Flip Hub"
            
        fname = f"{name_without_ext}{ext}"
        # 🔥 ------------------------------------- 🔥
        
        new_cap = get_fancy_caption(fname, humanbytes(getattr(media, "file_size", 0)), getattr(media, "duration", 0))
        
        db_msg = await c.send_video(DB_CHANNEL_ID, m.video.file_id, caption=new_cap, file_name=fname) if m.video else await c.send_document(DB_CHANNEL_ID, m.document.file_id, caption=new_cap, file_name=fname)
        try: await m.delete()
        except: pass
        
        tg_code, blogger_code = get_link_codes(f"link_{OWNER_ID}_{db_msg.id}")
        bot_uname = "CloneBot"
        try:
            if clone1_app and clone1_app.is_connected: bot_uname = (await clone1_app.get_me()).username
        except: pass
        
        await status.edit(f"✅ **Stored Successfully!**\n\n📂 **File:** `{fname}`\n🔗 <b>Blog:</b> {BLOGGER_URL}?data={quote(blogger_code)}\n🤖 <b>Direct:</b> https://t.me/{bot_uname}?start={tg_code}", disable_web_page_preview=True)
    except Exception as e: await status.edit(f"❌ Error: {e}")

@app.on_callback_query(filters.regex("^upload_img"))
async def upload_to_cloud(c, cb):
    await cb.message.edit("⏳ **Uploading to ImgBB...**")
    try:
        path = await c.download_media(cb.message.reply_to_message, file_name=f"downloads/imgbb_{int(time.time())}.jpg")
        async with aiohttp.ClientSession() as session:
            data = aiohttp.FormData(); data.add_field('key', IMG_API_KEY); data.add_field('image', open(path, 'rb'), filename='img.jpg', content_type='image/jpeg')
            async with session.post("https://api.imgbb.com/1/upload", data=data) as resp: result = await resp.json()
        os.remove(path)
        await cb.message.edit(f"✅ **Link:** `{result['data']['url']}`" if 'data' in result else f"❌ Error: {result.get('error', {}).get('message')}")
    except Exception as e: await cb.message.edit(f"❌ Error: {e}")

async def get_real_filename(url):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.head(url, allow_redirects=True) as resp:
                if "Content-Disposition" in resp.headers:
                    match = re.search(r'filename="?([^"]+)"?', resp.headers["Content-Disposition"])
                    if match: return unquote(match.group(1))
        return unquote(url.split("/")[-1].split("?")[0])
    except: return "Downloaded_File.mkv"

@app.on_message(filters.private & filters.regex(r"^https?://") & filters.user(OWNER_ID))
async def url_handler(c, m):
    url = m.text.strip()
    try: await m.delete()
    except: pass
    status = await m.reply("🔗 **Fetching URL...**")
    orig_name = await get_real_filename(url)
    download_queue[m.from_user.id] = {"url": url, "orig_name": orig_name, "prompt_id": status.id}
    await status.edit(f"📂 **Original:**\n<code>{orig_name}</code>\n\n📝 **Type New Name (or send /cancel):**", parse_mode=enums.ParseMode.HTML)

@app.on_message(filters.private & filters.text & ~filters.regex(r"^https?://") & filters.user(OWNER_ID))
async def text_handler(c, m):
    if m.text.startswith("/"): return
    uid = m.from_user.id
    if uid in download_queue:
        download_queue[uid]["new_name"] = m.text.strip()
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🎥 Video", callback_data="dl_video"), InlineKeyboardButton("📁 Document", callback_data="dl_doc")]])
        try: await c.edit_message_text(uid, download_queue[uid]["prompt_id"], f"✅ **Name:** `{m.text.strip()}`\n\n👇 **Select Format:**", reply_markup=btn)
        except: pass

@app.on_callback_query(filters.regex("^dl_"))
async def dl_process(c, cb):
    uid = cb.from_user.id
    data = download_queue.get(uid)
    if not data: return await cb.answer("❌ Task Expired!")
    await cb.message.edit("📥 **Downloading...**")
    
    clean_custom = (await apply_rename_rules(data['new_name'])).replace(".", " ").replace("_", " ")
    
    # 🔥 AUTO-BRANDING PROTECTOR (URL Downloads) 🔥
    if not clean_custom.strip().startswith("["):
        clean_custom = re.sub(r'^filmy\s*flip\s*hub\s*', '', clean_custom.strip(), flags=re.IGNORECASE)
        clean_custom = f"[Filmy Flip Hub] {clean_custom}"
        
    if not re.search(r'filmy\s*flip\s*hub$', clean_custom.strip(), flags=re.IGNORECASE):
        clean_custom = f"{clean_custom.strip()} Filmy Flip Hub"
    # 🔥 -------------------------------------- 🔥

    ext = os.path.splitext(data['orig_name'])[1]
    final_filename = f"{clean_custom}{ext if ext and len(ext)<=5 else '.mkv'}"
    internal_path = f"downloads/{uid}_{final_filename}"
    
    try:
        start = time.time()
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3600)) as session:
            async with session.get(data['url'], headers={"User-Agent": "Mozilla/5.0"}) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                with open(internal_path, "wb") as f:
                    dl = 0
                    async for chunk in resp.content.iter_chunked(1024*1024):
                        f.write(chunk); dl += len(chunk)
                        if time.time() - start > 5: await progress(dl, total, cb.message, start, f"📥 DL: {final_filename}")
        
        await cb.message.edit("⚙️ **Processing...**")
        duration, fsize = get_duration(internal_path), humanbytes(os.path.getsize(internal_path))
        cap = get_fancy_caption(final_filename, fsize, duration)
        thumb_path = apply_watermark(f"thumbnails/{uid}.jpg", f"watermarks/{uid}.png") if os.path.exists(f"thumbnails/{uid}.jpg") and os.path.exists(f"watermarks/{uid}.png") else (f"thumbnails/{uid}.jpg" if os.path.exists(f"thumbnails/{uid}.jpg") else None)
        
        start = time.time()
        db_msg = await c.send_video(DB_CHANNEL_ID, internal_path, caption=cap, duration=duration, thumb=thumb_path, file_name=final_filename, progress=progress, progress_args=(cb.message, start, f"📤 UP: {final_filename}")) if "video" in cb.data else await c.send_document(DB_CHANNEL_ID, internal_path, caption=cap, thumb=thumb_path, file_name=final_filename, progress=progress, progress_args=(cb.message, start, f"📤 UP: {final_filename}"))
        
        tg_code, blogger_code = get_link_codes(f"link_{OWNER_ID}_{db_msg.id}")
        bot_uname = (await clone1_app.get_me()).username if clone1_app and clone1_app.is_connected else "CloneBot"
        await cb.message.edit(f"✅ **Stored!**\n📂 **File:** `{final_filename}`\n🔗 <b>Blog:</b> {BLOGGER_URL}?data={quote(blogger_code)}\n🤖 <b>Direct:</b> https://t.me/{bot_uname}?start={tg_code}", disable_web_page_preview=True)
        os.remove(internal_path); del download_queue[uid]
    except Exception as e: await cb.message.edit(f"❌ Error: {str(e)}")

@app.on_callback_query(filters.regex("^save_"))
async def save_img_callback(c, cb):
    uid, mode = cb.from_user.id, "thumbnails" if "thumb" in cb.data else "watermarks"
    os.makedirs(mode, exist_ok=True)
    path = f"{mode}/{uid}{'.png' if mode == 'watermarks' else '.jpg'}"
    await cb.message.edit("⏳ **Processing...**")
    try:
        await c.download_media(message=cb.message.reply_to_message, file_name=path)
        await cb.message.delete()
        msg = await c.send_message(uid, f"✅ **{'Thumbnail' if mode=='thumbnails' else 'Watermark'} Saved!**")
        await asyncio.sleep(3); await msg.delete()
    except Exception as e: await cb.message.edit(f"❌ Error: {e}")

# ==========================================
# 🌟 PART 4: AI, SEARCH, CLONES & POSTING 🌟
# ==========================================
import datetime
import asyncio
import aiohttp
from pyrogram import enums, filters, Client
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiohttp import web
import pyrogram

# 🔥 AAPKA ASLI GROUP LINK 🔥
REAL_GROUP_LINK = "https://t.me/+COWqvDXiQUkxOWE9"

async def get_gemini_reply(client, chat_id, user_id, prompt_text):
    await client.send_chat_action(chat_id, enums.ChatAction.TYPING)
    if user_id not in user_memory: user_memory[user_id] = []
    user_memory[user_id].append({"role": "user", "parts": [{"text": prompt_text}]})
    if len(user_memory[user_id]) > 6: user_memory[user_id] = user_memory[user_id][-6:]
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent?key={GEMINI_API_KEY}"
        data = {"systemInstruction": {"parts": [{"text": NEHA_PROMPT}]}, "contents": user_memory[user_id]}
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers={'Content-Type': 'application/json'}, json=data) as resp:
                if resp.status != 200: return "Yaar mera dimaag kharab ho raha hai, thodi der baad aana! 😫"
                result = await resp.json()
        reply_text = result['candidates'][0]['content']['parts'][0]['text']
        user_memory[user_id].append({"role": "model", "parts": [{"text": reply_text}]})
        return reply_text
    except Exception: return "Bhai server down chal raha hai... 😔"

# 🕒 AUTO-POST SCHEDULER (Indian Time)
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
                    msg = f"✨ **Good Morning Filmy Family!** ✨\nAaj **{days_hindi.get(now.strftime('%A'), now.strftime('%A'))}** hai! 🔥\n👇\n{FINAL_WEBSITE_URL}"
                    await clone2_app.send_message(MAIN_GROUP_ID, msg)
                    last_morning_date = now.date()
                if now.hour == 19 and last_evening_date != now.date():
                    msg = f"🌆 **Good Evening!** 🌆\nAaj ki movies upload ho gayi hain! Enjoy karo. 👇\n{FINAL_WEBSITE_URL}"
                    await clone2_app.send_message(MAIN_GROUP_ID, msg)
                    last_evening_date = now.date()
        except: pass
        await asyncio.sleep(600)

async def start_clone_bots():
    global clone1_app, clone2_app
    
    # --- CLONE 1: DELIVERY BOT (WITH SMART VIP CAPTION) ---
    d1 = await settings_col.find_one({"_id": "clone1_token"})
    if d1:
        try:
            clone1_app = Client("Clone1", api_id=API_ID, api_hash=API_HASH, bot_token=d1["token"])
            @clone1_app.on_message(filters.command("start") & filters.private)
            async def c1_start(c, m):
                btn = InlineKeyboardMarkup([[InlineKeyboardButton("🚀 Join Now", url=REAL_GROUP_LINK)], [InlineKeyboardButton("📥 Download New", url=FINAL_WEBSITE_URL)]])
                payload = m.command[1] if len(m.command) > 1 else None
                if not payload: return await m.reply("👋 **Hello! Main Delivery Bot hoon.** 🎬", reply_markup=btn)
                
                mid = extract_msg_id(decode_payload(payload))
                if mid:
                    try:
                        msg = await app.get_messages(DB_CHANNEL_ID, mid)
                        
                        # 🔥 SMART CAPTION READER 🔥
                        raw_caption = msg.caption if msg.caption else "🎬 Your Movie File!"
                        
                        if "<blockquote>" in raw_caption:
                            final_cap = f"{raw_caption}\n\n<blockquote>⏳ Note: Yeh file 5 Minute mein delete ho jayegi! ⚠️</blockquote>"
                        else:
                            vip_blocks = []
                            for chunk in raw_caption.split('\n\n'):
                                if chunk.strip(): 
                                    vip_blocks.append(f"<blockquote>{chunk.strip()}</blockquote>")
                            vip_caption = "\n\n".join(vip_blocks)
                            final_cap = f"{vip_caption}\n\n<blockquote>⏳ Note: Yeh file 5 Minute mein delete ho jayegi! ⚠️</blockquote>"

                        sent_msg = await c.copy_message(
                            m.chat.id, 
                            DB_CHANNEL_ID, 
                            mid, 
                            caption=final_cap,
                            parse_mode=enums.ParseMode.HTML
                        )
                        
                        async def auto_del(msg_to_del, cid):
                            await asyncio.sleep(300)
                            try:
                                await msg_to_del.delete()
                                await c.send_message(cid, "⚠️ **File Delete ho chuki hai!** 🕒\nNayi movies ke liye niche click karein! 👇", reply_markup=btn)
                            except: pass
                        asyncio.create_task(auto_del(sent_msg, m.chat.id))
                    except Exception as e: 
                        print(f"Delivery Error: {e}")
                        await m.reply("❌ **File Not Found!**")
            await clone1_app.start()
        except: pass

    # --- CLONE 2: NEHA AI ---
    d2 = await settings_col.find_one({"_id": "clone2_token"})
    if d2:
        try:
            clone2_app = Client("Clone2", api_id=API_ID, api_hash=API_HASH, bot_token=d2["token"])
            
            # 🖼️ AUTO-COMMENT ON PHOTO POSTS
            @clone2_app.on_message(filters.group & filters.photo)
            async def neha_photo_comment(c, m):
                try:
                    await asyncio.sleep(2)
                    await m.reply("Wow! 😍 Ye movie toh bahut mast lag rahi hai. Kis kis ko iska link chahiye? Jaldi batao! 👇✨", quote=True)
                except: pass

            @clone2_app.on_message(filters.command("start") & filters.private)
            async def neha_start_pm(c, m):
                await m.reply(f"Hi! Main Neha hoon. 😉\n\n👉 **Join Group:** {REAL_GROUP_LINK}")

            @clone2_app.on_message(filters.group & filters.text)
            async def neha_grp_handler(c, m):
                bot_me = await c.get_me()
                text, words, uid = m.text.lower(), m.text.lower().split(), (m.from_user.id if m.from_user else m.chat.id)
                remove_list = {"movie", "movies", "film", "series", "link", "de", "do", "chahiye", "upload", "dedo", "dena", "bhej", "bhejo", "kaha", "kahan", "kidhar", "hi", "hello", "hey", "suno", "oye", "oyee", "ka", "ki", "ke", "hai", "koi", "yar", "yaar", "please", "pls", "bhai", "mujhe", "mera", "meri", "download", "neha", f"@{bot_me.username.lower()}"}
                demand_words = {"movie", "film", "series", "link", "chahiye", "dedo", "dena", "bhej"}
                
                is_mentioned = "neha" in text or f"@{bot_me.username.lower()}" in text
                is_reply_to_bot = bool(m.reply_to_message and m.reply_to_message.from_user and m.reply_to_message.from_user.id == bot_me.id)
                has_demand = any(x in words for x in demand_words)

                if is_mentioned or is_reply_to_bot or (not bool(m.reply_to_message and m.reply_to_message.from_user and m.reply_to_message.from_user.id != bot_me.id) and has_demand):
                    ai_reply = await get_gemini_reply(c, m.chat.id, uid, m.text)
                    if ai_reply: await m.reply(ai_reply, quote=True)
                    
                    if has_demand or (is_mentioned and len(words) > 1):
                        query = " ".join([w for w in words if w not in remove_list])
                        if len(query) < 2: return 
                        
                        found_msg, is_from_db = None, False
                        try:
                            async for msg in c.search_messages(m.chat.id, query=query, limit=50, filter=enums.MessagesFilter.PHOTO):
                                if msg.id != m.id: found_msg = msg; break
                            if not found_msg:
                                async for msg in app.search_messages(DB_CHANNEL_ID, query=query, limit=50):
                                    found_msg, is_from_db = msg, True; break
                        except: pass
                        
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
                            try: await c.send_message(int(OWNER_ID), f"🚨 **BOSS ALERT!**\n\n`{query}` nahi mili. Upload kardo!")
                            except: pass

            @clone2_app.on_message(filters.private & filters.text & ~filters.command("start"))
            async def neha_pm(c, m):
                uid = m.from_user.id
                if str(uid) == str(OWNER_ID):
                    r = await get_gemini_reply(c, m.chat.id, uid, m.text)
                    if r: await m.reply(r)
                    return
                if uid not in user_msg_data: user_msg_data[uid] = {'last_time': None, 'is_waiting': False}
                if user_msg_data[uid].get('last_time') and (datetime.datetime.now() - user_msg_data[uid]['last_time']).total_seconds() < 86400: return
                if user_msg_data[uid]['is_waiting']: return
                user_msg_data[uid]['is_waiting'] = True
                await asyncio.sleep(300) 
                try:
                    await m.reply(f"Yaar, main abhi thoda kaam kar rahi hoon! 😊\n🔗 {REAL_GROUP_LINK}")
                    user_msg_data[uid]['last_time'] = datetime.datetime.now()
                except: pass
                finally: user_msg_data[uid]['is_waiting'] = False
            await clone2_app.start()
        except: pass

async def start_services():
    await app.start()
    await start_clone_bots()
    asyncio.create_task(daily_posting_task())
    app_web = web.Application()
    app_web.add_routes([web.get("/", lambda q: web.Response(text="Running!"))])
    runner = web.AppRunner(app_web); await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    await pyrogram.idle()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(start_services())

