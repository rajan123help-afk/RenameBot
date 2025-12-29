import os
import time
import math
import base64
import re
import asyncio
import requests
import shutil
from aiohttp import web
import aiofiles
from PIL import Image
from hachoir.metadata import extractMetadata
from hachoir.parser import createParser
# 🔥 IMPORTANT: enums import karna zaroori hai styling ke liye
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ForceReply

# --- CONFIGURATION ---
API_ID = int(os.environ.get("API_ID", "12345"))
API_HASH = os.environ.get("API_HASH", "hash")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "token")
TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "02a832d91755c2f5e8a2d1a6740a8674") 
CREDIT_NAME = "🦋 Filmy Flip Hub 🦋"
BLOGGER_URL = "https://filmyflip1.blogspot.com/p/download.html"

# 🔥 FIX: Global Parse Mode HTML set kiya
app = Client(
    "filmy_bot", 
    api_id=API_ID, 
    api_hash=API_HASH, 
    bot_token=BOT_TOKEN, 
    parse_mode=enums.ParseMode.HTML
)

# --- GLOBAL VARIABLES ---
user_data = {}
batch_data = {}
download_queue = {}
user_modes = {} 
REPLACE_DICT = {}

# --- WEB SERVER (Render Keep Alive) ---
routes = web.RouteTableDef()

@routes.get("/", allow_head=True)
async def root_route_handler(request):
    return web.json_response({"status": "running"})

async def web_server():
    web_app = web.Application(client_max_size=30000000)
    web_app.add_routes(routes)
    return web_app

