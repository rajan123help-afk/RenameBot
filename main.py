import os
import re
import asyncio
import time
import math
import shutil
import base64
import datetime
import html
import requests
import io
from PIL import Image
from pyrogram import Client, filters, enums
from pyrogram.types import ForceReply, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from aiohttp import web
from hachoir.metadata import extractMetadata
from hachoir.parser import createParser

# --- Configs ---
API_ID = int(os.environ.get("API_ID", "12345"))
API_HASH = os.environ.get("API_HASH", "hash")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "token")

# 👇 USER CONFIGS
BLOGGER_URL = "https://filmyflip1.blogspot.com/p/download.html"
CREDIT_NAME = "🦋 Filmy Flip Hub 🦋"
TMDB_API_KEY = "02a832d91755c2f5e8a2d1a6740a8674"

# --- SERVER SETTINGS ---
MAX_TASK_LIMIT = 2
ACTIVE_TASKS = 0

# --- 🗑️ AUTO REPLACE LIST ---
REPLACE_DICT = {
    "hdhub": "Filmy Flip Hub",
    "mkvcinemas": "Filmy Flip Hub",
    "bolly4u": "Filmy Flip Hub",
    "djpunjab": "Filmy Flip Hub",
    "mp4moviez": "Filmy Flip Hub",
    "www.": "",
    ".com": "",
    "[": "",
    "]": ""
}

# --- GLOBAL VARIABLES ---
user_watermarks = {}
batch_data = {}
user_data = {}
user_modes = {}

# 🔥 CLIENT SETUP
app = Client(
    "all_in_one_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=4, 
    max_concurrent_transmissions=2,
    ipv6=False,
    parse_mode=enums.ParseMode.HTML 
)

if os.path.exists("downloads"): shutil.rmtree("downloads")
os.makedirs("downloads")
if not os.path.exists("thumbnails"): os.makedirs("thumbnails")

# --- Web Server ---
async def web_server():
    async def handle(request):
        return web.Response(text="Bot is Running!")
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8000)
    await site.start()

