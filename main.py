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
from urllib.parse import quote, unquote
from PIL import Image
from hachoir.metadata import extractMetadata
from hachoir.parser import createParser
from aiohttp import web
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient

# --- CONFIGURATION ---
API_ID = int(os.environ.get("API_ID", "234127"))
API_HASH = os.environ.get("API_HASH", "0375dd2029d0c1c06590dfb")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8468501pD5dzd1EzkJs9AqHkAOAhPcmGv1Dwlgk")
OWNER_ID = int(os.environ.get("OWNER_ID", "5014470"))
MONGO_URL = os.environ.get("MONGO_URL", "mongodb+srv://raja:raja12345@filmyflip.jlitika.mongodb.net/?retryWrites=true&w=majority&appName=Filmyflip")
DB_CHANNEL_ID = int(os.environ.get("DB_CHANNEL_ID", "-1003311810643"))
TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "02a832d91755c2f5e8a2d1a6740a8674")
BLOGGER_URL = "https://filmyflip1.blogspot.com/p/download.html"
FINAL_WEBSITE_URL = "https://filmyflip-hub.blogspot.com"
CREDIT_NAME = "🦋 Filmy Flip Hub 🦋"

# 🔥 ImgBB API Key
IMG_API_KEY = "727ccce0985cf58d329ffb4d0005ea06"
IMG_API_URL = "https://api.imgbb.com/1/upload"

# --- DATABASE SETUP ---
try:
    mongo = AsyncIOMotorClient(MONGO_URL)
    db = mongo["FilmyFlipStore"]
    settings_col = db["settings"]
    channels_col = db["channels"]
    users_col = db["users"]
    rename_col = db["rename_rules"] # 🆕 Rename Rules Collection
    print("✅ MongoDB Connected")
except Exception as e:
    print(f"❌ MongoDB Error: {e}")

