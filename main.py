import os
import time
import math
import base64
import aiohttp
import aiofiles
import asyncio
import requests
import shutil
from aiohttp import web
from hachoir.metadata import extractMetadata
from hachoir.parser import createParser
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ForceReply

# --- CONFIGURATION ---
API_ID = int(os.environ.get("API_ID", "12345"))
API_HASH = os.environ.get("API_HASH", "hash")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "token")
TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "b3b754854b7375276e19195a63969a41") 
CREDIT_NAME = "Filmy Flip"
BLOGGER_URL = os.environ.get("BLOGGER_URL", "https://yoursite.com") # Optional for /link

app = Client("filmy_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- GLOBAL VARIABLES ---
user_data = {}
batch_data = {}
download_queue = {}
user_modes = {} 
REPLACE_DICT = {}
ACTIVE_TASKS = 0
MAX_TASK_LIMIT = 5

# --- WEB SERVER (Render Keep-Alive) ---
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
    m, s = divmod(duration, 60); h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"

def get_extension(filename): return os.path.splitext(filename)[1]

def auto_clean(text):
    for k, v in REPLACE_DICT.items(): text = text.replace(k, v)
    return text.strip()

def get_video_attributes(file_path):
    width, height, duration = 0, 0, 0
    try:
        metadata = extractMetadata(createParser(file_path))
        if metadata.has("duration"): duration = metadata.get('duration').seconds
        if metadata.has("width"): width = metadata.get("width")
        if metadata.has("height"): height = metadata.get("height")
    except: pass
    return width, height, duration

def get_media_info(name):
    import re
    s = re.search(r"[Ss](\d{1,2})", name)
    e = re.search(r"[Ee](\d{1,3})", name)
    return (s.group(1) if s else None), (e.group(1) if e else None)

async def progress(current, total, message, start_time, status):
    now = time.time()
    diff = now - start_time
    if round(diff % 5.00) == 0 or current == total:
        percentage = current * 100 / total
        speed = current / diff
        time_left = round((total - current) / speed) if speed > 0 else 0
        tmp = (f"{status}\n"
               f"[{''.join(['●' for i in range(math.floor(percentage / 5))])}{''.join(['○' for i in range(20 - math.floor(percentage / 5))])}] {round(percentage, 2)}%\n"
               f"💾 {humanbytes(current)} / {humanbytes(total)}\n"
               f"🚀 {humanbytes(speed)}/s | ⏳ {time.strftime('%H:%M:%S', time.gmtime(time_left))}")
        try: await message.edit(tmp)
        except: pass
            # --- MAIN COMMANDS ---
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    try: await message.delete()
    except: pass
    await message.reply_text(
        f"👋 <b>Hello {message.from_user.first_name}!</b>\n\n"
        "🤖 <b>Filmy Flip All-in-One Bot</b>\n\n"
        "🌐 <b>URL Mod:</b> <code>/url</code>\n"
        "🎬 <b>Search:</b> <code>/search</code>, <code>/series</code>\n"
        "📁 <b>Rename:</b> <code>/rename</code>, <code>/caption</code>\n"
        "🔗 <b>Link Gen:</b> <code>/link</code>\n"
        "📦 <b>Batch:</b> <code>/batch</code>\n"
        "🧹 <b>Cleaner:</b> <code>/add</code>, <code>/del</code>, <code>/words</code>\n"
        "💧 <b>Extra:</b> <code>/watermark</code>"
    )

@app.on_message(filters.command("rename") & filters.private)
async def set_rename_mode(client, message):
    try: await message.delete(); 
    except: pass
    user_modes[message.from_user.id] = "renamer"
    msg = await message.reply_text("📁 <b>Renamer Mode ON!</b>")
    await asyncio.sleep(3); await msg.delete()

@app.on_message(filters.command("caption") & filters.private)
async def set_caption_mode(client, message):
    try: await message.delete(); 
    except: pass
    user_modes[message.from_user.id] = "caption_only"
    msg = await message.reply_text("📝 <b>Caption Mode ON!</b>")
    await asyncio.sleep(3); await msg.delete()

@app.on_message(filters.command("link") & filters.private)
async def set_link_mode(client, message):
    try: await message.delete(); 
    except: pass
    user_modes[message.from_user.id] = "blogger_link"
    msg = await message.reply_text("🔗 <b>Link Mode ON!</b>")
    await asyncio.sleep(3); await msg.delete()

@app.on_message(filters.command("url") & filters.private)
async def set_url_mode(client, message):
    try: await message.delete(); 
    except: pass
    uid = message.from_user.id
    user_modes[uid] = "url"
    if uid in user_data: del user_data[uid]
    msg = await message.reply_text("🌐 <b>URL Mode ON!</b>")
    await asyncio.sleep(3); await msg.delete()

@app.on_message(filters.command("cancel") & filters.private)
async def cancel_task(client, message):
    try: await message.delete(); 
    except: pass
    uid = message.from_user.id
    if uid in batch_data: del batch_data[uid]
    if uid in user_data: del user_data[uid]
    if uid in download_queue: del download_queue[uid]
    msg = await message.reply_text("❌ <b>Task Cancelled!</b>")
    await asyncio.sleep(3); await msg.delete()

# --- WORDS CLEANER COMMANDS ---
@app.on_message(filters.command("add") & filters.private)
async def add_word(client, message):
    try: await message.delete()
    except: pass
    if len(message.command) < 2: return 
    for word in message.command[1:]: REPLACE_DICT[word] = ""
    msg = await message.reply_text(f"✅ Added: {message.command[1:]}")
    await asyncio.sleep(3); await msg.delete()

@app.on_message(filters.command("del") & filters.private)
async def del_word(client, message):
    try: await message.delete()
    except: pass
    if len(message.command) < 2: return 
    deleted = [w for w in message.command[1:] if REPLACE_DICT.pop(w, None) is not None]
    msg = await message.reply_text(f"🗑 Deleted: {deleted}")
    await asyncio.sleep(3); await msg.delete()

@app.on_message(filters.command("words") & filters.private)
async def view_words(client, message):
    try: await message.delete()
    except: pass
    disp = ", ".join(REPLACE_DICT.keys())
    msg = await message.reply_text(f"📋 <b>Blocked Words:</b>\n{disp}" if REPLACE_DICT else "Empty.")
    await asyncio.sleep(5); await msg.delete()

# --- SEARCH & WATERMARK ---
@app.on_message(filters.command("search"))
async def search_movie(client, message):
    try: await message.delete(); 
    except: pass
    if len(message.command) < 2: return await message.reply_text("Usage: `/search MovieName`")
    try:
        url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={' '.join(message.command[1:])}"
        data = requests.get(url).json()
        if not data['results']: return await message.reply_text("❌ Not found.")
        movie = data['results'][0]
        poster = f"https://image.tmdb.org/t/p/w500{movie['poster_path']}" if movie['poster_path'] else None
        caption = f"🎬 <b>{movie['title']}</b>\n📅 {movie['release_date']}\n⭐️ {movie['vote_average']}\n\n📝 {movie['overview'][:200]}..."
        if poster: await message.reply_photo(poster, caption=caption)
        else: await message.reply_text(caption)
    except: pass

@app.on_message(filters.command("series"))
async def search_series(client, message):
    try: await message.delete(); 
    except: pass
    if len(message.command) < 2: return await message.reply_text("Usage: `/series SeriesName`")
    try:
        url = f"https://api.themoviedb.org/3/search/tv?api_key={TMDB_API_KEY}&query={' '.join(message.command[1:])}"
        data = requests.get(url).json()
        if not data['results']: return await message.reply_text("❌ Not found.")
        tv = data['results'][0]
        poster = f"https://image.tmdb.org/t/p/w500{tv['poster_path']}" if tv['poster_path'] else None
        caption = f"📺 <b>{tv['name']}</b>\n📅 {tv['first_air_date']}\n⭐️ {tv['vote_average']}\n\n📝 {tv['overview'][:200]}..."
        if poster: await message.reply_photo(poster, caption=caption)
        else: await message.reply_text(caption)
    except: pass

@app.on_message(filters.command("watermark") & filters.private)
async def watermark_cmd(client, message):
    try: await message.delete(); 
    except: pass
    await message.reply_text("🖼 <b>Photo bhejein</b> (Thumbnail/Watermark ke liye).")

@app.on_message(filters.photo & filters.private)
async def save_watermark(client, message):
    if message.caption and "thumb" in message.caption: return
    btn = InlineKeyboardMarkup([[InlineKeyboardButton("🖼 Thumbnail", callback_data="save_thumb"), InlineKeyboardButton("💧 Watermark", callback_data="save_wm")]])
    await message.reply_text("Save as:", reply_markup=btn, quote=True)

@app.on_callback_query(filters.regex("save_"))
async def save_callback(client, callback):
    uid = callback.from_user.id
    path = f"thumbnails/{uid}.jpg" if "thumb" in callback.data else f"watermarks/{uid}.jpg"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    await client.download_media(callback.message.reply_to_message, path)
    await callback.message.edit_text("✅ <b>Saved!</b>")
# ==========================================
# ==========================================
# 🚀 1. URL UPLOADER LOGIC (Auto-Delete Added)
# ==========================================
@app.on_message(filters.private & filters.regex(r"^https?://"))
async def link_handler(client, message):
    uid = message.from_user.id
    if uid in batch_data and batch_data[uid].get('status') == 'naming': return 
    
    url = message.text.strip()
    status = await message.reply_text("🔎 <b>Checking Link...</b>")
    
    # 👇 Link Wala Message Delete Karo
    try: await message.delete()
    except: pass

    try:
        async with aiohttp.ClientSession() as session:
            async with session.head(url) as resp:
                if resp.status != 200: return await status.edit("❌ <b>Invalid Link!</b>")
                fname = url.split("/")[-1].split("?")[0] or "file.dat"
                download_queue[uid] = {"url": url, "filename": fname}
                
                btn = InlineKeyboardMarkup([
                    [InlineKeyboardButton("✏️ Rename", callback_data="url_rename")],
                    [InlineKeyboardButton("⏩ Next", callback_data="url_mode")]
                ])
                await status.edit(f"🔗 <b>Link Found!</b>\n📂 <code>{fname}</code>\n\nKya karna hai?", reply_markup=btn)
    except Exception as e: await status.edit(f"❌ Error: {e}")

@app.on_callback_query(filters.regex("^url_"))
async def url_handler(client, callback):
    uid = callback.from_user.id
    data = callback.data
    if uid not in download_queue: return await callback.answer("Task Expired!", show_alert=True)
    
    if data == "url_rename":
        await callback.message.delete()
        download_queue[uid]['wait_name'] = True
        await client.send_message(uid, "📝 <b>Naya Naam Bhejein:</b>", reply_markup=ForceReply(True))
    
    elif data == "url_mode":
        await ask_url_format(client, callback.message, uid, is_new=False)

    elif "video" in data or "document" in data:
        await process_url_upload(client, callback.message, uid, "video" if "video" in data else "doc")

async def ask_url_format(client, message, uid, is_new=False):
    fname = download_queue[uid]['filename']
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎥 Video", callback_data="url_video"), InlineKeyboardButton("📁 File", callback_data="url_document")]
    ])
    text = f"✅ <b>Name Set!</b>\n📂 <code>{fname}</code>\n\n👇 <b>Format Select Karein:</b>"
    
    if is_new:
        await message.reply_text(text, reply_markup=btn)
    else:
        await message.edit(text, reply_markup=btn)

