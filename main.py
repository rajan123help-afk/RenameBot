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
from PIL import Image
from hachoir.metadata import extractMetadata
from hachoir.parser import createParser
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ForceReply

# --- CONFIGURATION ---
API_ID = int(os.environ.get("API_ID", "12345"))
API_HASH = os.environ.get("API_HASH", "hash")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "token")

# ✅ NEW API KEY SET HERE
TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "02a832d91755c2f5e8a2d1a6740a8674") 

CREDIT_NAME = "🦋 Filmy Flip Hub 🦋"
BLOGGER_URL = os.environ.get("BLOGGER_URL", "https://yoursite.com")

app = Client("filmy_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- GLOBAL VARIABLES ---
user_data = {}
batch_data = {}
download_queue = {}
user_modes = {} 
REPLACE_DICT = {}
ACTIVE_TASKS = 0
MAX_TASK_LIMIT = 5

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
    duration = int(duration)
    m, s = divmod(duration, 60)
    h, m = divmod(m, 60)
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

def get_fancy_caption(filename, filesize, duration=0):
    caption = f"<b>{filename}</b>\n\n"
    caption += f"<blockquote><code>File Size ♻️ ➥ {filesize}</code></blockquote>\n"
    if duration > 0:
        caption += f"<blockquote><code>Duration ⏰ ➥ {get_duration_str(duration)}</code></blockquote>\n"
    caption += f"<blockquote><code>Powered By ➥ {CREDIT_NAME}</code></blockquote>"
    return caption

# --- WATERMARK LOGIC (Bottom Center + 70%) ---
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
    except Exception as e:
        print(f"WM Error: {e}")
        return base_path

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
            # --- COMMANDS ---
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    try: await message.delete()
    except: pass
    await message.reply_text(
        f"👋 <b>Hello {message.from_user.first_name}!</b>\n\n"
        "🤖 <b>Filmy Flip Hub Bot</b>\n\n"
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
    msg = await message.reply_text("🔗 <b>Link Mode ON!</b>\nAb koi bhi text/link bhejein.")
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

# ==========================================
# 🚀 SEARCH HANDLER (With Buttons)
# ==========================================
@app.on_message(filters.command(["search", "series"]))
async def search_handler(client, message):
    if len(message.command) < 2:
        return await message.reply_text("Usage: `/search Name`")
    
    query = " ".join(message.command[1:])
    is_series = "series" in message.command[0]
    stype = "tv" if is_series else "movie"
    
    status = await message.reply_text("🔎 <b>Searching...</b>")
    try:
        url = f"https://api.themoviedb.org/3/search/{stype}?api_key={TMDB_API_KEY}&query={query}"
        data = requests.get(url).json()
        
        if not data.get('results'):
            return await status.edit("❌ <b>Not found!</b> Check spelling.")
        
        res = data['results'][0]
        mid = res['id']
        title = res.get('name') if is_series else res.get('title')
        date = res.get('first_air_date') if is_series else res.get('release_date')
        
        btn = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🖼 Poster", callback_data=f"img_poster_{stype}_{mid}"),
                InlineKeyboardButton("🎞 Thumbnail", callback_data=f"img_backdrop_{stype}_{mid}")
            ]
        ])
        
        caption = f"🎬 <b>{title}</b>\n📅 {date}\n⭐️ {res.get('vote_average')}\n\n👇 <b>Kya download karna hai?</b>"
        await status.edit(caption, reply_markup=btn)
        
    except Exception as e:
        await status.edit(f"❌ Error: {e}")
# --- ALL BUTTON CALLBACKS ---
@app.on_callback_query(filters.regex("^img_"))
async def img_type_callback(client, callback):
    try:
        _, img_type, stype, mid = callback.data.split("_")
        btn = InlineKeyboardMarkup([
            [InlineKeyboardButton("1", callback_data=f"cnt_1_{img_type}_{stype}_{mid}"),
             InlineKeyboardButton("2", callback_data=f"cnt_2_{img_type}_{stype}_{mid}")],
            [InlineKeyboardButton("3", callback_data=f"cnt_3_{img_type}_{stype}_{mid}"),
             InlineKeyboardButton("4", callback_data=f"cnt_4_{img_type}_{stype}_{mid}")]
        ])
        await callback.message.edit(f"✅ <b>{img_type.capitalize()} Selected!</b>\n\nKitne photos chahiye?", reply_markup=btn)
    except: await callback.answer("Error")