# --- BOT SETUP ---
app = Client("MainBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workers=10, parse_mode=enums.ParseMode.HTML)
clone_app = None
download_queue = {} 

# --- HELPERS ---

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

# 🔥 LINK LOGIC
def get_link_codes(string_data):
    b64_bytes = base64.b64encode(string_data.encode("utf-8"))
    b64_str = b64_bytes.decode("utf-8")
    tg_code = b64_str.rstrip("=")
    blogger_bytes = base64.b64encode(tg_code.encode("utf-8"))
    blogger_code = blogger_bytes.decode("utf-8")
    return tg_code, blogger_code

def decode_payload(s):
    try:
        def fix_pad(s): return s + "=" * ((4 - len(s) % 4) % 4)
        s = fix_pad(s.strip())
        return base64.b64decode(s).decode("utf-8")
    except: return None

def extract_msg_id(payload):
    try:
        if "_" in payload: return int(payload.split("_")[-1])
        else: return int(payload)
    except: return None

# 🔥 CAPTION LOGIC
def get_media_info(name):
    clean_name = name.replace(".", " ").replace("_", " ").replace("-", " ")
    match1 = re.search(r"(?i)(?:s|season)\s*[\.]?\s*(\d{1,2})\s*[\.]?\s*(?:e|ep|episode)\s*[\.]?\s*(\d{1,3})", clean_name)
    if match1: return match1.group(1), match1.group(2)
    match2 = re.search(r"(\d{1,2})x(\d{1,3})", clean_name)
    if match2: return match2.group(1), match2.group(2)
    return None, None

def get_fancy_caption(filename, filesize, duration):
    clean_name = filename.replace(".", " ").replace("_", " ")
    safe_name = html.escape(clean_name)
    caption = f"<b>{safe_name}</b>\n\n"
    s, e = get_media_info(filename)
    if s: s = s.zfill(2); caption += f"💿 <b>Season ➥ {s}</b>\n"
    if e: e = e.zfill(2); caption += f"📺 <b>Episode ➥ {e}</b>\n"
    if s or e: caption += "\n"
    caption += f"<blockquote><code>File Size ♻️ ➥ {filesize}</code></blockquote>\n\n"
    dur_str = get_duration_str(duration)
    if dur_str: caption += f"<blockquote><code>Duration ⏰ ➥ {dur_str}</code></blockquote>\n\n"
    caption += f"<blockquote><b>Powered By ➥ {CREDIT_NAME} ❞</b></blockquote>"
    return caption

# 🔥 WATERMARK LOGIC
def apply_watermark(base_path, wm_path):
    try:
        base = Image.open(base_path).convert("RGBA")
        wm = Image.open(wm_path).convert("RGBA")
        base_w, base_h = base.size
        wm_w, wm_h = wm.size
        new_wm_w = int(base_w * 0.60)
        ratio = new_wm_w / wm_w
        new_wm_h = int(wm_h * ratio)
        wm = wm.resize((new_wm_w, new_wm_h), Image.Resampling.LANCZOS)
        x = (base_w - new_wm_w) // 2
        y = base_h - new_wm_h - 20 
        if y < 0: y = base_h - new_wm_h
        base.paste(wm, (x, y), wm)
        base = base.convert("RGB")
        base.save(base_path, "JPEG")
        return base_path
    except: return base_path

# 🔥 NAME FETCHER
async def get_real_filename(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, allow_redirects=True, timeout=10) as resp:
                if "Content-Disposition" in resp.headers:
                    cd = resp.headers["Content-Disposition"]
                    fname_match = re.search(r'filename="?([^"]+)"?', cd)
                    if fname_match: return unquote(fname_match.group(1))
                    utf_match = re.search(r"filename\*=UTF-8''(.+)", cd)
                    if utf_match: return unquote(utf_match.group(1))
    except: pass
    name = unquote(url.split("/")[-1].split("?")[0])
    return name.replace(".", " ").replace("_", " ")

# 🔥 RENAME RULES LOGIC (NEW - THE MAGIC)
async def apply_rename_rules(filename):
    rules = await rename_col.find({}).to_list(length=None)
    new_filename = filename
    for rule in rules:
        old_word = rule['old']
        new_word = rule['new']
        # Case Insensitive Replace
        pattern = re.compile(re.escape(old_word), re.IGNORECASE)
        new_filename = pattern.sub(new_word, new_filename)
    return new_filename

# 🔥 PROGRESS BAR
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
            # --- COMMANDS ---
@app.on_message(filters.command("start") & filters.private)
async def main_start(c, m):
    try: await users_col.update_one({"_id": m.from_user.id}, {"$set": {"id": m.from_user.id}}, upsert=True)
    except: pass
    if m.from_user.id == OWNER_ID:
        db_status = "✅ Connected"
        try: await db.command("ping")
        except: db_status = "❌ Disconnected"
        await m.reply(f"👋 **Boss! v53.0 (Speed Boost) Ready.**\n\n🗄 **DB:** `{db_status}`\n🆔 **ID:** `{DB_CHANNEL_ID}`")

# 🔥 STATS COMMAND
@app.on_message(filters.command("stats") & filters.user(OWNER_ID))
async def get_stats(c, m):
    status = await m.reply("📊 **Counting Users...**")
    count = await users_col.count_documents({})
    await status.edit(f"👥 **Total Users:** `{count}`")

# 🔥 ADD REPLACE RULES COMMANDS (NEW)
@app.on_message(filters.command("addreplace") & filters.user(OWNER_ID))
async def add_replace_handler(c, m):
    try:
        # User input: /addreplace Old Word | New Word
        text = m.text.split(" ", 1)[1]
        if "|" in text:
            old_word, new_word = text.split("|", 1)
            old_word = old_word.strip()
            new_word = new_word.strip()
        else:
            old_word = text.strip()
            new_word = ""

        await rename_col.update_one(
            {"old": old_word},
            {"$set": {"new": new_word}},
            upsert=True
        )
        await m.reply(f"✅ **Rule Added!**\n\n🔹 **Find:** `{old_word}`\n🔸 **Replace With:** `{new_word or '(Empty)'}`")
    except IndexError:
        await m.reply("❌ **Format:** `/addreplace Old Word | New Word`\nExample: `/addreplace mkvCinemas | FilmyFlip`")

@app.on_message(filters.command("viewreplace") & filters.user(OWNER_ID))
async def view_rules_handler(c, m):
    rules = await rename_col.find({}).to_list(length=None)
    if not rules:
        return await m.reply("📂 **No Rules Found!**\nUse `/addreplace` to add one.")
    
    msg = "📝 **Your Rename Rules:**\n\n"
    for rule in rules:
        target = rule['new'] if rule['new'] else "(Remove)"
        msg += f"🔹 `{rule['old']}` ➡️ `{target}`\n"
    
    msg += "\n🗑 Use `/delreplace word` to delete."
    await m.reply(msg)

@app.on_message(filters.command("delreplace") & filters.user(OWNER_ID))
async def del_rule_handler(c, m):
    try:
        word = m.text.split(" ", 1)[1].strip()
        result = await rename_col.delete_one({"old": word})
        if result.deleted_count > 0:
            await m.reply(f"🗑 **Deleted Rule:** `{word}`")
        else:
            await m.reply(f"❌ **Rule not found:** `{word}`")
    except IndexError:
        await m.reply("❌ Word to likho!\nExample: `/delreplace HdHub4u`")

@app.on_message(filters.command("cancel") & filters.private & filters.user(OWNER_ID))
async def cancel_task(c, m):
    uid = m.from_user.id
    if uid in download_queue: del download_queue[uid]
    try: shutil.rmtree("downloads"); os.makedirs("downloads", exist_ok=True)
    except: pass
    await m.delete()
    msg = await m.reply("✅ **Cleaned!**")
    await asyncio.sleep(3)
    await msg.delete()

@app.on_message(filters.command("setdb") & filters.user(OWNER_ID))
async def set_db_channel(c, m):
    if len(m.command) < 2: return await m.reply("❌ Usage: `/setdb -100xxxxxxx`")
    try:
        new_id = int(m.command[1])
        await settings_col.update_one({"_id": "db_channel"}, {"$set": {"id": new_id}}, upsert=True)
        global DB_CHANNEL_ID
        DB_CHANNEL_ID = new_id
        await m.reply(f"✅ **DB Channel Updated!**\n🆔 New ID: `{new_id}`")
    except Exception as e: await m.reply(f"❌ Error: {e}")

@app.on_message(filters.command("addfs") & filters.user(OWNER_ID))
async def add_fs(c, m):
    if len(m.command) < 3: return await m.reply("❌ Usage: `/addfs ID Link`")
    status = await m.reply("🔄 **Adding to DB...**")
    try:
        ch_id = int(m.command[1])
        link = m.command[2]
        await channels_col.update_one({"_id": ch_id}, {"$set": {"link": link}}, upsert=True)
        await status.edit(f"✅ **Force Subscribe Added!**\n\n🆔 `{ch_id}`\n🔗 {link}")
    except Exception as e: await status.edit(f"❌ Error: {e}")

@app.on_message(filters.command("delfs") & filters.user(OWNER_ID))
async def del_fs(c, m):
    try: await channels_col.delete_one({"_id": int(m.command[1])}); await m.reply("🗑 Deleted.")
    except: pass

# --- TMDB SEARCH ---
@app.on_message(filters.command(["search", "series"]))
async def search_handler(c, m):
    if len(m.command) < 2: return await m.reply("❌ **Usage:**\n`/search Movie Name`\n`/series Name S1`")
    raw_query = " ".join(m.command[1:])
    stype = "tv" if "series" in m.command[0] else "movie"
    season_num = 0
    if stype == "tv":
        match = re.search(r"(?i)\s*(?:s|season)\s*(\d+)$", raw_query)
        if match:
            season_num = int(match.group(1))
            raw_query = re.sub(r"(?i)\s*(?:s|season)\s*(\d+)$", "", raw_query).strip()
    status = await m.reply(f"🔎 **Searching:** `{raw_query}`...")
    try:
        url = f"https://api.themoviedb.org/3/search/{stype}?api_key={TMDB_API_KEY}&query={quote(raw_query)}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
        results = data.get('results')
        if not results: return await status.edit("❌ **Not Found!**")
        mid = results[0]['id']
        title = results[0].get('name') if stype == 'tv' else results[0].get('title')
        overview = results[0].get('overview', 'No description.')[:200] + "..."
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🖼 Poster", callback_data=f"type_poster_{stype}_{mid}_{season_num}"), InlineKeyboardButton("🎞 Thumbnail", callback_data=f"type_backdrop_{stype}_{mid}_{season_num}")]])
        txt = f"🎬 <b>{title}</b>\n\n📝 <i>{overview}</i>"
        if season_num > 0: txt += f"\n\n💿 <b>Season: {season_num}</b>"
        txt += "\n\n👇 **Select Type:**"
        await status.edit(txt, reply_markup=btn)
    except Exception as e: await status.edit(f"❌ Error: {e}")

@app.on_callback_query(filters.regex("^type_"))
async def type_callback(c, cb):
    try:
        _, img_type, stype, mid, s_num = cb.data.split("_")
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("1", callback_data=f"num_1_{img_type}_{stype}_{mid}_{s_num}"), InlineKeyboardButton("2", callback_data=f"num_2_{img_type}_{stype}_{mid}_{s_num}")], [InlineKeyboardButton("3", callback_data=f"num_3_{img_type}_{stype}_{mid}_{s_num}"), InlineKeyboardButton("4", callback_data=f"num_4_{img_type}_{stype}_{mid}_{s_num}")]])
        await cb.message.edit(f"✅ **{img_type.capitalize()} Selected!**\nHow many images?", reply_markup=btn)
    except: pass