# --- Helper Functions ---
def humanbytes(size):
    if not size: return ""
    power = 2**10
    n = 0
    dic_power = {0: ' ', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
    while size > power:
        size /= power
        n += 1
    return str(round(size, 2)) + " " + dic_power[n] + 'B'

def get_duration_str(seconds):
    if not seconds: return "0s"
    try:
        seconds = int(seconds)
        return str(datetime.timedelta(seconds=seconds))
    except:
        return "0s"

def auto_clean(text):
    for bad_word, new_word in REPLACE_DICT.items():
        pattern = re.compile(re.escape(bad_word), re.IGNORECASE)
        text = pattern.sub(new_word, text)
    text = " ".join(text.split())
    return text.strip()

def get_extension(filename):
    if not filename: return ".mkv"
    _, ext = os.path.splitext(filename)
    if not ext: return ".mkv"
    return ext

def get_media_info(filename):
    pattern = r"[sS](\d+)[eE](\d+)|[eE]([pP])?(\d+)|(\d+)[xX](\d+)"
    match = re.search(pattern, filename)
    if match:
        if match.group(1) and match.group(2): 
            return match.group(1), match.group(2)
        elif match.group(4): 
            return None, match.group(4)
        elif match.group(5) and match.group(6): 
            return match.group(5), match.group(6)
    return None, None

def get_video_attributes(file_path):
    width = 0
    height = 0
    duration = 0
    try:
        metadata = extractMetadata(createParser(file_path))
        if metadata.has("duration"):
            duration = metadata.get('duration').seconds
        if metadata.has("width"):
            width = metadata.get("width")
        if metadata.has("height"):
            height = metadata.get("height")
    except:
        pass
    return width, height, duration

async def progress(current, total, message, start_time, task_type):
    now = time.time()
    diff = now - start_time
    if round(diff % 5.00) == 0 or current == total:
        percentage = current * 100 / total
        speed = current / diff
        time_to_completion = round((total - current) / speed) if speed > 0 else 0
        time_left_str = time.strftime("%H:%M:%S", time.gmtime(time_to_completion))
        tmp = (f"{task_type}\n"
               f"[{''.join(['●' for i in range(math.floor(percentage / 5))])}{''.join(['○' for i in range(20 - math.floor(percentage / 5))])}] {round(percentage, 2)}%\n"
               f"💾 <b>Size:</b> {humanbytes(current)} / {humanbytes(total)}\n"
               f"🚀 <b>Speed:</b> {humanbytes(speed)}/s\n"
               f"⏳ <b>ETA:</b> {time_left_str}")
        try: await message.edit(tmp)
        except: pass

# --- Helper Function (Watermark Fixed PNG) ---
def apply_watermark(base_image_url, watermark_img, position):
    response = requests.get(base_image_url)
    base = Image.open(io.BytesIO(response.content)).convert("RGBA")
    wm = watermark_img.copy().convert("RGBA")
    
    width, height = base.size
    wm_width = int(width * 0.3)
    aspect_ratio = wm_width / float(wm.size[0])
    wm_height = int(float(wm.size[1]) * float(aspect_ratio))
    wm = wm.resize((wm_width, wm_height), Image.Resampling.LANCZOS)
    
    x, y = 0, 0
    padding = 20
    
    if position == "center":
        x = (width - wm_width) // 2
        y = (height - wm_height) // 2
    elif position == "top_left":
        x, y = padding, padding
    elif position == "top_right":
        x = width - wm_width - padding
        y = padding
    elif position == "bottom_left":
        x = padding
        y = height - wm_height - padding
    elif position == "bottom_right":
        x = width - wm_width - padding
        y = height - wm_height - padding
    elif position == "top_center":
        x = (width - wm_width) // 2
        y = padding
    elif position == "bottom_center":
        x = (width - wm_width) // 2
        y = height - wm_height - padding

    transparent = Image.new('RGBA', (width, height), (0,0,0,0))
    transparent.paste(base, (0,0))
    transparent.paste(wm, (x, y), mask=wm)
    
    output = io.BytesIO()
    transparent.save(output, format="PNG") 
    output.seek(0)
    return output
    # ==========================================
# 🔥 COMMANDS & SEASON SUPPORT LOGIC
# ==========================================

@app.on_message(filters.command("start") & filters.private)
async def start_msg(client, message):
    await message.reply_text(
        f"👋 <b>Hello {message.from_user.first_name}!</b>\n\n"
        "🤖 <b>Filmy Flip All-in-One Bot</b>\n\n"
        "🎬 <b>Movies:</b> <code>/search MovieName</code>\n"
        "📺 <b>Series:</b> <code>/series Name S1</code>\n"
        "📁 <b>Renamer:</b> <code>/rename</code>, <code>/caption</code>\n"
        "💧 <b>Watermark:</b> <code>/watermark</code>, <code>/position</code>\n"
        "⚙️ <b>Settings:</b> <code>/add</code>, <code>/del</code>, <code>/words</code>"
    )

# --- Watermark Commands ---
@app.on_message(filters.command("watermark"))
async def watermark_menu(client, message):
    try: await message.delete() 
    except: pass

    user_id = message.from_user.id
    if user_id in user_watermarks and user_watermarks[user_id].get("image"):
        status = "✅ <b>Set Hai!</b>"
        btn = InlineKeyboardButton("🗑 Delete", callback_data="wm_delete")
    else:
        status = "❌ <b>Set Nahi Hai.</b>"
        btn = InlineKeyboardButton("📤 Upload Image (AS FILE)", callback_data="wm_upload_info")
    await message.reply_text(f"<b>Watermark Manager</b>\nStatus: {status}", reply_markup=InlineKeyboardMarkup([[btn]]))

@app.on_callback_query(filters.regex("^wm_"))
async def wm_callback(client, callback):
    data = callback.data
    user_id = callback.from_user.id
    if data == "wm_delete":
        user_watermarks.pop(user_id, None)
        await callback.answer("Deleted!")
        await callback.message.edit_text("❌ <b>Watermark Deleted.</b>")
    elif data == "wm_upload_info":
        await callback.answer()
        await callback.message.edit_text("📤 <b>Apni PNG Logo ko FILE (Document) banakar bhejein.</b>\n(Taaki background transparent rahe)")

# --- Photo/Document Callback Handler (Auto Clean) ---
@app.on_callback_query(filters.regex("^save_as_"))
async def save_photo_callback(client, callback):
    await callback.answer()
    data = callback.data
    user_id = callback.from_user.id
    
    original_msg = callback.message.reply_to_message
    if not original_msg or (not original_msg.photo and not original_msg.document):
        await callback.message.edit_text("❌ <b>Error:</b> File purani ho gayi hai.")
        return

    status_msg = await callback.message.edit_text("⏳ <b>Saving...</b>")

    try:
        if data == "save_as_thumb":
            if not os.path.exists("thumbnails"): os.makedirs("thumbnails")
            path = f"thumbnails/{user_id}.jpg"
            await client.download_media(original_msg, file_name=path)
            
        elif data == "save_as_wm":
            path = f"wm_{user_id}.png"
            dl_path = await client.download_media(original_msg, file_name=path)
            
            if not dl_path or not os.path.exists(dl_path):
                await status_msg.edit("❌ <b>Error:</b> Download failed.")
                return
            
            img = Image.open(dl_path).convert("RGBA")
            if user_id not in user_watermarks: user_watermarks[user_id] = {}
            user_watermarks[user_id]["image"] = img
            if "position" not in user_watermarks[user_id]:
                user_watermarks[user_id]["position"] = "center"
            
            os.remove(dl_path)

        try: await original_msg.delete() 
        except: pass
        
        await status_msg.edit("✅ <b>Saved!</b>")
        await asyncio.sleep(2)
        await status_msg.delete()

    except Exception as e:
        await status_msg.edit(f"❌ Error: {e}")
        await asyncio.sleep(5)
        try: await status_msg.delete()
        except: pass

@app.on_message(filters.command("position"))
async def position_menu(client, message):
    try: await message.delete() 
    except: pass

    user_id = message.from_user.id
    if user_id not in user_watermarks or not user_watermarks[user_id].get("image"):
        msg = await message.reply_text("❌ Pehle Watermark upload karein.")
        await asyncio.sleep(3)
        await msg.delete()
        return
    
    buttons = [
        [InlineKeyboardButton("↖️ Top Left", callback_data="pos_top_left"), InlineKeyboardButton("⬆️ Top Center", callback_data="pos_top_center"), InlineKeyboardButton("↗️ Top Right", callback_data="pos_top_right")],
        [InlineKeyboardButton("⏺️ Center", callback_data="pos_center")],
        [InlineKeyboardButton("↙️ Bottom Left", callback_data="pos_bottom_left"), InlineKeyboardButton("⬇️ Bottom Center", callback_data="pos_bottom_center"), InlineKeyboardButton("↘️ Bottom Right", callback_data="pos_bottom_right")]
    ]
    await message.reply_text(f"📍 <b>Select Position:</b>", reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex("^pos_"))
async def pos_callback(client, callback):
    user_id = callback.from_user.id
    new_pos = callback.data.replace("pos_", "")
    
    if user_id not in user_watermarks:
        return await callback.answer("Watermark missing!", show_alert=True)

    user_watermarks[user_id]["position"] = new_pos
    await callback.answer(f"Position: {new_pos}")
    
    try:
        demo_url = "https://image.tmdb.org/t/p/w1280/jXJxMcVoEuXzym3vFnjqDW4ifo6.jpg"
        wm_img = user_watermarks[user_id]["image"]
        demo_bytes = apply_watermark(demo_url, wm_img, new_pos)
        
        await callback.message.reply_photo(photo=demo_bytes, caption=f"✅ <b>Demo:</b> {new_pos}")
        await callback.message.delete() 
    except Exception as e: await callback.message.reply_text(str(e))

# --- 1️⃣ MOVIE SEARCH COMMAND ---
@app.on_message(filters.command("search"))
async def search_movie_ask(client, message):
    if len(message.command) < 2: 
        msg = await message.reply_text("❌ Usage: <code>/search Movie Name</code>")
        await asyncio.sleep(3)
        await msg.delete()
        try: await message.delete()
        except: pass
        return

    query = " ".join(message.command[1:])
    status_msg = await message.reply_text(f"🔎 <b>Searching Movie:</b> <code>{query}</code>...")
    try: await message.delete()
    except: pass
    
    try:
        search_url = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={query}"
        response = requests.get(search_url).json()
        if not response.get('results'):
            await status_msg.edit("❌ <b>Movie nahi mili!</b>")
            await asyncio.sleep(3)
            await status_msg.delete()
            return

        movie_id = response['results'][0]['id']
        movie_title = response['results'][0]['title']
        
        # '0' means no season (Movie)
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎬 Posters", callback_data=f"ask_count|poster|{movie_id}|movie|0")],
            [InlineKeyboardButton("🖼 Thumbnails", callback_data=f"ask_count|thumb|{movie_id}|movie|0")]
        ])
        
        await status_msg.edit(f"🍿 <b>Found:</b> {movie_title}\n\nKya chahiye?", reply_markup=buttons)

    except Exception as e:
        await status_msg.edit(f"❌ Error: {e}")
        await asyncio.sleep(5)
        try: await status_msg.delete()
        except: pass

