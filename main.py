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
from urllib.parse import unquote
from PIL import Image
from hachoir.metadata import extractMetadata
from hachoir.parser import createParser
from aiohttp import web
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ForceReply
from pyrogram.errors import UserNotParticipant
from motor.motor_asyncio import AsyncIOMotorClient

# --- CONFIGURATION ---
API_ID = int(os.environ.get("API_ID", "23421127"))
API_HASH = os.environ.get("API_HASH", "0375dd20aba9f2e7c29d0c1c06590dfb")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8468501492:AAGpD5dzd1EzkJs9AqHkAOAhPcmGv1Dwlgk")
OWNER_ID = int(os.environ.get("OWNER_ID", "5027914470"))
MONGO_URL = os.environ.get("MONGO_URL", "mongodb+srv://raja:raja12345@filmyflip.jlitika.mongodb.net/?retryWrites=true&w=majority&appName=Filmyflip")
DB_CHANNEL_ID = int(os.environ.get("DB_CHANNEL_ID", "-1003311810643"))
TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "02a832d91755c2f5e8a2d1a6740a8674")
CREDIT_NAME = "🦋 Filmy Flip Hub 🦋"
BLOGGER_URL = "https://filmyflip1.blogspot.com/p/download.html"

FS_CHANNELS = [
    {"id": -1002410972822, "link": "https://t.me/+j4eYjjJLTGY4MTFl"},
    {"id": -1002312115538, "link": "https://t.me/+COWqvDXiQUkxOWE9"},
    {"id": -1002384884726, "link": "https://t.me/+5Rue8fj6dC80NmE9"},
]

mongo = AsyncIOMotorClient(MONGO_URL)
db = mongo["FilmyFlipBot"]
settings_col = db["settings"]

app = Client("filmy_pro_final", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, parse_mode=enums.ParseMode.HTML, workers=10, max_concurrent_transmissions=5)

clone_app = None
user_modes, user_data, batch_data, download_queue, cleaner_dict = {}, {}, {}, {}, {}
# --- HELPERS & PROGRESS BAR ---
async def progress(current, total, message, start_time, task_name):
    now = time.time()
    diff = now - start_time
    if round(diff % 5.00) == 0 or current == total:
        percentage = current * 100 / total
        speed = current / diff if diff > 0 else 0
        
        # 🌀 Professional Progress Bar
        filled_length = int(15 * current // total)
        bar = '🟢' * filled_length + '⚪' * (15 - filled_length)
        
        tmp = (f"<b>{task_name}...</b>\n\n"
               f"<code>{bar}</code> {round(percentage, 2)}%\n"
               f"🚀 <b>Speed:</b> {humanbytes(speed)}/s\n"
               f"📦 <b>Done:</b> {humanbytes(current)} of {humanbytes(total)}\n")
        try:
            await message.edit(tmp)
        except:
            pass

def humanbytes(size):
    if not size: return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024: return f"{size:.2f} {unit}"
        size /= 1024

def decode_id(s): return base64.urlsafe_b64decode(s + "=" * (len(s) % 4)).decode("ascii")
def encode_id(i): return base64.urlsafe_b64encode(str(i).encode("ascii")).decode("ascii").strip("=")

def get_fancy_caption(filename, filesize):
    return f"<b>{html.escape(filename)}</b>\n\n<blockquote><b>File Size ♻️ ➥ {filesize} ”</b></blockquote>\n<blockquote><b>Powered By ➥ {CREDIT_NAME} ”</b></blockquote>"

# --- COMMANDS ---
@app.on_message(filters.command("start") & filters.private)
async def start_cmd(c, m): await m.reply_text("👋 Bot Active!")

@app.on_message(filters.command(["search", "series"]) & filters.private)
async def search_cmd(c, m):
    query = " ".join(m.command[1:]); stype = "tv" if "series" in m.command[0] else "movie"
    res = requests.get(f"https://api.themoviedb.org/3/search/{stype}?api_key={TMDB_API_KEY}&query={query}").json().get('results')
    if res:
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🖼 Poster", callback_data=f"type_poster_{stype}_{res[0]['id']}_0")]])
        await m.reply(f"🎬 **{res[0].get('name' if stype == 'tv' else 'title')}**", reply_markup=btn)

# --- MEDIA & TEXT HANDLER (RENAME/URL) ---
@app.on_message(filters.private & (filters.document | filters.video | filters.photo))
async def media_handler(c, m):
    uid = m.from_user.id
    if user_modes.get(uid) == "store":
        db_msg = await m.copy(DB_CHANNEL_ID)
        payload = base64.b64encode(encode_id(db_msg.id).encode()).decode()
        await m.reply(f"✅ **Stored!**\n🔗 `{BLOGGER_URL}?data={payload}`")
        return await m.delete()
    if m.photo or (m.document and "image" in (m.document.mime_type or "")):
        return await m.reply("📸 Image Detected!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🖼 Save Thumb", callback_data="save_thumb"), InlineKeyboardButton("💧 Save Watermark", callback_data="save_wm")]]), quote=True)
    download_queue[uid] = {'msg': m}
    await m.reply("📝 **New Name?**", reply_markup=ForceReply(True))

@app.on_message(filters.private & filters.text)
async def text_handler(c, m):
    if m.text.startswith("/"): return
    uid = m.from_user.id
    if uid in download_queue and 'name' not in download_queue[uid]:
        download_queue[uid]['name'] = m.text
        await m.reply(f"✅ Name: {m.text}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎥 Video", callback_data="dl_vid")]]))

# --- START SERVICE LOGIC ---
async def start_services():
    print("🚀 Starting Web Server...")
    routes = web.RouteTableDef()
    @routes.get("/", allow_head=True)
    async def h(request): return web.json_response({"status": "running"})
    web_app = web.Application(); web_app.add_routes(routes)
    runner = web.AppRunner(web_app); await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", int(os.environ.get("PORT", 8080))).start()
    
    print("🤖 Starting Main Bot...")
    await app.start()
    print("✅ Bot is Live now!")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(start_services())
    # --- WEB SERVER ---
async def web_server():
    routes = web.RouteTableDef()
    @routes.get("/", allow_head=True)
    async def h(request): return web.json_response({"status": "running"})
    web_app = web.Application(); web_app.add_routes(routes)
    return web_app

# --- START SERVICE LOGIC ---
async def start_services():
    print("🚀 Starting Web Server...")
    runner = web.AppRunner(await web_server())
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", int(os.environ.get("PORT", 8080))).start()
    
    print("🤖 Starting Main Bot...")
    await app.start()
    
    # Auto-start Clone Bot agar DB mein token hai
    data = await settings_col.find_one({"_id": "active_clone"})
    if data:
        print("♻️ Starting Clone Bot...")
        # Clone bot ka start logic yahan call hoga
        
    print("✅ Bot is Live now!")
    await asyncio.Event().wait()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(start_services())
    