@app.on_callback_query(filters.regex("^num_"))
async def num_callback(c, cb):
    uid = cb.from_user.id
    try:
        _, count, img_type, stype, mid, s_num = cb.data.split("_")
        count = int(count); s_num = int(s_num)
        await cb.answer(f"⚡ Fetching Best Images...")
        await cb.message.delete()
        raw_pool = []
        async with aiohttp.ClientSession() as session:
            if stype == "tv" and s_num > 0:
                url = f"https://api.themoviedb.org/3/tv/{mid}/season/{s_num}/images?api_key={TMDB_API_KEY}&include_image_language=en,hi,null"
                async with session.get(url) as resp:
                    data = await resp.json()
                    raw_pool = data.get('posters' if img_type == 'poster' else 'backdrops', [])
            if not raw_pool:
                url = f"https://api.themoviedb.org/3/{stype}/{mid}/images?api_key={TMDB_API_KEY}&include_image_language=en,hi,null"
                async with session.get(url) as resp:
                    data = await resp.json()
                    raw_pool = data.get('posters' if img_type == 'poster' else 'backdrops', [])
        final_pool = [img for img in raw_pool if img.get('iso_639_1') in ['en', 'hi']]
        if not final_pool: final_pool = raw_pool 
        if not final_pool: return await c.send_message(uid, "❌ **No images found!**")
        images_to_send = final_pool[:count]
        wm_path = f"watermarks/{uid}.png"
        os.makedirs("downloads", exist_ok=True)
        for i, img_data in enumerate(images_to_send):
            img_path = img_data['file_path']
            full_url = f"https://image.tmdb.org/t/p/original{img_path}"
            temp_path = f"downloads/temp_{uid}_{i}.jpg"
            async with aiohttp.ClientSession() as session:
                async with session.get(full_url) as resp:
                    if resp.status == 200:
                        f = await aiofiles.open(temp_path, mode='wb')
                        await f.write(await resp.read()); await f.close()
            final_path = temp_path
            if os.path.exists(wm_path): final_path = apply_watermark(temp_path, wm_path)
            has_logo = " (with Logo)" if img_data.get('iso_639_1') else ""
            await c.send_photo(uid, photo=final_path, caption=f"🖼 <b>{img_type.capitalize()} {i+1}{has_logo}</b>")
            if os.path.exists(temp_path): os.remove(temp_path)
            await asyncio.sleep(0.5)
    except Exception as e: await c.send_message(uid, f"❌ Error: {e}")
    # --- MEDIA HANDLER (IMAGE UPLOAD + FILE STORE + AUTO RENAME) ---
