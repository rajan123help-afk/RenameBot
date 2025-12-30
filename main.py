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
from PIL import Image
from hachoir.metadata import extractMetadata
from hachoir.parser import createParser
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

# --- BOT SETUP (SPEED BOOSTER ACTIVATED 🚀) ---
app = Client(
    "filmy_pro_turbo_max", 
    api_id=API_ID, 
    api_hash=API_HASH, 
    bot_token=BOT_TOKEN, 
    parse_mode=enums.ParseMode.HTML,
    workers=4,  # ✅ 4 Workers ek sath kaam karenge
    max_concurrent_transmissions=4 # ✅ High Speed Upload/Download
)

# --- GLOBAL VARS ---
user_modes = {}
batch_data = {}
download_queue = {}
cleaner_dict = {}

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
    if not size: return "0 B"
    power = 2**10
    n = 0
    dic_power = {0: ' ', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
    while size > power: size /= power; n += 1
    return str(round(size, 2)) + " " + dic_power[n] + 'B'

def get_duration(filepath):
    try:
        metadata = extractMetadata(createParser(filepath))
        if metadata.has("duration"):
            return metadata.get('duration').seconds
    except: pass
    return 0

def get_duration_str(duration):
    if not duration: return "0s"
    m, s = divmod(int(duration), 60)
    h, m = divmod(m, 60)
    return f"{h}h {m}m {s}s" if h > 0 else f"{m}m {s}s"

def get_media_info(name):
    s = re.search(r"[Ss](\d{1,2})", name)
    e = re.search(r"[Ee](\d{1,3})", name)
    return (s.group(1) if s else None), (e.group(1) if e else None)

def clean_filename(name):
    for k, v in cleaner_dict.items(): name = name.replace(k, v)
    return name.strip()

def get_fancy_caption(filename, filesize, duration=0):
    safe_name = html.escape(filename)
    caption = f"<b>{safe_name}</b>\n\n"
    s, e = get_media_info(filename)
    if s: caption += f"💿 <b>Season ➥ {s}</b>\n"
    if e: caption += f"📺 <b>Episode ➥ {e}</b>\n"
    if s or e: caption += "\n"
    caption += f"<blockquote><b>File Size ♻️ ➥ {filesize}</b></blockquote>\n"
    dur_str = get_duration_str(duration)
    caption += f"<blockquote><b>Duration ⏰ ➥ {dur_str}</b></blockquote>\n"
    caption += f"<blockquote><b>Powered By ➥ {CREDIT_NAME}</b></blockquote>"
    return caption

# 🔥 WATERMARK LOGIC
def apply_watermark(base_path, wm_path):
    try:
        base = Image.open(base_path).convert("RGBA")
        wm = Image.open(wm_path).convert("RGBA")
        
        # Resize Watermark to 40%
        base_w, base_h = base.size
        wm_w, wm_h = wm.size
        new_wm_w = int(base_w * 0.40) 
        ratio = new_wm_w / wm_w
        new_wm_h = int(wm_h * ratio)
        
        wm = wm.resize((new_wm_w, new_wm_h), Image.Resampling.LANCZOS)
        
        # Position: Bottom Center
        x = (base_w - new_wm_w) // 2
        y = base_h - new_wm_h - 20
        
        base.paste(wm, (x, y), wm)
        base = base.convert("RGB")
        base.save(base_path, "JPEG")
        return base_path
    except Exception as e:
        print(f"WM Error: {e}")
        return base_path

# 🔥 STYLISH PROGRESS BAR
async def progress(current, total, message, start_time, task_name):
    now = time.time()
    diff = now - start_time
    if round(diff % 5.00) == 0 or current == total:
        percentage = current * 100 / total
        completed = int(percentage // 10)
        bar = "■" * completed + "□" * (10 - completed)
        speed = current / diff if diff > 0 else 0
        time_to_completion = round((total - current) / speed) if speed > 0 else 0
        eta = get_duration_str(time_to_completion)
        
        text = f"""<b>{task_name}</b>

<b>Progress:</b> [{bar}] {round(percentage, 1)}%
<b>📂 Done:</b> {humanbytes(current)} | {humanbytes(total)}
<b>⚡ Speed:</b> {humanbytes(speed)}/s
<b>⏳ ETA:</b> {eta}"""

        try:
            await message.edit(
                text, 
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_task")]])
            )
        except: pass

# --- COMMANDS ---
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    await message.reply_text(
        f"👋 <b>Hello {message.from_user.first_name}!</b>\n\n"
        "🎬 <b>Filmy Flip Commands:</b>\n"
        "🔹 <code>/search Name</code> (Movie)\n"
        "🔹 <code>/series Name S1</code> (Series + Season)\n"
        "🔹 <code>/caption</code> (Green Line)\n"
        "🔹 <code>/batch</code> (Rename)\n"
        "🔹 <code>/url</code> (Link Upload)\n"
        "🔹 Send Photo -> Save Thumb/Watermark"
    )

@app.on_message(filters.command("caption") & filters.private)
async def set_caption(client, message):
    user_modes[message.from_user.id] = "caption"
    await message.reply_text("📝 <b>Caption Mode ON!</b>")

@app.on_message(filters.command("link") & filters.private)
async def set_link(client, message):
    user_modes[message.from_user.id] = "link"
    await message.reply_text("🔗 <b>Link Mode ON!</b> Telegram Link ya Code bhejein.")

@app.on_message(filters.command("url") & filters.private)
async def set_url(client, message):
    user_modes[message.from_user.id] = "url"
    await message.reply_text("🌐 <b>URL Mode ON!</b> Link bhejein.")

@app.on_message(filters.command("add") & filters.private)
async def add_clean(client, message):
    if len(message.command) < 2: return
    cleaner_dict[message.command[1]] = ""
    await message.reply_text(f"✅ Added: {message.command[1]}")

@app.on_message(filters.command("del") & filters.private)
async def del_clean(client, message):
    if len(message.command) < 2: return
    if message.command[1] in cleaner_dict: del cleaner_dict[message.command[1]]
    await message.reply_text(f"🗑 Removed: {message.command[1]}")
  # --- SEARCH ---
@app.on_message(filters.command(["search", "series"]))
async def search_handler(client, message):
    if len(message.command) < 2: return await message.reply_text("Usage: /search Name or /series Name S1")
    raw_query = " ".join(message.command[1:])
    stype = "tv" if "series" in message.command[0] else "movie"
    season_num = 0
    if stype == "tv":
        match = re.search(r"(?i)\s*(?:s|season)\s*(\d+)$", raw_query)
        if match:
            season_num = int(match.group(1))
            raw_query = re.sub(r"(?i)\s*(?:s|season)\s*(\d+)$", "", raw_query).strip()
    status = await message.reply_text(f"🔎 <b>Searching:</b> {raw_query}...")
    try:
        url = f"https://api.themoviedb.org/3/search/{stype}?api_key={TMDB_API_KEY}&query={raw_query}"
        res = requests.get(url).json().get('results')
        if not res: return await status.edit("❌ Not Found")
        mid = res[0]['id']
        title = res[0].get('name') if stype == 'tv' else res[0].get('title')
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🖼 Poster", callback_data=f"type_poster_{stype}_{mid}_{season_num}"), InlineKeyboardButton("🎞 Thumbnail", callback_data=f"type_backdrop_{stype}_{mid}_{season_num}")]])
        txt = f"🎬 <b>{title}</b>"
        if season_num > 0: txt += f"\n💿 <b>Season: {season_num}</b>"
        txt += "\n👇 Kya chahiye?"
        await status.edit(txt, reply_markup=btn)
    except Exception as e: await status.edit(f"Error: {e}")

@app.on_callback_query(filters.regex("^type_"))
async def type_callback(client, callback):
    try:
        _, img_type, stype, mid, s_num = callback.data.split("_")
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("1", callback_data=f"num_1_{img_type}_{stype}_{mid}_{s_num}"), InlineKeyboardButton("2", callback_data=f"num_2_{img_type}_{stype}_{mid}_{s_num}")], [InlineKeyboardButton("3", callback_data=f"num_3_{img_type}_{stype}_{mid}_{s_num}"), InlineKeyboardButton("4", callback_data=f"num_4_{img_type}_{stype}_{mid}_{s_num}")]])
        await callback.message.edit(f"✅ <b>{img_type.capitalize()} Selected!</b>\nKitni images chahiye?", reply_markup=btn)
    except: pass