# --- HELPERS ---
def humanbytes(size):
    if not size: return ""
    power = 2**10
    n = 0
    dic_power = {0: ' ', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
    while size > power: size /= power; n += 1
    return str(round(size, 2)) + " " + dic_power[n] + 'B'

def get_duration_str(duration):
    if not duration: return "00:00"
    m, s = divmod(int(duration), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"

def get_media_info(name):
    s = re.search(r"[Ss](\d{1,2})", name)
    e = re.search(r"[Ee](\d{1,3})", name)
    return (s.group(1) if s else None), (e.group(1) if e else None)

# 🔥 FIX: Quote Style Check
def get_fancy_caption(filename, filesize, duration=0):
    caption = f"<b>{filename}</b>\n\n"
    s, e = get_media_info(filename)
    if s: caption += f"💿 <b>Season ➥ {s}</b>\n"
    if e: caption += f"📺 <b>Episode ➥ {e}</b>\n"
    if s or e: caption += "\n"
    
    # Ye blockquote tabhi chalega jab HTML mode ON hoga
    caption += f"<blockquote><b>File Size ♻️ ➥ {filesize}</b></blockquote>\n"
    if duration > 0: caption += f"<blockquote><b>Duration ⏰ ➥ {get_duration_str(duration)}</b></blockquote>\n"
    caption += f"<blockquote><b>Powered By ➥ {CREDIT_NAME}</b></blockquote>"
    return caption

def get_video_attributes(file_path):
    width, height, duration = 0, 0, 0
    try:
        metadata = extractMetadata(createParser(file_path))
        if metadata.has("duration"): duration = metadata.get('duration').seconds
        if metadata.has("width"): width = metadata.get("width")
        if metadata.has("height"): height = metadata.get("height")
    except: pass
    return width, height, duration

def get_extension(filename): return os.path.splitext(filename)[1]

def auto_clean(text):
    for k, v in REPLACE_DICT.items(): text = text.replace(k, v)
    return text.strip()

# --- WATERMARK ---
def apply_watermark(base_path, wm_path):
    try:
        base = Image.open(base_path).convert("RGBA")
        wm = Image.open(wm_path).convert("RGBA")
        base_w, base_h = base.size
        wm_w, wm_h = wm.size
        new_wm_w = int(base_w * 0.70)
        new_wm_h = int(wm_h * (new_wm_w / wm_w))
        wm = wm.resize((new_wm_w, new_wm_h), Image.LANCZOS)
        x = (base_w - new_wm_w) // 2
        y = base_h - new_wm_h - 20 
        base.paste(wm, (x, y), wm)
        base = base.convert("RGB")
        base.save(base_path, "JPEG")
        return base_path
    except: return base_path

# --- PROGRESS BAR ---
async def progress(current, total, message, start_time, status):
    now = time.time()
    diff = now - start_time
    if round(diff % 3.00) == 0 or current == total:
        percentage = current * 100 / total
        speed = current / diff if diff > 0 else 0
        eta = time.strftime('%H:%M:%S', time.gmtime(round((total - current) / speed))) if speed > 0 else "00:00:00"
        bar = '●' * int(percentage / 10) + '○' * (10 - int(percentage / 10))
        tmp = f"{status}\n\n[{bar}] <b>{round(percentage, 1)}%</b>\n📂 <b>Size:</b> {humanbytes(current)} / {humanbytes(total)}\n🚀 <b>Speed:</b> {humanbytes(speed)}/s\n⏳ <b>ETA:</b> {eta}"
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_process")]])
        try: await message.edit(tmp, reply_markup=btn)
        except: pass

# --- HANDLERS ---
@app.on_callback_query(filters.regex("^cancel_process"))
async def cancel_process_callback(client, callback):
    uid = callback.from_user.id
    if uid in download_queue: del download_queue[uid]
    if uid in user_data: del user_data[uid]
    if uid in batch_data: del batch_data[uid]
    await callback.answer("❌ Task Cancelled!", show_alert=True)
    try: await callback.message.edit("❌ <b>Process Stopped!</b>")
    except: await callback.message.delete()

@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    await message.reply_text(
        f"👋 <b>Hello {message.from_user.first_name}!</b>\n\n"
        "🤖 <b>Filmy Flip Hub Bot</b>\n\n"
        "📝 <b>Caption Mode:</b> <code>/caption</code>\n"
        "📁 <b>Rename:</b> <code>/rename</code>\n"
        "📦 <b>Batch:</b> <code>/batch</code>\n"
        "💧 <b>Thumbnail:</b> <code>/watermark</code>"
    )

@app.on_message(filters.command("rename") & filters.private)
async def set_rename_mode(client, message):
    user_modes[message.from_user.id] = "renamer"
    await message.reply_text("📁 <b>Renamer Mode ON!</b>")

@app.on_message(filters.command("caption") & filters.private)
async def set_caption_mode(client, message):
    user_modes[message.from_user.id] = "caption_only"
    await message.reply_text("📝 <b>Caption Mode ON!</b>\nAb file bhejo, main bas caption badal dunga.")

@app.on_message(filters.command("batch") & filters.private)
async def batch_cmd(client, message):
    uid = message.from_user.id
    batch_data[uid] = {'status': 'collecting', 'files': []}
    if uid in user_modes: del user_modes[uid]
    await message.reply_text("🚀 <b>Batch Mode ON!</b>\nFiles forward karein, fir <code>/done</code> likhein.")

@app.on_message(filters.command("done") & filters.private)
async def batch_done(client, message):
    uid = message.from_user.id
    if uid in batch_data and batch_data[uid]['files']:
        batch_data[uid]['status'] = 'wait_name'
        await message.reply_text(f"✅ <b>{len(batch_data[uid]['files'])} Files collected.</b>\nAb Series Name bhejein:")
    else: await message.reply_text("⚠️ Pehle files bhejein!")

@app.on_message(filters.command("watermark") & filters.private)
async def watermark_cmd(client, message):
    await message.reply_text("🖼 <b>Ab Photo Bhejein!</b> (Thumbnail/Watermark ke liye)")

@app.on_message(filters.command("link") & filters.private)
async def set_link_mode(client, message):
    user_modes[message.from_user.id] = "blogger_link"
    await message.reply_text("🔗 <b>Link Mode ON!</b>")

@app.on_message(filters.command("url") & filters.private)
async def set_url_mode(client, message):
    user_modes[message.from_user.id] = "url"
    await message.reply_text("🌐 <b>URL Mode ON!</b>")

@app.on_message(filters.command(["search", "series"]))
async def search_handler(client, message):
    if len(message.command) < 2: return await message.reply_text("Usage: /search Name")
    query_list = message.command[1:]
    raw_text = " ".join(query_list).lower()
    match = re.search(r'\b(?:s|season)\s?(\d{1,2})\b', raw_text)
    
    ignore = ["full", "movie", "hindi", "dubbed", "hd", "series", "season"]
    clean = [w for w in query_list if w.lower() not in ignore and not re.match(r'^s\d+$', w.lower())]
    query = " ".join(clean)
    stype = "tv" if "series" in message.command[0] else "movie"
    
    status = await message.reply_text(f"🔎 Searching: <code>{query}</code>...")
    try:
        url = f"https://api.themoviedb.org/3/search/{stype}?api_key={TMDB_API_KEY}&query={query}"
        res = requests.get(url).json()['results'][0]
        mid = res['id']
        title = res.get('name') if stype == "tv" else res.get('title')
        
        img_url = f"https://api.themoviedb.org/3/{stype}/{mid}/images?api_key={TMDB_API_KEY}&include_image_language=en,hi"
        poster = requests.get(img_url).json().get('posters', [res])[0].get('file_path', res.get('poster_path'))
        
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🖼 Poster", callback_data=f"img_poster_{stype}_{mid}"), InlineKeyboardButton("🎞 Thumbnail", callback_data=f"img_backdrop_{stype}_{mid}")]])
        caption = f"🎬 <b>{title}</b>\n⭐️ {res.get('vote_average')}\n\n👇 Select:"
        await status.delete()
        await message.reply_photo(f"https://image.tmdb.org/t/p/w500{poster}", caption=caption, reply_markup=btn)
    except Exception as e: await status.edit(f"❌ Error: {e}")

@app.on_callback_query(filters.regex("^img_"))
async def img_type_callback(client, callback):
    _, img_type, stype, mid = callback.data.split("_")
    btn = InlineKeyboardMarkup([
            [InlineKeyboardButton("1", callback_data=f"cnt_1_{img_type}_{stype}_{mid}"),
             InlineKeyboardButton("2", callback_data=f"cnt_2_{img_type}_{stype}_{mid}")],
            [InlineKeyboardButton("3", callback_data=f"cnt_3_{img_type}_{stype}_{mid}"),
             InlineKeyboardButton("4", callback_data=f"cnt_4_{img_type}_{stype}_{mid}")]
        ])
    await callback.message.edit(f"✅ <b>{img_type.capitalize()} Selected!</b>\nHow many?", reply_markup=btn)

@app.on_callback_query(filters.regex("^cnt_"))
async def img_process_callback(client, callback):
    uid = callback.from_user.id
    try:
        _, count, img_type, stype, mid = callback.data.split("_")
        count = int(count)
        await callback.message.edit("⏳ <b>Downloading...</b>")
        
        url_logo = f"https://api.themoviedb.org/3/{stype}/{mid}/images?api_key={TMDB_API_KEY}&include_image_language=en,hi"
        data_logo = requests.get(url_logo).json()
        key = 'posters' if img_type == 'poster' else 'backdrops'
        pool = data_logo.get(key, [])
        if len(pool) < count:
            url_clean = f"https://api.themoviedb.org/3/{stype}/{mid}/images?api_key={TMDB_API_KEY}&include_image_language=null"
            data_clean = requests.get(url_clean).json()
            pool.extend(data_clean.get(key, []))
        
        if not pool: return await callback.message.edit("❌ No images found!")
        images = pool[:count]
        wm_path = f"watermarks/{uid}.jpg"
        has_wm = os.path.exists(wm_path)
        for i, img in enumerate(images):
            img_url = f"https://image.tmdb.org/t/p/w500{img['file_path']}"
            fpath = f"downloads/{mid}_{i}.jpg"
            os.makedirs("downloads", exist_ok=True)
            with open(fpath, 'wb') as f: f.write(requests.get(img_url).content)
            if has_wm: apply_watermark(fpath, wm_path)
            await client.send_photo(uid, fpath, caption=f"🦋 <b>Filmy Flip Hub</b>")
            os.remove(fpath)
        await callback.message.delete()
    except Exception as e: await callback.message.edit(f"❌ Error: {e}")

@app.on_message(filters.private & filters.photo)
async def handle_photos(client, message):
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("🖼 Thumbnail", callback_data="save_thumb"),
         InlineKeyboardButton("💧 Watermark", callback_data="save_wm")]
    ])
    await message.reply_text("<b>📸 Photo Detected!</b>\nSave as:", reply_markup=btn, quote=True)

