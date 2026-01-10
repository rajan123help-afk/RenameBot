import os
import asyncio
import base64
import html
from aiohttp import web
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant, FloodWait
from motor.motor_asyncio import AsyncIOMotorClient

# --- CONFIGURATION (Aapki Details) ---
API_ID = int(os.environ.get("API_ID", "21127"))
API_HASH = os.environ.get("API_HASH", "0375dd20aba7c29d0c1c06590dfb")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "84685014AAGpD5dzd1EzkJs9AqHkAOAhPcmGv1Dwlgk")
OWNER_ID = int(os.environ.get("OWNER_ID", "50214470"))
MONGO_URL = os.environ.get("MONGO_URL", "mongodb+srv://raja:raja12345@filmyflip.jlitika.mongodb.net/?retryWrites=true&w=majority&appName=Filmyflip")
DB_CHANNEL_ID = int(os.environ.get("DB_CHANNEL_ID", "-1003311810643"))
BLOGGER_URL = "https://filmyflip1.blogspot.com/p/download.html"
CREDIT_NAME = "🦋 Filmy Flip Hub 🦋"

# --- DATABASE SETUP ---
mongo = AsyncIOMotorClient(MONGO_URL)
db = mongo["FilmyFlipStore"]
settings_col = db["settings"]
channels_col = db["channels"]