@app.on_message(filters.private & (filters.document | filters.video | filters.audio | filters.photo) & filters.user(OWNER_ID))
async def media_handler(c, m):
    uid = m.from_user.id
    is_image = False
    if m.photo: is_image = True
    elif m.document:
        mime = m.document.mime_type or ""
        fname = m.document.file_name or ""
        if mime.startswith("image/") or fname.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
            is_image = True
            
    if is_image:
        btn = InlineKeyboardMarkup([
            [InlineKeyboardButton("🖼 Set Thumbnail", callback_data="save_thumb"), InlineKeyboardButton("💧 Set Watermark", callback_data="save_wm")],
            [InlineKeyboardButton("🌐 Generate Link (ImgBB)", callback_data="upload_img")]
        ])
        await m.reply_text("📸 **Image Detected!**", reply_markup=btn, quote=True)
        return

    status = await m.reply("⚙️ **Processing...**")
    try:
        media = m.document or m.video or m.audio
        fname = getattr(media, "file_name", "File")
        
        # 🔥 APPLY RENAME RULES (AUTO RENAME LOGIC)
        # Yaha magic hoga: HdHub4u hat jayega, FilmyFlip aa jayega
        fname = await apply_rename_rules(fname)

        fsize = humanbytes(getattr(media, "file_size", 0))
        dur = getattr(media, "duration", 0)
        new_cap = get_fancy_caption(fname, fsize, dur)
        
        # Upload to DB Channel with NEW NAME
        if m.video: db_msg = await c.send_video(DB_CHANNEL_ID, m.video.file_id, caption=new_cap, file_name=fname)
        else: db_msg = await c.send_document(DB_CHANNEL_ID, m.document.file_id, caption=new_cap, file_name=fname)
        
        try: await m.delete()
        except: pass
        
        raw_data = f"link_{OWNER_ID}_{db_msg.id}"
        tg_code, blogger_code = get_link_codes(raw_data)
        bot_uname = "CloneBot"
        try:
            if clone_app and clone_app.is_connected: bot_uname = (await clone_app.get_me()).username
        except: pass
        final_link = f"{BLOGGER_URL}?data={quote(blogger_code)}"
        await status.edit(f"✅ **Stored!**\n\n📂 **File:** `{fname}`\n\n🔗 <b>Blog:</b> {final_link}\n\n🤖 <b>Direct:</b> https://t.me/{bot_uname}?start={tg_code}", disable_web_page_preview=True)
    except Exception as e: await status.edit(f"❌ Error: {e}")

