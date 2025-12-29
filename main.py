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
from aiohttp import web
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ForceReply

# --- CONFIGURATION ---
API_ID = int(os.environ.get("API_ID", "12345"))
API_HASH = os.environ.get("API_HASH", "hash")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "token")
TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "02a832d91755c2f5e8a2d1a6740a8674")
CREDIT_NAME = "🦋 Filmy Flip Hub 🦋"
BLOGGER_URL = "https://filmyflip1.blogspot.com/p/download.html"

# --- BOT SETUP ---
app = Client(
    "filmy_ultimate", 
    api_id=API_ID, 
    api_hash=API_HASH, 
    bot_token=BOT_TOKEN, 
    parse_mode=enums.ParseMode.HTML
)

# --- GLOBAL VARS ---
user_modes = {}
batch_data = {}
download_queue = {}
cleaner_dict = {} # For /add and /del

# --- WEB SERVER ---
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

def clean_filename(name):
    for k, v in cleaner_dict.items():
        name = name.replace(k, v)
    return name.strip()

def get_fancy_caption(filename, filesize, duration=0):
    safe_name = html.escape(filename)
    caption = f"<b>{safe_name}</b>\n\n"
    s, e = get_media_info(filename)
    if s: caption += f"💿 <b>Season ➥ {s}</b>\n"
    if e: caption += f"📺 <b>Episode ➥ {e}</b>\n"
    if s or e: caption += "\n"
    caption += f"<blockquote><b>File Size ♻️ ➥ {filesize}</b></blockquote>\n"
    if duration > 0: caption += f"<blockquote><b>Duration ⏰ ➥ {get_duration_str(duration)}</b></blockquote>\n"
    caption += f"<blockquote><b>Powered By ➥ {CREDIT_NAME}</b></blockquote>"
    return caption

# --- PROGRESS BAR (STATUS) ---
async def progress(current, total, message, start_time, status_text):
    now = time.time()
    diff = now - start_time
    if round(diff % 5.00) == 0 or current == total:
        percentage = current * 100 / total
        speed = current / diff if diff > 0 else 0
        eta = time.strftime('%H:%M:%S', time.gmtime(round((total - current) / speed))) if speed > 0 else "00:00:00"
        try:
            btn = InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_task")]])
            await message.edit(
                f"{status_text}\n\n"
                f"📊 <b>Progress:</b> {round(percentage, 1)}%\n"
                f"🚀 <b>Speed:</b> {humanbytes(speed)}/s\n"
                f"⏳ <b>ETA:</b> {eta}",
                reply_markup=btn
            )
        except: pass

# --- COMMANDS ---
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    await message.reply_text(
        f"👋 <b>Hello {message.from_user.first_name}!</b>\n\n"
        "🛠 <b>AVAILABLE COMMANDS:</b>\n"
        "🔹 <code>/search Name</code> - Poster with Logo\n"
        "🔹 <code>/caption</code> - Caption Mode (Green Line)\n"
        "🔹 <code>/batch</code> - Batch Rename Mode\n"
        "🔹 <code>/done</code> - Process Batch\n"
        "🔹 <code>/url</code> - URL Upload Mode\n"
        "🔹 <code>/link</code> - Blogger Link Gen\n"
        "🔹 <code>/watermark</code> - Set Thumbnail\n"
        "🔹 <code>/add word</code> - Add to Cleaner\n"
        "🔹 <code>/del word</code> - Remove from Cleaner\n\n"
        "⚠️ <b>Note:</b> Single Rename Disabled."
    )

# --- MODE SWITCHERS ---
@app.on_message(filters.command("caption") & filters.private)
async def set_caption(client, message):
    user_modes[message.from_user.id] = "caption"
    await message.reply_text("📝 <b>Caption Mode ON!</b>")

@app.on_message(filters.command("link") & filters.private)
async def set_link(client, message):
    user_modes[message.from_user.id] = "link"
    await message.reply_text("🔗 <b>Link Mode ON!</b>")

@app.on_message(filters.command("url") & filters.private)
async def set_url(client, message):
    user_modes[message.from_user.id] = "url"
    await message.reply_text("🌐 <b>URL Mode ON!</b> Link bhejein.")

@app.on_message(filters.command("watermark") & filters.private)
async def set_thumb(client, message):
    await message.reply_text("🖼 <b>Send Photo</b> to set as Thumbnail.")

# --- CLEANER COMMANDS ---
@app.on_message(filters.command("add") & filters.private)
async def add_clean(client, message):
    if len(message.command) < 2: return await message.reply_text("Usage: <code>/add word</code>")
    word = message.command[1]
    cleaner_dict[word] = ""
    await message.reply_text(f"✅ Added '<b>{word}</b>' to cleaner.")

