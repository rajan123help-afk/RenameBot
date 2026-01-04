import os
import time
import math
import base64
import re
import asyncio
import requests
import shutil
import html
import aiofiles
import aiohttp
from urllib.parse import unquote
from PIL import Image
from hachoir.metadata import extractMetadata
from hachoir.parser import createParser
from aiohttp import web
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ForceReply, InputMediaPhoto

# --- CONFIGURATION ---
API_ID = int(os.environ.get("API_ID", "23421127"))
API_HASH = os.environ.get("API_HASH", "0375dd20aba9f2e7c29d0c1c06590dfb")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8404232346:AAGiYT6p7mssrLQ8DtoYk8i36djut-XXXX")
TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "d13cc5e0d0e2ec0d878bbf6276325040")
CREDIT_NAME = "🦋 Filmy Flip Hub 🦋"
BLOGGER_URL = "https://filmyflip1.blogspot.com/p/download.html"
LOG_CHANNEL = "@filmyflip_screenshots"

# --- BOT SETUP ---
app = Client(
    "filmy_pro_v15_final", 
    api_id=API_ID, 
    api_hash=API_HASH, 
    bot_token=BOT_TOKEN, 
    parse_mode=enums.ParseMode.HTML,
    workers=4, 
    max_concurrent_transmissions=4
)

# --- GLOBAL VARIABLES ---
user_modes = {}
batch_data = {}
download_queue = {} 
cleaner_dict = {} 

# --- WEB SERVER ---
routes = web.RouteTableDef()
@routes.get("/", allow_head=True)
async def root_route_handler(request):
    return web.json_response({"status": "running"})

