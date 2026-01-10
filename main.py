import os
import time
import math
import base64
import html
import re
import asyncio
import aiofiles
import aiohttp
from urllib.parse import quote, unquote
from PIL import Image
from hachoir.metadata import extractMetadata
from hachoir.parser import createParser
from aiohttp import web
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant, PeerIdInvalid, FloodWait
from motor.motor_asyncio import AsyncIOMotorClient

# --- CONFIGURATION ---
API_ID = int(os.environ.get("API_ID", "23427"))
API_HASH = os.environ.get("API_HASH", "03f2e7c29d0c1c06590dfb")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "846pD5dzd1EzkJs9AqHkAOAhPcmGv1Dwlgk")
OWNER_ID = int(os.environ.get("OWNER_ID", "5470"))
MONGO_URL = os.environ.get("MONGO_URL", "mongodb+srv://raja:raja12345@filmyflip.jlitika.mongodb.net/?retryWrites=true&w=majority&appName=Filmyflip")
DB_CHANNEL_ID = int(os.environ.get("DB_CHANNEL_ID", "-1003311810643"))
BLOGGER_URL = "https://filmyflip1.blogspot.com/p/download.html"
CREDIT_NAME = "🦋 Filmy Flip Hub 🦋"

# --- DATABASE SETUP ---
mongo = AsyncIOMotorClient(MONGO_URL)
db = mongo["FilmyFlipStore"]
settings_col = db["settings"]
channels_col = db["channels"]

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
    if not duration: return "0s"
    m, s = divmod(int(duration), 60); h, m = divmod(m, 60)
    return f"{h}h {m}m {s}s" if h else f"{m}m {s}s"

# 🔥 LINK LOGIC (Safe Mode)
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

# 🔥 CAPTION LOGIC (v17.0 Style)
def get_media_info(name):
    name = name.replace(".", " ").replace("_", " ").replace("-", " ")
    match1 = re.search(r"(?i)(?:s|season)\s*[\.]?\s*(\d{1,2})\s*[\.]?\s*(?:e|ep|episode)\s*[\.]?\s*(\d{1,3})", name)
    if match1: return match1.group(1), match1.group(2)
    match2 = re.search(r"(\d{1,2})x(\d{1,3})", name)
    if match2: return match2.group(1), match2.group(2)
    return None, None

def get_fancy_caption(filename, filesize, duration):
    safe_name = html.escape(filename)
    caption = f"<code>{safe_name}</code>\n\n"
    s, e = get_media_info(filename)
    if s: s = s.zfill(2)
    if e: e = e.zfill(2)
    if s: caption += f"💿 <b>Season ➥ {s}</b>\n"
    if e: caption += f"📺 <b>Episode ➥ {e}</b>\n"
    if s or e: caption += "\n"
    caption += f"<blockquote><b>File Size ♻️ ➥ {filesize} ❞</b></blockquote>\n\n"
    caption += f"<blockquote><b>Duration ⏰ ➥ {get_duration_str(duration)} ❞</b></blockquote>\n\n"
    caption += f"<blockquote><b>Powered By ➥ {CREDIT_NAME} ❞</b></blockquote>"
    return caption

# 🔥 WATERMARK LOGIC
def apply_watermark(base_path, wm_path):
    try:
        base = Image.open(base_path).convert("RGBA")
        wm = Image.open(wm_path).convert("RGBA")
        base_w, base_h = base.size
        wm_w, wm_h = wm.size
        new_wm_w = int(base_w * 0.70)
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

async def progress(current, total, message, start_time, task_name):
    now = time.time()
    diff = now - start_time
    if round(diff % 5.00) == 0 or current == total:
        percentage = current * 100 / total
        speed = current / diff if diff > 0 else 0
        eta = get_duration_str(round((total - current) / speed) if speed > 0 else 0)
        text = f"<b>{task_name}</b>\n\n<b>{round(percentage, 1)}%</b> | {humanbytes(current)}/{humanbytes(total)}\n<b>Speed:</b> {humanbytes(speed)}/s | <b>ETA:</b> {eta}"
        try: await message.edit(text)
        except: pass

async def get_real_filename(url):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, allow_redirects=True) as resp:
                if "Content-Disposition" in resp.headers:
                    fname = re.findall("filename=(.+)", resp.headers["Content-Disposition"])
                    if fname: return unquote(fname[0].strip('"'))
    except: pass
    return unquote(url.split("/")[-1])