# --- 2️⃣ WEBSERIES SEARCH COMMAND (WITH SEASON DETECTION) ---
@app.on_message(filters.command("series"))
async def search_series_ask(client, message):
    if len(message.command) < 2: 
        msg = await message.reply_text("❌ Usage: <code>/series Name S1</code>")
        await asyncio.sleep(3)
        await msg.delete()
        try: await message.delete()
        except: pass
        return

    full_query = " ".join(message.command[1:])
    
    # 🔥 DETECT SEASON (e.g., "Mirzapur S2" or "Mirzapur Season 2")
    season_match = re.search(r"(?:s|season)\s*(\d+)", full_query, re.IGNORECASE)
    season_number = "0" # Default 0 means Main Show
    clean_query = full_query
    
    if season_match:
        season_number = season_match.group(1)
        # Remove 'S2' from name to search properly
        clean_query = re.sub(r"(?:s|season)\s*(\d+)", "", full_query, flags=re.IGNORECASE).strip()

    status_msg = await message.reply_text(f"📺 <b>Searching:</b> <code>{clean_query}</code> (Season: {season_number if season_number != '0' else 'All'})...")
    try: await message.delete()
    except: pass
    
    try:
        # Search using Clean Name
        search_url = f"https://api.themoviedb.org/3/search/tv?api_key={TMDB_API_KEY}&query={clean_query}"
        response = requests.get(search_url).json()
        if not response.get('results'):
            await status_msg.edit("❌ <b>Series nahi mili!</b>")
            await asyncio.sleep(3)
            await status_msg.delete()
            return

        series_id = response['results'][0]['id']
        series_name = response['results'][0]['name']
        
        display_text = f"📺 <b>Found:</b> {series_name}"
        if season_number != "0":
            display_text += f"\n💿 <b>Season:</b> {season_number}"

        # Pass season_number in callback
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎬 Posters", callback_data=f"ask_count|poster|{series_id}|tv|{season_number}")],
            [InlineKeyboardButton("🖼 Thumbnails", callback_data=f"ask_count|thumb|{series_id}|tv|{season_number}")]
        ])
        
        await status_msg.edit(f"{display_text}\n\nKya chahiye?", reply_markup=buttons)

    except Exception as e:
        await status_msg.edit(f"❌ Error: {e}")
        await asyncio.sleep(5)
        try: await status_msg.delete()
        except: pass