# --- MAIN BOT CLIENT ---
app = Client("MainBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workers=10)

# --- GLOBAL VARS ---
clone_app = None

# --- HELPERS ---
def encode_id(i): return base64.urlsafe_b64encode(str(i).encode("ascii")).decode("ascii").strip("=")
def decode_id(s): return base64.urlsafe_b64decode(s + "=" * (len(s) % 4)).decode("ascii")

def humanbytes(size):
    if not size: return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024: return f"{size:.2f} {unit}"
        size /= 1024

def get_fancy_caption(filename, filesize):
    return (f"<b>{html.escape(filename)}</b>\n\n"
            f"<blockquote><b>File Size ♻️ ➥ {filesize} ”</b></blockquote>\n"
            f"<blockquote><b>Powered By ➥ {CREDIT_NAME} ”</b></blockquote>")

# --- MAIN BOT COMMANDS ---

@app.on_message(filters.command("start") & filters.private)
async def main_start(c, m):
    if m.from_user.id == OWNER_ID:
        await m.reply("👋 **Boss! Main Bot Ready hai.**\n\n🔹 `/setclone token` - Clone Start\n🔹 `/addfs id link` - Add Channel\n🔹 `/delfs id` - Remove Channel\n🔹 **Send File** - Get Link")

# 1. Store File & Generate Link (CRASH PROOF FIX ✅)
@app.on_message(filters.private & (filters.document | filters.video | filters.audio | filters.photo) & filters.user(OWNER_ID))
async def store_file(c, m):
    status = await m.reply("⚙️ **Processing...**")
    try:
        # DB Channel mein copy
        db_msg = await m.copy(DB_CHANNEL_ID)
        code = encode_id(db_msg.id)
        link = f"{BLOGGER_URL}?data={code}"
        
        # Safe Clone Username Check
        bot_uname = "CloneBot"
        try:
            if clone_app and clone_app.is_connected:
                me = await clone_app.get_me()
                bot_uname = me.username
        except: pass
            
        await status.edit(f"✅ **Stored Successfully!**\n\n🔗 **Blogger Link:**\n`{link}`\n\n🤖 **Direct Link:**\n`https://t.me/{bot_uname}?start={code}`")
    except Exception as e:
        await status.edit(f"❌ Error: {e}")

# 2. Set Clone Token
@app.on_message(filters.command("setclone") & filters.user(OWNER_ID))
async def set_clone(c, m):
    if len(m.command) < 2: return await m.reply("Usage: `/setclone TOKEN` (No Brackets!)")
    token = m.command[1]
    await settings_col.update_one({"_id": "clone_token"}, {"$set": {"token": token}}, upsert=True)
    await m.reply("♻️ **Token Saved! Restarting Clone Bot...**")
    await start_clone_bot()

# 3. Add Force Subscribe
@app.on_message(filters.command("addfs") & filters.user(OWNER_ID))
async def add_fs(c, m):
    if len(m.command) < 3: return await m.reply("Usage: `/addfs ChannelID Link`")
    try:
        await channels_col.update_one({"_id": int(m.command[1])}, {"$set": {"link": m.command[2]}}, upsert=True)
        await m.reply(f"✅ **Added:** {m.command[1]}")
    except: await m.reply("Error.")

# 4. Delete Force Subscribe
@app.on_message(filters.command("delfs") & filters.user(OWNER_ID))
async def del_fs(c, m):
    if len(m.command) < 2: return await m.reply("Usage: `/delfs ChannelID`")
    try:
        await channels_col.delete_one({"_id": int(m.command[1])})
        await m.reply(f"🗑 **Deleted:** {m.command[1]}")
    except: await m.reply("Error.")

# --- CLONE BOT LOGIC ---

async def start_clone_bot():
    global clone_app
    data = await settings_col.find_one({"_id": "clone_token"})
    if not data: return print("⚠️ No Clone Token in DB")
    
    if clone_app: await clone_app.stop()
    clone_app = Client("CloneBot_Session", api_id=API_ID, api_hash=API_HASH, bot_token=data["token"])

    @clone_app.on_message(filters.command("start") & filters.private)
    async def clone_start(c, m):
        if len(m.command) < 2:
            txt = (f"👋 **Hello {m.from_user.first_name}!**\n\n🚀 **Filmy Flip Hub Fast Bot!**\n\n📂 **File ke liye:**\n👉 https://t.me/+tBDrm_F2038yNGM9")
            return await m.reply(txt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👨‍💻 Contact Admin", url="https://t.me/Moviessrudio_bot")]]), disable_web_page_preview=True)

        payload = m.command[1]
        
        # Force Sub Check
        channels = channels_col.find()
        missing = []
        async for ch in channels:
            try: await c.get_chat_member(ch["_id"], m.from_user.id)
            except UserNotParticipant: missing.append(ch["link"])
            except: pass
        
        if missing:
            btn = [[InlineKeyboardButton(f"📢 Join Channel {i+1}", url=l)] for i, l in enumerate(missing)]
            btn.append([InlineKeyboardButton("🔄 Try Again", url=f"https://t.me/{c.me.username}?start={payload}")])
            return await m.reply("⚠️ **Join Channels First!**", reply_markup=InlineKeyboardMarkup(btn))

        # Send File & Auto Delete
        try:
            msg_id = int(decode_id(payload))
            temp = await m.reply("🔄 **Checking File...**")
            msg = await c.get_messages(DB_CHANNEL_ID, msg_id)
            media = msg.document or msg.video or msg.audio or msg.photo
            if not media: return await temp.edit("❌ **File Deleted.**")
            
            cap = get_fancy_caption(getattr(media, "file_name", "FilmyFlip_File"), humanbytes(getattr(media, "file_size", 0)))
            sent = await c.copy_message(m.chat.id, DB_CHANNEL_ID, msg_id, caption=cap)
            await temp.delete()
            
            # Auto Delete Timer
            btn = InlineKeyboardMarkup([[InlineKeyboardButton("📂 Get File Again", url=f"https://t.me/{c.me.username}?start={payload}")]])
            alert = await m.reply("⏳ **File deletes in 5 mins! Forward now.**", reply_markup=btn)
            await asyncio.sleep(300)
            await sent.delete(); await alert.delete()
            await m.reply("❌ **Time Over! File Deleted.**", reply_markup=btn)
        except Exception as e: await m.reply(f"❌ Error: {e}")

    try: await clone_app.start(); print("✅ Clone Started")
    except Exception as e: print(f"❌ Clone Error: {e}")

# --- SERVER & START ---
async def web_server():
    r = web.RouteTableDef()
    @r.get("/", allow_head=True)
    async def h(q): return web.json_response({"status": "running"})
    app = web.Application(); app.add_routes(r)
    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", 8080).start()

async def start_services():
    print("🚀 Starting Main Bot...")
    await app.start()
    print("✅ Main Bot Live!")
    await start_clone_bot()
    await web_server()
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(start_services())
    
