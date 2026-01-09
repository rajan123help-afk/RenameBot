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

# --- CONFIGURATION (UPDATED WITH 3 CHANNELS) ---
API_ID = int(os.environ.get("API_ID", "23421127"))
API_HASH = os.environ.get("API_HASH", "0375dd20aba9f2e7c29d0c1c06590dfb")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8468501492:AAGpDSdzdlEzkJs9AqHkA0AHPcmSv1Dwlgk") 
OWNER_ID = int(os.environ.get("OWNER_ID", "5027914470"))
MONGO_URL = os.environ.get("MONGO_URL", "mongodb+srv://raja:raja2001@filmyflip.jlitika.mongodb.net/?retryWrites=true&w=majority")
DB_CHANNEL_ID = int(os.environ.get("DB_CHANNEL_ID", "-1003311810643"))

# 🔥 FORCE SUBSCRIBE CHANNELS LIST (3 Links) 🔥
FS_CHANNELS = [
    {"id": -1002410972822, "link": "https://t.me/+j4eYjjJLTGY4MTFl"},
    {"id": -1002312115538, "link": "https://t.me/+COWqvDXiQUkxOWE9"},
    {"id": -1002384884726, "link": "https://t.me/+5Rue8fj6dC80NmE9"},
]

TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "02a832d91755c2f5e8a2d1a6740a8674")
CREDIT_NAME = "🦋 Filmy Flip Hub 🦋"
BLOGGER_URL = "https://filmyflip1.blogspot.com/p/download.html"
# --- DATABASE SETUP ---
mongo = AsyncIOMotorClient(MONGO_URL)
db = mongo["FilmyFlipBot"]
settings_col = db["settings"]

# --- BOT SETUP ---
app = Client(
    "filmy_pro_main", 
    api_id=API_ID, 
    api_hash=API_HASH, 
    bot_token=BOT_TOKEN, 
    parse_mode=enums.ParseMode.HTML,
    workers=10, 
    max_concurrent_transmissions=5
)

clone_app = None
user_modes = {}
user_data = {} # To store temp data like last_msg_id
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

def encode_id(msg_id):
    return base64.urlsafe_b64encode(str(msg_id).encode("ascii")).decode("ascii").strip("=")

def decode_id(string):
    string = str(string)
    padding = len(string) % 4
    if padding: string += "=" * (4 - padding)
    return base64.urlsafe_b64decode(string.encode("ascii")).decode("ascii")

def create_payload(start_param):
    return base64.b64encode(start_param.encode("utf-8")).decode("utf-8")
     # --- CLONE LOGIC ---
async def get_active_clone_token():
    data = await settings_col.find_one({"_id": "active_clone"})
    return data["token"] if data else None

async def set_active_clone_token(token):
    await settings_col.update_one({"_id": "active_clone"}, {"$set": {"token": token}}, upsert=True)

async def start_clone_bot(token):
    global clone_app
    if clone_app: await clone_app.stop()
    print(f"♻️ Starting Clone Bot...")
    clone_app = Client("CloneBot_Session", api_id=API_ID, api_hash=API_HASH, bot_token=token, ipv6=False)
    
    @clone_app.on_message(filters.command("start") & filters.private)
    async def clone_start(client, message):
        # 1. Start without Link
        if len(message.command) < 2:
            txt = (f"👋 **Hello {message.from_user.first_name}!**\n\n🚀 **Yeh Filmy Flip Hub ka Super Fast File Deliver Bot hai!**\n\n📂 **Files ke liye:** 👇\n🔗 {FS_CHANNELS[0]['link']}")
            btn = InlineKeyboardMarkup([[InlineKeyboardButton("👨‍💻 Contact Admin", url="https://t.me/Moviessrudio_bot")]])
            return await message.reply_text(txt, reply_markup=btn, disable_web_page_preview=True)

        # 2. Force Subscribe Check (For ALL 3 Channels)
        missing = []
        for ch in FS_CHANNELS:
            try:
                await client.get_chat_member(ch["id"], message.from_user.id)
            except UserNotParticipant:
                missing.append(ch["link"])
            except Exception as e:
                pass # Ignore other errors

        if missing:
            buttons = [[InlineKeyboardButton(f"📢 Join Channel {i+1}", url=link)] for i, link in enumerate(missing)]
            try:
                buttons.append([InlineKeyboardButton("🔄 Try Again", url=f"https://t.me/{client.me.username}?start={message.command[1]}")])
            except: pass
            return await message.reply("**⚠️ Pehle Saare Channels Join Karein!**\n\nTabhi Movie ki File milegi 👇", reply_markup=InlineKeyboardMarkup(buttons))

        # 3. File Delivery
        try:
            decoded = decode_id(message.command[1])
            msg_id = int(decoded.split("_")[-1]) if "link_" in decoded else int(decoded)
            loading = await message.reply("🔄 **Checking File...**")
            await client.copy_message(message.chat.id, DB_CHANNEL_ID, msg_id)
            await loading.delete()
        except Exception as e:
            await message.reply(f"❌ **File Not Found.**\n\nError: {e}")

    await clone_app.start()
    return (await clone_app.get_me()).username
    # --- MAIN HANDLERS ---

