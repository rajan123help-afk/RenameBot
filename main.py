import os
import asyncio
import base64
import html
from aiohttp import web
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import UserNotParticipant, FloodWait
from motor.motor_asyncio import AsyncIOMotorClient

# --- CONFIGURATION ---
API_ID = int(os.environ.get("API_ID", "23421127"))
API_HASH = os.environ.get("API_HASH", "0375dd20aba9f2e7c29d0c1c06590dfb")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8468501492:AAGpD5dzd1EzkJs9AqHkAOAhPcmGv1Dwlgk")
OWNER_ID = int(os.environ.get("OWNER_ID", "5027914470"))
MONGO_URL = os.environ.get("MONGO_URL", "mongodb+srv://raja:raja12345@filmyflip.jlitika.mongodb.net/?retryWrites=true&w=majority&appName=Filmyflip")
DB_CHANNEL_ID = int(os.environ.get("DB_CHANNEL_ID", "-1003311810643"))
BLOGGER_URL = "https://filmyflip1.blogspot.com/p/download.html"
CREDIT_NAME = "🦋 Filmy Flip Hub 🦋"

# --- DATABASE SETUP ---
mongo = AsyncIOMotorClient(MONGO_URL)
db = mongo["FilmyFlipStore"]
settings_col = db["settings"]      # Clone Bot Token yahan save hoga
channels_col = db["channels"]      # Force Sub Channels yahan save honge