# --- COUNT SELECTION ---
@app.on_callback_query(filters.regex("^ask_count"))
async def ask_count_callback(client, callback):
    await callback.answer()
    data = callback.data.split("|") # ask_count | type | id | media_type | season
    img_type = data[1]
    media_id = data[2]
    media_type = data[3]
    season = data[4]
    
    # Pass all info forward
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("1️⃣", callback_data=f"final_img|{img_type}|{media_id}|1|{media_type}|{season}"),
         InlineKeyboardButton("2️⃣", callback_data=f"final_img|{img_type}|{media_id}|2|{media_type}|{season}")],
        [InlineKeyboardButton("3️⃣", callback_data=f"final_img|{img_type}|{media_id}|3|{media_type}|{season}"),
         InlineKeyboardButton("4️⃣", callback_data=f"final_img|{img_type}|{media_id}|4|{media_type}|{season}")]
    ])
    
    title_xtra = f"(Season {season})" if season != "0" else ""
    await callback.message.edit_text(f"🔢 <b>Kitni photos chahiye?</b>\n{title_xtra}", reply_markup=buttons)

# --- FINAL SENDING (Supports Movie, TV & Seasons) ---
@app.on_callback_query(filters.regex("^final_img"))
async def final_image_callback(client, callback):
    await callback.answer()
    user_id = callback.from_user.id
    data = callback.data.split("|") # final_img | type | id | count | media_type | season
    img_type = data[1]
    media_id = data[2]
    count_needed = int(data[3])
    media_type = data[4]
    season = data[5]

    status_msg = await callback.message.edit_text(f"⏳ <b>Fetching Images...</b>")
    
    try:
        # 1. Get Title
        if media_type == "movie":
            details_url = f"https://api.themoviedb.org/3/movie/{media_id}?api_key={TMDB_API_KEY}"
            details_resp = requests.get(details_url).json()
            media_title = details_resp.get("title")
        else:
            # TV Show
            details_url = f"https://api.themoviedb.org/3/tv/{media_id}?api_key={TMDB_API_KEY}"
            details_resp = requests.get(details_url).json()
            media_title = details_resp.get("name")
            if season != "0":
                media_title += f" S{season}"

        # 2. Get Images (Dynamic URL for Season)
        if media_type == "tv" and season != "0":
            # Specific Season API
            images_url = f"https://api.themoviedb.org/3/tv/{media_id}/season/{season}/images?api_key={TMDB_API_KEY}&include_image_language=en,hi,kn,te,ta,ml,null"
        else:
            # Standard Movie or Main TV Show API
            images_url = f"https://api.themoviedb.org/3/{media_type}/{media_id}/images?api_key={TMDB_API_KEY}&include_image_language=en,hi,kn,te,ta,ml,null"
        
        img_response = requests.get(images_url).json()
        
        raw_list = []
        if img_type == "poster":
            raw_list = img_response.get('posters', [])
        else:
            raw_list = img_response.get('backdrops', [])

        if not raw_list:
            await status_msg.edit(f"❌ No {img_type}s found for this Season.")
            await asyncio.sleep(3)
            await status_msg.delete()
            return

        # 🔥 TEXT PRIORITY LOGIC (Same as before)
        titled_images = [img for img in raw_list if img.get('iso_639_1') is not None]
        clean_images = [img for img in raw_list if img.get('iso_639_1') is None]

        titled_images.sort(key=lambda x: x.get('vote_average', 0), reverse=True)
        clean_images.sort(key=lambda x: x.get('vote_average', 0), reverse=True)

        if len(titled_images) > 0:
            final_list = titled_images
        else:
            final_list = clean_images
        
        if not final_list: final_list = raw_list

        media_group = []
        current_count = 0
        has_watermark = user_id in user_watermarks and user_watermarks[user_id].get("image")
        if has_watermark:
            await status_msg.edit("💧 <b>Processing...</b>")
            wm_img = user_watermarks[user_id]["image"]
            pos = user_watermarks[user_id]["position"]
        
        for img in final_list:
            if current_count >= count_needed: break 
            full_url = f"https://image.tmdb.org/t/p/w1280{img['file_path']}"
            
            if has_watermark:
                processed_bytes = apply_watermark(full_url, wm_img, pos)
                media_group.append(InputMediaPhoto(processed_bytes, caption=f"🎬 <b>{media_title}</b>"))
            else:
                media_group.append(InputMediaPhoto(full_url, caption=f"🎬 <b>{media_title}</b>"))
            current_count += 1
            
        await callback.message.reply_media_group(media_group)
        try: await status_msg.delete()
        except: pass

    except Exception as e:
        await status_msg.edit(f"❌ Error: {e}")
        await asyncio.sleep(5)
        try: await status_msg.delete()
        except: pass
    # --- Renamer Commands ---