@app.on_callback_query(filters.regex("^cnt_"))
async def img_process_callback(client, callback):
    uid = callback.from_user.id
    try:
        _, count, img_type, stype, mid = callback.data.split("_")
        count = int(count)
        
        await callback.message.edit("⏳ <b>Downloading...</b>")
        
        url = f"https://api.themoviedb.org/3/{stype}/{mid}/images?api_key={TMDB_API_KEY}"
        data = requests.get(url).json()
        
        key = 'posters' if img_type == 'poster' else 'backdrops'
        if not data.get(key):
            return await callback.message.edit("❌ No images found!")
            
        images = data[key][:count]
        
        wm_path = f"watermarks/{uid}.jpg"
        has_wm = os.path.exists(wm_path)
        
        for i, img in enumerate(images):
            img_url = f"https://image.tmdb.org/t/p/w500{img['file_path']}"
            fpath = f"downloads/{mid}_{i}.jpg"
            os.makedirs("downloads", exist_ok=True)
            
            with open(fpath, 'wb') as f:
                f.write(requests.get(img_url).content)
            
            if has_wm:
                apply_watermark(fpath, wm_path)
            
            await client.send_photo(uid, fpath, caption=f"🦋 <b>Filmy Flip Hub</b>")
            os.remove(fpath)
            
        await callback.message.delete()
    except Exception as e:
        await callback.message.edit(f"❌ Error: {e}")

@app.on_callback_query(filters.regex("save_"))
async def save_callback(client, callback):
    uid = callback.from_user.id
    try:
        await callback.answer("Processing...")
        path = f"thumbnails/{uid}.jpg" if "thumb" in callback.data else f"watermarks/{uid}.jpg"
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if callback.message.reply_to_message:
            await client.download_media(callback.message.reply_to_message, path)
            await callback.message.edit_text("✅ <b>Saved Successfully!</b>")
        else:
            await callback.message.edit_text("❌ <b>Error:</b> Original photo not found.")
    except Exception as e:
        await callback.message.edit_text(f"❌ Error: {e}")

@app.on_callback_query(filters.regex("^force_rename"))
async def force_rename_callback(client, callback):
    try:
        await callback.answer()
        await callback.message.delete()
        uid = callback.from_user.id
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🎥 Video", callback_data="mode_video"), InlineKeyboardButton("📁 File", callback_data="mode_document")]])
        await client.send_message(uid, "Format select karein:", reply_markup=btn)
    except: pass

@app.on_callback_query(filters.regex("^mode_"))
async def single_mode(client, callback):
    uid = callback.from_user.id
    try:
        await callback.answer()
        user_data[uid]['mode'] = "video" if "video" in callback.data else "doc"
        await callback.message.delete()
        await client.send_message(uid, "📝 <b>New Name:</b>", reply_markup=ForceReply(True))
    except: pass

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

# --- MAIN HANDLERS ---
@app.on_message(filters.private & filters.regex(r"^https?://"))
async def link_handler(client, message):
    uid = message.from_user.id
    if uid in batch_data and batch_data[uid].get('status') == 'naming': return 
    
    # 🔥 LINK MODE CHECK (Fix)
    if user_modes.get(uid) == "blogger_link":
        return await handle_text(client, message)

    url = message.text.strip()
    status = await message.reply_text("🔎 <b>Checking Link...</b>")
    try: await message.delete(); 
    except: pass

    try:
        async with aiohttp.ClientSession() as session:
            async with session.head(url) as resp:
                if resp.status != 200: return await status.edit("❌ <b>Invalid Link!</b>")
                fname = url.split("/")[-1].split("?")[0] or "file.dat"
                download_queue[uid] = {"url": url, "filename": fname}
                btn = InlineKeyboardMarkup([[InlineKeyboardButton("✏️ Rename", callback_data="url_rename"), InlineKeyboardButton("⏩ Next", callback_data="url_mode")]])
                await status.edit(f"🔗 <b>Link Found!</b>\n📂 <code>{fname}</code>\n\nKya karna hai?", reply_markup=btn)
    except Exception as e: await status.edit(f"❌ Error: {e}")