@app.on_callback_query(filters.regex("^num_"))
async def num_callback(client, callback):
    try:
        uid = callback.from_user.id
        _, count, img_type, stype, mid, s_num = callback.data.split("_")
        count = int(count)
        s_num = int(s_num)
        await callback.answer(f"Sending top {count} images...")
        await callback.message.delete()
        pool = []
        if stype == "tv" and s_num > 0:
            url = f"https://api.themoviedb.org/3/tv/{mid}/season/{s_num}/images?api_key={TMDB_API_KEY}&include_image_language=en,hi,null"
            data = requests.get(url).json()
            pool = data.get('posters' if img_type == 'poster' else 'backdrops', [])
        if not pool:
            url = f"https://api.themoviedb.org/3/{stype}/{mid}/images?api_key={TMDB_API_KEY}&include_image_language=en,hi"
            data = requests.get(url).json()
            pool = data.get('posters' if img_type == 'poster' else 'backdrops', [])
        if not pool: return await client.send_message(uid, "❌ No images found!")
        images_to_send = pool[:count]
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
                        await f.write(await resp.read())
                        await f.close()
            final_path = temp_path
            if os.path.exists(wm_path): final_path = apply_watermark(temp_path, wm_path)
            await client.send_photo(uid, photo=final_path, caption=f"🖼 <b>{img_type.capitalize()} {i+1}</b>")
            os.remove(temp_path)
            time.sleep(0.5)
    except Exception as e: await client.send_message(callback.from_user.id, f"Error: {e}")

