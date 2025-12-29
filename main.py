import os
import re
import asyncio
import requests
import html
import base64
from aiohttp import web
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- CONFIGURATION ---
API_ID = int(os.environ.get("API_ID", "12345"))
API_HASH = os.environ.get("API_HASH", "hash")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "token")
TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "02a832d91755c2f5e8a2d1a6740a8674")
CREDIT_NAME = "🦋 Filmy Flip Hub 🦋"
BLOGGER_URL = "https://filmyflip1.blogspot.com/p/download.html"

# --- BOT SETUP ---
app = Client(
    "filmy_lite", 
    api_id=API_ID, 
    api_hash=API_HASH, 
    bot_token=BOT_TOKEN, 
    parse_mode=enums.ParseMode.HTML
)

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
    m, s = divmod(int(duration), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"

def get_media_info(name):
    s = re.search(r"[Ss](\d{1,2})", name)
    e = re.search(r"[Ee](\d{1,3})", name)
    return (s.group(1) if s else None), (e.group(1) if e else None)

def get_fancy_caption(filename, filesize, duration=0):
    safe_name = html.escape(filename)
    caption = f"<b>{safe_name}</b>\n\n"
    s, e = get_media_info(filename)
    if s: caption += f"💿 <b>Season ➥ {s}</b>\n"
    if e: caption += f"📺 <b>Episode ➥ {e}</b>\n"
    if s or e: caption += "\n"
    caption += f"<blockquote><b>File Size ♻️ ➥ {filesize}</b></blockquote>\n"
    if duration > 0: caption += f"<blockquote><b>Duration ⏰ ➥ {get_duration_str(duration)}</b></blockquote>\n"
    caption += f"<blockquote><b>Powered By ➥ {CREDIT_NAME}</b></blockquote>"
    return caption

user_modes = {}

# --- COMMANDS ---
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    await message.reply_text(
        f"👋 <b>Hello {message.from_user.first_name}!</b>\n\n"
        "✅ <b>Bot is Ready!</b>\n"
        "Use /search, /caption, or /link"
    )

@app.on_message(filters.command("caption") & filters.private)
async def set_caption_mode(client, message):
    user_modes[message.from_user.id] = "caption"
    await message.reply_text("📝 <b>Caption Mode ON!</b>")

@app.on_message(filters.command("link") & filters.private)
async def set_link_mode(client, message):
    user_modes[message.from_user.id] = "link"
    await message.reply_text("🔗 <b>Link Mode ON!</b>")

@app.on_message(filters.command(["search", "series"]))
async def search_handler(client, message):
    if len(message.command) < 2: return await message.reply_text("Usage: /search Name")
    query = " ".join(message.command[1:])
    stype = "tv" if "series" in message.command[0] else "movie"
    status = await message.reply_text("🔎 Searching...")
    try:
        url = f"https://api.themoviedb.org/3/search/{stype}?api_key={TMDB_API_KEY}&query={query}"
        res = requests.get(url).json().get('results')
        if not res: return await status.edit("❌ Not Found")
        top = res[0]
        img_url = f"https://api.themoviedb.org/3/{stype}/{top['id']}/images?api_key={TMDB_API_KEY}&include_image_language=en,hi"
        posters = requests.get(img_url).json().get('posters', [])
        final_poster = posters[0]['file_path'] if posters else top.get('poster_path')
        if not final_poster: return await status.edit("❌ No Logo Poster Found")
        
        caption = f"🎬 <b>{top.get('name') if stype=='tv' else top.get('title')}</b>"
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🖼 Get Poster", callback_data=f"get_poster_{stype}_{top['id']}")]])
        await status.delete()
        await message.reply_photo(f"https://image.tmdb.org/t/p/w500{final_poster}", caption=caption, reply_markup=btn)
    except Exception as e: await status.edit(f"Error: {e}")

@app.on_callback_query(filters.regex("^get_"))
async def get_callback(client, callback):
    try:
        _, _, stype, mid = callback.data.split("_")
        url = f"https://api.themoviedb.org/3/{stype}/{mid}/images?api_key={TMDB_API_KEY}&include_image_language=en,hi"
        data = requests.get(url).json().get('posters', [])[:3]
        if not data: return await callback.answer("No logos found!")
        for img in data:
            await client.send_photo(callback.from_user.id, f"https://image.tmdb.org/t/p/original{img['file_path']}")
        await callback.answer()
    except: pass

@app.on_message(filters.private & filters.text)
async def handle_text(client, message):
    if message.text.startswith("/"): return
    uid = message.from_user.id
    if user_modes.get(uid) == "link":
        txt = message.text.strip().split("?start=")[1].split()[0] if "?start=" in message.text else message.text.strip()
        enc = base64.b64encode(txt.encode()).decode()
        await message.reply_text(f"🔗 <code>{BLOGGER_URL}?data={enc}</code>")

@app.on_message(filters.private & (filters.document | filters.video | filters.audio))
async def handle_files(client, message):
    uid = message.from_user.id
    if user_modes.get(uid) == "caption":
        media = message.document or message.video or message.audio
        cap = get_fancy_caption(media.file_name or "File", humanbytes(getattr(media, "file_size", 0)), getattr(media, "duration", 0))
        if message.video: await client.send_video(uid, media.file_id, caption=cap)
        else: await client.send_document(uid, media.file_id, caption=cap)

async def start_services():
    web_app = await web_server()
    runner = web.AppRunner(web_app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", int(os.environ.get("PORT", 8080))).start()
    await app.start()
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(start_services())
    