@app.on_message(filters.command("add") & filters.private)
async def add_word(client, message):
    try: await message.delete()
    except: pass
    if len(message.command) < 2: return 
    for word in message.command[1:]: REPLACE_DICT[word] = CREDIT_NAME
    msg = await message.reply_text(f"✅ Added {len(message.command[1:])} words.")
    await asyncio.sleep(3)
    await msg.delete()

@app.on_message(filters.command("del") & filters.private)
async def del_word(client, message):
    try: await message.delete()
    except: pass
    if len(message.command) < 2: return 
    deleted = [w for w in message.command[1:] if REPLACE_DICT.pop(w, None)]
    msg = await message.reply_text(f"🗑 Deleted: {', '.join(deleted)}" if deleted else "❌ Not found.")
    await asyncio.sleep(3)
    await msg.delete()

@app.on_message(filters.command("words") & filters.private)
async def view_words(client, message):
    try: await message.delete()
    except: pass
    disp = "\n".join([f"🔹 <code>{k}</code> ➡ <code>{v}</code>" for k, v in REPLACE_DICT.items()])
    msg = await message.reply_text(f"📋 <b>Filter List:</b>\n\n{disp}" if REPLACE_DICT else "📭 Empty List.")
    await asyncio.sleep(10)
    await msg.delete()