# --- PHOTO HANDLER ---
@app.on_message(filters.private & filters.photo)
async def photo_handler(client, message):
    btn = InlineKeyboardMarkup([[InlineKeyboardButton("🖼 Save Thumbnail", callback_data="save_thumb"), InlineKeyboardButton("💧 Save Watermark", callback_data="save_wm")]])
    await message.reply_text("📸 <b>Image Detected!</b>\nKya karna hai?", reply_markup=btn, quote=True)

@app.on_callback_query(filters.regex("^save_"))
async def save_img_callback(client, callback):
    uid = callback.from_user.id
    mode = "thumbnails" if "thumb" in callback.data else "watermarks"
    os.makedirs(mode, exist_ok=True)
    ext = ".png" if mode == "watermarks" else ".jpg"
    path = f"{mode}/{uid}{ext}"
    await callback.message.edit("⏳ <b>Processing...</b>")
    try:
        reply = callback.message.reply_to_message
        if not reply: return await callback.message.edit("❌ Error.")
        temp_path = f"downloads/{uid}_temp.png"
        os.makedirs("downloads", exist_ok=True)
        await client.download_media(message=reply, file_name=temp_path)
        if mode == "watermarks":
            img = Image.open(temp_path).convert("RGBA")
            img.save(path, "PNG")
        else:
            img = Image.open(temp_path).convert("RGB")
            img.save(path, "JPEG")
        os.remove(temp_path)
        await callback.message.edit(f"✅ <b>Set Successfully!</b>")
    except Exception as e: await callback.message.edit(f"❌ Error: {e}")

