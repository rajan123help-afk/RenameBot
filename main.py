import os
import re
import asyncio
import time
import math
import shutil
import base64
import datetime
import html # 🔥 HTML library add ki hai safety ke liye
from pyrogram import Client, filters, enums
from pyrogram.types import ForceReply, InlineKeyboardMarkup, InlineKeyboardButton
from aiohttp import web
from hachoir.metadata import extractMetadata
from hachoir.parser import createParser

# --- Configs ---
API_ID = int(os.environ.get("API_ID", "12345"))
API_HASH = os.environ.get("API_HASH", "hash")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "token")
BLOGGER_URL = "https://filmyflip1.blogspot.com/p/download.html"

# 🔥 BRAND NAME
CREDIT_NAME = "🦋 Filmy Flip Hub 🦋"

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

# 🔥 HTML MODE (Ye zaroori hai Box ke liye)
app = Client(
    "my_multibot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=4, 
    max_concurrent_transmissions=2,
    ipv6=False,
    parse_mode=enums.ParseMode.HTML 
)

batch_data = {}
user_data = {}
user_modes = {}

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

async def progress(current, total, message, start_time, task_type):
    now = time.time()
    diff = now - start_time
    if round(diff % 5.00) == 0 or current == total:
        percentage = current * 100 / total
        speed = current / diff
        time_to_completion = round((total - current) / speed) if speed > 0 else 0
        time_left_str = time.strftime("%H:%M:%S", time.gmtime(time_to_completion))
        progress_str = "[{0}{1}] {2}%".format(
            ''.join(["●" for i in range(math.floor(percentage / 5))]),
            ''.join(["○" for i in range(20 - math.floor(percentage / 5))]),
            round(percentage, 2))
        tmp = (f"{task_type}\n"
               f"{progress_str}\n"
               f"💾 <b>Size:</b> {humanbytes(current)} / {humanbytes(total)}\n"
               f"🚀 <b>Speed:</b> {humanbytes(speed)}/s\n"
               f"⏳ <b>ETA:</b> {time_left_str}")
        try:
            await message.edit(tmp)
        except:
            pass

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

# ==========================================
# 🔥 COMMANDS
# ==========================================

@app.on_message(filters.command("start") & filters.private)
async def start_msg(client, message):
    await message.reply_text(
        f"👋 <b>Hello {message.from_user.first_name}!</b>\n\n"
        "🤖 <b>Filmy Flip Hub Bot</b>\n"
        "✨ <b>Fixed:</b> No Backslash & Quote Box\n\n"
        "⚙️ <b>Manage:</b> <code>/add</code>, <code>/del</code>, <code>/words</code>\n"
        "📝 <b>Caption:</b> <code>/caption</code>\n"
        "📁 <b>Rename:</b> <code>/rename</code>"
    )

@app.on_message(filters.command("add") & filters.private)
async def add_word(client, message):
    if len(message.command) < 2: return await message.reply_text("❌ Usage: <code>/add word</code>")
    new_words = message.command[1:]
    for word in new_words: REPLACE_DICT[word] = "Filmy Flip Hub"
    await message.reply_text(f"✅ Added {len(new_words)} words.")

@app.on_message(filters.command("del") & filters.private)
async def del_word(client, message):
    if len(message.command) < 2: return await message.reply_text("❌ Usage: <code>/del word</code>")
    words = message.command[1:]
    deleted = [w for w in words if REPLACE_DICT.pop(w, None)]
    await message.reply_text(f"🗑 Deleted: {', '.join(deleted)}" if deleted else "❌ Not found.")

@app.on_message(filters.command("words") & filters.private)
async def view_words(client, message):
    if not REPLACE_DICT: return await message.reply_text("📭 Empty List.")
    disp = "\n".join([f"🔹 <code>{k}</code> ➡ <code>{v}</code>" for k, v in REPLACE_DICT.items()])
    await message.reply_text(f"📋 <b>Filter List:</b>\n\n{disp}")

@app.on_message(filters.command("link") & filters.private)
async def set_link_mode(client, message):
    user_modes[message.from_user.id] = "blogger_link"
    await message.reply_text("🔗 <b>Link Mode ON!</b>")

@app.on_message(filters.command("rename") & filters.private)
async def set_rename_mode(client, message):
    user_modes[message.from_user.id] = "renamer"
    await message.reply_text("📁 <b>Renamer Mode ON!</b>")

@app.on_message(filters.command("caption") & filters.private)
async def set_caption_mode(client, message):
    user_modes[message.from_user.id] = "caption_only"
    await message.reply_text("📝 <b>Caption Mode ON!</b>")

@app.on_message(filters.private & filters.photo)
async def save_thumbnail(client, message):
    path = f"thumbnails/{message.from_user.id}.jpg"
    await client.download_media(message=message, file_name=path)
    await message.reply_text("✅ <b>Thumbnail Saved!</b>")

