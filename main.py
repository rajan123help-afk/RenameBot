import os
import asyncio
import base64
import html
from aiohttp import web
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant, MessageNotModified
from motor.motor_asyncio import AsyncIOMotorClient

# --- CONFIGURATION ---
API_ID = int(os.environ.get("API_ID", "234227"))
API_HASH = os.environ.get("API_HASH", "0375dd20aba9f2e7cd0c1c06590dfb")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "84601492:AAGpD5dzd1Js9AkAOAhPcmGv1Dwlgk")
OWNER_ID = int(os.environ.get("OWNER_ID", "50914470"))
MONGO_URL = os.environ.get("MONGO_URL", "mongodb+srv://raja:raja12345@filmyflip.jlitika.mongodb.net/?retryWrites=true&w=majority&appName=Filmyflip")
DB_CHANNEL_ID = int(os.environ.get("DB_CHANNEL_ID", "-1003311810643"))
BLOGGER_URL = "https://filmyflip1.blogspot.com/p/download.html"
CREDIT_NAME = "🦋 Filmy Flip Hub 🦋"

# --- DATABASE SETUP ---
mongo = AsyncIOMotorClient(MONGO_URL)
db = mongo["FilmyFlipStore"]
settings_col = db["settings"]
channels_col = db["channels"]

