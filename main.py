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
API_HASH = os.environ.get("API_HASH", "0375dd20a7c29d0c1c06590dfb")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "846850D5dzd1EzkJs9AqHkAOAhPcmGv1Dwlgk")
OWNER_ID = int(os.environ.get("OWNER_ID", "54470"))
MONGO_URL = os.environ.get("MONGO_URL", "mongodb+srv://raja:raja12345@filmyflip.jlitika.mongodb.net/?retryWrites=true&w=majority&appName=Filmyflip")
DB_CHANNEL_ID = int(os.environ.get("DB_CHANNEL_ID", "-1003311810643"))
BLOGGER_URL = "https://filmyflip1.blogspot.com/p/download.html"
FINAL_WEBSITE_URL = "https://filmyflip-hub.blogspot.com"
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
    name = unquote(name).replace(".", " ").replace("_", " ").replace("-", " ")
    match1 = re.search(r"(?i)(?:s|season)\s*[\.]?\s*(\d{1,2})\s*[\.]?\s*(?:e|ep|episode)\s*[\.]?\s*(\d{1,3})", name)
    if match1: return match1.group(1), match1.group(2)
    match2 = re.search(r"(\d{1,2})x(\d{1,3})", name)
    if match2: return match2.group(1), match2.group(2)
    return None, None

def get_fancy_caption(filename, filesize, duration):
    clean_name = unquote(filename)
    safe_name = html.escape(clean_name)
    caption = f"<code>{safe_name}</code>\n\n"
    s, e = get_media_info(clean_name)
    if s: s = s.zfill(2); caption += f"💿 <b>Season ➥ {s}</b>\n"
    if e: e = e.zfill(2); caption += f"📺 <b>Episode ➥ {e}</b>\n"
    if s or e: caption += "\n"
    caption += f"<blockquote><b>File Size ♻️ ➥ {filesize} ❞</b></blockquote>\n\n"
    dur_str = get_duration_str(duration)
    if dur_str: caption += f"<blockquote><b>Duration ⏰ ➥ {dur_str} ❞</b></blockquote>\n\n"
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

# 🔥 CIRCLE PROGRESS BAR
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

# 🔥 ADVANCED NAME FETCHER (With Fake Browser Headers)
async def get_real_filename(url):
    name = None
    # ⚠️ Fake Browser Headers to trick server
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            # 1. Try HEAD request
            async with session.head(url, headers=headers, allow_redirects=True) as resp:
                if "Content-Disposition" in resp.headers:
                    fname = re.findall("filename=\"?([^\"]+)\"?", resp.headers["Content-Disposition"])
                    if fname: return unquote(fname[0])
            
            # 2. Try GET request (Streamed)
            if not name:
                async with session.get(url, headers=headers, allow_redirects=True) as resp:
                    if "Content-Disposition" in resp.headers:
                        fname = re.findall("filename=\"?([^\"]+)\"?", resp.headers["Content-Disposition"])
                        if fname: return unquote(fname[0])
    except: pass
    
    # 3. Fallback: Clean URL
    if not name: name = unquote(url.split("/")[-1])
    
    # Remove Query Params
    if "?" in name: name = name.split("?")[0]
        
    return name

# --- COMMANDS ---
@app.on_message(filters.command("start") & filters.private)
async def main_start(c, m):
    if m.from_user.id == OWNER_ID:
        ver = pyrogram.__version__
        await m.reply(f"👋 **Boss! v34.0 (Browser Mode) Ready.**\n\n🛠 **Pyrogram:** `{ver}`", parse_mode=enums.ParseMode.HTML)

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

# --- MEDIA HANDLER ---
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
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🖼 Set Thumbnail", callback_data="save_thumb"), InlineKeyboardButton("💧 Set Watermark", callback_data="save_wm")]])
        await m.reply_text("📸 **Image Detected!**", reply_markup=btn, quote=True, parse_mode=enums.ParseMode.HTML)
        return

    status = await m.reply("⚙️ **Processing...**")
    try:
        media = m.document or m.video or m.audio
        fname = getattr(media, "file_name", "File")
        fsize = humanbytes(getattr(media, "file_size", 0))
        dur = getattr(media, "duration", 0)
        
        new_cap = get_fancy_caption(fname, fsize, dur)
        
        # Use send_video/document to FORCE green line
        if m.video:
             db_msg = await c.send_video(DB_CHANNEL_ID, m.video.file_id, caption=new_cap, parse_mode=enums.ParseMode.HTML)
        else:
             db_msg = await c.send_document(DB_CHANNEL_ID, m.document.file_id, caption=new_cap, parse_mode=enums.ParseMode.HTML)
        
        try: await m.delete()
        except: pass
        
        raw_data = f"link_{OWNER_ID}_{db_msg.id}"
        tg_code, blogger_code = get_link_codes(raw_data)
        
        bot_uname = "CloneBot"
        try:
            if clone_app and clone_app.is_connected: bot_uname = (await clone_app.get_me()).username
        except: pass
        final_link = f"{BLOGGER_URL}?data={quote(blogger_code)}"
        
        await status.edit(f"✅ **Stored!**\n\n🔗 <b>Blog:</b> {final_link}\n\n🤖 <b>Direct:</b> https://t.me/{bot_uname}?start={tg_code}", disable_web_page_preview=True, parse_mode=enums.ParseMode.HTML)
    except Exception as e: await status.edit(f"❌ Error: {e}")

