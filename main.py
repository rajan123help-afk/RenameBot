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
# Apni IDs yahan daalein ya Render Environment variables use karein
API_ID = int(os.environ.get("API_ID", "23421127"))
# 👇 YAHAN GALTI THI, AB SAHI HAI (Ek bracket hataya)
API_HASH = os.environ.get("API_HASH", "0375dd20aba9f2e7c29d0c1c06590dfb")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "7222455447:AAG3hsn3CLCm16wd8Mcdf7I67Oz2AhaIhA8") 
OWNER_ID = int(os.environ.get("OWNER_ID", "5027914470"))
MONGO_URL = os.environ.get("MONGO_URL", "mongodb+srv://raja:raja2001@filmyflip.jlitika.mongodb.net/?retryWrites=true&w=majority")
DB_CHANNEL_ID = int(os.environ.get("DB_CHANNEL_ID", "-1003311810643"))
TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "02a832d91755c2f5e8a2d1a6740a8674")
CREDIT_NAME = "🦋 Filmy Flip Hub 🦋"
BLOGGER_URL = "https://filmyflip1.blogspot.com/p/download.html"

# 🔥 FORCE SUBSCRIBE CHANNELS (3 Links) 🔥
FS_CHANNELS = [
    {"id": -1002410972822, "link": "https://t.me/+j4eYjjJLTGY4MTFl"},
    {"id": -1002312115538, "link": "https://t.me/+COWqvDXiQUkxOWE9"},
    {"id": -1002384884726, "link": "https://t.me/+5Rue8fj6dC80NmE9"},
]

# --- BOT & DATABASE SETUP ---
mongo = AsyncIOMotorClient(MONGO_URL)
db = mongo["FilmyFlipBot"]
settings_col = db["settings"]

app = Client(
    "filmy_pro_final", 
    api_id=API_ID, 
    api_hash=API_HASH, 
    bot_token=BOT_TOKEN, 
    parse_mode=enums.ParseMode.HTML,
    workers=10, 
    max_concurrent_transmissions=5
)

# --- GLOBAL VARS ---
clone_app = None
user_modes = {}
user_data = {} 
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
        if metadata.has("duration"): return metadata.get('duration').seconds
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

async def get_real_filename(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, allow_redirects=True, timeout=10) as resp:
                if "Content-Disposition" in resp.headers:
                    cd = resp.headers["Content-Disposition"]
                    fname_match = re.search(r'filename="?([^"]+)"?', cd)
                    if fname_match: return unquote(fname_match.group(1))
    except: pass
    return unquote(url.split("/")[-1].split("?")[0])

def clean_filename(name):
    for k, v in cleaner_dict.items(): name = name.replace(k, v)
    return re.sub(r'[<>:"/\\|?*]', '', name).strip()

def get_media_info(name):
    name = unquote(name).replace(".", " ").replace("_", " ").replace("-", " ")
    match1 = re.search(r"(?i)(?:s|season)\s*[\.]?\s*(\d{1,2})\s*[\.]?\s*(?:e|ep|episode)\s*[\.]?\s*(\d{1,3})", name)
    if match1: return match1.group(1), match1.group(2)
    match2 = re.search(r"(\d{1,2})x(\d{1,3})", name)
    if match2: return match2.group(1), match2.group(2)
    return None, None

# 🔥 FANCY CAPTION (Green Line & Quote Style) 🔥
def get_fancy_caption(filename, filesize, duration=0):
    safe_name = html.escape(filename)
    caption = f"{safe_name}\n\n"
    
    # S/E Logic
    s, e = get_media_info(filename)
    if s: s = s.zfill(2)
    if e: e = e.zfill(2)
    if s: caption += f"💿 <b>Season ➥ {s}</b>\n"
    if e: caption += f"📺 <b>Episode ➥ {e}</b>\n\n"
    
    caption += f"<blockquote><b>File Size ♻️ ➥ {filesize} ”</b></blockquote>\n"
    caption += f"<blockquote><b>Duration ⏰ ➥ {get_duration_str(duration)} ”</b></blockquote>\n"
    caption += f"<blockquote><b>Powered By ➥ {CREDIT_NAME} ”</b></blockquote>"
    return caption

def apply_watermark(base_path, wm_path):
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
    except Exception as e: return base_path