@app.on_message(filters.command("rename") & filters.private)
async def set_rename_mode(client, message):
    user_modes[message.from_user.id] = "renamer"
    try: await message.delete()
    except: pass
    msg = await message.reply_text("📁 <b>Renamer Mode ON!</b>")
    await asyncio.sleep(3)
    await msg.delete()

@app.on_message(filters.command("link") & filters.private)
async def set_link_mode(client, message):
    user_modes[message.from_user.id] = "blogger_link"
    try: await message.delete()
    except: pass
    msg = await message.reply_text("🔗 <b>Link Mode ON!</b>")
    await asyncio.sleep(3)
    await msg.delete()

@app.on_message(filters.command("caption") & filters.private)
async def set_caption_mode(client, message):
    user_modes[message.from_user.id] = "caption_only"
    try: await message.delete()
    except: pass
    msg = await message.reply_text("📝 <b>Caption Mode ON!</b>")
    await asyncio.sleep(3)
    await msg.delete()

# --- Batch Mode ---
@app.on_message(filters.command("batch") & filters.private)
async def batch_start(client, message):
    user_modes[message.from_user.id] = "renamer"
    batch_data[message.from_user.id] = {'status': 'collecting', 'files': []}
    try: await message.delete()
    except: pass
    await message.reply_text("🚀 <b>Batch Mode ON!</b> Files bhejein, fir <b>/done</b> karein.")

@app.on_message(filters.command("done") & filters.private)
async def batch_done(client, message):
    user_id = message.from_user.id
    try: await message.delete()
    except: pass
    if user_id in batch_data and batch_data[user_id]['files']:
        batch_data[user_id]['status'] = 'naming'
        prompt = await message.reply_text("✅ Files mili. Ab <b>Series Name</b> bhejein.")
        batch_data[user_id]['prompt_msg_id'] = prompt.id
    else: await message.reply_text("Pehle files bhejein!")