async def process_url_upload(client, message, uid, mode):
    data = download_queue[uid]
    if message.from_user.is_bot: status = await message.edit("📥 <b>Downloading...</b>")
    else: status = await message.reply_text("📥 <b>Downloading...</b>")

    path = f"downloads/{data['filename']}"
    os.makedirs("downloads", exist_ok=True)
    start = time.time()
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(data['url']) as resp:
                total = int(resp.headers.get("content-length", 0))
                async with aiofiles.open(path, "wb") as f:
                    dl = 0
                    async for chunk in resp.content.iter_chunked(1024*1024):
                        if not chunk: break
                        await f.write(chunk)
                        dl += len(chunk)
                        if (time.time()-start) > 5: await progress(dl, total, status, start, "📥 Downloading")
        
        await status.edit("📤 <b>Uploading...</b>")
        w, h, dur = get_video_attributes(path)
        file_size = humanbytes(os.path.getsize(path))
        
        thumb_path = f"thumbnails/{uid}.jpg"
        if not os.path.exists(thumb_path): thumb_path = None 

        caption = f"<b>{data['filename']}</b>\n\n"
        caption += f"<blockquote><code>File Size ♻️ ➥ {file_size}</code></blockquote>\n"
        if dur > 0: caption += f"<blockquote><code>Duration ⏰ ➥ {get_duration_str(dur)}</code></blockquote>\n"
        caption += f"<blockquote><code>Powered By ➥ {CREDIT_NAME}</code></blockquote>"

        if mode == "video":
            await client.send_video(uid, path, caption=caption, thumb=thumb_path, duration=dur, width=w, height=h, supports_streaming=True, progress=progress, progress_args=(status, time.time(), "📤 Uploading"))
        else:
            await client.send_document(uid, path, caption=caption, thumb=thumb_path, force_document=True, progress=progress, progress_args=(status, time.time(), "📤 Uploading"))
        
        await status.delete()
        os.remove(path)
        del download_queue[uid]

    except Exception as e:
        await status.edit(f"❌ Error: {e}")
        if os.path.exists(path): os.remove(path)