async def progress(current, total, message, start_time, task_name):
    now = time.time()
    diff = now - start_time
    if round(diff % 5.00) == 0 or current == total:
        percentage = current * 100 / total
        speed = current / diff if diff > 0 else 0
        try: await message.edit(f"<b>{task_name}</b>\n{round(percentage, 1)}% | {humanbytes(speed)}/s")
        except: pass
    # --- CLONE BOT LOGIC ---
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

        # 2. Force Subscribe Check (3 Channels)
        missing = []
        for ch in FS_CHANNELS:
            try: await client.get_chat_member(ch["id"], message.from_user.id)
            except UserNotParticipant: missing.append(ch["link"])
            except: pass

        if missing:
            buttons = [[InlineKeyboardButton(f"📢 Join Channel {i+1}", url=link)] for i, link in enumerate(missing)]
            try: buttons.append([InlineKeyboardButton("🔄 Try Again", url=f"https://t.me/{client.me.username}?start={message.command[1]}")])
            except: pass
            return await message.reply("**⚠️ Pehle Saare Channels Join Karein!**\n\nTabhi Movie ki File milegi 👇", reply_markup=InlineKeyboardMarkup(buttons))

        # 3. File Delivery + Auto Delete ⏳
        try:
            decoded = decode_id(message.command[1])
            msg_id = int(decoded.split("_")[-1]) if "link_" in decoded else int(decoded)
            
            loading = await message.reply("🔄 **Checking File...**")
            sent_msg = await client.copy_message(message.chat.id, DB_CHANNEL_ID, msg_id)
            await loading.delete()
            
            # 🔥 5 Minute Timer (300 Seconds)
            msg_alert = await message.reply_text("⏳ **Yeh File 5 Minute mein Delete ho jayegi! Jaldi Forward kar lo.**")
            await asyncio.sleep(300)
            
            # 🔥 Delete & Button
            await sent_msg.delete()
            await msg_alert.delete()
            
            btn = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Get File Again", url=f"https://t.me/{client.me.username}?start={message.command[1]}")],[InlineKeyboardButton("📢 Join Channel", url=FS_CHANNELS[0]['link'])]])
            await message.reply_text("❌ **Time Over! File Delete ho gayi.**\n\nWapas lene ke liye niche click karein:", reply_markup=btn)

        except Exception as e:
            await message.reply(f"❌ **File Not Found.**\n\nError: {e}")

    await clone_app.start()
    return (await clone_app.get_me()).username
                    # --- MAIN COMMANDS ---
@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    user_modes[message.from_user.id] = None
    await message.reply_text(
        f"👋 <b>Hello {message.from_user.first_name}!</b>\n\n"
        "🎬 <b>Filmy Flip Commands:</b>\n"
        "🔹 <code>/store</code> (Save & Link)\n"
        "🔹 <code>/clone</code> (Public Bot)\n"
        "🔹 <code>/search Name</code> (Movie)\n"
        "🔹 <code>/series Name S1</code> (Series)\n"
        "🔹 <code>/caption</code> (Green Line)\n"
        "🔹 <code>/batch</code> (Rename)\n"
        "🔹 <code>/url</code> (Link Upload)\n"
        "🔹 <code>/add</code> & <code>/del</code> (Cleaner)"
    )

@app.on_message(filters.command(["clone", "replace"]) & filters.user(OWNER_ID))
async def clone_ask(client, message):
    user_modes[message.from_user.id] = "waiting_clone_token"
    msg = await message.reply_text("⚙️ **Send Clone Bot Token:**\n(Msg will auto-delete)", reply_markup=ForceReply(True))
    user_data[message.from_user.id] = {"ask_msg_id": msg.id}

@app.on_message(filters.command("store") & filters.private)
async def store_mode_handler(client, message):
    user_modes[message.from_user.id] = "store"
    await message.reply_text("📥 **Store Mode ON!** File bhejo -> Caption lagega -> Link milega.")

@app.on_message(filters.command("caption") & filters.private)
async def set_caption(client, message):
    user_modes[message.from_user.id] = "caption"
    await message.reply_text("📝 **Caption Mode ON!** (Always Active)")

@app.on_message(filters.command("link") & filters.private)
async def set_link(client, message):
    user_modes[message.from_user.id] = "link"
    await message.reply_text("🔗 **Link Mode ON!** Code bhejein.")

@app.on_message(filters.command("url") & filters.private)
async def set_url(client, message):
    user_modes[message.from_user.id] = "url"
    await message.reply_text("🌐 **URL Mode ON!** Link bhejein.")

@app.on_message(filters.command("add") & filters.private)
async def add_clean(client, message):
    if len(message.command) > 1: cleaner_dict[message.command[1]] = ""; await message.reply(f"✅ Added: {message.command[1]}")