# --- 🔥 MAIN HANDLER (Smart Logic & Cleanup) ---
@app.on_message(filters.private & (filters.document | filters.video | filters.audio | filters.photo))
async def handle_files(client, message):
    
    # 1. Check if it's a PHOTO or IMAGE DOCUMENT (For Watermark)
    is_image = False
    if message.photo:
        is_image = True
    elif message.document:
        # Check MIME type
        if message.document.mime_type and message.document.mime_type.startswith("image/"):
            is_image = True
            
    # Agar Image hai, toh Watermark Menu dikhao
    if is_image:
        await message.reply_text(
            "📸 <b>Image Detected!</b>\n\nIska kya karna hai?",
            quote=True,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🖼 Set as Thumbnail", callback_data="save_as_thumb")],
                [InlineKeyboardButton("💧 Set as Watermark", callback_data="save_as_wm")]
            ])
        )
        return

    # 2. Agar Video/Audio hai, toh Renamer Logic chalao
    global ACTIVE_TASKS
    user_id = message.from_user.id
    current_mode = user_modes.get(user_id, "renamer")
    
    if current_mode == "caption_only":
        try:
            media = message.document or message.video or message.audio
            clean_name = auto_clean(media.file_name or "video.mkv")
            file_size = humanbytes(media.file_size)
            duration = get_duration_str(getattr(media, "duration", 0))
            s_num, e_num = get_media_info(clean_name)
            
            caption = f"<b>{clean_name}</b>\n\n"
            if s_num: caption += f"💿 Season ➥ {s_num}\n"
            if e_num: caption += f"📺 Episode ➥ {e_num}\n\n"
            caption += f"<blockquote><code>File Size ♻️ ➥ {file_size}</code></blockquote>\n"
            if getattr(media, "duration", 0) > 0: caption += f"<blockquote><code>Duration ⏰ ➥ {duration}</code></blockquote>\n"
            caption += f"<blockquote><code>Powered By ➥ {CREDIT_NAME}</code></blockquote>"
            
            await message.reply_cached_media(media.file_id, caption=caption)
            try: await message.delete() 
            except: pass
        except Exception as e: await message.reply_text(f"❌ Error: {e}")
        return

    if ACTIVE_TASKS >= MAX_TASK_LIMIT:
        return await message.reply_text("⚠️ <b>Busy!</b> Wait...")

    if user_id in batch_data and batch_data[user_id]['status'] == 'collecting':
        batch_data[user_id]['files'].append(message)
        return

    user_modes[user_id] = "renamer"
    user_data[user_id] = {'file_msg': message, 'mode': None}
    btn = InlineKeyboardMarkup([[InlineKeyboardButton("🎥 Video", callback_data="mode_video"), InlineKeyboardButton("📁 Document", callback_data="mode_document")]])
    await message.reply_text("<b>Mode Select:</b>", reply_to_message_id=message.id, reply_markup=btn)

@app.on_callback_query(filters.regex("mode_"))
async def mode_selection(client, callback):
    user_id = callback.from_user.id
    user_data[user_id]['mode'] = 'video' if callback.data == "mode_video" else 'document'
    await callback.message.delete()
    media = user_data[user_id]['file_msg'].document or user_data[user_id]['file_msg'].video or user_data[user_id]['file_msg'].audio
    await client.send_message(user_id, f"<b>File:</b> <code>{auto_clean(media.file_name or 'vid.mkv')}</code>\nAb naya naam bhejein:", reply_to_message_id=user_data[user_id]['file_msg'].id, reply_markup=ForceReply(True))

