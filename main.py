import os, time, math, base64, re, asyncio, aiohttp, aiofiles, shutil
from PIL import Image
from hachoir.metadata import extractMetadata
from hachoir.parser import createParser
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiohttp import web

# --- CONFIGURATION ---
API_ID = int(os.environ.get("API_ID", "12345"))
API_HASH = os.environ.get("API_HASH", "your_hash")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "your_token")
TMDB_API_KEY = "02a832d91755c2f5e8a2d1a6740a8674"
OWNER_ID = 123456789  # Apni numerical ID yahan zaroor dalein
BLOGGER_URL = "https://filmyflip1.blogspot.com/p/download.html"
CREDIT_NAME = "🦋 Filmy Flip Hub 🦋"

app = Client("filmy_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- GLOBAL STORAGE ---
user_modes, user_data, batch_data, REPLACE_DICT = {}, {}, {}, {}

# --- HELPER FUNCTIONS ---
def humanbytes(size):
    if not size: return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024: return f"{size:.2f} {unit}"
        size /= 1024

def get_video_attributes(file_path):
    w, h, d = 0, 0, 0
    try:
        metadata = extractMetadata(createParser(file_path))
        if metadata.has("duration"): d = metadata.get('duration').seconds
        if metadata.has("width"): w = metadata.get("width")
        if metadata.has("height"): h = metadata.get("height")
    except: pass
    return w, h, d

def get_fancy_caption(filename, filesize, duration=0):
    s = re.search(r"[Ss](\d{1,2})", filename)
    e = re.search(r"[Ee](\d{1,3})", filename)
    caption = f"<b>{filename}</b>\n\n"
    if s: caption += f"💿 <b>Season ➥ {s.group(1)}</b>\n"
    if e: caption += f"📺 <b>Episode ➥ {e.group(1)}</b>\n"
    caption += f"<blockquote><b>File Size ♻️ ➥ {filesize}</b></blockquote>\n"
    if duration > 0:
        h, m, sec = divmod(duration, 3600); m, sec = divmod(m, 60)
        caption += f"<blockquote><b>Duration ⏰ ➥ {h:02d}:{m:02d}:{sec:02d}</b></blockquote>\n"
    caption += f"<blockquote><b>Powered By ➥ {CREDIT_NAME}</b></blockquote>"
    return caption

async def progress(current, total, message, start_time, status):
    now = time.time()
    diff = now - start_time
    if round(diff % 4.00) == 0 or current == total:
        percentage = current * 100 / total
        speed = current / diff if diff > 0 else 0
        time_left = round((total - current) / speed) if speed > 0 else 0
        bar = '●' * int(percentage / 10) + '○' * (10 - int(percentage / 10))
        tmp = (f"{status}\n\n[{bar}] <b>{round(percentage, 1)}%</b>\n"
               f"📂 {humanbytes(current)}/{humanbytes(total)}\n🚀 Speed: {humanbytes(speed)}/s\n⏳ ETA: {time.strftime('%H:%M:%S', time.gmtime(time_left))}")
        try: await message.edit(tmp, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_process")]]))
        except: pass
           def reset_user(uid):
    for d in [user_modes, batch_data, user_data]: d.pop(uid, None)

@app.on_message(filters.command("start") & filters.user(OWNER_ID))
async def start_cmd(c, m):
    reset_user(m.from_user.id)
    await m.reply_text("🚀 **Filmy Flip Bot is Online!**\nAap menu se koi bhi command select kar sakte hain.")

@app.on_message(filters.command(["url", "rename", "batch", "caption", "link", "watermark"]) & filters.user(OWNER_ID))
async def mode_setter(c, m):
    uid = m.from_user.id
    cmd = m.command[0]
    reset_user(uid)
    user_modes[uid] = "blogger_link" if cmd == "link" else "renamer" if cmd == "rename" else "caption_mode" if cmd == "caption" else cmd
    if cmd == "batch": batch_data[uid] = {'status': 'collecting', 'files': []}
    await m.reply_text(f"✅ **{cmd.upper()} Mode Active!**")

@app.on_message(filters.command("done") & filters.user(OWNER_ID))
async def batch_done(c, m):
    uid = m.from_user.id
    if uid in batch_data and batch_data[uid]['files']:
        batch_data[uid]['status'] = 'wait_name'
        await m.reply_text("✅ Files collected. Ab **Series Name** bhejein:")
    else: await m.reply_text("⚠️ Batch khali hai!")

@app.on_message(filters.command(["search", "series"]) & filters.user(OWNER_ID))
async def movie_search(c, m):
    if len(m.command) < 2: return
    query = " ".join(m.command[1:])
    async with aiohttp.ClientSession() as session:
        url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={query}"
        async with session.get(url) as r:
            data = await r.json()
            if not data.get('results'): return await m.reply_text("❌ Not Found")
            res = data['results'][0]
            btn = InlineKeyboardMarkup([[InlineKeyboardButton("🖼 Poster", callback_data=f"img_poster_{res['id']}"), InlineKeyboardButton("🎞 Backdrop", callback_data=f"img_backdrop_{res['id']}")]])
            await m.reply_photo(f"https://image.tmdb.org/t/p/w500{res['poster_path']}", caption=f"🎬 **{res['title']}**", reply_markup=btn)

@app.on_message(filters.command("add") & filters.user(OWNER_ID))
async def add_clean(c, m):
    if len(m.command) < 2: return
    for word in m.command[1:]: REPLACE_DICT[word] = ""
    await m.reply_text(f"✅ Added to cleaner: {m.command[1:]}")

@app.on_message(filters.command("del") & filters.user(OWNER_ID))
async def del_clean(c, m):
    if len(m.command) < 2: return
    for word in m.command[1:]: REPLACE_DICT.pop(word, None)
    await m.reply_text("🗑 Removed successfully.")

@app.on_message(filters.command("words") & filters.user(OWNER_ID))
async def show_words(c, m):
    words = list(REPLACE_DICT.keys())
    await m.reply_text(f"📝 **Cleaner Words:**\n{words if words else 'Khali hai.'}")

@app.on_message(filters.command("cancel") & filters.user(OWNER_ID))
async def cancel_cmd(c, m):
    reset_user(m.from_user.id)
    await m.reply_text("❌ Current task cancelled & Modes reset.")
 @app.on_message(filters.private & filters.user(OWNER_ID))
async def engine(c, m):
    uid = m.from_user.id
    mode = user_modes.get(uid)

    # 1. LINK MOD (Instant Convert + Auto-Delete User Message)
    if mode == "blogger_link" and m.text and not m.text.startswith("/"):
        enc = base64.b64encode(m.text.encode()).decode()
        await m.reply_text(f"🔗 **Converted Link:**\n`{BLOGGER_URL}?data={enc}`")
        return await m.delete()

    # 2. IMAGE RECOGNITION (Har mode mein images ko Thumbnail/WM hi samjhega)
    is_img = m.photo or (m.document and m.document.mime_type and m.document.mime_type.startswith("image/"))
    if is_img and mode != "batch":
        user_data[uid] = {'msg': m}
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🖼 Save Thumb", callback_data="save_thumb"), InlineKeyboardButton("💧 Save WM", callback_data="save_wm")]])
        return await m.reply_text("📸 Image detected. Save as:", reply_markup=btn)

    # 3. URL UPLOADER (With Progress Bar & Cleanup)
    if mode == "url" and m.text and m.text.startswith("http"):
        sts = await m.reply_text("📥 Downloading URL...")
        fpath = f"downloads/{uid}_url"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(m.text) as r:
                    total = int(r.headers.get('content-length', 0))
                    curr = 0
                    async with aiofiles.open(fpath, "wb") as f:
                        async for chunk in r.content.iter_chunked(1024*10):
                            await f.write(chunk); curr += len(chunk)
                            await progress(curr, total, sts, time.time(), "📥 Downloading...")
            await c.send_document(uid, fpath, progress=progress, progress_args=(sts, time.time(), "📤 Uploading..."))
            await asyncio.gather(m.delete(), sts.delete()) # User link aur status dono delete
        except Exception as e: await sts.edit(f"❌ Error: {e}")
        finally: 
            if os.path.exists(fpath): os.remove(fpath)
        return

    # 4. BATCH COLLECTION
    if uid in batch_data and batch_data[uid]['status'] == 'collecting':
        if m.document or m.video:
            batch_data[uid]['files'].append(m); return await m.delete()

    # 5. RENAME / CAPTION (For Single Files)
    if m.document or m.video:
        user_data[uid] = {'msg': m}
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🎥 Video", callback_data="mode_video"), InlineKeyboardButton("📁 File", callback_data="mode_doc")]])
        await m.reply_text("Select Action for this File:", reply_markup=btn)

# --- CALLBACKS & WEB SERVER ---
@app.on_callback_query(filters.regex("^save_"))
async def save_cb(c, cb):
    uid = cb.from_user.id
    fld = "thumbnails" if "thumb" in cb.data else "watermarks"
    os.makedirs(fld, exist_ok=True)
    msg = user_data[uid]['msg']
    await c.download_media(msg, file_name=f"{fld}/{uid}.jpg")
    await asyncio.gather(cb.message.delete(), msg.delete()) # Bot's prompt aur user's image delete
    await c.send_message(uid, f"✅ {fld.capitalize()} Saved!")

async def start_all():
    for f in ["downloads", "thumbnails", "watermarks"]: os.makedirs(f, exist_ok=True)
    await app.start()
    # Render Web Server
    app_w = web.Application()
    app_w.router.add_get("/", lambda r: web.Response(text="Bot Alive"))
    await web.TCPSite(web.AppRunner(app_w), "0.0.0.0", 8080).start()
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(start_all())