# --- MAIN BOT ---
app = Client("MainBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workers=10, parse_mode=enums.ParseMode.HTML)
clone_app = None

# --- HELPERS (DOUBLE ENCODE FIX 🛠️) ---

def encode_payload(string_data):
    # Step 1: Encode String to Base64
    b64_1 = base64.urlsafe_b64encode(string_data.encode("utf-8")).decode("utf-8")
    # Step 2: Encode AGAIN (Double Encode for Blogger)
    b64_2 = base64.urlsafe_b64encode(b64_1.encode("utf-8")).decode("utf-8")
    return b64_2.strip("=")

def decode_payload(s):
    try:
        # Step 1: Fix Padding & Decode First Layer
        s = s.strip()
        padding = len(s) % 4
        if padding > 0: s += "=" * (4 - padding)
        decoded_1 = base64.urlsafe_b64decode(s).decode("utf-8")
        
        # Step 2: Fix Padding & Decode Second Layer
        decoded_1 = decoded_1.strip()
        padding = len(decoded_1) % 4
        if padding > 0: decoded_1 += "=" * (4 - padding)
        final_data = base64.urlsafe_b64decode(decoded_1).decode("utf-8")
        
        return final_data
    except:
        # Fallback: Agar Single Encoded hai (Purane Links)
        try:
            return base64.urlsafe_b64decode(s).decode("utf-8")
        except:
            return None

def extract_msg_id(payload):
    # Format: link_OWNERID_MSGID
    try:
        if "_" in payload: return int(payload.split("_")[-1])
        else: return int(payload)
    except: return None

def humanbytes(size):
    if not size: return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024: return f"{size:.2f} {unit}"
        size /= 1024

def get_duration_str(duration):
    if not duration: return "0s"
    m, s = divmod(int(duration), 60); h, m = divmod(m, 60)
    return f"{h}h {m}m {s}s" if h else f"{m}m {s}s"

def get_fancy_caption(filename, filesize, duration):
    return (f"<b>{html.escape(filename)}</b>\n\n"
            f"<blockquote><b>📂 Size ➥ {filesize}</b></blockquote>\n"
            f"<blockquote><b>⏰ Duration ➥ {get_duration_str(duration)}</b></blockquote>\n"
            f"<blockquote><b>⚡ Powered By ➥ {CREDIT_NAME}</b></blockquote>")

# --- COMMANDS ---
@app.on_message(filters.command("start") & filters.private)
async def main_start(c, m):
    if m.from_user.id == OWNER_ID:
        await m.reply("👋 **Boss! Ready.**\n\n🔹 `/setclone TOKEN`\n🔹 `/addfs ID Link`\n🔹 `/delfs ID`")

# 1. STORE FILE (Fix: MessageNotModified Error Ignored)
@app.on_message(filters.private & (filters.document | filters.video | filters.audio | filters.photo) & filters.user(OWNER_ID))
async def store_file(c, m):
    status = await m.reply("⚙️ **Processing...**")
    try:
        # Caption Logic
        media = m.document or m.video or m.audio or m.photo
        fname = getattr(media, "file_name", "File")
        fsize = humanbytes(getattr(media, "file_size", 0))
        dur = getattr(media, "duration", 0)
        new_cap = get_fancy_caption(fname, fsize, dur)

        # Copy to DB
        db_msg = await m.copy(DB_CHANNEL_ID)
        
        # Edit Caption (Try-Except Block)
        try: await db_msg.edit_caption(new_cap)
        except MessageNotModified: pass # Ignore if caption is same
        except: pass 
        
        # Double Encode for Blogger
        raw_data = f"link_{OWNER_ID}_{db_msg.id}"
        code = encode_payload(raw_data)
        
        bot_uname = "CloneBot"
        try:
            if clone_app and clone_app.is_connected:
                bot_uname = (await clone_app.get_me()).username
        except: pass
            
        await status.edit(f"✅ **Stored!**\n\n🔗 **Blog:** `{BLOGGER_URL}?data={code}`\n\n🤖 **Direct:** `https://t.me/{bot_uname}?start={code}`")
    except Exception as e: await status.edit(f"❌ Error: {e}")

# 2. SETTINGS
@app.on_message(filters.command("setclone") & filters.user(OWNER_ID))
async def set_clone(c, m):
    if len(m.command) < 2: return await m.reply("Usage: `/setclone TOKEN`")
    await settings_col.update_one({"_id": "clone_token"}, {"$set": {"token": m.command[1]}}, upsert=True)
    await m.reply("♻️ **Saved! Restarting...**"); await start_clone_bot()

@app.on_message(filters.command("addfs") & filters.user(OWNER_ID))
async def add_fs(c, m):
    if len(m.command) < 3: return await m.reply("Usage: `/addfs ID Link`")
    await channels_col.update_one({"_id": int(m.command[1])}, {"$set": {"link": m.command[2]}}, upsert=True)
    await m.reply("✅ Added.")

@app.on_message(filters.command("delfs") & filters.user(OWNER_ID))
async def del_fs(c, m):
    try: await channels_col.delete_one({"_id": int(m.command[1])}); await m.reply("🗑 Deleted.")
    except: pass

# --- CLONE BOT LOGIC ---
async def start_clone_bot():
    global clone_app
    data = await settings_col.find_one({"_id": "clone_token"})
    if not data: return
    if clone_app: await clone_app.stop()
    clone_app = Client("CloneBot_Session", api_id=API_ID, api_hash=API_HASH, bot_token=data["token"], parse_mode=enums.ParseMode.HTML)

    @clone_app.on_message(filters.command("start") & filters.private)
    async def clone_start(c, m):
        if len(m.command) < 2:
            return await m.reply(f"👋 **Hello!**\n📂 **File ke liye:**\n👉 https://t.me/+tBDrm_F2038yNGM9", 
                               reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👨‍💻 Contact Admin", url="https://t.me/Moviessrudio_bot")]]), disable_web_page_preview=True)

        payload = m.command[1]
        
        # FS Check
        missing = []
        async for ch in channels_col.find():
            try: await c.get_chat_member(ch["_id"], m.from_user.id)
            except UserNotParticipant: missing.append(ch["link"])
            except: pass
        if missing:
            btn = [[InlineKeyboardButton(f"📢 Join Channel {i+1}", url=l)] for i, l in enumerate(missing)]
            btn.append([InlineKeyboardButton("🔄 Try Again", url=f"https://t.me/{c.me.username}?start={payload}")])
            return await m.reply("⚠️ **Join Channels First!**", reply_markup=InlineKeyboardMarkup(btn))

        # Decode Logic (Handles Double Encoded)
        decoded_string = decode_payload(payload)
        if not decoded_string: return await m.reply("❌ **Link Invalid!**")
        
        msg_id = extract_msg_id(decoded_string)
        if not msg_id: return await m.reply("❌ **Link Invalid!**")

        try:
            temp = await m.reply("🔄 **Checking File...**")
            # Clone Bot MUST be Admin in DB Channel
            try:
                msg = await c.get_messages(DB_CHANNEL_ID, msg_id)
            except Exception as e:
                return await temp.edit(f"❌ **Error: Peer Id Invalid.**\nClone Bot ko DB Channel ({DB_CHANNEL_ID}) me Admin banao!")
            
            if not msg or not (msg.document or msg.video or msg.audio or msg.photo): 
                return await temp.edit("❌ **File Deleted.**")
            
            # Use Caption from DB
            cap = msg.caption or get_fancy_caption(getattr(msg.document or msg.video, "file_name", "File"), humanbytes(getattr(msg.document or msg.video, "file_size", 0)), 0)
            
            sent = await c.copy_message(m.chat.id, DB_CHANNEL_ID, msg_id, caption=cap)
            await temp.delete()
            
            btn = InlineKeyboardMarkup([[InlineKeyboardButton("📂 Get File Again", url=f"https://t.me/{c.me.username}?start={payload}")]])
            alert = await m.reply("⏳ **File 5 min mein delete hogi!**", reply_markup=btn)
            await asyncio.sleep(300)
            await sent.delete(); await alert.delete()
            await m.reply("❌ **Time Over!**", reply_markup=btn)
        except Exception as e: await m.reply(f"❌ Error: {e}")

    try: await clone_app.start(); print("✅ Clone Started")
    except: pass

async def start_services():
    await app.start()
    await start_clone_bot()
    r = web.RouteTableDef()
    @r.get("/", allow_head=True)
    async def h(q): return web.json_response({"status": "running"})
    app_web = web.Application(); app_web.add_routes(r)
    runner = web.AppRunner(app_web); await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", 8080).start()
    await asyncio.Event().wait()

if __name__ == "__main__": asyncio.get_event_loop().run_until_complete(start_services())
    