@app.on_message(filters.command("del") & filters.private)
async def del_clean(client, message):
    if len(message.command) > 1 and message.command[1] in cleaner_dict: del cleaner_dict[message.command[1]]; await message.reply(f"🗑 Removed")

# --- TEXT HANDLER ---
@app.on_message(filters.private & filters.text)
async def text_handler(client, message):
    if message.text.startswith("/"): return
    uid = message.from_user.id
    text = message.text.strip()
    
    # 1. Clone Token
    if user_modes.get(uid) == "waiting_clone_token":
        try: await message.delete(); await client.delete_messages(uid, user_data[uid]["ask_msg_id"])
        except: pass
        status = await client.send_message(uid, "♻️ **Connecting...**")
        try:
            await set_active_clone_token(text)
            username = await start_clone_bot(text)
            await status.edit(f"✅ **Clone Active:** @{username}")
        except Exception as e: await status.edit(f"❌ Error: {e}")
        user_modes[uid] = None
        return
    
    # 2. Link Mode (Blogger)
    if user_modes.get(uid) == "link":
        code = text
        if "t.me/" in text: code = text.split("/")[-1] 
        elif "?start=" in text: code = text.split("?start=")[1].split()[0]
        enc = base64.b64encode(code.encode()).decode()
        await message.reply_text(f"🔗 <code>{BLOGGER_URL}?data={enc}</code>")
        return

    # 3. URL Uploader & Rename
    if text.startswith("http://") or text.startswith("https://"):
        status = await message.reply("🔗 **Checking URL...**")
        real_name = await get_real_filename(text)
        download_queue[uid] = {'url': text, 'original_name': real_name}
        await status.delete()
        await message.reply(f"📂 **Original:** {real_name}\n📝 **New Name bhejein:**", reply_markup=ForceReply(True))
        return

    if uid in download_queue and 'name' not in download_queue[uid]:
        download_queue[uid]['name'] = text
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🎥 Video", callback_data="dl_vid"), InlineKeyboardButton("📁 File", callback_data="dl_doc")]])
        await message.reply_text(f"✅ Name: <b>{text}</b>\nFormat Select karein:", reply_markup=btn)
        return

    if uid in batch_data and batch_data[uid].get('step') == 'naming':
        batch_data[uid]['name'] = text
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🎥 Video", callback_data="batch_run_vid"), InlineKeyboardButton("📁 File", callback_data="batch_run_doc")]])
        await message.reply_text(f"✅ Name: {text}\nStart?", reply_markup=btn)
        return
# --- MEDIA HANDLER (STORE, THUMB, ETC) ---
@app.on_message(filters.private & (filters.document | filters.video | filters.audio | filters.photo))
async def media_handler(client, message):
    uid = message.from_user.id
    
    # A. STORE MODE (Sabse Important)
    if user_modes.get(uid) == "store":
        try:
            loading = await message.reply("⚙️ **Processing...**")
            # 1. DB me copy karo
            db_msg = await message.copy(chat_id=DB_CHANNEL_ID)
            
            # 2. Fancy Caption lagao DB me
            media = db_msg.document or db_msg.video or db_msg.audio or db_msg.photo
            if media:
                new_cap = get_fancy_caption(getattr(media, "file_name", "File"), humanbytes(getattr(media, "file_size", 0)), getattr(media, "duration", 0))
                await db_msg.edit_caption(new_cap)
            
            # 3. Link generate karo
            payload = create_payload(encode_id(db_msg.id))
            await loading.delete()
            await message.reply(f"✅ **Stored!**\n🔗 `{BLOGGER_URL}?data={payload}`")
            
            # 4. User ki file delete (Safety)
            await message.delete() 
        except Exception as e: await message.reply(f"❌ Error: {e}")
        return

    # B. IMAGE/THUMBNAIL
    is_img = message.photo or (message.document and message.document.mime_type.startswith("image/"))
    if is_img:
        await message.reply("📸 **Image Detected!**", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🖼 Save Thumbnail", callback_data="save_thumb"), InlineKeyboardButton("💧 Save Watermark", callback_data="save_wm")]], quote=True))
        return

    # C. BATCH COLLECT
    if uid in batch_data and 'step' not in batch_data[uid]:
        batch_data[uid]['files'].append(message)

# --- SEARCH, SERIES COMMANDS ---
@app.on_message(filters.command(["search", "series"]))
async def search_handler(client, message):
    if len(message.command) < 2: return await message.reply_text("Usage: /search Name or /series Name S1")
    raw_query = " ".join(message.command[1:])
    stype = "tv" if "series" in message.command[0] else "movie"
    season_num = 0
    if stype == "tv":
        match = re.search(r"(?i)\s*(?:s|season)\s*(\d+)$", raw_query)
        if match: season_num = int(match.group(1)); raw_query = re.sub(r"(?i)\s*(?:s|season)\s*(\d+)$", "", raw_query).strip()
    status = await message.reply_text(f"🔎 <b>Searching:</b> {raw_query}...")
    try:
        url = f"https://api.themoviedb.org/3/search/{stype}?api_key={TMDB_API_KEY}&query={raw_query}"
        res = requests.get(url).json().get('results')
        if not res: return await status.edit("❌ Not Found")
        mid = res[0]['id']
        title = res[0].get('name') if stype == 'tv' else res[0].get('title')
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("🖼 Poster", callback_data=f"type_poster_{stype}_{mid}_{season_num}"), InlineKeyboardButton("🎞 Thumbnail", callback_data=f"type_backdrop_{stype}_{mid}_{season_num}")]])
        txt = f"🎬 <b>{title}</b>"
        if season_num > 0: txt += f"\n💿 <b>Season: {season_num}</b>"
        txt += "\n👇 Kya chahiye?"
        await status.edit(txt, reply_markup=btn)
    except Exception as e: await status.edit(f"Error: {e}")