# --- URL HANDLER ---
@app.on_message(filters.private & filters.regex(r"^https?://"))
async def url_handler(client, message):
    uid = message.from_user.id
    text = message.text.strip()
    if user_modes.get(uid) == "link":
        code = text
        if "t.me/" in text: code = text.split("/")[-1] 
        elif "?start=" in text: code = text.split("?start=")[1].split()[0]
        enc = base64.b64encode(code.encode()).decode()
        await message.reply_text(f"🔗 <code>{BLOGGER_URL}?data={enc}</code>")
        return
    download_queue[uid] = text
    btn = InlineKeyboardMarkup([[InlineKeyboardButton("🎥 Video", callback_data="dl_vid"), InlineKeyboardButton("📁 File", callback_data="dl_doc")]])
    await message.reply_text("🔗 <b>Link Found!</b> Download as:", reply_markup=btn, quote=True)

@app.on_callback_query(filters.regex("^dl_"))
async def dl_process(client, callback):
    uid = callback.from_user.id
    url = download_queue.get(uid)
    if not url: return await callback.answer("Expired!")
    mode = "video" if "vid" in callback.data else "doc"
    await callback.message.delete()
    status = await callback.message.reply_text("📥 <b>Starting...</b>")
    fname = url.split("/")[-1] or "file.dat"
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
                        if uid not in download_queue: await status.edit("❌ Cancelled"); return
                        f.write(chunk); dl += len(chunk)
                        if time.time() - start > 5: await progress(dl, total, status, start, f"📥 Downloading: {fname}")
        await status.edit("📤 <b>Uploading...</b>")
        duration = get_duration(path)
        cap = get_fancy_caption(fname, humanbytes(os.path.getsize(path)), duration)
        thumb_path = f"thumbnails/{uid}.jpg" if os.path.exists(f"thumbnails/{uid}.jpg") else None
        wm_path = f"watermarks/{uid}.png"
        if thumb_path and os.path.exists(wm_path): thumb_path = apply_watermark(thumb_path, wm_path)
        start = time.time()
        if mode == "video": await client.send_video(uid, path, caption=cap, duration=duration, thumb=thumb_path, progress=progress, progress_args=(status, start, f"📤 Uploading: {fname}"))
        else: await client.send_document(uid, path, caption=cap, thumb=thumb_path, progress=progress, progress_args=(status, start, f"📤 Uploading: {fname}"))
        os.remove(path); del download_queue[uid]
        await status.delete()
    except Exception as e: await status.edit(f"❌ Error: {e}")

# --- BATCH HANDLER ---
@app.on_message(filters.command("batch") & filters.private)
async def batch_start(client, message):
    batch_data[message.from_user.id] = {'files': []}
    await message.reply_text("📦 <b>Batch Mode!</b> Files bhejein, fir /done likhein.")

@app.on_message(filters.command("done") & filters.private)
async def batch_done(client, message):
    uid = message.from_user.id
    if uid in batch_data and batch_data[uid]['files']:
        batch_data[uid]['step'] = 'naming'
        await message.reply_text("📝 <b>Name bhejein:</b>", reply_markup=ForceReply(True))

@app.on_message(filters.private & filters.text)
async def text_handler(client, message):
    if message.text.startswith("/"): return
    uid = message.from_user.id
    text = message.text.strip()
    if uid in batch_data and batch_data[uid].get('step') == 'naming':
        batch_data[uid]['name'] = text
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🎥 Video", callback_data="batch_run_vid"), InlineKeyboardButton("📁 File", callback_data="batch_run_doc")]])
        await message.reply_text(f"✅ Name: {text}\nStart?", reply_markup=btn)
        return
    if user_modes.get(uid) == "link":
        code = text
        if "t.me/" in text: code = text.split("/")[-1] 
        elif "?start=" in text: code = text.split("?start=")[1].split()[0]
        enc = base64.b64encode(code.encode()).decode()
        await message.reply_text(f"🔗 <code>{BLOGGER_URL}?data={enc}</code>")

