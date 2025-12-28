import os, time, math, base64, re, asyncio, aiohttp, aiofiles, shutil
from PIL import Image
from hachoir.metadata import extractMetadata
from hachoir.parser import createParser
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiohttp import web

# --- CONFIG ---
API_ID = int(os.environ.get("API_ID", "12345"))
API_HASH = os.environ.get("API_HASH", "hash")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "token")
TMDB_API_KEY = "02a832d91755c2f5e8a2d1a6740a8674"
OWNER_ID = 123456789 
BLOGGER_URL = "https://filmyflip1.blogspot.com/p/download.html"
CREDIT_NAME = "🦋 Filmy Flip Hub 🦋"

app = Client("filmy_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
user_modes, user_data, batch_data = {}, {}, {}

# --- CAPTION LOGIC ---
def get_media_info(name):
    s = re.search(r"[Ss](\d{1,2})", name)
    e = re.search(r"[Ee](\d{1,3})", name)
    return (s.group(1) if s else None), (e.group(1) if e else None)

def get_fancy_caption(filename, filesize, duration=0):
    s, e = get_media_info(filename)
    caption = f"<b>{filename}</b>\n\n"
    if s: caption += f"💿 <b>Season ➥ {s}</b>\n"
    if e: caption += f"📺 <b>Episode ➥ {e}</b>\n"
    caption += f"<blockquote><b>File Size ♻️ ➥ {filesize}</b></blockquote>\n"
    if duration > 0:
        caption += f"<blockquote><b>Duration ⏰ ➥ {time.strftime('%H:%M:%S', time.gmtime(duration))}</b></blockquote>\n"
    caption += f"<blockquote><b>Powered By ➥ {CREDIT_NAME}</b></blockquote>"
    return caption
    def reset_user(uid):
    for d in [user_modes, batch_data, user_data]: d.pop(uid, None)

@app.on_message(filters.command(["url", "rename", "batch", "caption", "link"]) & filters.user(OWNER_ID))
async def mode_setter(c, m):
    uid = m.from_user.id
    cmd = m.command[0]
    reset_user(uid)
    user_modes[uid] = "blogger_link" if cmd == "link" else "renamer" if cmd == "rename" else "caption_mode" if cmd == "caption" else cmd
    if cmd == "batch": batch_data[uid] = {'status': 'collecting', 'files': []}
    await m.reply_text(f"✅ **{cmd.upper()} Mode Active!**")

@app.on_message(filters.command("clear") & filters.user(OWNER_ID))
async def clear_chat(c, m):
    async for msg in c.get_chat_history(m.chat.id, limit=50):
        try: await msg.delete()
        except: pass
@app.on_message(filters.private & filters.user(OWNER_ID))
async def main_engine(c, m):
    uid = m.from_user.id
    mode = user_modes.get(uid)

    # 1. LINK MOD (Blogger link + Auto-Delete)
    if mode == "blogger_link" and m.text:
        enc = base64.b64encode(m.text.encode()).decode()
        await m.reply_text(f"🔗 **Converted Link:**\n`{BLOGGER_URL}?data={enc}`")
        return await m.delete()

    # 2. IMAGE IDENTIFICATION (Thumb/WM)
    if m.photo or (m.document and m.document.mime_type.startswith("image/")):
        if mode == "batch": return # Batch mein image allow nahi
        user_data[uid] = {'msg': m}
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🖼 Thumb", callback_data="save_thumb"), InlineKeyboardButton("💧 WM", callback_data="save_wm")]])
        return await m.reply_text("Save Image As:", reply_markup=btn)

    # 3. FILE/VIDEO HANDLING (Caption/Rename)
    if m.document or m.video:
        if uid in batch_data and batch_data[uid]['status'] == 'collecting':
            batch_data[uid]['files'].append(m); return await m.delete()
        
        # Single Process logic here (Renaming/Captioning)
        user_data[uid] = {'msg': m}
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🎥 Video", callback_data="mode_video"), InlineKeyboardButton("📁 File", callback_data="mode_doc")]])
        await m.reply_text("Select Format:", reply_markup=btn)

# --- WEB SERVER FOR RENDER ---
async def start_bot():
    for f in ["downloads", "thumbnails", "watermarks"]: os.makedirs(f, exist_ok=True)
    await app.start()
    app_w = web.Application()
    app_w.router.add_get("/", lambda r: web.Response(text="Bot is Running"))
    await web.TCPSite(web.AppRunner(app_w), "0.0.0.0", 8080).start()
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(start_bot())
