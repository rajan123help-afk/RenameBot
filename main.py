import os
import re
import asyncio
import time
import math
import shutil
from pyrogram import Client, filters
from pyrogram.types import ForceReply, InlineKeyboardMarkup, InlineKeyboardButton
from aiohttp import web

# --- Configs ---
API_ID = int(os.environ.get("API_ID", "12345"))
API_HASH = os.environ.get("API_HASH", "hash")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "token")

# Aapka Blogger Page
BLOGGER_URL = "https://filmyflip1.blogspot.com/p/download.html"

# --- ⚙️ SERVER SETTINGS ---
MAX_TASK_LIMIT = 2
ACTIVE_TASKS = 0

app = Client(
    "my_multibot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=4, 
    max_concurrent_transmissions=2,
    ipv6=False
)

# Data Storage
batch_data = {}
user_data = {}
user_modes = {}  # Track karega ki user kaunse mode me hai

# Startup Cleaning
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
               f"💾 **Size:** {humanbytes(current)} / {humanbytes(total)}\n"
               f"🚀 **Speed:** {humanbytes(speed)}/s\n"
               f"⏳ **ETA:** {time_left_str}")
        try:
            await message.edit(tmp)
        except:
            pass

def extract_season_episode(filename):
    pattern = r"[sS](\d+)[eE](\d+)|[eE]([pP])?(\d+)|(\d+)[xX](\d+)"
    match = re.search(pattern, filename)
    if match:
        if match.group(1) and match.group(2): return f"S{match.group(1)}E{match.group(2)}"
        elif match.group(4): return f"E{match.group(4)}"
        elif match.group(5) and match.group(6): return f"S{match.group(5)}E{match.group(6)}"
    return None

# ==========================================
# 🔥 MODE SWITCHING & COMMANDS
# ==========================================

@app.on_message(filters.command("start") & filters.private)
async def start_msg(client, message):
    await message.reply_text(
        f"👋 **Hello {message.from_user.first_name}!**\n\n"
        "🤖 **2-in-1 Features:**\n"
        "1️⃣ **File Renamer** (Video/File)\n"
        "2️⃣ **Permanent Link Generator** (Blogger)\n\n"
        "👇 **Modes Change Karein:**\n"
        "🔗 `/link` - Link Converter Mode\n"
        "📁 `/rename` - Renamer Mode (Default)"
    )

@app.on_message(filters.command("link") & filters.private)
async def set_link_mode(client, message):
    user_id = message.from_user.id
    user_modes[user_id] = "blogger_link"
    await message.reply_text(
        "🔗 **Link Mode ON!**\n\n"
        "Ab mujhe **Telegram Bot ka Link** bhejein.\n"
        "Main use **Permanent Blogger Link** bana dunga."
    )

@app.on_message(filters.command("rename") & filters.private)
async def set_rename_mode(client, message):
    user_id = message.from_user.id
    user_modes[user_id] = "renamer"
    await message.reply_text("📁 **Renamer Mode ON!**\nAb Files bhejein.")

@app.on_message(filters.private & filters.photo)
async def save_thumbnail(client, message):
    path = f"thumbnails/{message.from_user.id}.jpg"
    await client.download_media(message=message, file_name=path)
    await message.reply_text("✅ **Thumbnail Saved!**")

@app.on_message(filters.command("delthumb") & filters.private)
async def delete_thumb(client, message):
    path = f"thumbnails/{message.from_user.id}.jpg"
    if os.path.exists(path):
        os.remove(path)
        await message.reply_text("🗑 Thumbnail Deleted.")

# --- Batch Mode ---
@app.on_message(filters.command("batch") & filters.private)
async def batch_start(client, message):
    user_modes[message.from_user.id] = "renamer" # Batch always renamer
    user_id = message.from_user.id
    batch_data[user_id] = {'status': 'collecting', 'files': []}
    await message.reply_text("🚀 **Batch Mode ON!** Files forward karein, fir **/done** bhejein.")

@app.on_message(filters.command("done") & filters.private)
async def batch_done(client, message):
    user_id = message.from_user.id
    if user_id in batch_data and batch_data[user_id]['files']:
        batch_data[user_id]['status'] = 'naming'
        await message.reply_text("✅ Files received. Ab **Series Name** bhejein.")
    else:
        await message.reply_text("Pehle files bhejein!")

# ==========================================
# 🔥 MAIN HANDLER (TEXT & FILES)
# ==========================================

@app.on_message(filters.private & (filters.document | filters.video | filters.audio))
async def handle_files(client, message):
    global ACTIVE_TASKS
    user_id = message.from_user.id
    
    # Check Overload
    if ACTIVE_TASKS >= MAX_TASK_LIMIT:
        try: await message.delete()
        except: pass
        warning = await message.reply_text("⚠️ **OVERLOAD!** Wait for ongoing tasks.")
        await asyncio.sleep(5)
        await warning.delete()
        return

    # Batch Collection
    if user_id in batch_data and batch_data[user_id]['status'] == 'collecting':
        batch_data[user_id]['files'].append(message)
        return

    # Single Rename Setup
    user_modes[user_id] = "renamer" # File aayi hai to Rename mode hi hoga
    user_data[user_id] = {'file_msg': message, 'mode': None}
    
    buttons = InlineKeyboardMarkup([[
        InlineKeyboardButton("🎥 Video", callback_data="mode_video"),
        InlineKeyboardButton("📁 Document", callback_data="mode_document")
    ]])
    await message.reply_text("**Upload Mode Select Karein:**", reply_to_message_id=message.id, reply_markup=buttons)

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
    filename = file_msg.document.file_name if file_msg.document else (file_msg.video.file_name if file_msg.video else "file.mkv")
    
    await client.send_message(
        chat_id=user_id,
        text=f"**File:** `{filename}`\nMode: **{data.split('_')[1].title()}**\nAb naya naam bhejein:",
        reply_to_message_id=file_msg.id,
        reply_markup=ForceReply(True)
    )