# 🔥 UPLOAD CALLBACK (ImgBB WITH API KEY)
@app.on_callback_query(filters.regex("^upload_img"))
async def upload_to_cloud(c, cb):
    await cb.message.edit("⏳ **Uploading to ImgBB...**")
    path = None
    try:
        reply = cb.message.reply_to_message
        if not reply or not reply.photo: return await cb.message.edit("❌ Photo not found!")
        
        timestamp = int(time.time())
        path = await c.download_media(reply, file_name=f"downloads/imgbb_{timestamp}.jpg")
        await asyncio.sleep(1) 
        
        async with aiohttp.ClientSession() as session:
            payload = {'key': IMG_API_KEY}
            with open(path, 'rb') as f:
                data = aiohttp.FormData()
                for k, v in payload.items(): data.add_field(k, v)
                data.add_field('image', f, filename='image.jpg', content_type='image/jpeg')
                
                async with session.post(IMG_API_URL, data=data) as resp:
                    result = await resp.json()
        
        if path and os.path.exists(path): os.remove(path)
        
        if 'data' in result and 'url' in result['data']:
            img_url = result['data']['url']
            await cb.message.edit(f"✅ **Upload Successful!**\n\n🔗 **Link:**\n`{img_url}`", disable_web_page_preview=True)
        else:
            err_msg = result.get('error', {}).get('message', 'Unknown Error')
            await cb.message.edit(f"❌ Upload Failed: {err_msg}")
            
    except Exception as e:
        if path and os.path.exists(path): os.remove(path)
        await cb.message.edit(f"❌ Error: {e}")