# --- MAIN BOT CLIENT ---
app = Client("MainBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# --- GLOBAL VARIABLES ---
clone_app = None  # Clone bot ka session yahan rahega

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

# --- MAIN BOT COMMANDS (ADMIN ONLY) ---

@app.on_message(filters.command("start") & filters.private)
async def main_start(c, m):
    if m.from_user.id != OWNER_ID: return
    await m.reply("👋 **Boss! Main Bot Ready hai.**\n\n🔹 `/setclone [token]` - Clone Bot Start karein\n🔹 `/addfs [id] [link]` - Channel Add karein\n🔹 `/delfs [id]` - Channel Delete karein\n🔹 **File bhejein** - Link lene ke liye")

# 1. Store File & Generate Link
@app.on_message(filters.private & (filters.document | filters.video | filters.audio | filters.photo) & filters.user(OWNER_ID))
async def store_file(c, m):
    status = await m.reply("⚙️ **Processing...**")
    try:
        # DB Channel mein copy karna
        db_msg = await m.copy(DB_CHANNEL_ID)
        
        # Payload banana
        msg_id = db_msg.id
        code = encode_id(msg_id)
        link = f"{BLOGGER_URL}?data={code}"
        
        # Clone bot ka username nikalna (Link ke liye)
        bot_uname = "CloneBot"
        if clone_app:
            me = await clone_app.get_me()
            bot_uname = me.username
            
        await status.edit(f"✅ **Stored Successfully!**\n\n🔗 **Blogger Link:**\n`{link}`\n\n🤖 **Direct Link:**\n`https://t.me/{bot_uname}?start={code}`")
    except Exception as e:
        await status.edit(f"❌ Error: {e}")

# 2. Set Clone Bot Token
@app.on_message(filters.command("setclone") & filters.user(OWNER_ID))
async def set_clone(c, m):
    if len(m.command) < 2: return await m.reply("Usage: `/setclone 12345:ABCDE...`")
    token = m.command[1]
    await settings_col.update_one({"_id": "clone_token"}, {"$set": {"token": token}}, upsert=True)
    await m.reply("♻️ **Token Saved! Restarting Clone Bot...**")
    await start_clone_bot()

# 3. Add Force Subscribe Channel
@app.on_message(filters.command("addfs") & filters.user(OWNER_ID))
async def add_fs(c, m):
    if len(m.command) < 3: return await m.reply("Usage: `/addfs -100xxxx https://t.me/...`")
    try:
        cid = int(m.command[1])
        link = m.command[2]
        await channels_col.update_one({"_id": cid}, {"$set": {"link": link}}, upsert=True)
        await m.reply(f"✅ **Channel Added:** {cid}")
    except Exception as e: await m.reply(f"Error: {e}")

# 4. Delete Force Subscribe Channel
@app.on_message(filters.command("delfs") & filters.user(OWNER_ID))
async def del_fs(c, m):
    if len(m.command) < 2: return await m.reply("Usage: `/delfs -100xxxx`")
    try:
        cid = int(m.command[1])
        await channels_col.delete_one({"_id": cid})
        await m.reply(f"🗑 **Channel Deleted:** {cid}")
    except: await m.reply("Error.")

# --- CLONE BOT LOGIC (PUBLIC) ---

async def start_clone_bot():
    global clone_app
    # Token DB se lena
    data = await settings_col.find_one({"_id": "clone_token"})
    if not data: return print("⚠️ No Clone Token Found in DB!")
    
    token = data["token"]
    
    if clone_app: await clone_app.stop()
    clone_app = Client("CloneBot_Session", api_id=API_ID, api_hash=API_HASH, bot_token=token)

    @clone_app.on_message(filters.command("start") & filters.private)
    async def clone_start_handler(c, m):
        # 1. Simple Start (No Payload)
        if len(m.command) < 2:
            txt = (f"👋 **Hello {m.from_user.first_name}!**\n\n"
                   f"🚀 **Yeh Filmy Flip Hub ka Super Fast File Deliver Bot hai!**\n\n"
                   f"📂 **File ke liye is pr click kre:**\n"
                   f"👉 https://t.me/+tBDrm_F2038yNGM9")
            
            btn = InlineKeyboardMarkup([[InlineKeyboardButton("👨‍💻 Contact Admin", url="https://t.me/Moviessrudio_bot")]])
            return await m.reply(txt, reply_markup=btn, disable_web_page_preview=True)

        # 2. File Delivery Logic (Payload Exists)
        payload = m.command[1]
        
        # A. Force Subscribe Check
        channels = channels_col.find()
        missing = []
        async for ch in channels:
            try:
                await c.get_chat_member(ch["_id"], m.from_user.id)
            except UserNotParticipant:
                missing.append(ch["link"])
            except Exception: pass # Bot admin nahi hai ya channel delete ho gaya
        
        if missing:
            buttons = [[InlineKeyboardButton(f"📢 Join Channel {i+1}", url=link)] for i, link in enumerate(missing)]
            buttons.append([InlineKeyboardButton("🔄 Try Again", url=f"https://t.me/{c.me.username}?start={payload}")])
            return await m.reply(
                "⚠️ **Pehle Saare Channels Join Karein!**\n\nTabhi Movie ki File milegi 👇",
                reply_markup=InlineKeyboardMarkup(buttons)
            )

        # B. Send File
        try:
            msg_id = int(decode_id(payload))
            temp_msg = await m.reply("🔄 **Checking File...**")
            
            # DB Channel se message uthana
            file_msg = await c.get_messages(DB_CHANNEL_ID, msg_id)
            media = file_msg.document or file_msg.video or file_msg.audio or file_msg.photo
            
            if not media: return await temp_msg.edit("❌ **File Not Found or Deleted.**")

            # Caption Setup
            fname = getattr(media, "file_name", "FilmyFlip_File")
            fsize = humanbytes(getattr(media, "file_size", 0))
            cap = get_fancy_caption(fname, fsize)

            # File Bhejna
            sent_msg = await c.copy_message(
                chat_id=m.chat.id,
                from_chat_id=DB_CHANNEL_ID,
                message_id=msg_id,
                caption=cap
            )
            await temp_msg.delete()

            # C. Auto Delete & Get File Button
            btn = InlineKeyboardMarkup([[InlineKeyboardButton("📂 Get File Again", url=f"https://t.me/{c.me.username}?start={payload}")]])
            alert = await m.reply("⏳ **Yeh File 5 Minute mein Delete ho jayegi! Jaldi Forward kar lo.**", reply_markup=btn)

            await asyncio.sleep(300) # 5 Minute Wait
            
            await sent_msg.delete()
            await alert.delete()
            await m.reply("❌ **Time Over! File Delete ho gayi.**", reply_markup=btn)

        except Exception as e:
            await m.reply(f"❌ **Error:** Link expired or invalid.\n{e}")

    await clone_app.start()
    print(f"♻️ Clone Bot Started: @{(await clone_app.get_me()).username}")

# --- WEB SERVER (To Keep Render Alive) ---
async def web_server():
    routes = web.RouteTableDef()
    @routes.get("/", allow_head=True)
    async def root_route_handler(request): return web.json_response({"status": "running"})
    app = web.Application()
    app.add_routes(routes)
    return app

async def start_services():
    print("🚀 Starting Main Bot...")
    await app.start()
    print("✅ Main Bot Started!")

    # Auto Start Clone Bot if Token Exists
    try: await start_clone_bot()
    except Exception as e: print(f"⚠️ Clone Bot Error: {e}")

    # Start Web Server
    runner = web.AppRunner(await web_server())
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", 8080).start()
    
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(start_services())
    