@app.on_callback_query(filters.regex("^batch_run_"))
async def batch_run(client, callback):
    uid = callback.from_user.id
    mode = "video" if "vid" in callback.data else "doc"
    files = batch_data[uid]['files']
    base = batch_data[uid]['name']
    status = await callback.message.edit("🚀 <b>Starting Batch...</b>")
    for i, msg in enumerate(files):
        if uid not in batch_data: break
        try:
            media = msg.document or msg.video or msg.audio
            s, e = get_media_info(media.file_name or "")
            ext = os.path.splitext(media.file_name or "")[1] or ".mkv"
            new_name = f"{base} - S{s}E{e}{ext}" if s and e else f"{base} - {i+1}{ext}"
            new_name = clean_filename(new_name)
            path = await client.download_media(media, file_name=f"downloads/{new_name}", progress=progress, progress_args=(status, time.time(), f"📥 Downloading ({i+1}/{len(files)})"))
            duration = get_duration(path)
            cap = get_fancy_caption(new_name, humanbytes(os.path.getsize(path)), duration)
            thumb_path = f"thumbnails/{uid}.jpg" if os.path.exists(f"thumbnails/{uid}.jpg") else None
            wm_path = f"watermarks/{uid}.png"
            if thumb_path and os.path.exists(wm_path): thumb_path = apply_watermark(thumb_path, wm_path)
            start = time.time()
            if mode == "video": await client.send_video(uid, path, caption=cap, duration=duration, thumb=thumb_path, progress=progress, progress_args=(status, start, f"📤 Uploading ({i+1}/{len(files)})"))
            else: await client.send_document(uid, path, caption=cap, thumb=thumb_path, progress=progress, progress_args=(status, start, f"📤 Uploading ({i+1}/{len(files)})"))
            os.remove(path)
        except: pass
    await status.edit("🎉 <b>Batch Done!</b>")
    if uid in batch_data: del batch_data[uid]

@app.on_callback_query(filters.regex("cancel_task"))
async def cancel_handler(client, callback):
    uid = callback.from_user.id
    if uid in download_queue: del download_queue[uid]
    if uid in batch_data: del batch_data[uid]
    await callback.answer("Cancelled!")
    await callback.message.delete()

@app.on_message(filters.private & filters.document)
async def document_handler(client, message):
    uid = message.from_user.id
    if message.document.mime_type and message.document.mime_type.startswith("image/"):
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🖼 Save Thumbnail", callback_data="save_thumb"), InlineKeyboardButton("💧 Save Watermark", callback_data="save_wm")]])
        await message.reply_text("📸 <b>Image File Detected!</b>\nKya karna hai?", reply_markup=btn, quote=True)
        return 
    if uid in batch_data and 'step' not in batch_data[uid]:
        batch_data[uid]['files'].append(message)
    elif user_modes.get(uid) == "caption":
        media = message.document
        cap = get_fancy_caption(media.file_name or "File", humanbytes(media.file_size), 0)
        await client.send_document(uid, media.file_id, caption=cap)

@app.on_message(filters.private & (filters.video | filters.audio))
async def media_handler(client, message):
    uid = message.from_user.id
    if uid in batch_data and 'step' not in batch_data[uid]:
        batch_data[uid]['files'].append(message)
    elif user_modes.get(uid) == "caption":
        media = message.video or message.audio
        cap = get_fancy_caption(media.file_name or "File", humanbytes(getattr(media, "file_size", 0)), getattr(media, "duration", 0))
        if message.video: await client.send_video(uid, media.file_id, caption=cap)
        else: await client.send_audio(uid, media.file_id, caption=cap)

# --- START ---
async def start_services():
    web_app = await web_server()
    runner = web.AppRunner(web_app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", int(os.environ.get("PORT", 8080))).start()
    await app.start()
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(start_services())
  