@app.on_message(filters.private & filters.regex(r"^https?://") & filters.user(OWNER_ID))
async def url_handler(c, m):
    url = m.text.strip()
    try: await m.delete()
    except: pass
    status = await m.reply("🔗 **Fetching...**")
    orig_name = await get_real_filename(url)
    download_queue[m.from_user.id] = {"url": url, "orig_name": orig_name, "prompt_id": status.id}
    await status.edit(f"📂 **Original:**\n<code>{orig_name}</code>\n\n📝 **New Name:**", parse_mode=enums.ParseMode.HTML)

@app.on_message(filters.private & filters.text & ~filters.regex(r"^https?://") & filters.user(OWNER_ID))
async def text_handler(c, m):
    if m.text.startswith("/"): return
    uid = m.from_user.id
    if uid in download_queue:
        try: await m.delete()
        except: pass
        download_queue[uid]["new_name"] = m.text.strip()
        prompt_id = download_queue[uid].get("prompt_id")
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🎥 Video", callback_data="dl_video"), InlineKeyboardButton("📁 Document", callback_data="dl_doc")]])
        if prompt_id:
            try: await c.edit_message_text(uid, prompt_id, f"✅ **Name:** `{m.text.strip()}`\n\n👇 **Format:**", reply_markup=btn)
            except: pass