@app.on_callback_query(filters.regex("^type_"))
async def type_callback(client, callback):
    try:
        _, img_type, stype, mid, s_num = callback.data.split("_")
        btn = InlineKeyboardMarkup([[InlineKeyboardButton("1", callback_data=f"num_1_{img_type}_{stype}_{mid}_{s_num}"), InlineKeyboardButton("2", callback_data=f"num_2_{img_type}_{stype}_{mid}_{s_num}")], [InlineKeyboardButton("3", callback_data=f"num_3_{img_type}_{stype}_{mid}_{s_num}"), InlineKeyboardButton("4", callback_data=f"num_4_{img_type}_{stype}_{mid}_{s_num}")]])
        await callback.message.edit(f"✅ <b>{img_type.capitalize()} Selected!</b>\nKitni images chahiye?", reply_markup=btn)
    except: pass

@app.on_callback_query(filters.regex("^num_"))
async def num_callback(client, callback):
    try:
        uid = callback.from_user.id
        _, count, img_type, stype, mid, s_num = callback.data.split("_")
        count = int(count); s_num = int(s_num)
        await callback.answer(f"Sending top {count} images...")
        await callback.message.delete()
        pool = []
        if stype == "tv" and s_num > 0:
            url = f"https://api.themoviedb.org/3/tv/{mid}/season/{s_num}/images?api_key={TMDB_API_KEY}&include_image_language=en,hi,null"
            data = requests.get(url).json()
            pool = data.get('posters' if img_type == 'poster' else 'backdrops', [])
        if not pool:
            url = f"https://api.themoviedb.org/3/{stype}/{mid}/images?api_key={TMDB_API_KEY}&include_image_language=en,hi"
            data = requests.get(url).json()
            pool = data.get('posters' if img_type == 'poster' else 'backdrops', [])
        if not pool: return await client.send_message(uid, "❌ No images found!")
        for i, img_data in enumerate(pool[:count]):
            full_url = f"https://image.tmdb.org/t/p/original{img_data['file_path']}"
            temp_path = f"downloads/temp_{uid}_{i}.jpg"
            os.makedirs("downloads", exist_ok=True)
            async with aiohttp.ClientSession() as session:
                async with session.get(full_url) as resp:
                    if resp.status == 200:
                        f = await aiofiles.open(temp_path, mode='wb'); await f.write(await resp.read()); await f.close()
            wm_path = f"watermarks/{uid}.png"
            final_path = apply_watermark(temp_path, wm_path) if os.path.exists(wm_path) else temp_path
            await client.send_photo(uid, photo=final_path, caption=f"🖼 <b>{img_type.capitalize()} {i+1}</b>")
            os.remove(temp_path); time.sleep(0.5)
    except Exception as e: await client.send_message(callback.from_user.id, f"Error: {e}")