@app.on_callback_query(filters.regex("save_"))
async def save_callback(client, callback):
    uid = callback.from_user.id
    try:
        await callback.answer("Saving...")
        path = f"thumbnails/{uid}.jpg" if "thumb" in callback.data else f"watermarks/{uid}.jpg"
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if callback.message.reply_to_message:
            await client.download_media(callback.message.reply_to_message, path)
            await callback.message.edit_text("✅ <b>Saved Successfully!</b>")
        else: await callback.message.edit_text("❌ Error")
    except Exception as e: await callback.message.edit_text(f"❌ Error: {e}")

@app.on_message(filters.private & filters.text)
async def handle_text(client, message):
    if message.text.startswith("/"): return
    uid, text = message.from_user.id, message.text.strip()

    if uid in batch_data and batch_data[uid]['status'] == 'wait_name':
        batch_data[uid].update({'base_name': text, 'status': 'ready'})
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🎥 Video", callback_data="batch_video"), InlineKeyboardButton("📁 File", callback_data="batch_doc")]])
        await message.reply_text(f"✅ Name set: <b>{text}</b>\nSelect Format:", reply_markup=btn)
        return

    if user_modes.get(uid) == "blogger_link" or "t.me/" in text:
        code = text.split("?start=")[1].split()[0] if "?start=" in text else text
        enc = base64.b64encode(code.encode()).decode()
        await message.reply_text(f"✅ <b>Link Ready!</b>\n\n🔗 <code>{BLOGGER_URL}?data={enc}</code>")