@app.on_callback_query(filters.regex("^dl_"))
async def dl_process(c, cb):
    uid = cb.from_user.id
    data = download_queue.get(uid)
    if not data: return await cb.answer("❌ Task Expired!")
    await cb.message.edit("📥 **Initializing...**")
    url = data['url']; custom_name = data['new_name']; mode = "video" if "video" in cb.data else "doc"
    
    # 🔥 APPLY RENAME RULES ON CUSTOM NAME
    clean_custom = await apply_rename_rules(custom_name)
    clean_custom = clean_custom.replace(".", " ").replace("_", " ")

    orig_clean = data['orig_name']
    root, ext = os.path.splitext(orig_clean)
    if not ext or len(ext) > 5: ext = ".mkv"
    final_filename = f"{clean_custom}{ext}"
    internal_path = f"downloads/{uid}_{final_filename}"
    os.makedirs("downloads", exist_ok=True)
    
    # 🔥 OPTIMIZED DOWNLOADER
    try:
        start = time.time()
        # Fake Chrome Headers to Boost Speed
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Accept-Encoding": "identity" # Force no compression for direct stream
        }
        
        # High Timeout to prevent "Error" on slow starts
        timeout_settings = aiohttp.ClientTimeout(total=3600, connect=60) # 1 Hour total time, 60s connect
        
        async with aiohttp.ClientSession(timeout=timeout_settings) as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    return await cb.message.edit(f"❌ Error: Server returned {resp.status}")
                
                total = int(resp.headers.get("Content-Length", 0))
                with open(internal_path, "wb") as f:
                    dl = 0
                    async for chunk in resp.content.iter_chunked(1024*1024): # 1MB Chunk
                        f.write(chunk); dl += len(chunk)
                        if time.time() - start > 5: await progress(dl, total, cb.message, start, f"📥 Downloading: {final_filename}")
        
        await cb.message.edit("⚙️ **Processing...**")
        duration = get_duration(internal_path)
        fsize = humanbytes(os.path.getsize(internal_path))
        cap = get_fancy_caption(final_filename, fsize, duration)
        thumb_path = f"thumbnails/{uid}.jpg" if os.path.exists(f"thumbnails/{uid}.jpg") else None
        wm_path = f"watermarks/{uid}.png"
        if thumb_path and os.path.exists(wm_path): thumb_path = apply_watermark(thumb_path, wm_path)
        start = time.time()
        if mode == "video":
            db_msg = await c.send_video(DB_CHANNEL_ID, internal_path, caption=cap, duration=duration, thumb=thumb_path, file_name=final_filename, progress=progress, progress_args=(cb.message, start, f"📤 Uploading: {final_filename}"))
        else:
            db_msg = await c.send_document(DB_CHANNEL_ID, internal_path, caption=cap, thumb=thumb_path, file_name=final_filename, progress=progress, progress_args=(cb.message, start, f"📤 Uploading: {final_filename}"))
        raw_data = f"link_{OWNER_ID}_{db_msg.id}"
        tg_code, blogger_code = get_link_codes(raw_data)
        bot_uname = "CloneBot"
        try:
            if clone_app and clone_app.is_connected: bot_uname = (await clone_app.get_me()).username
        except: pass
        final_link = f"{BLOGGER_URL}?data={quote(blogger_code)}"
        await cb.message.edit(f"✅ **Stored!**\n\n📂 **File:** `{final_filename}`\n\n🔗 <b>Blog:</b> {final_link}\n\n🤖 <b>Direct:</b> https://t.me/{bot_uname}?start={tg_code}", disable_web_page_preview=True)
        os.remove(internal_path); del download_queue[uid]
    except Exception as e: await cb.message.edit(f"❌ Error: {str(e)}")

@app.on_callback_query(filters.regex("^save_"))
async def save_img_callback(c, cb):
    uid = cb.from_user.id
    mode = "thumbnails" if "thumb" in cb.data else "watermarks"
    os.makedirs(mode, exist_ok=True)
    ext = ".png" if mode == "watermarks" else ".jpg"
    path = f"{mode}/{uid}{ext}"
    await cb.message.edit("⏳ **Processing...**")
    try:
        reply = cb.message.reply_to_message
        if not reply: return await cb.message.edit("❌ Error: Image not found!")
        await c.download_media(message=reply, file_name=path)
        try: await reply.delete()
        except: pass
        await cb.message.delete()
        if mode == "thumbnails":
            wm_path = f"watermarks/{uid}.png"
            if os.path.exists(wm_path):
                preview_path = f"{mode}/{uid}_preview.jpg"
                img = Image.open(path).convert("RGB")
                img.save(preview_path); apply_watermark(preview_path, wm_path)
                # 🔥 PREVIEW FIX: Message delete line removed
                prev_msg = await c.send_photo(uid, preview_path, caption="✅ **Thumbnail Set!** (Preview)")
                os.remove(preview_path) 
            else: msg = await c.send_message(uid, "✅ **Thumbnail Set!**"); await asyncio.sleep(3); await msg.delete()
        else: msg = await c.send_message(uid, "✅ **Watermark Saved!** (60% Size)"); await asyncio.sleep(3); await msg.delete()
    except Exception as e: await cb.message.edit(f"❌ Error: {e}")

@app.on_message(filters.command("setclone") & filters.user(OWNER_ID))
async def set_clone(c, m):
    if len(m.command) < 2: return await m.reply("Usage: `/setclone TOKEN`")
    await settings_col.update_one({"_id": "clone_token"}, {"$set": {"token": m.command[1]}}, upsert=True)
    await m.reply("♻️ **Saved! Restarting...**"); await start_clone_bot()