@app.on_message(filters.command("del") & filters.private)
async def del_clean(client, message):
    if len(message.command) < 2: return await message.reply_text("Usage: <code>/del word</code>")
    word = message.command[1]
    if word in cleaner_dict:
        del cleaner_dict[word]
        await message.reply_text(f"🗑 Removed '<b>{word}</b>' from cleaner.")
    else:
        await message.reply_text("❌ Word not found.")

@app.on_message(filters.command("words") & filters.private)
async def view_clean(client, message):
    await message.reply_text(f"📋 <b>Cleaner Words:</b>\n{', '.join(cleaner_dict.keys())}")

# --- BATCH COMMANDS ---
@app.on_message(filters.command("batch") & filters.private)
async def batch_cmd(client, message):
    uid = message.from_user.id
    batch_data[uid] = {'files': []}
    await message.reply_text("📦 <b>Batch Mode ON!</b>\nFiles forward karein, fir <code>/done</code> likhein.")

@app.on_message(filters.command("done") & filters.private)
async def batch_done(client, message):
    uid = message.from_user.id
    if uid in batch_data and batch_data[uid]['files']:
        await message.reply_text("📝 <b>Series Name Bhejein:</b>", reply_markup=ForceReply(True))
        batch_data[uid]['step'] = 'naming'
    else:
        await message.reply_text("⚠️ Pehle kuch files bhejein!")

# --- SEARCH (LOGO FIX) ---
@app.on_message(filters.command(["search", "series"]))
async def search_handler(client, message):
    if len(message.command) < 2: return await message.reply_text("Usage: /search Name")
    query = " ".join(message.command[1:])
    stype = "tv" if "series" in message.command[0] else "movie"
    status = await message.reply_text("🔎 Searching...")
    try:
        url = f"https://api.themoviedb.org/3/search/{stype}?api_key={TMDB_API_KEY}&query={query}"
        res = requests.get(url).json().get('results')
        if not res: return await status.edit("❌ Not Found")
        top = res[0]
        img_url = f"https://api.themoviedb.org/3/{stype}/{top['id']}/images?api_key={TMDB_API_KEY}&include_image_language=en,hi"
        posters = requests.get(img_url).json().get('posters', [])
        final_poster = posters[0]['file_path'] if posters else top.get('poster_path')
        if not final_poster: return await status.edit("❌ No Logo Poster Found")
        
        caption = f"🎬 <b>{top.get('name') if stype=='tv' else top.get('title')}</b>"
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🖼 Get Poster", callback_data=f"get_poster_{stype}_{top['id']}")]])
        await status.delete()
        await message.reply_photo(f"https://image.tmdb.org/t/p/w500{final_poster}", caption=caption, reply_markup=btn)
    except Exception as e: await status.edit(f"Error: {e}")

@app.on_callback_query(filters.regex("^get_"))
async def get_callback(client, callback):
    try:
        _, _, stype, mid = callback.data.split("_")
        url = f"https://api.themoviedb.org/3/{stype}/{mid}/images?api_key={TMDB_API_KEY}&include_image_language=en,hi"
        data = requests.get(url).json().get('posters', [])[:3]
        for img in data:
            await client.send_photo(callback.from_user.id, f"https://image.tmdb.org/t/p/original{img['file_path']}")
        await callback.answer()
    except: pass

# --- URL UPLOADER ---
@app.on_message(filters.private & filters.regex(r"^https?://"))
async def url_handler(client, message):
    uid = message.from_user.id
    url = message.text.strip()
    await message.reply_text(
        "🔗 <b>Link Detected!</b>\nDownload as:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🎥 Video", callback_data=f"dl_vid"), InlineKeyboardButton("📁 File", callback_data=f"dl_doc")]
        ]),
        quote=True
    )
    download_queue[uid] = url

@app.on_callback_query(filters.regex("^dl_"))
async def process_url(client, callback):
    uid = callback.from_user.id
    url = download_queue.get(uid)
    if not url: return await callback.answer("Link Expired!")
    
    mode = "video" if "vid" in callback.data else "doc"
    await callback.message.delete()
    status = await callback.message.reply_text("📥 <b>Downloading...</b>")
    
    fname = url.split("/")[-1] or "downloaded_file"
    path = f"downloads/{uid}_{fname}"
    os.makedirs("downloads", exist_ok=True)
    
    try:
        start = time.time()
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                with open(path, "wb") as f:
                    dl = 0
                    async for chunk in resp.content.iter_chunked(1024*1024):
                        if uid not in download_queue: # Check cancel
                            await status.edit("❌ Cancelled"); return
                        f.write(chunk); dl += len(chunk)
                        if time.time() - start > 5: await progress(dl, total, status, start, "📥 Downloading")
        
        await status.edit("📤 <b>Uploading...</b>")
        file_size = humanbytes(os.path.getsize(path))
        cap = get_fancy_caption(fname, file_size)
        thumb_path = f"thumbnails/{uid}.jpg" if os.path.exists(f"thumbnails/{uid}.jpg") else None
        
        start = time.time()
        if mode == "video":
            await client.send_video(uid, path, caption=cap, thumb=thumb_path, progress=progress, progress_args=(status, start, "📤 Uploading"))
        else:
            await client.send_document(uid, path, caption=cap, thumb=thumb_path, progress=progress, progress_args=(status, start, "📤 Uploading"))
        
        os.remove(path) # Auto Delete
        await status.delete() # Auto Delete Status
        del download_queue[uid]
    except Exception as e:
        await status.edit(f"❌ Error: {e}")