# --- COMMANDS ---
@app.on_message(filters.command("start") & filters.private)
async def main_start(c, m):
    if m.from_user.id == OWNER_ID:
        await m.reply("👋 **Boss! URL & Watermark Ready.**\n\n📸 **Photo bhejo:** Thumb/Watermark ke liye.\n🌐 **Link bhejo:** Upload karne ke liye.\n📂 **File bhejo:** Direct Store karne ke liye.")

# 1. IMAGE HANDLER (Thumbnail/Watermark)
@app.on_message(filters.private & filters.photo & filters.user(OWNER_ID))
async def save_photo_handler(c, m):
    btn = InlineKeyboardMarkup([[InlineKeyboardButton("🖼 Set Thumbnail", callback_data="save_thumb"), InlineKeyboardButton("💧 Set Watermark", callback_data="save_wm")]])
    await m.reply_text("📸 **Image Detected!**\nIsse kya banana hai?", reply_markup=btn, quote=True)

@app.on_callback_query(filters.regex("^save_"))
async def save_img_callback(c, cb):
    uid = cb.from_user.id
    mode = "thumbnails" if "thumb" in cb.data else "watermarks"
    os.makedirs(mode, exist_ok=True)
    ext = ".png" if mode == "watermarks" else ".jpg"
    path = f"{mode}/{uid}{ext}"
    await cb.message.edit("⏳ **Saving...**")
    try:
        reply = cb.message.reply_to_message
        await c.download_media(message=reply, file_name=path)
        await cb.message.edit(f"✅ **{mode.capitalize()} Saved!**\nAb URL upload par ye apply hoga.")
    except Exception as e: await cb.message.edit(f"❌ Error: {e}")

# 2. URL UPLOADER (With Watermark)
@app.on_message(filters.private & filters.regex(r"^https?://") & filters.user(OWNER_ID))
async def url_uploader(c, m):
    url = m.text.strip()
    status = await m.reply("🔗 **Analyzing Link...**")
    
    # Download
    fname = await get_real_filename(url)
    path = f"downloads/{m.from_user.id}_{fname}"
    os.makedirs("downloads", exist_ok=True)
    
    try:
        start = time.time()
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                with open(path, "wb") as f:
                    dl = 0
                    async for chunk in resp.content.iter_chunked(1024*1024):
                        f.write(chunk)
                        dl += len(chunk)
                        if time.time() - start > 5: await progress(dl, total, status, start, "📥 Downloading...")
        
        await status.edit("⚙️ **Processing Watermark...**")
        duration = get_duration(path)
        fsize = humanbytes(os.path.getsize(path))
        cap = get_fancy_caption(fname, fsize, duration)
        
        # Watermark & Thumb Logic
        uid = m.from_user.id
        thumb_path = f"thumbnails/{uid}.jpg" if os.path.exists(f"thumbnails/{uid}.jpg") else None
        wm_path = f"watermarks/{uid}.png"
        
        # Agar Watermark set hai to Thumbnail par lagao
        if thumb_path and os.path.exists(wm_path):
            thumb_path = apply_watermark(thumb_path, wm_path)
        
        await status.edit("📤 **Uploading...**")
        start = time.time()
        
        # Upload to DB Channel
        if fname.endswith((".mkv", ".mp4", ".webm")):
            db_msg = await c.send_video(DB_CHANNEL_ID, path, caption=cap, duration=duration, thumb=thumb_path, progress=progress, progress_args=(status, start, "📤 Uploading..."))
        else:
            db_msg = await c.send_document(DB_CHANNEL_ID, path, caption=cap, thumb=thumb_path, progress=progress, progress_args=(status, start, "📤 Uploading..."))
        
        # Generate Link
        raw_data = f"link_{OWNER_ID}_{db_msg.id}"
        tg_code, blogger_code = get_link_codes(raw_data)
        
        bot_uname = "CloneBot"
        try:
            if clone_app and clone_app.is_connected: bot_uname = (await clone_app.get_me()).username
        except: pass
        
        final_link = f"{BLOGGER_URL}?data={quote(blogger_code)}"
        
        await status.edit(f"✅ **Uploaded & Stored!**\n\n🔗 <b>Blog:</b> {final_link}\n\n🤖 <b>Direct:</b> https://t.me/{bot_uname}?start={tg_code}", disable_web_page_preview=True)
        
        os.remove(path)
    except Exception as e: await status.edit(f"❌ Error: {e}")