@app.on_callback_query(filters.regex("^save_"))
async def save_img_callback(client, callback):
    uid = callback.from_user.id
    mode = "thumbnails" if "thumb" in callback.data else "watermarks"
    os.makedirs(mode, exist_ok=True)
    ext = ".png" if mode == "watermarks" else ".jpg"
    path = f"{mode}/{uid}{ext}"
    await callback.message.edit("⏳ <b>Processing...</b>")
    try:
        reply = callback.message.reply_to_message
        if not reply: return await callback.message.edit("❌ Error.")
        await client.download_media(message=reply, file_name=path)
        if mode == "watermarks": Image.open(path).convert("RGBA").save(path, "PNG")
        else: Image.open(path).convert("RGB").save(path, "JPEG")
        await callback.message.edit(f"✅ <b>{mode.capitalize()} Set!</b>")
    except Exception as e: await callback.message.edit(f"❌ Error: {e}")

@app.on_callback_query(filters.regex("^batch_run_|^dl_"))
async def process_run(client, cb):
    uid = cb.from_user.id
    is_batch = "batch" in cb.data
    data_src = batch_data if is_batch else download_queue
    if uid not in data_src: return await cb.answer("❌ Expired")
    
    files = data_src[uid]['files'] if is_batch else [data_src[uid]]
    base_name = data_src[uid].get('name', 'File')
    status = await cb.message.reply("🚀 **Starting...**")
    await cb.message.delete()
    
    for i, item in enumerate(files):
        try:
            path = f"downloads/{uid}_{i}.mkv"
            os.makedirs("downloads", exist_ok=True)
            if isinstance(item, dict) and 'url' in item:
                async with aiohttp.ClientSession() as sess:
                    async with sess.get(item['url']) as resp:
                        total = int(resp.headers.get("Content-Length", 0))
                        with open(path, "wb") as f:
                            dl = 0
                            async for chunk in resp.content.iter_chunked(1024*1024):
                                f.write(chunk); dl += len(chunk)
                                if time.time() % 5 < 0.5: await progress(dl, total, status, time.time(), "📥 Downloading")
                fname = item['original_name']
            else:
                msg_obj = item if is_batch else item['msg']
                media = msg_obj.document or msg_obj.video or msg_obj.audio
                path = await client.download_media(media, file_name=path, progress=progress, progress_args=(status, time.time(), "📥 Downloading"))
                fname = media.file_name or "video.mkv"

            s, e = get_media_info(fname)
            ext = os.path.splitext(fname)[1] or ".mkv"
            final_name = f"{base_name} - S{s.zfill(2)}E{e.zfill(2)}{ext}" if (is_batch and s and e) else (f"{base_name} - {i+1}{ext}" if is_batch else f"{base_name}{ext}")
            final_name = clean_filename(final_name)
            
            dur = get_duration(path)
            # 🔥 GREEN LINE CAPTION HERE 🔥
            cap = get_fancy_caption(final_name, humanbytes(os.path.getsize(path)), dur)
            thumb = f"thumbnails/{uid}.jpg" if os.path.exists(f"thumbnails/{uid}.jpg") else None
            wm = f"watermarks/{uid}.png"
            if thumb and os.path.exists(wm): thumb = apply_watermark(thumb, wm)
            
            if "vid" in cb.data: await client.send_video(uid, path, caption=cap, duration=dur, thumb=thumb, progress=progress, progress_args=(status, time.time(), "📤 Uploading"))
            else: await client.send_document(uid, path, caption=cap, thumb=thumb, progress=progress, progress_args=(status, time.time(), "📤 Uploading"))
            os.remove(path)
        except Exception as e: print(e)
    
    await status.edit("✅ **Done!**")
    if uid in data_src: del data_src[uid]

@app.on_callback_query(filters.regex("cancel_task"))
async def cancel_handler(client, callback):
    uid = callback.from_user.id
    if uid in download_queue: del download_queue[uid]
    if uid in batch_data: del batch_data[uid]
    await callback.answer("✅ Cancelled!")
    await callback.message.delete()

@app.on_command("batch")
async def batch_cmd(client, message):
    batch_data[message.from_user.id] = {'files': []}
    await message.reply("📦 **Batch Mode!** Files bhejo fir /done likho.")

@app.on_command("done")
async def batch_done_cmd(client, message):
    if message.from_user.id in batch_data:
        batch_data[message.from_user.id]['step'] = 'naming'
        await message.reply("📝 **Base Name bhejein:**", reply_markup=ForceReply(True))

# --- START SERVICE ---
async def start_services():
    runner = web.AppRunner(await web_server())
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", int(os.environ.get("PORT", 8080))).start()
    await app.start()
    print("🚀 Main Bot Started!")
    token = await get_active_clone_token()
    if token: asyncio.create_task(start_clone_bot(token))
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(start_services())
        
