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

# --- COMMANDS ---
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    reset_user(message.from_user.id)
    await message.reply_text("👋 Bot Online Hai! Menu use karein.")

@app.on_message(filters.command(["url", "rename", "batch", "caption", "link", "watermark"]) & filters.private)
async def set_modes(client, message):
    uid = message.from_user.id
    cmd = message.command[0]
    reset_user(uid)
    user_modes[uid] = "blogger_link" if cmd == "link" else "renamer" if cmd == "rename" else "caption_mode" if cmd == "caption" else cmd
    if cmd == "batch": batch_data[uid] = {'status': 'collecting', 'files': []}
    await message.reply_text(f"✅ **{cmd.upper()} Mode Active!**")

# --- SEARCH LOGIC (Poster/Thumb + 1-4 selection) ---
@app.on_message(filters.command(["search", "series"]) & filters.private)
async def search_handler(client, message):
    if len(message.command) < 2: return
    query = " ".join(message.command[1:])
    reset_user(message.from_user.id)
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("🖼 Poster", callback_data=f"stype_poster_{query}"),
         InlineKeyboardButton("🎞 Thumbnail", callback_data=f"stype_backdrop_{query}")]
    ])
    await message.reply_text(f"🔍 Search: **{query}**\nKya chahiye?", reply_markup=btn)

@app.on_callback_query(filters.regex("^stype_"))
async def search_type_cb(client, callback):
    _, stype, query = callback.data.split("_")
    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("1", callback_data=f"snum_{stype}_{query}_0"), InlineKeyboardButton("2", callback_data=f"snum_{stype}_{query}_1")],
        [InlineKeyboardButton("3", callback_data=f"snum_{stype}_{query}_2"), InlineKeyboardButton("4", callback_data=f"snum_{stype}_{query}_3")]
    ])
    await callback.message.edit(f"✅ Select Number (1-4) for {stype.capitalize()}:", reply_markup=btn)

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

# --- MAIN ENGINE (Fixing the TypeError) ---
@app.on_message(filters.private & ~filters.command(["start", "url", "search", "series", "rename", "caption", "batch", "done", "link", "watermark", "add", "del", "words", "cancel"]))
async def engine(client, message):
    uid = message.from_user.id
    mode = user_modes.get(uid)

    # 1. LINK MODE (Blogger Conversion)
    if mode == "blogger_link" and message.text:
        enc = base64.b64encode(message.text.encode()).decode()
        await message.reply_text(f"🔗 **Blogger Link:**\n`{BLOGGER_URL}?data={enc}`")
        return await message.delete()

    # 2. IMAGE RECOGNITION (Thumbnail/Watermark Choice)
    is_img = message.photo or (message.document and message.document.mime_type and message.document.mime_type.startswith("image/"))
    if is_img and mode != "batch":
        user_data[uid] = {'msg': message}
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🖼 Save Thumb", callback_data="save_thumb"), InlineKeyboardButton("💧 Save WM", callback_data="save_wm")]])
        return await message.reply_text("📸 Image detected! Ise save karein:", reply_markup=btn)

    # 3. BATCH COLLECTION
    if uid in batch_data and batch_data[uid]['status'] == 'collecting':
        if message.document or message.video:
            batch_data[uid]['files'].append(message)
            return await message.delete()

    # 4. RENAME OPTIONS
    if message.document or message.video:
        user_data[uid] = {'msg': message}
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🎥 Video", callback_data="mode_video"), InlineKeyboardButton("📁 File", callback_data="mode_doc")]])
        await message.reply_text("Format select karein:", reply_markup=btn)

# --- CALLBACKS & SERVER ---
@app.on_callback_query(filters.regex("^save_"))
async def save_cb(client, callback):
    uid = callback.from_user.id
    fld = "thumbnails" if "thumb" in callback.data else "watermarks"
    os.makedirs(fld, exist_ok=True)
    msg = user_data[uid]['msg']
    await client.download_media(msg, file_name=f"{fld}/{uid}.jpg")
    await asyncio.gather(callback.message.delete(), msg.delete())
    await client.send_message(uid, f"✅ {fld[:-1].capitalize()} Saved and chat cleared!")

async def start_bot():
    for f in ["downloads", "thumbnails", "watermarks"]: os.makedirs(f, exist_ok=True)
    await app.start()
    app_w = web.Application()
    app_w.router.add_get("/", lambda r: web.Response(text="Bot Alive"))
    await web.TCPSite(web.AppRunner(app_w), "0.0.0.0", 8080).start()
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(start_bot())
    
