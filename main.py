import os
import asyncio
import base64
import html
from aiohttp import web
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant
from motor.motor_asyncio import AsyncIOMotorClient

# --- CONFIGURATION ---
API_ID = int(os.environ.get("API_ID", "234127"))
API_HASH = os.environ.get("API_HASH", "0375dda9f2e7c29d0c1c06590dfb")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "84685492:AAGpD5dzd1EzkJs9AqHkAOAhPcmGv1Dwlgk")
OWNER_ID = int(os.environ.get("OWNER_ID", "5027914470"))
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

# --- HELPERS (Caption & Decoder Fixed) ---
def encode_id(i): 
    return base64.urlsafe_b64encode(str(i).encode("utf-8")).decode("utf-8").strip("=")

def decode_id(s):
    try:
        padding = len(s) % 4
        if padding > 0: s += "=" * (4 - padding)
        return base64.urlsafe_b64decode(s).decode("utf-8")
    except: return None

def humanbytes(size):
    if not size: return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024: return f"{size:.2f} {unit}"
        size /= 1024

def get_duration_str(duration):
    if not duration: return "0s"
    m, s = divmod(int(duration), 60)
    h, m = divmod(m, 60)
    return f"{h}h {m}m {s}s" if h else f"{m}m {s}s"

# 🔥 NEW FANCY CAPTION (Green Line + Duration)
def get_fancy_caption(filename, filesize, duration):
    return (f"<b>{html.escape(filename)}</b>\n\n"
            f"<blockquote><b>📂 Size ➥ {filesize}</b></blockquote>\n"
            f"<blockquote><b>⏰ Duration ➥ {get_duration_str(duration)}</b></blockquote>\n"
            f"<blockquote><b>⚡ Powered By ➥ {CREDIT_NAME}</b></blockquote>")

# --- MAIN BOT COMMANDS ---
@app.on_message(filters.command("start") & filters.private)
async def main_start(c, m):
    if m.from_user.id == OWNER_ID:
        await m.reply("👋 **Boss! Main Bot Ready.**\n\n🔹 `/setclone token`\n🔹 `/addfs ID Link`\n🔹 `/delfs ID`")

# 1. Store File (Updated Caption)
@app.on_message(filters.private & (filters.document | filters.video | filters.audio | filters.photo) & filters.user(OWNER_ID))
async def store_file(c, m):
    status = await m.reply("⚙️ **Processing...**")
    try:
        db_msg = await m.copy(DB_CHANNEL_ID)
        code = encode_id(db_msg.id)
        
        bot_uname = "CloneBot"
        try:
            if clone_app and clone_app.is_connected:
                bot_uname = (await clone_app.get_me()).username
        except: pass
            
        await status.edit(f"✅ **Stored!**\n\n🔗 **Blog:** `{BLOGGER_URL}?data={code}`\n\n🤖 **Bot:** `https://t.me/{bot_uname}?start={code}`")
    except Exception as e: await status.edit(f"❌ Error: {e}")

# 2. Settings
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

# --- CLONE BOT LOGIC (New Caption Here too) ---
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
        
        # Check Force Sub
        missing = []
        async for ch in channels_col.find():
            try: await c.get_chat_member(ch["_id"], m.from_user.id)
            except UserNotParticipant: missing.append(ch["link"])
            except: pass
        
        if missing:
            btn = [[InlineKeyboardButton(f"📢 Join Channel {i+1}", url=l)] for i, l in enumerate(missing)]
            btn.append([InlineKeyboardButton("🔄 Try Again", url=f"https://t.me/{c.me.username}?start={payload}")])
            return await m.reply("⚠️ **Join Channels First!**", reply_markup=InlineKeyboardMarkup(btn))

        # Decode & Send
        decoded = decode_id(payload)
        if not decoded: return await m.reply("❌ **Invalid Link**")

        try:
            msg_id = int(decoded.split("_")[-1]) if "_" in decoded else int(decoded)
            temp = await m.reply("🔄 **Checking File...**")
            msg = await c.get_messages(DB_CHANNEL_ID, msg_id)
            media = msg.document or msg.video or msg.audio or msg.photo
            if not media: return await temp.edit("❌ **File Deleted.**")
            
            # 🔥 New Fancy Caption Logic
            fname = getattr(media, "file_name", "File")
            fsize = humanbytes(getattr(media, "file_size", 0))
            dur = getattr(media, "duration", 0)
            cap = get_fancy_caption(fname, fsize, dur)
            
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
    
