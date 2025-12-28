import os, time, math, base64, re, asyncio, aiohttp, aiofiles, shutil
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiohttp import web

# --- CONFIGURATION ---
API_ID = int(os.environ.get("API_ID", "12345"))
API_HASH = os.environ.get("API_HASH", "your_hash")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "your_token")
TMDB_API_KEY = "02a832d91755c2f5e8a2d1a6740a8674"
CREDIT_NAME = "🦋 Filmy Flip Hub 🦋"

app = Client("RenameBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
user_modes, user_data, batch_data = {}, {}, {}

# --- HELPER FUNCTIONS ---
def reset_user(uid):
    user_modes.pop(uid, None)
    batch_data.pop(uid, None)
    user_data.pop(uid, None)

def humanbytes(size):
    if not size: return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024: return f"{size:.2f} {unit}"
        size /= 1024

def get_fancy_caption(filename, filesize):
    caption = f"<b>{filename}</b>\n\n"
    caption += f"<blockquote><b>File Size ♻️ ➥ {humanbytes(filesize)}</b></blockquote>\n"
    caption += f"<blockquote><b>Powered By ➥ {CREDIT_NAME}</b></blockquote>"
    return caption

async def shorten_link(link):
    try:
        url = f"http://tinyurl.com/api-create.php?url={link}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                return await response.text()
    except:
        return link

async def progress(current, total, message, start_time, status):
    now = time.time()
    diff = now - start_time
    if round(diff % 4.00) == 0 or current == total:
        percentage = current * 100 / total
        speed = current / diff if diff > 0 else 0
        tmp = (f"{status}\n\n📊 <b>{round(percentage, 1)}%</b>\n"
               f"📂 {humanbytes(current)} / {humanbytes(total)}\n"
               f"🚀 Speed: {humanbytes(speed)}/s")
        try: await message.edit(tmp)
        except: pass

# --- COMMANDS ---
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    reset_user(message.from_user.id)
    await message.reply_text("👋 **Bot Online!**\nSaare features working hain.")

@app.on_message(filters.command(["url", "rename", "batch", "caption", "link", "watermark"]) & filters.private)
async def mode_setter(client, message):
    uid = message.from_user.id
    cmd = message.command[0]
    reset_user(uid)
    user_modes[uid] = "shortener" if cmd == "link" else "renamer" if cmd == "rename" else "caption_mode" if cmd == "caption" else cmd
    if cmd == "batch": batch_data[uid] = {'status': 'collecting', 'files': []}
    
    msg = f"✅ **{cmd.upper()} Mode Active!**"
    if cmd == "url": msg += "\nLink bhejo download ke liye."
    if cmd == "caption": msg += "\nFile bhejo caption badalne ke liye."
    await message.reply_text(msg)

@app.on_message(filters.command("done") & filters.private)
async def batch_done(client, message):
    uid = message.from_user.id
    if uid in batch_data and batch_data[uid]['files']:
        batch_data[uid]['status'] = 'wait_name'
        await message.reply_text("✅ Files collected. Ab **Series Name** bhejein:")
    else: await message.reply_text("⚠️ Batch khali hai!")

# --- SEARCH ---
@app.on_message(filters.command(["search", "series"]) & filters.private)
async def search_handler(client, message):
    if len(message.command) < 2: return
    query = " ".join(message.command[1:])
    reset_user(message.from_user.id)
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("🖼 Poster", callback_data=f"stype_poster_{query}"),
         InlineKeyboardButton("🎞 Thumbnail", callback_data=f"stype_backdrop_{query}")]
    ])
    await message.reply_text(f"🔍 Search: **{query}**", reply_markup=btn)

@app.on_callback_query(filters.regex("^stype_"))
async def search_type_cb(client, callback):
    _, stype, query = callback.data.split("_")
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("1", callback_data=f"snum_{stype}_0_{query[:15]}"), InlineKeyboardButton("2", callback_data=f"snum_{stype}_1_{query[:15]}")],
        [InlineKeyboardButton("3", callback_data=f"snum_{stype}_2_{query[:15]}"), InlineKeyboardButton("4", callback_data=f"snum_{stype}_3_{query[:15]}")]
    ])
    await callback.message.edit(f"✅ Select Option (1-4):", reply_markup=btn)

@app.on_callback_query(filters.regex("^snum_"))
async def search_final_cb(client, callback):
    parts = callback.data.split("_")
    stype, idx, query = parts[1], int(parts[2]), parts[3]
    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_API_KEY}&query={query}&include_image_language=en,null") as r:
            data = await r.json()
            if data.get('results') and len(data['results']) > idx:
                res = data['results'][idx]
                path = res.get('poster_path' if stype == 'poster' else 'backdrop_path')
                await callback.message.delete()
                if path:
                    await client.send_photo(callback.from_user.id, f"https://image.tmdb.org/t/p/w500{path}", caption=f"🎬 **{res.get('title', res.get('name'))}**")
                else: await callback.answer("Image nahi mili.", show_alert=True)