# 3. DIRECT FILE STORE (Fast Mode)
@app.on_message(filters.private & (filters.document | filters.video | filters.audio) & filters.user(OWNER_ID))
async def direct_store(c, m):
    status = await m.reply("⚙️ **Storing...**")
    try:
        media = m.document or m.video or m.audio
        fname = getattr(media, "file_name", "File")
        fsize = humanbytes(getattr(media, "file_size", 0))
        dur = getattr(media, "duration", 0)
        
        new_cap = get_fancy_caption(fname, fsize, dur)
        db_msg = await m.copy(DB_CHANNEL_ID, caption=new_cap)
        
        raw_data = f"link_{OWNER_ID}_{db_msg.id}"
        tg_code, blogger_code = get_link_codes(raw_data)
        
        bot_uname = "CloneBot"
        try:
            if clone_app and clone_app.is_connected: bot_uname = (await clone_app.get_me()).username
        except: pass
        
        final_link = f"{BLOGGER_URL}?data={quote(blogger_code)}"
        
        await status.edit(f"✅ **Stored!**\n\n🔗 <b>Blog:</b> {final_link}\n\n🤖 <b>Direct:</b> https://t.me/{bot_uname}?start={tg_code}", disable_web_page_preview=True)
    except Exception as e: await status.edit(f"❌ Error: {e}")

# --- SETTINGS COMMANDS ---
@app.on_message(filters.command("setclone") & filters.user(OWNER_ID))
async def set_clone(c, m):
    if len(m.command) < 2: return await m.reply("Usage: `/setclone TOKEN`")
    await settings_col.update_one({"_id": "clone_token"}, {"$set": {"token": m.command[1]}}, upsert=True)
    await m.reply("♻️ **Saved! Restarting...**"); await start_clone_bot()

@app.on_message(filters.command("addfs") & filters.user(OWNER_ID))
async def add_fs(c, m):
    if len(m.command) < 3: return await m.reply("Usage: `/addfs ID Link`")
    await channels_col.update_one({"_id": int(m.command[1])}, {"$set": {"link": m.command[2]}}, upsert=True)
    await m.reply("✅ Added.")

@app.on_message(filters.command("delfs") & filters.user(OWNER_ID))
async def del_fs(c, m):
    try: await channels_col.delete_one({"_id": int(m.command[1])}); await m.reply("🗑 Deleted.")
    except: pass

# --- CLONE BOT LOGIC ---
async def start_clone_bot():
    global clone_app
    data = await settings_col.find_one({"_id": "clone_token"})
    if not data: return
    if clone_app: await clone_app.stop()
    clone_app = Client("CloneBot_Session", api_id=API_ID, api_hash=API_HASH, bot_token=data["token"], parse_mode=enums.ParseMode.HTML)

    @clone_app.on_message(filters.command("start") & filters.private)
    async def clone_start(c, m):
        if len(m.command) < 2: return await m.reply("👋 **Hello!**")
        payload = m.command[1]
        
        missing = []
        async for ch in channels_col.find():
            try: await c.get_chat_member(ch["_id"], m.from_user.id)
            except UserNotParticipant: missing.append(ch["link"])
            except: pass
        if missing:
            btn = [[InlineKeyboardButton(f"📢 Join Channel {i+1}", url=l)] for i, l in enumerate(missing)]
            btn.append([InlineKeyboardButton("🔄 Try Again", url=f"https://t.me/{c.me.username}?start={payload}")])
            return await m.reply("⚠️ **Join Channels First!**", reply_markup=InlineKeyboardMarkup(btn))

        decoded_string = decode_payload(payload)
        msg_id = extract_msg_id(decoded_string) if decoded_string else None
        if not msg_id: return await m.reply("❌ **Link Invalid!**")

        try:
            temp = await m.reply("🔄 **Checking File...**")
            msg = await c.get_messages(DB_CHANNEL_ID, msg_id)
            if not msg: return await temp.edit("❌ **File Deleted.**")
            
            cap = msg.caption or get_fancy_caption(getattr(msg.document or msg.video, "file_name", "File"), humanbytes(getattr(msg.document or msg.video, "file_size", 0)), 0)
            await c.copy_message(m.chat.id, DB_CHANNEL_ID, msg_id, caption=cap)
            await temp.delete()
        except Exception as e: await m.reply(f"❌ Error: {e}")

    try: await clone_app.start(); print("✅ Clone Started")
    except: pass

async def start_services():
    await app.start()
    await start_clone_bot()
    r = web.RouteTableDef()
    @r.get("/", allow_head=True)
    async def h(q): return web.json_response({"status": "running"})
    app_web = web.Application(); app_web.add_routes(r)
    runner = web.AppRunner(app_web); await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", 8080).start()
    await asyncio.Event().wait()

if __name__ == "__main__": asyncio.get_event_loop().run_until_complete(start_services())