@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    user_modes[message.from_user.id] = None # Reset modes
    await message.reply_text(
        f"👋 <b>Hello {message.from_user.first_name}!</b>\n\n"
        "🎬 <b>Commands:</b>\n"
        "🔹 <code>/store</code> (File Store & Link)\n"
        "🔹 <code>/clone</code> (Create Public Bot)\n"
        "🔹 <code>/replace</code> (Change Clone Bot)\n"
        "🔹 <code>/search Name</code> (TMDB Search)\n"
        "🔹 <code>/batch</code> (Bulk Rename)"
    )

# 1. CLONE & REPLACE (NEW LOGIC: ASK & DELETE)
@app.on_message(filters.command(["clone", "replace"]) & filters.user(OWNER_ID))
async def clone_ask(client, message):
    user_modes[message.from_user.id] = "waiting_clone_token"
    # Save bot message id to delete later
    msg = await message.reply_text("⚙️ **Send Clone Bot Token:**\n\n(Message will be deleted automatically for security)", reply_markup=ForceReply(True))
    user_data[message.from_user.id] = {"ask_msg_id": msg.id}

# 2. STORE MODE
@app.on_message(filters.command("store") & filters.private)
async def store_mode_handler(client, message):
    user_modes[message.from_user.id] = "store"
    await message.reply_text("📥 **Store Mode ON!**\n\nAb File bhejo.\nLink milega aur aapki File **Delete** ho jayegi (Safety ke liye).")
    # 3. TEXT HANDLER (Token Catch & Normal)
@app.on_message(filters.private & filters.text)
async def text_handler(client, message):
    if message.text.startswith("/"): return
    uid = message.from_user.id
    text = message.text.strip()
    
    # --- CLONE TOKEN LOGIC ---
    if user_modes.get(uid) == "waiting_clone_token":
        token = text
        ask_data = user_data.get(uid, {})
        
        # 1. Delete User's Token Message (SECURITY)
        try: await message.delete() 
        except: pass
        
        # 2. Delete Bot's "Send Token" Message
        if "ask_msg_id" in ask_data:
            try: await client.delete_messages(uid, ask_data["ask_msg_id"])
            except: pass
            
        status = await client.send_message(uid, "♻️ **Connecting Clone Bot...**")
        
        try:
            await set_active_clone_token(token)
            username = await start_clone_bot(token)
            await status.edit(f"✅ **Clone Active:** @{username}\n\n⚠️ **Bot ko DB Channel me Admin bana dena!**")
        except Exception as e:
            await status.edit(f"❌ Error: {e}")
        
        user_modes[uid] = None # Reset
        return
    # -------------------------

    # --- NORMAL TEXT LOGIC ---
    if user_modes.get(uid) == "link":
        code = text
        if "t.me/" in text: code = text.split("/")[-1] 
        elif "?start=" in text: code = text.split("?start=")[1].split()[0]
        enc = base64.b64encode(code.encode()).decode()
        await message.reply_text(f"🔗 <code>{BLOGGER_URL}?data={enc}</code>")
        return

    if uid in download_queue and 'name' not in download_queue[uid]:
        download_queue[uid]['name'] = text
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🎥 Video", callback_data="dl_vid"), InlineKeyboardButton("📁 File", callback_data="dl_doc")]])
        await message.reply_text(f"✅ Name: <b>{text}</b>", reply_markup=btn)
        return

    if uid in batch_data and batch_data[uid].get('step') == 'naming':
        batch_data[uid]['name'] = text
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🎥 Video", callback_data="batch_run_vid"), InlineKeyboardButton("📁 File", callback_data="batch_run_doc")]])
        await message.reply_text(f"✅ Name: {text}\nStart?", reply_markup=btn)
        return

# 4. MEDIA HANDLER (STORE & DELETE LOGIC)
@app.on_message(filters.private & (filters.photo | filters.document | filters.video | filters.audio))
async def media_handler(client, message):
    uid = message.from_user.id
    
    # --- STORE MODE ---
    if user_modes.get(uid) == "store":
        try:
            # Copy to DB
            db_msg = await message.copy(chat_id=DB_CHANNEL_ID)
            # Link
            payload = create_payload(encode_id(db_msg.id))
            final_link = f"{BLOGGER_URL}?data={payload}"
            
            await message.reply_text(f"✅ **File Stored!**\n\n🔗 **Link:**\n`{final_link}`")
            
            # 🔥 DELETE USER FILE (SAFETY) 🔥
            await message.delete()
            
        except Exception as e:
            await message.reply_text(f"❌ Error: {e}")
        return
    # ------------------

    # --- NORMAL RENAME ---
    is_image = False
    if message.photo: is_image = True
    elif message.document and (message.document.mime_type.startswith("image/") or message.document.file_name.lower().endswith((".jpg", ".png"))): is_image = True

    if is_image:
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🖼 Save Thumbnail", callback_data="save_thumb"), InlineKeyboardButton("💧 Save Watermark", callback_data="save_wm")]])
        await message.reply_text("📸 <b>Image Detected!</b>", reply_markup=btn, quote=True)
        return 

    if user_modes.get(uid) == "caption":
        return

    if uid in batch_data and 'step' not in batch_data[uid]:
        batch_data[uid]['files'].append(message)
        return
        # --- OLD CALLBACKS & UTILS ---
