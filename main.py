import os
import time
import base64
import re
import asyncio
import requests
import aiofiles
import html
from aiohttp import web
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- CONFIGURATION (Apna Data Dalein) ---
API_ID = int(os.environ.get("API_ID", "12345"))
API_HASH = os.environ.get("API_HASH", "hash")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "token")
TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "02a832d91755c2f5e8a2d1a6740a8674") 
CREDIT_NAME = "🦋 Filmy Flip Hub 🦋"
BLOGGER_URL = "https://filmyflip1.blogspot.com/p/download.html"

# 🔥 IMPORTANT: HTML Mode ON for Green Line
app = Client(
    "filmy_lite", 
    api_id=API_ID, 
    api_hash=API_HASH, 
    bot_token=BOT_TOKEN, 
    parse_mode=enums.ParseMode.HTML
)

# --- WEB SERVER (Render ke liye zaroori) ---
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

# 🔥 Green Line Caption Logic
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
# --- START COMMAND ---
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    await message.reply_text(
        f"👋 <b>Hello {message.from_user.first_name}!</b>\n\n"
        "SIMPLE MODE ACTIVATED 🚀\n\n"
        "1️⃣ <b>Search:</b> <code>/search MovieName</code>\n"
        "   (Title Logo ke sath poster milega)\n\n"
        "2️⃣ <b>Caption:</b> <code>/caption</code>\n"
        "   (File bhejo, Green line caption lag jayega)\n\n"
        "3️⃣ <b>Link:</b> <code>/link</code>\n"
        "   (Text bhejo, Blogger link ban jayega)"
    )

# --- 1. SEARCH FUNCTION (With Logo Check) ---
@app.on_message(filters.command(["search", "series"]))
async def search_handler(client, message):
    if len(message.command) < 2: 
        return await message.reply_text("❌ Usage: <code>/search Mirzapur</code>")
    
    query = " ".join(message.command[1:])
    stype = "tv" if "series" in message.command[0] else "movie"
    status = await message.reply_text(f"🔎 <b>Searching for '{query}'...</b>")
    
    try:
        # Step 1: Find ID
        url = f"https://api.themoviedb.org/3/search/{stype}?api_key={TMDB_API_KEY}&query={query}"
        res = requests.get(url).json()['results']
        if not res: return await status.edit("❌ Not Found!")
        
        top_res = res[0]
        mid = top_res['id']
        title = top_res.get('name') if stype == "tv" else top_res.get('title')
        overview = top_res.get('overview', '')[:200] + "..."

        # Step 2: Get Images (Strictly English/Hindi for Logos)
        img_url = f"https://api.themoviedb.org/3/{stype}/{mid}/images?api_key={TMDB_API_KEY}&include_image_language=en,hi"
        img_data = requests.get(img_url).json()
        
        # Filter: Only Logos
        posters = img_data.get('posters', [])
        backdrops = img_data.get('backdrops', [])
        
        # Fallback to main poster if no specific logo found, but prioritize EN/HI
        final_poster = posters[0]['file_path'] if posters else top_res.get('poster_path')
        
        if not final_poster: return await status.edit("❌ No Poster Found!")

        # Buttons
        btn = InlineKeyboardMarkup([
            [InlineKeyboardButton("🖼 Posters (Logos)", callback_data=f"get_poster_{stype}_{mid}"),
             InlineKeyboardButton("🎞 Thumbnails (Logos)", callback_data=f"get_back_{stype}_{mid}")]
        ])
        
        caption = f"🎬 <b>{title}</b>\n\n📝 <i>{overview}</i>"
        await status.delete()
        await message.reply_photo(f"https://image.tmdb.org/t/p/w500{final_poster}", caption=caption, reply_markup=btn)

    except Exception as e:
        await status.edit(f"❌ Error: {e}")