@app.on_message(filters.command("delthumb") & filters.private)
async def delete_thumb(client, message):
    path = f"thumbnails/{message.from_user.id}.jpg"
    if os.path.exists(path):
        os.remove(path)
        await message.reply_text("🗑 Thumbnail Deleted.")

@app.on_message(filters.command("batch") & filters.private)
async def batch_start(client, message):
    user_modes[message.from_user.id] = "renamer"
    batch_data[message.from_user.id] = {'status': 'collecting', 'files': []}
    await message.reply_text("🚀 <b>Batch Mode ON!</b> Files forward karein, fir <b>/done</b> bhejein.")

@app.on_message(filters.command("done") & filters.private)
async def batch_done(client, message):
    user_id = message.from_user.id
    if user_id in batch_data and batch_data[user_id]['files']:
        batch_data[user_id]['status'] = 'naming'
        prompt_msg = await message.reply_text("✅ Files received. Ab <b>Series Name</b> bhejein.")
        batch_data[user_id]['prompt_msg_id'] = prompt_msg.id
    else:
        await message.reply_text("Pehle files bhejein!")
        # --- Main Handler ---
@app.on_message(filters.private & (filters.document | filters.video | filters.audio))
async def handle_files(client, message):
    global ACTIVE_TASKS
    user_id = message.from_user.id
    
    current_mode = user_modes.get(user_id, "renamer")
    
    # --- CAPTION ONLY MODE ---
    if current_mode == "caption_only":
        try:
            media = message.document or message.video or message.audio
            org_filename = media.file_name or "video.mkv"
            file_id = media.file_id
            file_size = humanbytes(media.file_size)
            duration_sec = getattr(media, "duration", 0)
            duration_str = get_duration_str(duration_sec)
            
            clean_filename = auto_clean(org_filename)
            s_num, e_num = get_media_info(clean_filename)
            
            # 🔥 HTML MODE (No Backslash Issue)
            # <b>Filename</b> = Bold
            caption = f"<b>{clean_filename}</b>\n\n"
            
            if s_num: caption += f"💿 Season ➥ {s_num}\n"
            if e_num: caption += f"📺 Episode ➥ {e_num}\n\n"
            
            # 🔥 BLOCKQUOTE (White Vertical Line Box)
            # Sabko ek sath blockquote me daal diya taaki ek bada box bane
            caption += f"<blockquote>File Size ♻️ ➥ {file_size}\n"
            
            if duration_sec > 0:
                caption += f"Duration ⏰ ➥ {duration_str}\n"
                
            caption += f"Powered By ➥ {CREDIT_NAME}</blockquote>"
            
            await message.reply_cached_media(file_id, caption=caption)
        except Exception as e:
            await message.reply_text(f"❌ Error: {e}")
        return

    # --- Renamer Logic ---
    if ACTIVE_TASKS >= MAX_TASK_LIMIT:
        w = await message.reply_text("⚠️ <b>OVERLOAD!</b> Wait...")
        await asyncio.sleep(5)
        try: await w.delete()
        except: pass
        return

    if user_id in batch_data and batch_data[user_id]['status'] == 'collecting':
        batch_data[user_id]['files'].append(message)
        return

    user_modes[user_id] = "renamer"
    user_data[user_id] = {'file_msg': message, 'mode': None}
    
    buttons = InlineKeyboardMarkup([[
        InlineKeyboardButton("🎥 Video", callback_data="mode_video"),
        InlineKeyboardButton("📁 Document", callback_data="mode_document")
    ]])
    await message.reply_text("<b>Upload Mode Select Karein:</b>", reply_to_message_id=message.id, reply_markup=buttons)