# --- URL HANDLER ---
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
            try: await c.edit_message_text(uid, prompt_id, f"✅ **Name:** `{m.text.strip()}`\n\n👇 **Format:**", reply_markup=btn, parse_mode=enums.ParseMode.HTML)
            except: pass

@app.on_callback_query(filters.regex("^dl_"))
async def dl_process(c, cb):
    uid = cb.from_user.id
    data = download_queue.get(uid)
    if not data: return await cb.answer("❌ Task Expired!")
    
    await cb.message.edit("📥 **Initializing...**")
    url = data['url']; custom_name = data['new_name']; mode = "video" if "video" in cb.data else "doc"
    root, ext = os.path.splitext(data['orig_name'])
    if not ext: ext = ".mkv"
    final_filename = f"{custom_name}{ext}"
    internal_path = f"downloads/{uid}_{final_filename}"
    os.makedirs("downloads", exist_ok=True)
    
    try:
        start = time.time()
        # Headers for download too!
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                with open(internal_path, "wb") as f:
                    dl = 0
                    async for chunk in resp.content.iter_chunked(1024*1024):
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
            db_msg = await c.send_video(DB_CHANNEL_ID, internal_path, caption=cap, duration=duration, thumb=thumb_path, file_name=final_filename, progress=progress, progress_args=(cb.message, start, f"📤 Uploading: {final_filename}"), parse_mode=enums.ParseMode.HTML)
        else:
            db_msg = await c.send_document(DB_CHANNEL_ID, internal_path, caption=cap, thumb=thumb_path, file_name=final_filename, progress=progress, progress_args=(cb.message, start, f"📤 Uploading: {final_filename}"), parse_mode=enums.ParseMode.HTML)
            
        raw_data = f"link_{OWNER_ID}_{db_msg.id}"
        tg_code, blogger_code = get_link_codes(raw_data)
        bot_uname = "CloneBot"
        try:
            if clone_app and clone_app.is_connected: bot_uname = (await clone_app.get_me()).username
        except: pass
        final_link = f"{BLOGGER_URL}?data={quote(blogger_code)}"
        
        await cb.message.edit(f"✅ **Stored!**\n\n🔗 <b>Blog:</b> {final_link}\n\n🤖 <b>Direct:</b> https://t.me/{bot_uname}?start={tg_code}", disable_web_page_preview=True, parse_mode=enums.ParseMode.HTML)
        os.remove(internal_path)
        del download_queue[uid]
    except Exception as e: await cb.message.edit(f"❌ Error: {e}")

# --- CALLBACK FOR SAVE IMAGE (SAME AS BEFORE) ---
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
                prev_msg = await c.send_photo(uid, preview_path, caption="✅ **Thumbnail Set!** (Preview)", parse_mode=enums.ParseMode.HTML)
                os.remove(preview_path); await asyncio.sleep(5); await prev_msg.delete()
            else: msg = await c.send_message(uid, "✅ **Thumbnail Set!**"); await asyncio.sleep(3); await msg.delete()
        else: msg = await c.send_message(uid, "✅ **Watermark Saved!** (60% Size)"); await asyncio.sleep(3); await msg.delete()
    except Exception as e: await cb.message.edit(f"❌ Error: {e}")

# --- CLONE SETUP (SAME AS BEFORE) ---
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
            sent_file = await c.copy_message(m.chat.id, DB_CHANNEL_ID, msg_id, caption=cap, parse_mode=enums.ParseMode.HTML)
            await temp.delete(); timer_msg = await m.reply("⏳ **File will be deleted in 5 Mins!**")
            await asyncio.sleep(300); await sent_file.delete(); await timer_msg.delete()
            btn = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Get File Again", url=f"https://t.me/{c.me.username}?start={payload}")]])
            get_again_msg = await m.reply("❌ **Time Over! File Deleted.**\n👇 Get again (Valid 1 Min).", reply_markup=btn)
            await asyncio.sleep(60); await get_again_msg.delete(); await m.reply(f"🚫 **Link Expired!**\n\n🌐 Visit: {FINAL_WEBSITE_URL}", disable_web_page_preview=True)
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
                