@app.on_callback_query(filters.regex("^get_"))
async def get_images_callback(client, callback):
    try:
        _, img_type, stype, mid = callback.data.split("_")
        await callback.answer("Fetching Logos...")
        
        # Fetch Again for clean list
        img_url = f"https://api.themoviedb.org/3/{stype}/{mid}/images?api_key={TMDB_API_KEY}&include_image_language=en,hi"
        data = requests.get(img_url).json()
        pool = data.get('posters' if img_type == 'poster' else 'backdrops', [])
        
        if not pool: return await callback.message.reply_text("❌ Iska koi Logo wala image nahi mila!")
        
        # Send top 3 images
        limit = min(3, len(pool))
        for i in range(limit):
            path = pool[i]['file_path']
            await client.send_photo(callback.from_user.id, f"https://image.tmdb.org/t/p/original{path}", caption=f"🖼 <b>Image {i+1}</b>")
            
    except Exception as e:
        await callback.message.reply_text(f"Error: {e}")

# --- 2. CAPTION & LINK SETUP ---
@app.on_message(filters.command("caption") & filters.private)
async def set_caption_mode(client, message):
    user_modes[message.from_user.id] = "caption"
    await message.reply_text("📝 <b>Caption Mode ON!</b>\nAb koi bhi Video/File bhejo, main naya caption laga dunga.")

@app.on_message(filters.command("link") & filters.private)
async def set_link_mode(client, message):
    user_modes[message.from_user.id] = "link"
    await message.reply_text("🔗 <b>Link Mode ON!</b>\nAb text/code bhejo.")

# --- 3. HANDLE TEXT (For Link) ---
@app.on_message(filters.private & filters.text)
async def handle_text(client, message):
    uid = message.from_user.id
    if user_modes.get(uid) == "link":
        text = message.text.strip()
        # Clean if user sends a full link
        if "?start=" in text: text = text.split("?start=")[1].split()[0]
        
        encoded = base64.b64encode(text.encode()).decode()
        final_link = f"{BLOGGER_URL}?data={encoded}"
        
        await message.reply_text(f"✅ <b>Generated Link:</b>\n\n<code>{final_link}</code>")
    else:
        # Agar bina command ke text bheja
        await message.reply_text("⚠️ Kripya <code>/link</code> ya <code>/search</code> use karein.")

# --- 4. HANDLE FILES (For Caption) ---
@app.on_message(filters.private & (filters.document | filters.video | filters.audio))
async def handle_files(client, message):
    uid = message.from_user.id
    
    if user_modes.get(uid) == "caption":
        msg = await message.reply_text("⏳ <b>Processing...</b>")
        try:
            media = message.document or message.video or message.audio
            file_name = media.file_name or "Unknown_File"
            file_size = humanbytes(getattr(media, "file_size", 0))
            duration = getattr(media, "duration", 0) or 0
            
            # 🔥 Fancy Caption Generate
            new_caption = get_fancy_caption(file_name, file_size, duration)
            
            # Send Back (No Download needed, just File ID copy)
            if message.video:
                await client.send_video(uid, media.file_id, caption=new_caption, parse_mode=enums.ParseMode.HTML)
            else:
                await client.send_document(uid, media.file_id, caption=new_caption, parse_mode=enums.ParseMode.HTML)
                
            await msg.delete()
        except Exception as e:
            await msg.edit(f"❌ Error: {e}")
    else:
        await message.reply_text("⚠️ <b>Caption Mode OFF hai.</b>\nOn karne ke liye <code>/caption</code> dabayein.")

# --- SERVER START ---
async def start_services():
    try:
        port = int(os.environ.get("PORT", 8080))
        web_app = await web_server()
        runner = web.AppRunner(web_app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        print("✅ Web Server Started!")
        print("✅ Starting Bot...")
        await app.start()
        print("✅ Bot is Alive!")
        await asyncio.Event().wait()
    except Exception as e:
        print(f"❌ CRITICAL ERROR: {e}")

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(start_services())