@app.on_callback_query(filters.regex("mode_"))
async def mode_selection(client, callback_query):
    user_id = callback_query.from_user.id
    data = callback_query.data
    if user_id not in user_data:
        await callback_query.answer("Session expired.", show_alert=True)
        return
    user_data[user_id]['mode'] = 'video' if data == "mode_video" else 'document'
    await callback_query.message.delete()
    
    file_msg = user_data[user_id]['file_msg']
    media = file_msg.document or file_msg.video or file_msg.audio
    filename = media.file_name or "video.mkv"
    clean_display = auto_clean(filename)
    
    await client.send_message(
        chat_id=user_id,
        text=f"<b>File:</b> <code>{clean_display}</code>\nMode: <b>{data.split('_')[1].title()}</b>\nAb naya naam bhejein:",
        reply_to_message_id=file_msg.id,
        reply_markup=ForceReply(True)
    )

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
            except: await message.reply_text("❌ Error.")
        else: await message.reply_text("❌ No <code>?start=</code> found.")
        return

    # RENAMER LOGIC
    if user_id in batch_data and batch_data[user_id]['status'] == 'naming':
        batch_data[user_id]['status'] = 'processing'
        ACTIVE_TASKS += 1
        status_msg = await message.reply_text(f"⏳ <b>Batch Processing...</b>")
        
        try:
            base_name = auto_clean(message.text.strip())
            files = batch_data[user_id]['files']
            
            for idx, media in enumerate(files):
                try:
                    file = media.document or media.video or media.audio
                    org_name = file.file_name or "vid.mkv"
                    ext = get_extension(org_name)
                    
                    s_num, e_num = get_media_info(org_name)
                    if s_num and e_num: new_name = f"{base_name} - S{s_num}E{e_num}{ext}"
                    elif e_num: new_name = f"{base_name} - E{e_num}{ext}"
                    else: new_name = f"{base_name}{ext}"

                    if not new_name.endswith(ext): new_name += ext
                    
                    start_time = time.time()
                    dl_path = await client.download_media(media, file_name=f"downloads/{new_name}", progress=progress, progress_args=(status_msg, start_time, f"📥 <b>Down</b> ({idx+1}/{len(files)})"))
                    
                    width, height, duration = get_video_attributes(dl_path)
                    file_size = humanbytes(os.path.getsize(dl_path))
                    duration_str = get_duration_str(duration)
                    
                    # 🔥 HTML + BLOCKQUOTE (Batch)
                    caption = f"<b>{new_name}</b>\n\n"
                    if s_num: caption += f"💿 Season ➥ {s_num}\n"
                    if e_num: caption += f"📺 Episode ➥ {e_num}\n\n"
                    
                    caption += f"<blockquote>File Size ♻️ ➥ {file_size}\n"
                    if duration > 0: caption += f"Duration ⏰ ➥ {duration_str}\n"
                    caption += f"Powered By ➥ {CREDIT_NAME}</blockquote>"

                    start_time = time.time()
                    await client.send_document(message.chat.id, document=dl_path, caption=caption, force_document=True, progress=progress, progress_args=(status_msg, start_time, f"📤 <b>Up</b> ({idx+1})"))
                    os.remove(dl_path)
                except Exception as e: print(e)
            
            await status_msg.delete()
        except: pass
        finally:
            try: await message.delete() 
            except: pass
            del batch_data[user_id]
            ACTIVE_TASKS -= 1
        return

    # --- Single ---
    if message.reply_to_message and user_id in user_data:
        user_task = user_data.pop(user_id)
        ACTIVE_TASKS += 1
        status_msg = await message.reply_text("⏳ <b>Starting...</b>")
        
        try:
            original_msg = user_task['file_msg']
            mode = user_task.get('mode', 'document')
            media = original_msg.document or original_msg.video or original_msg.audio
            
            org_ext = get_extension(media.file_name)
            new_name = auto_clean(message.text.strip())
            
            if not new_name.endswith(org_ext):
                new_name += org_ext
            
            thumb_path = f"thumbnails/{user_id}.jpg"
            if not os.path.exists(thumb_path): thumb_path = None
            
            path = f"downloads/{new_name}"
            start_time = time.time()
            dl_path = await client.download_media(original_msg, file_name=path, progress=progress, progress_args=(status_msg, start_time, "📥 <b>Downloading...</b>"))
            
            width, height, duration = get_video_attributes(dl_path)
            file_size = humanbytes(os.path.getsize(dl_path))
            duration_str = get_duration_str(duration)
            s_num, e_num = get_media_info(new_name)
            
            # 🔥 HTML + BLOCKQUOTE (Single)
            caption = f"<b>{new_name}</b>\n\n"
            if s_num: caption += f"💿 Season ➥ {s_num}\n"
            if e_num: caption += f"📺 Episode ➥ {e_num}\n\n"
            
            caption += f"<blockquote>File Size ♻️ ➥ {file_size}\n"
            if duration > 0: caption += f"Duration ⏰ ➥ {duration_str}\n"
            caption += f"Powered By ➥ {CREDIT_NAME}</blockquote>"

            start_time = time.time()
            if mode == 'video':
                await client.send_video(message.chat.id, video=dl_path, caption=caption, thumb=thumb_path, supports_streaming=True, duration=duration, width=width, height=height, progress=progress, progress_args=(status_msg, start_time, "📤 <b>Up Video</b>"))
            else:
                await client.send_document(message.chat.id, document=dl_path, caption=caption, thumb=thumb_path, force_document=True, progress=progress, progress_args=(status_msg, start_time, "📤 <b>Up File</b>"))
            
            os.remove(dl_path)
            await status_msg.delete()
        except Exception as e:
            await status_msg.edit(f"❌ Error: {e}")
        finally:
            try: await message.delete()
            except: pass
            ACTIVE_TASKS -= 1

async def main():
    await asyncio.gather(web_server(), app.start())
    await asyncio.Event().wait()

if __name__ == "__main__":
    print("HTML Box Mode Corrected!")
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
