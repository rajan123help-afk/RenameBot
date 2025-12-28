import os, time, math, base64, re, asyncio, aiohttp, aiofiles
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiohttp import web

# --- CONFIGURATION ---
API_ID = int(os.environ.get("API_ID", "12345"))
API_HASH = os.environ.get("API_HASH", "your_hash")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "your_token")
TMDB_API_KEY = "02a832d91755c2f5e8a2d1a6740a8674"
BLOGGER_URL = "https://filmyflip1.blogspot.com/p/download.html"

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

async def progress(current, total, message, start_time, status):
    now = time.time()
    diff = now - start_time
    if round(diff % 4.00) == 0 or current == total:
        percentage = current * 100 / total
        speed = current / diff if diff > 0 else 0
        time_left = round((total - current) / speed) if speed > 0 else 0
        bar = '●' * int(percentage / 10) + '○' * (10 - int(percentage / 10))
        tmp = (f"{status}\n\n[{bar}] <b>{round(percentage, 1)}%</b>\n"
               f"📂 {humanbytes(current)}/{humanbytes(total)}\n🚀 Speed: {humanbytes(speed)}/s")
        try: await message.edit(tmp, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_process")]]))
        except: pass

# --- COMMANDS ---
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    reset_user(message.from_user.id)
    await message.reply_text("👋 **Bot Online!**\nUse Menu commands.")

@app.on_message(filters.command(["url", "rename", "batch", "caption", "link", "watermark"]) & filters.private)
async def mode_setter(client, message):
    uid = message.from_user.id
    cmd = message.command[0]
    reset_user(uid)
    user_modes[uid] = "blogger_link" if cmd == "link" else "renamer" if cmd == "rename" else "caption_mode" if cmd == "caption" else cmd
    if cmd == "batch": batch_data[uid] = {'status': 'collecting', 'files': []}
    await message.reply_text(f"✅ **{cmd.upper()} Mode Active!**")

@app.on_message(filters.command("done") & filters.private)
async def batch_done(client, message):
    uid = message.from_user.id
    if uid in batch_data and batch_data[uid]['files']:
        batch_data[uid]['status'] = 'wait_name'
        await message.reply_text("✅ Files collected. Ab **Series Name** bhejein:")
    else: await message.reply_text("⚠️ Batch khali hai!")

@app.on_message(filters.command(["add", "del", "words", "cancel", "clear"]) & filters.private)
async def utility_cmds(client, message):
    uid = message.from_user.id
    cmd = message.command[0]
    if cmd == "cancel":
        reset_user(uid)
        await message.reply_text("❌ Task Cancelled.")
    elif cmd == "clear":
        async for msg in client.get_chat_history(message.chat.id, limit=50):
            try: await msg.delete()
            except: pass

# --- SEARCH LOGIC ---
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
        [InlineKeyboardButton("1", callback_data=f"snum_{stype}_{query}_0"), InlineKeyboardButton("2", callback_data=f"snum_{stype}_{query}_1")],
        [InlineKeyboardButton("3", callback_data=f"snum_{stype}_{query}_2"), InlineKeyboardButton("4", callback_data=f"snum_{stype}_{query}_3")]
    ])
    await callback.message.edit(f"✅ Select Number (1-4):", reply_markup=btn)

@app.on_callback_query(filters.regex("^snum_"))
async def search_final_cb(client, callback):
    _, stype, query, idx = callback.data.split("_")
    idx = int(idx)
    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://api.themoviedb.org/3/search/multi?api_key={TMDB_API_KEY}&query={query}") as r:
            data = await r.json()
            if data.get('results') and len(data['results']) > idx:
                res = data['results'][idx]
                path = res.get('poster_path' if stype == 'poster' else 'backdrop_path')
                await callback.message.delete()
                await client.send_photo(callback.from_user.id, f"https://image.tmdb.org/t/p/w500{path}", caption=f"🎬 **{res.get('title', res.get('name'))}**")

# --- ENGINE (Use Regex instead of ~filters.command to fix TypeError) ---
@app.on_message(filters.private & ~filters.regex(r"^/"))
async def engine(client, message):
    uid = message.from_user.id
    mode = user_modes.get(uid)

    if mode == "blogger_link" and message.text:
        enc = base64.b64encode(message.text.encode()).decode()
        await message.reply_text(f"🔗 **Blogger Link:**\n`{BLOGGER_URL}?data={enc}`")
        return await message.delete()

    is_img = message.photo or (message.document and message.document.mime_type and message.document.mime_type.startswith("image/"))
    if is_img and mode != "batch":
        user_data[uid] = {'msg': message}
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🖼 Save Thumb", callback_data="save_thumb"), InlineKeyboardButton("💧 Save WM", callback_data="save_wm")]])
        return await message.reply_text("📸 Image detected! Save as:", reply_markup=btn)

    if message.document or message.video:
        if uid in batch_data and batch_data[uid]['status'] == 'collecting':
            batch_data[uid]['files'].append(message)
            return await message.delete()
        user_data[uid] = {'msg': message}
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🎥 Video", callback_data="mode_video"), InlineKeyboardButton("📁 File", callback_data="mode_doc")]])
        await message.reply_text("Select Action:", reply_markup=btn)

# --- CALLBACKS & SERVER FIX (Fixes RuntimeError) ---
@app.on_callback_query(filters.regex("^save_") | filters.regex("cancel_process"))
async def callbacks(client, cb):
    if cb.data == "cancel_process":
        reset_user(cb.from_user.id)
        return await cb.message.edit("❌ Cancelled.")
    
    uid = cb.from_user.id
    fld = "thumbnails" if "thumb" in cb.data else "watermarks"
    os.makedirs(fld, exist_ok=True)
    msg = user_data[uid]['msg']
    await client.download_media(msg, file_name=f"{fld}/{uid}.jpg")
    await asyncio.gather(cb.message.delete(), msg.delete())
    await client.send_message(uid, f"✅ {fld.capitalize()} Saved!")

async def start_services():
    for f in ["downloads", "thumbnails", "watermarks"]: os.makedirs(f, exist_ok=True)
    await app.start()
    
    # FIX FOR RUNTIME ERROR (Correct aiohttp setup)
    app_w = web.Application()
    app_w.router.add_get("/", lambda r: web.Response(text="Bot Alive"))
    runner = web.AppRunner(app_w)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", 8080).start()
    
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(start_services())
    