@app.on_message(filters.private & filters.text)
async def handle_text(client, message):
    global ACTIVE_TASKS
    user_id = message.from_user.id
    text = message.text
    
    # Mode Check
    current_mode = user_modes.get(user_id, "renamer")

    # ---------------------------
    # 🔗 LINK CONVERTER LOGIC
    # ---------------------------
    if current_mode == "blogger_link":
        if "?start=" in text:
            try:
                # Telegram Link se Code nikalna (e.g., ?start=File123 -> File123)
                code = text.split("?start=")[1]
                
                # Blogger Link banana (Assuming ?id= is your parameter)
                final_link = f"{BLOGGER_URL}?id={code}"
                
                await message.reply_text(
                    f"✅ **Permanent Link Generated!**\n\n"
                    f"`{final_link}`\n\n"
                    "👉 Yeh link tab bhi chalega jab Store Bot delete ho jayega.",
                    disable_web_page_preview=True
                )
            except Exception as e:
                await message.reply_text(f"❌ Error: {e}")
        else:
            await message.reply_text("❌ Is link me `?start=` nahi hai. Sahi Bot Link bhejein.")
        return

    # ---------------------------
    # 📁 RENAMER LOGIC
    # ---------------------------
    
    # Batch Rename
    if user_id in batch_data and batch_data[user_id]['status'] == 'naming':
        batch_data[user_id]['status'] = 'processing' 
        if ACTIVE_TASKS >= MAX_TASK_LIMIT:
            await message.reply_text("⚠️ Server busy. Try later.")
            del batch_data[user_id]
            return
        
        ACTIVE_TASKS += 1
        try:
            base_name = message.text.strip()
            files = batch_data[user_id]['files']
            thumb_path = f"thumbnails/{user_id}.jpg"
            if not os.path.exists(thumb_path): thumb_path = None
            
            status_msg = await message.reply_text(f"⏳ **Batch Processing {len(files)} Files...**")
            
            for idx, media in enumerate(files):
                try:
                    file = media.document or media.video or media.audio
                    org_name = file.file_name or "vid.mkv"
                    _, ext = os.path.splitext(org_name)
                    if not ext: ext = ".mkv"
                    ep_tag = extract_season_episode(org_name)
                    new_name = f"{base_name} - {ep_tag}{ext}" if ep_tag else f"{base_name} - {org_name}"
                    
                    start_time = time.time()
                    dl_path = await client.download_media(
                        media, file_name=f"downloads/{new_name}",
                        progress=progress, progress_args=(status_msg, start_time, f"📥 **Down** ({idx+1}/{len(files)})")
                    )
                    
                    start_time = time.time()
                    await client.send_document(
                        message.chat.id, document=dl_path, caption=f"**{new_name}**", thumb=thumb_path, force_document=True,
                        progress=progress, progress_args=(status_msg, start_time, f"📤 **Up** ({idx+1}/{len(files)})")
                    )
                    os.remove(dl_path)
                except Exception as e: print(e)
            
            await status_msg.delete()
            await message.delete()
            del batch_data[user_id]
        finally:
            ACTIVE_TASKS -= 1
        return

    # Single Rename
    if message.reply_to_message and user_id in user_data:
        user_task = user_data.pop(user_id) 
        if ACTIVE_TASKS >= MAX_TASK_LIMIT:
            await message.reply_text("⚠️ Server busy. Try later.")
            return

        ACTIVE_TASKS += 1
        try:
            original_msg = user_task['file_msg']
            mode = user_task.get('mode', 'document')
            new_name = message.text
            thumb_path = f"thumbnails/{user_id}.jpg"
            if not os.path.exists(thumb_path): thumb_path = None
            
            status_msg = await message.reply_text("⏳ **Starting...**")
            path = f"downloads/{new_name}"
            start_time = time.time()
            dl_path = await client.download_media(
                original_msg, file_name=path,
                progress=progress, progress_args=(status_msg, start_time, "📥 **Downloading...**")
            )
            
            start_time = time.time()
            if mode == 'video':
                await client.send_video(
                    message.chat.id, video=dl_path, caption=f"**{new_name}**", thumb=thumb_path, supports_streaming=True,
                    progress=progress, progress_args=(status_msg, start_time, "📤 **Uploading Video...**")
                )
            else:
                await client.send_document(
                    message.chat.id, document=dl_path, caption=f"**{new_name}**", thumb=thumb_path, force_document=True,
                    progress=progress, progress_args=(status_msg, start_time, "📤 **Uploading File...**")
                )
            os.remove(dl_path)
            await status_msg.delete()
            await message.delete()
            await message.reply_to_message.delete()
        except Exception as e:
            await status_msg.edit(f"❌ Error: {e}")
        finally:
            ACTIVE_TASKS -= 1

async def main():
    await asyncio.gather(web_server(), app.start())
    await asyncio.Event().wait()

if __name__ == "__main__":
    print("All-in-One Bot Started!")
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