async def get_real_filename(url):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, allow_redirects=True) as resp:
                if "Content-Disposition" in resp.headers:
                    cd = resp.headers["Content-Disposition"]
                    fname = re.search(r'filename="?([^"]+)"?', cd)
                    if fname: return unquote(fname.group(1))
    except: pass
    return unquote(url.split("/")[-1].split("?")[0])

def clean_filename(name):
    for k, v in cleaner_dict.items(): name = name.replace(k, v)
    return re.sub(r'[<>:"/\\|?*]', '', name).strip()

def get_fancy_caption(filename, filesize, duration=0):
    safe_name = html.escape(filename)
    caption = f"<b>{safe_name}</b>\n\n"
    caption += f"<blockquote><b>File Size ♻️ ➥ {filesize}</b></blockquote>\n"
    caption += f"<blockquote><b>Powered By ➥ {CREDIT_NAME}</b></blockquote>"
    return caption

def apply_watermark(base_path, wm_path):
    # Same WM logic
    try:
        base = Image.open(base_path).convert("RGBA")
        wm = Image.open(wm_path).convert("RGBA")
        base_w, base_h = base.size
        wm_w, wm_h = wm.size
        new_wm_w = int(base_w * 0.70)
        ratio = new_wm_w / wm_w
        new_wm_h = int(wm_h * ratio)
        wm = wm.resize((new_wm_w, new_wm_h), Image.Resampling.LANCZOS)
        x = (base_w - new_wm_w) // 2
        y = base_h - new_wm_h - 20 
        if y < 0: y = base_h - new_wm_h
        base.paste(wm, (x, y), wm)
        base = base.convert("RGB")
        base.save(base_path, "JPEG")
        return base_path
    except: return base_path

async def progress(current, total, message, start_time, task_name):
    now = time.time()
    diff = now - start_time
    if round(diff % 5.00) == 0 or current == total:
        percentage = current * 100 / total
        speed = current / diff if diff > 0 else 0
        text = f"<b>{task_name}</b>\nProgress: {round(percentage, 1)}%\nSpeed: {humanbytes(speed)}/s"
        try: await message.edit(text)
        except: pass

@app.on_message(filters.command(["search", "series"]))
async def search_handler(client, message):
    if len(message.command) < 2: return await message.reply_text("Usage: /search Name")
    raw_query = " ".join(message.command[1:])
    stype = "tv" if "series" in message.command[0] else "movie"
    status = await message.reply_text(f"🔎 <b>Searching:</b> {raw_query}...")
    try:
        url = f"https://api.themoviedb.org/3/search/{stype}?api_key={TMDB_API_KEY}&query={raw_query}"
        res = requests.get(url).json().get('results')
        if not res: return await status.edit("❌ Not Found")
        mid = res[0]['id']
        title = res[0].get('name') if stype == 'tv' else res[0].get('title')
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🖼 Poster", callback_data=f"type_poster_{stype}_{mid}_0")]])
        await status.edit(f"🎬 <b>{title}</b>", reply_markup=btn)
    except Exception as e: await status.edit(f"Error: {e}")

@app.on_callback_query(filters.regex("^save_"))
async def save_img_callback(client, callback):
    uid = callback.from_user.id
    mode = "thumbnails" if "thumb" in callback.data else "watermarks"
    os.makedirs(mode, exist_ok=True)
    ext = ".png" if mode == "watermarks" else ".jpg"
    path = f"{mode}/{uid}{ext}"
    await callback.message.edit("⏳ <b>Saving...</b>")
    try:
        reply = callback.message.reply_to_message
        if not reply: return await callback.message.edit("❌ Error")
        temp_path = f"downloads/{uid}_temp_img"
        os.makedirs("downloads", exist_ok=True)
        await client.download_media(message=reply, file_name=temp_path)
        img = Image.open(temp_path)
        if mode == "watermarks":
             img = img.convert("RGBA")
             img.save(path, "PNG")
        else:
             img = img.convert("RGB")
             img.save(path, "JPEG")
        os.remove(temp_path)
        await callback.message.edit("✅ Saved!")
    except Exception as e: await callback.message.edit(f"❌ Error: {e}")

# --- START ---
async def start_services():
    app_web = await web_server()
    runner = web.AppRunner(app_web)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", int(os.environ.get("PORT", 8080))).start()
    
    await app.start()
    print("🚀 Main Bot Started!")

    token = await get_active_clone_token()
    if token:
        try: await start_clone_bot(token)
        except Exception as e: print(f"Clone Start Error: {e}")

    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(start_services())
    