async def start_clone_bot():
    global clone_app
    try:
        db_data = await settings_col.find_one({"_id": "db_channel"})
        if db_data: 
            global DB_CHANNEL_ID
            DB_CHANNEL_ID = db_data["id"]
    except: pass

    data = await settings_col.find_one({"_id": "clone_token"})
    if not data: return
    if clone_app: await clone_app.stop()
    clone_app = Client("CloneBot_Session", api_id=API_ID, api_hash=API_HASH, bot_token=data["token"], parse_mode=enums.ParseMode.HTML)
    
    @clone_app.on_message(filters.command("start") & filters.private)
    async def clone_start(c, m):
        try: await users_col.update_one({"_id": m.from_user.id}, {"$set": {"id": m.from_user.id}}, upsert=True)
        except: pass
        if len(m.command) < 2:
            return await m.reply(
                f"👋 **Hello {m.from_user.first_name}!**\n\n"
                f"🚀 **{CREDIT_NAME} Fast Bot!**\n"
                f"Use this bot to get your files instantly.\n\n"
                f"📂 **Join our Channel:**\n"
                f"👉 {FINAL_WEBSITE_URL}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👨‍💻 Contact Admin", url="https://t.me/Moviessrudio_bot")]])
            )
        
        payload = m.command[1]
        missing = []
        async for ch in channels_col.find():
            try: await c.get_chat_member(ch["_id"], m.from_user.id)
            except: missing.append(ch["link"])
        if missing:
            btn = [[InlineKeyboardButton(f"📢 Join Channel {i+1}", url=l)] for i, l in enumerate(missing)]
            btn.append([InlineKeyboardButton("🔄 Try Again", url=f"https://t.me/{c.me.username}?start={payload}")])
            return await m.reply("⚠️ **Join Channels First!**", reply_markup=InlineKeyboardMarkup(btn))
        decoded_string = decode_payload(payload)
        msg_id = extract_msg_id(decoded_string) if decoded_string else None
        if not msg_id: return await m.reply("❌ **Link Invalid!**")
        try:
            temp = await m.reply("🔄 **Processing...**")
            msg = await c.get_messages(DB_CHANNEL_ID, msg_id)
            if not msg: return await temp.edit("❌ **File Deleted.**")
            cap = msg.caption or get_fancy_caption(getattr(msg.document or msg.video, "file_name", "File"), humanbytes(getattr(msg.document or msg.video, "file_size", 0)), 0)
            
            sent_file = await c.copy_message(m.chat.id, DB_CHANNEL_ID, msg_id, caption=cap)
            await temp.delete()
            timer_msg = await m.reply("⏳ **File will be deleted in 5 Mins!**")
            await asyncio.sleep(300)
            await sent_file.delete(); await timer_msg.delete()
            
            btn = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Get File Again", url=f"https://t.me/{c.me.username}?start={payload}")]])
            get_again_msg = await m.reply("❌ **Time Over! File Deleted.**\n👇 Get again (Valid 1 Min).", reply_markup=btn)
            await asyncio.sleep(6); await get_again_msg.delete()
            
            web_btn = InlineKeyboardMarkup([[InlineKeyboardButton("🌐 Visit Website", url=FINAL_WEBSITE_URL)]])
            await m.reply(f"🚫 **Link Expired!**", reply_markup=web_btn)
        except Exception as e: await m.reply(f"❌ Error: {e}")
    try: await clone_app.start(); print("✅ Clone Started")
    except: pass

async def start_services():
    await app.start(); await start_clone_bot()
    r = web.RouteTableDef()
    @r.get("/", allow_head=True)
    async def h(q): return web.json_response({"status": "running"})
    app_web = web.Application(); app_web.add_routes(r)
    runner = web.AppRunner(app_web); await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", 8080).start()
    await asyncio.Event().wait()

if __name__ == "__main__": asyncio.get_event_loop().run_until_complete(start_services())
    