@app.on_message(filters.private & filters.text)
async def handle_text(client, message):
    global ACTIVE_TASKS
    user_id = message.from_user.id
    text = message.text.strip()
    current_mode = user_modes.get(user_id, "renamer")

    if current_mode == "blogger_link":
        if "?start=" in text:
            try:
                start_code = text.split("?start=")[1].split()[0]
                encoded = base64.b64encode(start_code.encode("utf-8")).decode("utf-8")
                final_link = f"{BLOGGER_URL}?data={encoded}"
                await message.reply_text(f"✅ <b>Link:</b>\n<code>{final_link}</code>", disable_web_page_preview=True)
                # 🔥 Link Generate karne ke baad Input link delete
                try: await message.delete() 
                except: pass
            except: await message.reply_text("❌ Error.")
        else: await message.reply_text("❌ No <code>?start=</code> found.")
        return
    
    # Batch Processing
    if user_id in batch_data and batch_data[user_id]['status'] == 'naming':
        batch_data[user_id]['status'] = 'processing'
        ACTIVE_TASKS += 1
        status_msg = await message.reply_text(f"⏳ <b>Batch Processing...</b>")
        try:
            base_name = auto_clean(text)
            for idx, msg in enumerate(batch_data[user_id]['files']):
                media = msg.document or msg.video or msg.audio
                ext = get_extension(media.file_name)
                s_num, e_num = get_media_info(media.file_name or "")
                
                new_name = f"{base_name} - S{s_num}E{e_num}{ext}" if s_num and e_num else (f"{base_name} - E{e_num}{ext}" if e_num else f"{base_name}{ext}")
                if not new_name.endswith(ext): new_name += ext
                
                dl_path = await client.download_media(media, f"downloads/{new_name}")
                caption = f"<b>{new_name}</b>\n\n<blockquote><code>File Size ♻️ ➥ {humanbytes(os.path.getsize(dl_path))}</code></blockquote>\n"
                dur = get_video_attributes(dl_path)[2]
                if dur > 0: caption += f"<blockquote><code>Duration ⏰ ➥ {get_duration_str(dur)}</code></blockquote>\n"
                caption += f"<blockquote><code>Powered By ➥ {CREDIT_NAME}</code></blockquote>"
                
                await client.send_document(user_id, dl_path, caption=caption, force_document=True)
                os.remove(dl_path)
        except Exception as e: print(e)
        finally:
            ACTIVE_TASKS -= 1
            await status_msg.delete()
            del batch_data[user_id]
        return

    # Single File Processing
    if message.reply_to_message and user_id in user_data:
        user_task = user_data.pop(user_id)
        ACTIVE_TASKS += 1
        status_msg = await message.reply_text("⏳ <b>Starting...</b>")
        try:
            media = user_task['file_msg'].document or user_task['file_msg'].video or user_task['file_msg'].audio
            new_name = auto_clean(text)
            ext = get_extension(media.file_name)
            if not new_name.endswith(ext): new_name += ext
            
            thumb_path = f"thumbnails/{user_id}.jpg"
            if not os.path.exists(thumb_path): thumb_path = None
            
            dl_path = await client.download_media(media, f"downloads/{new_name}", progress=progress, progress_args=(status_msg, time.time(), "📥 Downloading"))
            
            w, h, dur = get_video_attributes(dl_path)
            caption = f"<b>{new_name}</b>\n\n<blockquote><code>File Size ♻️ ➥ {humanbytes(os.path.getsize(dl_path))}</code></blockquote>\n"
            if dur > 0: caption += f"<blockquote><code>Duration ⏰ ➥ {get_duration_str(dur)}</code></blockquote>\n"
            caption += f"<blockquote><code>Powered By ➥ {CREDIT_NAME}</code></blockquote>"
            
            if user_task['mode'] == 'video':
                await client.send_video(user_id, dl_path, caption=caption, thumb=thumb_path, duration=dur, width=w, height=h, supports_streaming=True, progress=progress, progress_args=(status_msg, time.time(), "📤 Uploading"))
            else:
                await client.send_document(user_id, dl_path, caption=caption, thumb=thumb_path, force_document=True, progress=progress, progress_args=(status_msg, time.time(), "📤 Uploading"))
            
            os.remove(dl_path)
            # 🔥 AUTO-CLEAN: File bhejne ke baad original File aur "Name" command delete
            try:
                await user_task['file_msg'].delete() # Original File delete
                await message.delete() # Name command delete
            except: pass

        except Exception as e: await message.reply_text(f"Error: {e}")
        finally:
            ACTIVE_TASKS -= 1
            await status_msg.delete() # Bot ka status msg delete

async def main():
    await asyncio.gather(web_server(), app.start())
    await asyncio.Event().wait()

if __name__ == "__main__":
    print("All-in-One Bot Started!")
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
    