# ==========================================
# 🚀 2. TEXT HANDLER (Delete Logic Added)
# ==========================================
@app.on_message(filters.private & filters.text)
async def handle_text(client, message):
    uid = message.from_user.id
    text = message.text.strip()
    
    # --- A. URL Rename Handler ---
    if uid in download_queue and download_queue[uid].get('wait_name'):
        # 👇 Naya Naam delete karo
        try: await message.delete()
        except: pass
        
        download_queue[uid]['filename'] = text
        download_queue[uid]['wait_name'] = False
        await ask_url_format(client, message, uid, is_new=True)
        return

    # --- B. Blogger Link ---
    if user_modes.get(uid) == "blogger_link":
        if "?start=" in text:
            # 👇 Link Code delete karo
            try: await message.delete()
            except: pass
            
            code = text.split("?start=")[1].split()[0]
            enc = base64.b64encode(code.encode("utf-8")).decode("utf-8")
            await message.reply_text(f"✅ <b>Link:</b>\n<code>{BLOGGER_URL}?data={enc}</code>")
        return

    # --- C. Batch Rename ---
    if uid in batch_data and batch_data[uid]['status'] == 'wait_name':
        # 👇 Batch Name delete karo
        try: await message.delete()
        except: pass
        
        batch_data[uid]['base_name'] = auto_clean(text)
        batch_data[uid]['status'] = 'ready'
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🎥 Video", callback_data="batch_video"), InlineKeyboardButton("📁 File", callback_data="batch_doc")]])
        await message.reply_text(f"✅ Name: {text}\nFormat?", reply_markup=btn)
        return

    # --- D. Single File Rename (Clean Up) ---
    if message.reply_to_message and uid in user_data:
        global ACTIVE_TASKS
        task = user_data.pop(uid)
        ACTIVE_TASKS += 1
        status = await message.reply_text("⏳ <b>Processing...</b>")
        
        # 👇 Naam wala message delete karo (Start mein hi)
        try: await message.delete()
        except: pass

        try:
            media = task['msg'].document or task['msg'].video or task['msg'].audio
            new_name = auto_clean(text)
            if not new_name.endswith(get_extension(media.file_name)): new_name += get_extension(media.file_name)
            
            dl = await client.download_media(media, f"downloads/{new_name}", progress=progress, progress_args=(status, time.time(), "📥"))
            w, h, dur = get_video_attributes(dl)
            thumb = f"thumbnails/{uid}.jpg" if os.path.exists(f"thumbnails/{uid}.jpg") else None
            
            # Caption Logic (Same as URL)
            file_size = humanbytes(os.path.getsize(dl))
            cap = f"<b>{new_name}</b>\n\n"
            cap += f"<blockquote><code>File Size ♻️ ➥ {file_size}</code></blockquote>\n"
            if dur > 0: cap += f"<blockquote><code>Duration ⏰ ➥ {get_duration_str(dur)}</code></blockquote>\n"
            cap += f"<blockquote><code>Powered By ➥ {CREDIT_NAME}</code></blockquote>"
            
            if task['mode'] == 'video': await client.send_video(uid, dl, caption=cap, thumb=thumb, duration=dur, width=w, height=h, progress=progress, progress_args=(status, time.time(), "📤"))
            else: await client.send_document(uid, dl, caption=cap, thumb=thumb, force_document=True, progress=progress, progress_args=(status, time.time(), "📤"))
            
            os.remove(dl)
            
            # 👇 UPLOAD DONE: Ab Purani File Delete karo
            try: await task['msg'].delete()
            except: pass

        except Exception as e: await status.edit(f"Error: {e}")
        finally: ACTIVE_TASKS -= 1; await status.delete()

# --- Baki ka code same rahega (Batch Files, Main Loop) ---
# (Handle Files wala part aur main loop pichle code jaisa hi rahega)