# --- HELPER FUNCTIONS ---
def humanbytes(size):
    if not size: return "0 B"
    power = 2**10; n = 0
    dic_power = {0: ' ', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
    while size > power: 
        size /= power
        n += 1
    return str(round(size, 2)) + " " + dic_power[n] + 'B'

def get_duration(filepath):
    try:
        metadata = extractMetadata(createParser(filepath))
        if metadata.has("duration"): return metadata.get('duration').seconds
    except: pass
    return 0

def get_duration_str(duration):
    if not duration: return "0s"
    m, s = divmod(int(duration), 60); h, m = divmod(m, 60)
    return f"{h}h {m}m {s}s" if h > 0 else f"{m}m {s}s"

async def get_real_filename(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, allow_redirects=True, timeout=10) as resp:
                if "Content-Disposition" in resp.headers:
                    cd = resp.headers["Content-Disposition"]
                    fname_match = re.search(r'filename="?([^"]+)"?', cd)
                    if fname_match: return unquote(fname_match.group(1))
    except: pass
    return unquote(url.split("/")[-1].split("?")[0])

def clean_filename(name):
    for old_word, new_word in cleaner_dict.items():
        if old_word in name: 
            name = name.replace(old_word, new_word)
    return name.strip()

# --- LOGIC ---
def get_strict_se_info(name):
    se = re.search(r'\b[Ss](\d+)\b', name)
    ep = re.search(r'\b(?:[Ee]|[Ee][Pp]|[Ee][Pp][Ii])(\d+)\b', name)
    s = se.group(1) if se else None
    e = ep.group(1) if ep else None
    return s, e

def get_fancy_caption(filename, filesize, duration=0):
    final_display_name = clean_filename(filename)
    safe_name = html.escape(final_display_name)
    caption = f"<b>{safe_name}</b>\n\n"
    s, e = get_strict_se_info(final_display_name)
    if s: caption += f"💿 <b>Season ➥ {s.zfill(2)}</b>\n"
    if e: caption += f"📺 <b>Episode ➥ {e.zfill(2)}</b>\n"
    if s or e: caption += "\n"
    caption += f"<blockquote><b>File Size ♻️ ➥ {filesize}</b></blockquote>\n"
    caption += f"<blockquote><b>Duration ⏰ ➥ {get_duration_str(duration)}</b></blockquote>\n"
    caption += f"<blockquote><b>Powered By ➥ {CREDIT_NAME}</b></blockquote>"
    return caption

def apply_watermark(base_path, wm_path):
    try:
        base = Image.open(base_path).convert("RGBA")
        wm = Image.open(wm_path).convert("RGBA")
        base_w, base_h = base.size
        new_wm_w = int(base_w * 0.70)
        wm = wm.resize((new_wm_w, int(wm.size[1] * (new_wm_w/wm.size[0]))), Image.Resampling.LANCZOS)
        x = (base_w - new_wm_w) // 2
        y = base_h - wm.size[1] - 20 
        base.paste(wm, (x, y), wm)
        base.convert("RGB").save(base_path, "JPEG")
        return base_path
    except: return base_path

async def progress(current, total, message, start_time, task_name):
    now = time.time()
    diff = now - start_time
    if round(diff % 5.00) == 0 or current == total:
        percentage = current * 100 / total
        completed = int(percentage // 10)
        bar = "■" * completed + "□" * (10 - completed)
        speed = current / diff if diff > 0 else 0
        eta = get_duration_str(round((total - current) / speed)) if speed > 0 else "0s"
        await message.edit(f"<b>{task_name}</b>\n\n<b>Progress:</b> [{bar}] {round(percentage, 1)}%\n<b>📂 Done:</b> {humanbytes(current)} / {humanbytes(total)}\n<b>⚡ Speed:</b> {humanbytes(speed)}/s\n<b>⏳ ETA:</b> {eta}")

async def send_to_channel_logic(client, path, clean_name, uid):
    s, e = get_strict_se_info(clean_name)
    se_text = f" | 📺 Season: {s}" if s else ""
    se_text += f" | 🧩 Episode: {e}" if e else ""
    try:
        await client.send_message(LOG_CHANNEL, f"✨ <b>New Upload</b>\n🎬 <b>Title:</b> {clean_name}{se_text}")
    except Exception as e:
        try: await client.send_message(uid, f"⚠️ <b>Channel Title Error:</b> {e}")
        except: pass

    duration = get_duration(path)
    ss_files = []
    for i in range(1, 11):
        ts = (duration // 11) * i
        out = f"ss_{uid}_{i}.jpg"
        os.system(f'ffmpeg -ss {ts} -i "{path}" -frames:v 1 "{out}" -y -loglevel quiet')
        if os.path.exists(out):
            if os.path.exists(f"watermarks/{uid}.png"):
                apply_watermark(out, f"watermarks/{uid}.png")
            ss_files.append(out)
    if ss_files:
        for photo_path in ss_files:
            try: await client.send_photo(LOG_CHANNEL, photo=photo_path)
            except: pass
        for f in ss_files:
            if os.path.exists(f): os.remove(f)

# --- COMMANDS ---
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    await message.reply_text(f"👋 <b>Hello {message.from_user.first_name}!</b>\nCommands: /add, /caption, /ss, /batch, /link")

@app.on_message(filters.command("caption") & filters.private)
async def set_caption_mode(client, message):
    user_modes[message.from_user.id] = "caption"
    await message.reply_text("📝 <b>Caption Mode ON!</b>")

@app.on_message(filters.command("add") & filters.private)
async def add_clean(client, message):
    if len(message.command) < 2: return await message.reply_text("Usage: /add Word")
    cleaner_dict[message.command[1]] = " ".join(message.command[2:]) if len(message.command) > 2 else " Filmy Flip Hub"
    await message.reply_text(f"✅ Added: {message.command[1]}")

@app.on_message(filters.command("ss") & filters.private)
async def manual_ss(client, message):
    v = await message.chat.ask("🎬 <b>Video bhejein:</b>")
    status = await message.reply("⏳ <b>Processing...</b>")
    path = await client.download_media(v)
    real_name = "Video"
    if v.video: real_name = v.video.file_name or "Video"
    elif v.document: real_name = v.document.file_name or "File"
    await send_to_channel_logic(client, path, real_name, message.from_user.id)
    await status.edit("✅ <b>Process Complete!</b>")
    if os.path.exists(path): os.remove(path)

# --- LINK CONVERTER MODE ---
@app.on_message(filters.command("link") & filters.private)
async def link_mode_toggle(client, message):
    user_modes[message.from_user.id] = "link"
    await message.reply_text("🔗 <b>Link Convert Mode ON!</b>\n\nAb aap File Store Bot ke links bhejein, main unhe Blogger Links me badal dunga.\n\n(Mode hatane ke liye /caption dabayein)")

# --- URL HANDLER (Direct Downloads) ---
@app.on_message(filters.private & filters.regex(r"^https?://"))
async def url_handler(client, message):
    uid = message.from_user.id
    
    # Agar Link Mode ON hai, to download mat karo, convert karo
    if user_modes.get(uid) == "link":
        # Let text_handler handle it
        await text_handler(client, message)
        return

    status = await message.reply_text("🔗 <b>Checking...</b>")
    real_name = await get_real_filename(message.text)
    prompt = await message.reply_text(f"📂 <b>File:</b> <code>{real_name}</code>\n📝 <b>New Name bhejein:</b>")
    download_queue[uid] = {
        'url': message.text, 
        'original_name': real_name,
        'msg_ids_to_delete': [message.id, status.id, prompt.id]
    }

# --- MEDIA HANDLER ---
@app.on_message(filters.private & (filters.photo | filters.document | filters.video | filters.audio))
async def media_handler(client, message):
    uid = message.from_user.id
    is_image = False
    if message.photo: is_image = True
    elif message.document and (message.document.mime_type or "").startswith("image/"): is_image = True

    if is_image:
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🖼 Save Thumb", callback_data="save_thumb"), InlineKeyboardButton("💧 Save Watermark", callback_data="save_wm")]])
        await message.reply_text("📸 <b>Image Detected!</b>", reply_markup=btn, quote=True)
        return

    if user_modes.get(uid) == "caption":
        media = message.document or message.video or message.audio
        if media:
            file_name = getattr(media, "file_name", "Unknown File")
            file_size = getattr(media, "file_size", 0)
            duration = getattr(media, "duration", 0)
            cap = get_fancy_caption(file_name, humanbytes(file_size), duration)
            await message.copy(uid, caption=cap)
        return

    if uid in batch_data and 'step' not in batch_data[uid]:
        batch_data[uid]['files'].append(message)
        await message.reply_text(f"✅ Added to Batch (Total: {len(batch_data[uid]['files'])})")

@app.on_callback_query(filters.regex("^save_"))
async def save_img_callback(client, callback):
    uid = callback.from_user.id
    mode = "thumbnails" if "thumb" in callback.data else "watermarks"
    os.makedirs(mode, exist_ok=True)
    path = f"{mode}/{uid}.{'png' if mode == 'watermarks' else 'jpg'}"
    await callback.message.edit("⏳ <b>Saving...</b>")
    try:
        reply = callback.message.reply_to_message
        temp = await client.download_media(reply, file_name=f"downloads/{uid}_temp")
        img = Image.open(temp).convert("RGBA" if mode == "watermarks" else "RGB")
        img.save(path, "PNG" if mode == "watermarks" else "JPEG")
        os.remove(temp)
        await callback.message.edit(f"✅ <b>Saved as {mode[:-1]}!</b>")
    except Exception as e: await callback.message.edit(f"❌ Error: {e}")

# --- BATCH ---
@app.on_message(filters.command("batch") & filters.private)
async def batch_start(client, message):
    batch_data[message.from_user.id] = {'files': []}
    await message.reply_text("📦 <b>Batch Mode ON!</b>\nFiles forward karein, fir /done dabayein.")

@app.on_message(filters.command("done") & filters.private)
async def batch_done(client, message):
    uid = message.from_user.id
    if uid in batch_data:
        batch_data[uid]['step'] = 'naming'
        await message.reply_text("📝 <b>Batch Name bhejein:</b>\n(e.g., 'Mirzapur')")
    else:
        await message.reply_text("⚠️ Pehle /batch start karein.")

# 🔥 MAIN TEXT HANDLER (URL Name, Batch Name, Link Convert)
@app.on_message(filters.private & filters.text)
async def text_handler(client, message):
    if message.text.startswith("/"): return
    uid = message.from_user.id
    
    # 1. LINK CONVERT MODE
    if user_modes.get(uid) == "link":
        user_link = message.text
        # Logic: Extract 'start' param from Telegram link if possible
        code = ""
        if "start=" in user_link:
            try: code = user_link.split("start=")[1].split()[0]
            except: pass
        elif "file=" in user_link:
             try: code = user_link.split("file=")[1].split()[0]
             except: pass
        
        # Agar code nahi mila, to pure link ko encode kar do (Fallback)
        if not code:
             # Simple logic: assume user sent ID or clean link
             # Or just use the whole text if it looks like an ID
             code = user_link.strip()

        # Final Blogger Link
        final_link = f"{BLOGGER_URL}?file={code}"
        await message.reply_text(f"🔗 <b>Blogger Link:</b>\n<code>{final_link}</code>")
        return

    # 2. URL Uploader Name Input
    if uid in download_queue and 'name' not in download_queue[uid]:
        download_queue[uid]['name'] = message.text
        # Auto Delete Logic
        try: await message.delete()
        except: pass
        if 'msg_ids_to_delete' in download_queue[uid]:
            try: await client.delete_messages(message.chat.id, download_queue[uid]['msg_ids_to_delete'])
            except: pass

        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🎥 Video", callback_data="dl_vid"), InlineKeyboardButton("📁 File", callback_data="dl_doc")]])
        await message.reply_text(f"✅ Name: <b>{message.text}</b>\nFormat select karein:", reply_markup=btn)
        return

    # 3. Batch Naming
    if uid in batch_data and batch_data[uid].get('step') == 'naming':
        batch_data[uid]['name'] = message.text
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🎥 Start Video", callback_data="batch_run_vid"), InlineKeyboardButton("📁 Start File", callback_data="batch_run_doc")]])
        await message.reply_text(f"✅ Batch Name: {message.text}\nStart Processing?", reply_markup=btn)
        return

# --- PROCESS HANDLERS ---
@app.on_callback_query(filters.regex("^dl_"))
async def dl_process(client, callback):
    uid = callback.from_user.id
    data = download_queue.get(uid)
    if not data: return await callback.answer("Expired!")
    url = data['url']; custom_name = data['name']
    mode = "video" if "vid" in callback.data else "doc"
    
    await callback.message.delete()
    status = await callback.message.reply_text("📥 <b>Connecting...</b>")
    path = ""
    try:
        start = time.time()
        ext = os.path.splitext(data['original_name'])[1] or ".mkv"
        final_fname = clean_filename(f"{custom_name}{ext}")
        path = f"downloads/{uid}_{final_fname}"
        os.makedirs("downloads", exist_ok=True)
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                with open(path, "wb") as f:
                    dl = 0
                    async for chunk in resp.content.iter_chunked(1024*1024):
                        if uid not in download_queue: return
                        f.write(chunk); dl += len(chunk)
                        if time.time() - start > 5: await progress(dl, total, status, start, f"📥 Downloading")
        
        await send_to_channel_logic(client, path, custom_name, uid)
        
        await status.edit("📤 <b>Uploading...</b>")
        duration = get_duration(path)
        cap = get_fancy_caption(final_fname, humanbytes(os.path.getsize(path)), duration)
        thumb_path = f"thumbnails/{uid}.jpg" if os.path.exists(f"thumbnails/{uid}.jpg") else None
        if not thumb_path and os.path.exists(f"watermarks/{uid}.png"): thumb_path = f"watermarks/{uid}.png"
        
        if mode == "video": await client.send_video(uid, path, caption=cap, duration=duration, thumb=thumb_path, progress=progress, progress_args=(status, time.time(), "📤 Uploading"))
        else: await client.send_document(uid, path, caption=cap, thumb=thumb_path, progress=progress, progress_args=(status, time.time(), "📤 Uploading"))
    
    except Exception as e: await status.edit(f"❌ Error: {e}")
    finally:
        if path and os.path.exists(path): os.remove(path)
        if uid in download_queue: del download_queue[uid]
        try: await status.delete()
        except: pass

@app.on_callback_query(filters.regex("^batch_run_"))
async def batch_run(client, callback):
    uid = callback.from_user.id
    files = batch_data[uid]['files']; base = batch_data[uid]['name']
    mode = "video" if "vid" in callback.data else "doc"
    status = await callback.message.edit("🚀 <b>Processing Batch...</b>")
    for i, msg in enumerate(files):
        path = ""
        try:
            media = msg.video or msg.document
            path = await client.download_media(media)
            ext = os.path.splitext(media.file_name or "")[1] or ".mkv"
            s, e = get_strict_se_info(media.file_name or "")
            if s and e:
                new_name = f"{base} S{s}E{e}{ext}"
            else:
                new_name = f"{base} - {i+1}{ext}"
            
            cap = get_fancy_caption(new_name, humanbytes(os.path.getsize(path)), get_duration(path))
            await send_to_channel_logic(client, path, new_name, uid)
            if mode == "video": await client.send_video(uid, path, caption=cap)
            else: await client.send_document(uid, path, caption=cap)
        except: pass
        finally:
            if path and os.path.exists(path): os.remove(path)
    await status.edit("✅ Batch Complete!")
    del batch_data[uid]

# --- START ---
async def start_services():
    web_app = web.Application(client_max_size=30000000)
    web_app.add_routes(routes)
    runner = web.AppRunner(web_app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", int(os.environ.get("PORT", 8080))).start()
    await app.start()
    print("Bot Started")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(start_services())
        