# --- CANCEL HANDLER ---
@app.on_callback_query(filters.regex("cancel_task"))
async def cancel_task(client, callback):
    uid = callback.from_user.id
    if uid in download_queue: del download_queue[uid]
    if uid in batch_data: del batch_data[uid]
    await callback.answer("❌ Task Cancelled!")
    await callback.message.delete()

# --- TEXT & FILE HANDLER ---
@app.on_message(filters.private & filters.text)
async def handle_text(client, message):
    if message.text.startswith("/"): return
    uid = message.from_user.id
    text = message.text.strip()
    
    # Batch Naming
    if uid in batch_data and batch_data[uid].get('step') == 'naming':
        batch_data[uid]['name'] = text
        await message.reply_text(
            f"✅ Name: <b>{text}</b>\nFormat Select:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎥 Video", callback_data="batch_run_vid"), InlineKeyboardButton("📁 File", callback_data="batch_run_doc")]])
        )
        return

    # Link Gen
    if user_modes.get(uid) == "link":
        code = text.split("?start=")[1].split()[0] if "?start=" in text else text
        enc = base64.b64encode(code.encode()).decode()
        await message.reply_text(f"🔗 <code>{BLOGGER_URL}?data={enc}</code>")

@app.on_callback_query(filters.regex("^batch_run_"))
async def run_batch(client, callback):
    uid = callback.from_user.id
    mode = "video" if "vid" in callback.data else "doc"
    files = batch_data[uid]['files']
    base_name = batch_data[uid]['name']
    
    status = await callback.message.edit("🚀 <b>Batch Started!</b>")
    total = len(files)
    
    for i, msg in enumerate(files):
        try:
            if uid not in batch_data: break # Cancel check
            media = msg.document or msg.video or msg.audio
            s, e = get_media_info(media.file_name or "")
            ext = os.path.splitext(media.file_name or "")[1] or ".mkv"
            
            new_name = f"{base_name} - S{s}E{e}{ext}" if s and e else f"{base_name} - {i+1}{ext}"
            new_name = clean_filename(new_name) # Apply Cleaner
            
            path = await client.download_media(media, file_name=f"downloads/{new_name}")
            cap = get_fancy_caption(new_name, humanbytes(os.path.getsize(path)))
            thumb_path = f"thumbnails/{uid}.jpg" if os.path.exists(f"thumbnails/{uid}.jpg") else None
            
            if mode == "video": await client.send_video(uid, path, caption=cap, thumb=thumb_path)
            else: await client.send_document(uid, path, caption=cap, thumb=thumb_path)
            
            os.remove(path) # Auto Delete
            await status.edit(f"✅ Processed: {i+1}/{total}")
        except: pass
    
    await status.edit("🎉 <b>Batch Complete!</b>")
    if uid in batch_data: del batch_data[uid]

@app.on_message(filters.private & filters.photo)
async def save_thumb(client, message):
    uid = message.from_user.id
    path = f"thumbnails/{uid}.jpg"
    os.makedirs("thumbnails", exist_ok=True)
    await client.download_media(message, path)
    await message.reply_text("✅ <b>Thumbnail Saved!</b>")

@app.on_message(filters.private & (filters.document | filters.video | filters.audio))
async def handle_files(client, message):
    uid = message.from_user.id
    
    # Batch Collection
    if uid in batch_data and 'step' not in batch_data[uid]:
        batch_data[uid]['files'].append(message)
        return

    # Caption Mode
    if user_modes.get(uid) == "caption":
        media = message.document or message.video or message.audio
        cap = get_fancy_caption(media.file_name or "File", humanbytes(getattr(media, "file_size", 0)), getattr(media, "duration", 0))
        if message.video: await client.send_video(uid, media.file_id, caption=cap)
        else: await client.send_document(uid, media.file_id, caption=cap)

# --- START SERVICES ---
async def start_services():
    web_app = await web_server()
    runner = web.AppRunner(web_app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", int(os.environ.get("PORT", 8080))).start()
    await app.start()
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(start_services())
            