# --- MAIN ENGINE ---
@app.on_message(filters.private & ~filters.regex(r"^/"))
async def engine(client, message):
    uid = message.from_user.id
    mode = user_modes.get(uid)

    # 1. LINK SHORTENER
    if mode == "shortener" and message.text:
        short = await shorten_link(message.text)
        await message.reply_text(f"🔗 **Short Link:**\n`{short}`")
        return await message.delete()

    # 2. URL UPLOADER (With Progress Bar)
    if mode == "url" and message.text and message.text.startswith("http"):
        sts = await message.reply_text("📥 Downloading...")
        fpath = f"downloads/{uid}_file"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(message.text) as r:
                    if r.status != 200: return await sts.edit("❌ Link Error!")
                    total = int(r.headers.get('content-length', 0))
                    curr = 0
                    async with aiofiles.open(fpath, "wb") as f:
                        async for chunk in r.content.iter_chunked(1024*1024): 
                            await f.write(chunk); curr += len(chunk)
                            await progress(curr, total, sts, time.time(), "📥 Downloading...")
            await client.send_document(uid, fpath, caption="Uploaded by Bot", progress=progress, progress_args=(sts, time.time(), "📤 Uploading..."))
            await asyncio.gather(message.delete(), sts.delete())
        except Exception as e: await sts.edit(f"❌ Error: {e}")
        finally: 
            if os.path.exists(fpath): os.remove(fpath)
        return

    # 3. BATCH NAME INPUT
    if uid in batch_data and batch_data[uid]['status'] == 'wait_name' and message.text:
        batch_data[uid].update({'base_name': message.text, 'status': 'ready'})
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🎥 Video", callback_data="bt_video"), InlineKeyboardButton("📁 File", callback_data="bt_doc")]])
        return await message.reply_text(f"✅ Name: **{message.text}**\nSelect Format:", reply_markup=btn)

    # 4. CAPTION MODE (Direct & Fast)
    if mode == "caption_mode" and (message.document or message.video):
        file = message.document or message.video
        cap = get_fancy_caption(file.file_name or "File", file.file_size)
        await message.copy(chat_id=uid, caption=cap)
        return

    # 5. IMAGE DETECT
    is_img = message.photo or (message.document and message.document.mime_type and message.document.mime_type.startswith("image/"))
    if is_img and mode != "batch":
        user_data[uid] = {'msg': message}
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🖼 Save Thumb", callback_data="save_thumb"), InlineKeyboardButton("💧 Save WM", callback_data="save_wm")]])
        return await message.reply_text("📸 Image detected! Save as:", reply_markup=btn)

    # 6. RENAME HANDLER
    if message.document or message.video:
        if uid in batch_data and batch_data[uid]['status'] == 'collecting':
            batch_data[uid]['files'].append(message)
            return await message.delete()
        user_data[uid] = {'msg': message}
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🎥 Video", callback_data="mode_video"), InlineKeyboardButton("📁 File", callback_data="mode_doc")]])
        await message.reply_text("Select Format:", reply_markup=btn)

# --- CALLBACKS (BATCH & RENAME LOGIC) ---
@app.on_callback_query(filters.regex("^save_") | filters.regex("^mode_") | filters.regex("^bt_") | filters.regex("cancel_process"))
async def all_callbacks(client, cb):
    uid = cb.from_user.id
    
    if cb.data == "cancel_process":
        reset_user(uid)
        return await cb.message.edit("❌ Task Cancelled.")

    # SAVE THUMB/WM
    if "save_" in cb.data:
        fld = "thumbnails" if "thumb" in cb.data else "watermarks"
        os.makedirs(fld, exist_ok=True)
        msg = user_data[uid]['msg']
        await client.download_media(msg, file_name=f"{fld}/{uid}.jpg")
        await asyncio.gather(cb.message.delete(), msg.delete())
        return await client.send_message(uid, f"✅ {fld.capitalize()} Saved!")

    # SINGLE RENAME
    if "mode_" in cb.data:
        msg = user_data[uid]['msg']
        await process_rename(client, msg, cb, uid, "video" in cb.data)

    # BATCH RENAME LOOP
    if "bt_" in cb.data:
        files = batch_data[uid]['files']
        base_name = batch_data[uid]['base_name']
        is_video = "video" in cb.data
        await cb.message.edit(f"🚀 Starting Batch for {len(files)} files...")
        
        for index, msg in enumerate(files):
            new_name = f"{base_name} S01E{index+1}.mkv" # Simple naming logic
            await process_rename(client, msg, cb, uid, is_video, new_name)
            await asyncio.sleep(2) # Floodwait protection
        
        reset_user(uid)
        await client.send_message(uid, "✅ Batch Process Completed!")

# --- COMMON RENAME FUNCTION (With Progress Bar) ---
async def process_rename(client, msg, cb, uid, is_video, force_name=None):
    sts = await client.send_message(uid, "📥 Downloading...")
    try:
        # 1. Determine Name
        if force_name:
            fname = force_name
        else:
            fname = msg.video.file_name if msg.video else msg.document.file_name
            if not fname: fname = f"file_{uid}.mp4"

        # 2. Download
        fpath = await client.download_media(msg, file_name=f"downloads/{fname}", progress=progress, progress_args=(sts, time.time(), "📥 Downloading..."))
        
        # 3. Upload
        thumb_path = f"thumbnails/{uid}.jpg" if os.path.exists(f"thumbnails/{uid}.jpg") else None
        caption = get_fancy_caption(fname, os.path.getsize(fpath))
        
        if is_video:
            await client.send_video(uid, fpath, thumb=thumb_path, caption=caption, supports_streaming=True, progress=progress, progress_args=(sts, time.time(), "📤 Uploading..."))
        else:
            await client.send_document(uid, fpath, thumb=thumb_path, caption=caption, force_document=True, progress=progress, progress_args=(sts, time.time(), "📤 Uploading..."))
        
        # 4. Auto Delete
        await asyncio.gather(msg.delete(), sts.delete())
        if os.path.exists(fpath): os.remove(fpath)

    except Exception as e:
        await sts.edit(f"❌ Error: {e}")
        if os.path.exists(fpath): os.remove(fpath)

async def start_services():
    for f in ["downloads", "thumbnails", "watermarks"]: os.makedirs(f, exist_ok=True)
    await app.start()
    app_w = web.Application()
    app_w.router.add_get("/", lambda r: web.Response(text="Bot Alive"))
    runner = web.AppRunner(app_w)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", 8080).start()
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(start_services())
        