async def ask_url_format(client, message, uid, is_new=False):
    fname = download_queue[uid]['filename']
    btn = InlineKeyboardMarkup([[InlineKeyboardButton("🎥 Video", callback_data="url_video"), InlineKeyboardButton("📁 File", callback_data="url_document")]])
    text = f"✅ <b>Name Set!</b>\n📂 <code>{fname}</code>\n\n👇 <b>Format Select Karein:</b>"
    if is_new: await message.reply_text(text, reply_markup=btn)
    else: await message.edit(text, reply_markup=btn)

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
        thumb_path = f"thumbnails/{uid}.jpg" if os.path.exists(f"thumbnails/{uid}.jpg") else None
        wm_path = f"watermarks/{uid}.jpg"
        if thumb_path and os.path.exists(wm_path): thumb_path = apply_watermark(thumb_path, wm_path)
        caption = get_fancy_caption(data['filename'], file_size, dur)
        if mode == "video": await client.send_video(uid, path, caption=caption, thumb=thumb_path, duration=dur, width=w, height=h, supports_streaming=True, progress=progress, progress_args=(status, time.time(), "📤 Uploading"))
        else: await client.send_document(uid, path, caption=caption, thumb=thumb_path, force_document=True, progress=progress, progress_args=(status, time.time(), "📤 Uploading"))
        await status.delete(); os.remove(path); del download_queue[uid]
    except Exception as e: await status.edit(f"❌ Error: {e}")
    if os.path.exists(path): os.remove(path)

@app.on_message(filters.private & filters.text)
async def handle_text(client, message):
    uid = message.from_user.id
    text = message.text.strip()
    
    if uid in download_queue and download_queue[uid].get('wait_name'):
        try: await message.delete(); 
        except: pass
        download_queue[uid]['filename'] = text
        download_queue[uid]['wait_name'] = False
        await ask_url_format(client, message, uid, is_new=True)
        return

    # 🔥 LINK GENERATOR FIX (Accepts ALL Text)
    if user_modes.get(uid) == "blogger_link":
        try: await message.delete(); 
        except: pass
        enc = base64.b64encode(text.encode("utf-8")).decode("utf-8")
        await message.reply_text(f"✅ <b>Link Ready!</b>\n\n🔗 <b>Your URL:</b>\n<code>{BLOGGER_URL}?data={enc}</code>")
        return

    if uid in batch_data and batch_data[uid]['status'] == 'wait_name':
        try: await message.delete(); 
        except: pass
        batch_data[uid]['base_name'] = auto_clean(text)
        batch_data[uid]['status'] = 'ready'
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🎥 Video", callback_data="batch_video"), InlineKeyboardButton("📁 File", callback_data="batch_doc")]])
        await message.reply_text(f"✅ Name: {text}\nFormat?", reply_markup=btn)
        return

    if message.reply_to_message and uid in user_data:
        global ACTIVE_TASKS
        task = user_data.pop(uid)
        ACTIVE_TASKS += 1
        status = await message.reply_text("⏳ <b>Processing...</b>")
        try: await message.delete(); 
        except: pass
        try:
            media = task['msg'].document or task['msg'].video or task['msg'].audio
            new_name = auto_clean(text)
            if not new_name.endswith(get_extension(media.file_name)): new_name += get_extension(media.file_name)
            dl = await client.download_media(media, f"downloads/{new_name}", progress=progress, progress_args=(status, time.time(), "📥"))
            w, h, dur = get_video_attributes(dl)
            thumb_path = f"thumbnails/{uid}.jpg" if os.path.exists(f"thumbnails/{uid}.jpg") else None
            wm_path = f"watermarks/{uid}.jpg"
            if thumb_path and os.path.exists(wm_path): thumb_path = apply_watermark(thumb_path, wm_path)
            caption = get_fancy_caption(new_name, humanbytes(os.path.getsize(dl)), dur)
            if task['mode'] == 'video': await client.send_video(uid, dl, caption=caption, thumb=thumb, duration=dur, width=w, height=h, progress=progress, progress_args=(status, time.time(), "📤"))
            else: await client.send_document(uid, dl, caption=caption, thumb=thumb, force_document=True, progress=progress, progress_args=(status, time.time(), "📤"))
            os.remove(dl); 
            try: await task['msg'].delete()
            except: pass
        except Exception as e: await status.edit(f"Error: {e}")
        finally: ACTIVE_TASKS -= 1; await status.delete()

@app.on_message(filters.command("batch") & filters.private)
async def batch_cmd(client, message):
    try: await message.delete(); 
    except: pass
    batch_data[message.from_user.id] = {'status': 'collecting', 'files': []}
    await message.reply_text("🚀 <b>Batch Mode!</b> Files forward karein, fir /done dabayein.")

