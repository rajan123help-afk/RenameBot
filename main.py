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
BLOGGER_URL = "https://filmyflip1.blogspot.com/p/download.html"
CREDIT_NAME = "🦋 Filmy Flip Hub 🦋"

app = Client("filmy_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- GLOBAL STORAGE ---
user_modes, user_data, batch_data, REPLACE_DICT = {}, {}, {}, {}

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
           @app.on_message(filters.command("start") & filters.private)
async def start_cmd(c, m):
    reset_user(m.from_user.id)
    await m.reply_text(f"👋 **Hello {m.from_user.first_name}!**\nBot ready hai, menu commands use karein.")

@app.on_message(filters.command(["url", "rename", "batch", "caption", "link", "watermark"]) & filters.private)
async def mode_setter(c, m):
    uid = m.from_user.id
    cmd = m.command[0]
    reset_user(uid) # Instant switch to new mode
    user_modes[uid] = "blogger_link" if cmd == "link" else "renamer" if cmd == "rename" else "caption_mode" if cmd == "caption" else cmd
    if cmd == "batch": batch_data[uid] = {'status': 'collecting', 'files': []}
    await m.reply_text(f"✅ **{cmd.upper()} Mode Active!**")

@app.on_message(filters.command("done") & filters.private)
async def batch_done(c, m):
    uid = m.from_user.id
    if uid in batch_data and batch_data[uid]['files']:
        batch_data[uid]['status'] = 'wait_name'
        await m.reply_text("✅ Files collected. Ab **Series Name** bhejein:")
    else: await m.reply_text("⚠️ Batch khali hai!")

@app.on_message(filters.command(["add", "del", "words", "cancel", "clear"]) & filters.private)
async def utility_cmds(c, m):
    uid = m.from_user.id
    cmd = m.command[0]
    if cmd == "cancel":
        reset_user(uid)
        await m.reply_text("❌ Task Cancelled.")
    elif cmd == "clear":
        async for msg in c.get_chat_history(m.chat.id, limit=50):
            try: await msg.delete()
            except: pass
    elif cmd == "add":
        for w in m.command[1:]: REPLACE_DICT[w] = ""
        await m.reply_text("✅ Added to cleaner.")
 @app.on_message(filters.private & ~filters.command)
async def main_engine(c, m):
    uid = m.from_user.id
    mode = user_modes.get(uid)

    # 1. LINK MODE (Instant Convert + Auto-Delete User Message)
    if mode == "blogger_link" and m.text:
        enc = base64.b64encode(m.text.encode()).decode()
        await m.reply_text(f"🔗 **Converted Link:**\n`{BLOGGER_URL}?data={enc}`")
        return await m.delete()

    # 2. IMAGE RECOGNITION (Photo/File identified as Thumb/WM)
    is_img = m.photo or (m.document and m.document.mime_type and m.document.mime_type.startswith("image/"))
    if is_img and mode != "batch":
        user_data[uid] = {'msg': m}
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🖼 Save Thumb", callback_data="save_thumb"), InlineKeyboardButton("💧 Save WM", callback_data="save_wm")]])
        return await m.reply_text("📸 Image detected. Save as:", reply_markup=btn)

    # 3. URL UPLOADER
    if mode == "url" and m.text and m.text.startswith("http"):
        sts = await m.reply_text("📥 Processing URL...")
        # ... download & upload logic with progress ...
        await asyncio.gather(m.delete(), sts.delete())
        return

    # 4. MEDIA HANDLING (Batch/Rename)
    if m.document or m.video:
        if uid in batch_data and batch_data[uid]['status'] == 'collecting':
            batch_data[uid]['files'].append(m); return await m.delete()
        
        user_data[uid] = {'msg': m}
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🎥 Video", callback_data="mode_video"), InlineKeyboardButton("📁 File", callback_data="mode_doc")]])
        await m.reply_text("Select Action:", reply_markup=btn)

# --- CALLBACKS & SERVER ---
@app.on_callback_query(filters.regex("^save_"))
async def save_callback(c, cb):
    uid = cb.from_user.id
    fld = "thumbnails" if "thumb" in cb.data else "watermarks"
    os.makedirs(fld, exist_ok=True)
    msg = user_data[uid]['msg']
    await c.download_media(msg, file_name=f"{fld}/{uid}.jpg")
    await asyncio.gather(cb.message.delete(), msg.delete()) # Auto-Cleanup
    await c.send_message(uid, f"✅ {fld.capitalize()} Saved!")

async def start_all():
    for f in ["downloads", "thumbnails", "watermarks"]: os.makedirs(f, exist_ok=True)
    await app.start()
    # RENDER WEB SERVER (PORT 8080)
    app_w = web.Application()
    app_w.router.add_get("/", lambda r: web.Response(text="Bot Running"))
    await web.TCPSite(web.AppRunner(app_w), "0.0.0.0", 8080).start()
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(start_all())