@app.on_message(filters.private & (filters.document | filters.video | filters.audio))
async def handle_files(client, message):
    uid = message.from_user.id
    
    # 1. Batch Collection
    if uid in batch_data and batch_data[uid]['status'] == 'collecting':
        batch_data[uid]['files'].append(message)
        return
    
    # 2. Image Check
    mime = getattr(message.document or message.video, "mime_type", "")
    if "image" in mime: return await handle_photos(client, message)

    # 3. 🔥 CAPTION MODE (Checked & Fixed)
    if user_modes.get(uid) == "caption_only":
        status = await message.reply_text("⏳ <b>Processing Caption...</b>")
        try:
            media = message.document or message.video or message.audio
            
            # Create Caption
            file_size = humanbytes(getattr(media, "file_size", 0))
            duration = getattr(media, "duration", 0) or 0
            caption = get_fancy_caption(media.file_name or "File", file_size, duration)
            
            # Send with forced HTML mode
            if message.video:
                await client.send_video(uid, media.file_id, caption=caption, parse_mode=enums.ParseMode.HTML)
            else:
                await client.send_document(uid, media.file_id, caption=caption, parse_mode=enums.ParseMode.HTML)
            
            await status.delete()
        except Exception as e:
            await status.edit(f"❌ Error: {e}")
        return

    # 4. Default Rename
    user_data[uid] = {'msg': message}
    btn = InlineKeyboardMarkup([[InlineKeyboardButton("🎥 Video", callback_data="mode_video"), InlineKeyboardButton("📁 File", callback_data="mode_document")]])
    await message.reply_text("📁 <b>File Received!</b>\nRename Format:", reply_markup=btn, quote=True)

@app.on_callback_query(filters.regex("^mode_"))
async def single_mode(client, callback):
    uid = callback.from_user.id
    user_data[uid]['mode'] = "video" if "video" in callback.data else "doc"
    await callback.message.delete()
    await client.send_message(uid, "📝 <b>New Name:</b>", reply_markup=ForceReply(True))

@app.on_callback_query(filters.regex("^batch_"))
async def batch_process(client, callback):
    uid = callback.from_user.id
    mode = "video" if "video" in callback.data else "doc"
    btn = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_process")]])
    status = await callback.message.edit_text("⏳ <b>Starting Batch...</b>", reply_markup=btn)
    
    files_list = batch_data[uid]['files']
    total = len(files_list)
    for idx, msg in enumerate(files_list):
        if uid not in batch_data: return
        media = msg.document or msg.video or msg.audio
        s, e = get_media_info(media.file_name or "")
        base = batch_data[uid]['base_name']
        ext = get_extension(media.file_name or "")
        new_name = f"{base} - S{s}E{e}{ext}" if s and e else f"{base} - E{e}{ext}"
        
        start = time.time()
        dl = await client.download_media(media, f"downloads/{new_name}", progress=progress, progress_args=(status, start, f"📥 DL {idx+1}/{total}"))
        w, h, dur = get_video_attributes(dl)
        thumb_path = f"thumbnails/{uid}.jpg" if os.path.exists(f"thumbnails/{uid}.jpg") else None
        wm_path = f"watermarks/{uid}.jpg"
        if thumb_path and os.path.exists(wm_path): thumb_path = apply_watermark(thumb_path, wm_path)
        caption = get_fancy_caption(new_name, humanbytes(os.path.getsize(dl)), dur)
        
        start = time.time()
        # 🔥 Forced HTML Parse Mode here too
        if mode == 'video':
            await client.send_video(uid, dl, caption=caption, thumb=thumb_path, duration=dur, width=w, height=h, progress=progress, progress_args=(status, start, f"📤 UL {idx+1}/{total}"), parse_mode=enums.ParseMode.HTML)
        else:
            await client.send_document(uid, dl, caption=caption, thumb=thumb_path, progress=progress, progress_args=(status, start, f"📤 UL {idx+1}/{total}"), parse_mode=enums.ParseMode.HTML)
        os.remove(dl)
    await status.edit("✅ Batch Completed!"); del batch_data[uid]

async def start_services():
    port = int(os.environ.get("PORT", 8080))
    web_app = await web_server()
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    await app.start()
    print("Bot Started!")
    await asyncio.Event().wait()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(start_services())
    