@app.on_message(filters.command("done") & filters.private)
async def batch_done(client, message):
    try: await message.delete(); 
    except: pass
    uid = message.from_user.id
    if uid in batch_data and batch_data[uid]['files']:
        batch_data[uid]['status'] = 'wait_name'
        await message.reply_text(f"✅ <b>{len(batch_data[uid]['files'])} Files.</b>\nSeries Name bhejein:")
    else: await message.reply_text("⚠️ Pehle files bhejein!")

@app.on_callback_query(filters.regex("^batch_"))
async def batch_process(client, callback):
    uid = callback.from_user.id
    mode = "video" if "video" in callback.data else "doc"
    status = await callback.message.edit_text("⏳ <b>Starting Batch...</b>")
    for idx, msg in enumerate(batch_data[uid]['files']):
        media = msg.document or msg.video or msg.audio
        if not media: continue
        s, e = get_media_info(media.file_name or "")
        base = batch_data[uid]['base_name']
        ext = get_extension(media.file_name or "")
        new_name = f"{base} - S{s}E{e}{ext}" if s and e else (f"{base} - E{e}{ext}" if e else f"{base} - Part {idx+1}{ext}")
        await status.edit(f"♻️ Processing {idx+1}...\n📂 {new_name}")
        dl = await client.download_media(media, f"downloads/{new_name}")
        w, h, dur = get_video_attributes(dl)
        thumb_path = f"thumbnails/{uid}.jpg" if os.path.exists(f"thumbnails/{uid}.jpg") else None
        wm_path = f"watermarks/{uid}.jpg"
        if thumb_path and os.path.exists(wm_path): thumb_path = apply_watermark(thumb_path, wm_path)
        caption = get_fancy_caption(new_name, humanbytes(os.path.getsize(dl)), dur)
        if mode == 'video': await client.send_video(uid, dl, caption=caption, thumb=thumb, duration=dur, width=w, height=h)
        else: await client.send_document(uid, dl, caption=caption, thumb=thumb, force_document=True)
        os.remove(dl)
    await status.edit("✅ Batch Completed!"); del batch_data[uid]

@app.on_message(filters.private & (filters.document | filters.video | filters.audio))
async def handle_files(client, message):
    uid = message.from_user.id
    media = message.document or message.video or message.audio
    if not media: return
    # 1. Image Check
    mime = getattr(media, "mime_type", "")
    if mime and mime.startswith("image/"):
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🖼 Thumbnail", callback_data="save_thumb"), InlineKeyboardButton("💧 Watermark", callback_data="save_wm")], [InlineKeyboardButton("➡️ Rename File", callback_data="force_rename")]])
        await message.reply_text("<b>🖼 Image Detected!</b>\nSet as Thumbnail or Watermark?", reply_markup=btn, quote=True)
        return
    # 2. Caption Mode
    if user_modes.get(uid) == "caption_only":
        try:
            file_size = humanbytes(getattr(media, "file_size", 0))
            dur = int(getattr(media, "duration", 0) or 0)
            caption = get_fancy_caption(media.file_name or "Unknown File", file_size, dur)
            await message.reply_cached_media(media.file_id, caption=caption)
            try: await message.delete() 
            except: pass
        except Exception as e: await message.reply_text(f"❌ Error: {e}")
        return
    # 3. Batch
    if uid in batch_data and batch_data[uid]['status'] == 'collecting':
        batch_data[uid]['files'].append(message); return
    # 4. Normal
    global ACTIVE_TASKS
    if ACTIVE_TASKS >= MAX_TASK_LIMIT: return await message.reply_text("⚠️ Busy!")
    user_data[uid] = {'msg': message}
    btn = InlineKeyboardMarkup([[InlineKeyboardButton("🎥 Video", callback_data="mode_video"), InlineKeyboardButton("📁 File", callback_data="mode_document")]])
    await message.reply_text("Format select karein:", reply_markup=btn, quote=True)

# --- MAIN LOOP ---
async def main():
    port = int(os.environ.get("PORT", 8080))
    app_runner = web.AppRunner(await web_server())
    await app_runner.setup()
    site = web.TCPSite(app_runner, "0.0.0.0", port)
    await site.start()
    print(f"Server started on Port {port}")
    try: await app.start(); print("Bot Started Successfully!")
    except Exception as e: print(f"Bot Failed to Start: {e}")
    await asyncio.Event().wait()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
