import os
import re
import asyncio
import time
import math
from pyrogram import Client, filters
from pyrogram.types import ForceReply
from aiohttp import web

# --- Configs ---
API_ID = int(os.environ.get("API_ID", "12345"))
API_HASH = os.environ.get("API_HASH", "hash")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "token")

app = Client("my_renamer_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Data Storage
batch_data = {}
user_data = {}

# Folder Setup
if not os.path.exists("downloads"): os.makedirs("downloads")
if not os.path.exists("thumbnails"): os.makedirs("thumbnails")

# --- Web Server for Koyeb ---
async def web_server():
    async def handle(request):
        return web.Response(text="Bot is Running!")
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8000)
    await site.start()

# --- 🛠 Helper Functions for Progress Bar ---

def humanbytes(size):
    """Bytes ko MB/GB me convert karta hai"""
    if not size: return ""
    power = 2**10
    n = 0
    dic_power = {0: ' ', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
    while size > power:
        size /= power
        n += 1
    return str(round(size, 2)) + " " + dic_power[n] + 'B'

async def progress(current, total, message, start_time, task_type):
    """Progress Bar, Speed aur ETA show karne ke liye"""
    now = time.time()
    diff = now - start_time
    
    # Update har 4 second me ya jab complete ho jaye
    if round(diff % 4.00) == 0 or current == total:
        percentage = current * 100 / total
        speed = current / diff
        time_to_completion = round((total - current) / speed) if speed > 0 else 0
        time_left_str = time.strftime("%H:%M:%S", time.gmtime(time_to_completion))
        
        # Progress Bar Design (●●●○○)
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
            pass # Agar edit fail ho jaye toh ignore karein

def extract_season_episode(filename):
    pattern = r"[sS](\d+)[eE](\d+)|[eE]([pP])?(\d+)|(\d+)[xX](\d+)"
    match = re.search(pattern, filename)
    if match:
        if match.group(1) and match.group(2): return f"S{match.group(1)}E{match.group(2)}"
        elif match.group(4): return f"E{match.group(4)}"
        elif match.group(5) and match.group(6): return f"S{match.group(5)}E{match.group(6)}"
    return None

# --- Commands & Logic ---

@app.on_message(filters.command("start") & filters.private)
async def start_msg(client, message):
    await message.reply_text(
        f"👋 **Hello {message.from_user.first_name}!**\n\n"
        "🤖 **Available Commands:**\n"
        "/batch - Batch Mode (Bulk Rename)\n"
        "/delthumb - Delete Thumbnail\n\n"
        "📂 **Kaise Use Karein:**\n"
        "File bhejein aur naya naam likhein. Main **Progress Bar** ke saath rename karunga! 🚀"
    )

@app.on_message(filters.private & filters.photo)
async def save_thumbnail(client, message):
    user_id = message.from_user.id
    if user_id in batch_data and batch_data[user_id].get('status') == 'collecting': return
    path = f"thumbnails/{user_id}.jpg"
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
    user_id = message.from_user.id
    batch_data[user_id] = {'status': 'collecting', 'files': []}
    await message.reply_text("🚀 **Batch Mode ON!** Files forward karein, fir **/done** bhejein.")

@app.on_message(filters.command("done") & filters.private)
async def batch_done(client, message):
    user_id = message.from_user.id
    if user_id in batch_data and batch_data[user_id]['files']:
        batch_data[user_id]['status'] = 'naming'
        await message.reply_text(f"✅ {len(batch_data[user_id]['files'])} Files received.\nAb **Series Name** bhejein.")
    else:
        await message.reply_text("Pehle files bhejein!")

# --- File Handler ---
@app.on_message(filters.private & (filters.document | filters.video | filters.audio))
async def handle_files(client, message):
    user_id = message.from_user.id
    if user_id in batch_data and batch_data[user_id]['status'] == 'collecting':
        batch_data[user_id]['files'].append(message)
        return

    file = message.document or message.video or message.audio
    filename = file.file_name or "video.mkv"
    user_data[user_id] = message
    
    await message.reply_text(
        f"**File:** `{filename}`\n"
        "Naya naam bhejein (Extension ke saath):",
        reply_to_message_id=message.id,
        reply_markup=ForceReply(True)
    )

# --- Rename Logic with Progress Bar ---
@app.on_message(filters.private & filters.text)
async def perform_rename(client, message):
    user_id = message.from_user.id
    
    # --- Batch Renaming ---
    if user_id in batch_data and batch_data[user_id]['status'] == 'naming':
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
                
                # Download Start
                start_time = time.time()
                dl_path = await client.download_media(
                    media, 
                    file_name=f"downloads/{new_name}",
                    progress=progress,
                    progress_args=(status_msg, start_time, f"📥 **Downloading...** ({idx+1}/{len(files)})")
                )
                
                # Upload Start
                start_time = time.time()
                await client.send_document(
                    message.chat.id, 
                    document=dl_path, 
                    caption=f"**{new_name}**", 
                    thumb=thumb_path, 
                    force_document=True,
                    progress=progress,
                    progress_args=(status_msg, start_time, f"📤 **Uploading...** ({idx+1}/{len(files)})")
                )
                os.remove(dl_path)
            except Exception as e: print(e)
        
        await status_msg.edit("✅ **Batch Done!**")
        del batch_data[user_id]
        return

    # --- Single File Renaming ---
    if message.reply_to_message and user_id in user_data:
        original_msg = user_data[user_id]
        new_name = message.text
        thumb_path = f"thumbnails/{user_id}.jpg"
        if not os.path.exists(thumb_path): thumb_path = None
        
        status_msg = await message.reply_text("⏳ **Initialising...**")
        try:
            path = f"downloads/{new_name}"
            
            # Download
            start_time = time.time()
            dl_path = await client.download_media(
                original_msg, 
                file_name=path,
                progress=progress,
                progress_args=(status_msg, start_time, "📥 **Downloading...**")
            )
            
            # Upload
            start_time = time.time()
            await client.send_document(
                message.chat.id, 
                document=dl_path, 
                caption=f"**{new_name}**", 
                thumb=thumb_path, 
                force_document=True,
                progress=progress,
                progress_args=(status_msg, start_time, "📤 **Uploading...**")
            )
            
            os.remove(dl_path)
            await status_msg.delete()
            del user_data[user_id]
        except Exception as e:
            await status_msg.edit(f"Error: {e}")

# --- Main Runner ---
async def main():
    await asyncio.gather(web_server(), app.start())
    await asyncio.Event().wait()

if __name__ == "__main__":
    print("Bot Started!")
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
