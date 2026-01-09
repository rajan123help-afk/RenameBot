import os
import logging
import base64
import asyncio
from pyrogram import Client, filters, idle
from pyrogram.errors import UserNotParticipant, FloodWait
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import motor.motor_asyncio
from aiohttp import web

# --- 1. CONFIGURATION ---
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "") 
MONGO_URI = os.environ.get("MONGO_URI", "")
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))
WEBSITE_URL = os.environ.get("WEBSITE_URL", "") # Blogger Link

# --- 2. DATABASE CLASS (MongoDB) ---
class Database:
    def __init__(self, uri):
        self._client = motor.motor_asyncio.AsyncIOMotorClient(uri)
        self.db = self._client["MyProBot"]
        self.col = self.db.files
        self.settings = self.db.settings 

    # --- File Save Logic ---
    async def add_file(self, message):
        file_unique_id = None
        if message.document: file_unique_id = message.document.file_unique_id
        elif message.video: file_unique_id = message.video.file_unique_id
        elif message.audio: file_unique_id = message.audio.file_unique_id
        
        if not file_unique_id: return None

        # Check agar file pehle se hai
        exist = await self.col.find_one({'unique_id': file_unique_id})
        if exist: return exist['short_id']

        # Nayi Short ID Banana
        short_id = base64.urlsafe_b64encode(str(message.id).encode("ascii")).decode("ascii").strip("=")
        data = {
            'unique_id': file_unique_id,
            'msg_id': message.id, 
            'short_id': short_id,
            'caption': message.caption or ""
        }
        await self.col.insert_one(data)
        return short_id

    async def get_file(self, short_id):
        return await self.col.find_one({'short_id': short_id})

    # --- Force Subscribe Settings ---
    async def add_fs_channel(self, channel_id):
        await self.settings.update_one(
            {'_id': 'main_settings'}, 
            {'$addToSet': {'fs_channels': int(channel_id)}}, 
            upsert=True
        )

    async def remove_fs_channel(self, channel_id):
        await self.settings.update_one(
            {'_id': 'main_settings'}, 
            {'$pull': {'fs_channels': int(channel_id)}}
        )
    
    async def clear_fs_channels(self):
        await self.settings.update_one(
            {'_id': 'main_settings'}, 
            {'$set': {'fs_channels': []}}
        )

    async def get_fs_channels(self):
        data = await self.settings.find_one({'_id': 'main_settings'})
        return data.get('fs_channels', []) if data else []

    # --- DB Channel Settings ---
    async def set_db_channel(self, channel_id):
        await self.settings.update_one(
            {'_id': 'main_settings'}, 
            {'$set': {'db_channel': int(channel_id)}}, 
            upsert=True
        )

    async def get_db_channel(self):
        data = await self.settings.find_one({'_id': 'main_settings'})
        return data.get('db_channel') if data else 0

# Database Connect
db = Database(MONGO_URI)

# --- 3. BOT CLIENT ---
bot = Client("MainBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
# --- 4. COMMANDS & FEATURES ---

@bot.on_message(filters.command("start"))
async def start(client, message):
    text = message.text
    if len(text) > 7: 
        code = text.split(maxsplit=1)[1]
        
        # A. Force Subscribe Check (Multi-Channel)
        fs_channels = await db.get_fs_channels()
        not_joined = []
        
        for channel_id in fs_channels:
            try:
                await client.get_chat_member(channel_id, message.from_user.id)
            except UserNotParticipant:
                try:
                    chat = await client.get_chat(channel_id)
                    link = chat.invite_link
                    not_joined.append((chat.title, link))
                except:
                    not_joined.append(("Join Channel", "https://t.me/YourChannel"))
            except Exception:
                pass 

        if not_joined:
            buttons = []
            for name, link in not_joined:
                buttons.append([InlineKeyboardButton(name, url=link)])
            
            # Wapas try karne ka button (Direct Start Link)
            try_again_link = f"https://t.me/{client.me.username}?start={code}"
            buttons.append([InlineKeyboardButton("🔄 Try Again", url=try_again_link)])
            
            return await message.reply_text(
                "⚠️ **Access Denied!**\n\nFile paane ke liye niche diye gaye channels ko join karein:",
                reply_markup=InlineKeyboardMarkup(buttons)
            )

        # B. File Delivery
        file_data = await db.get_file(code)
        db_channel_id = await db.get_db_channel()
        
        if file_data and db_channel_id:
            try:
                await client.copy_message(
                    chat_id=message.chat.id,
                    from_chat_id=db_channel_id,
                    message_id=file_data['msg_id'],
                    caption=file_data['caption']
                )
            except Exception as e:
                await message.reply_text("❌ Error: DB Channel me Bot Admin nahi hai ya File delete ho gayi.")
        else:
            await message.reply_text("❌ File Database mein nahi mili.")
    else:
        await message.reply_text(f"👋 Hello {message.from_user.mention}!\nMain Filmy Flip Hub Bot hoon.")

# --- ADMIN COMMANDS ---

@bot.on_message(filters.command("setdb") & filters.user(OWNER_ID))
async def set_db_channel_cmd(client, message):
    try:
        channel_id = int(message.command[1])
        await db.set_db_channel(channel_id)
        await message.reply_text(f"✅ **Database Channel Set!**\nID: `{channel_id}`")
    except: await message.reply_text("Usage: `/setdb -100xxxx`")

@bot.on_message(filters.command("addfs") & filters.user(OWNER_ID))
async def add_force_sub(client, message):
    try:
        channel_id = int(message.command[1])
        await db.add_fs_channel(channel_id)
        await message.reply_text(f"✅ **FS Channel Added!**\nID: `{channel_id}`")
    except: await message.reply_text("Usage: `/addfs -100xxxx`")

@bot.on_message(filters.command("delfs") & filters.user(OWNER_ID))
async def del_force_sub(client, message):
    try:
        channel_id = int(message.command[1])
        await db.remove_fs_channel(channel_id)
        await message.reply_text(f"🗑️ **FS Channel Removed!**")
    except: await message.reply_text("Usage: `/delfs -100xxxx`")

@bot.on_message(filters.command("clearfs") & filters.user(OWNER_ID))
async def clear_all_fs(client, message):
    await db.clear_fs_channels()
    await message.reply_text("🗑️ **All FS Channels Cleared!**")

@bot.on_message(filters.command("listfs") & filters.user(OWNER_ID))
async def list_force_sub(client, message):
    channels = await db.get_fs_channels()
    if channels:
        await message.reply_text("**Active FS Channels:**\n" + "\n".join([f"`{c}`" for c in channels]))
    else:
        await message.reply_text("No FS Channels set.")

# --- AUTO STORE & CLEAN (With Blogger Link) ---
@bot.on_message((filters.document | filters.video | filters.audio) & filters.private & filters.user(OWNER_ID))
async def auto_store_clean(client, message):
    db_channel = await db.get_db_channel()
    if not db_channel:
        return await message.reply_text("❌ **DB Channel Not Set!** `/setdb` use karein.")

    status = await message.reply_text("⚙️ Processing...")
    try:
        # 1. Copy to DB Channel
        db_msg = await message.copy(db_channel)
        
        # 2. Save to DB
        short_id = await db.add_file(db_msg)
        
        # 3. Generate Link (Blogger or Direct)
        if WEBSITE_URL:
            # Smart Link with Bot Username for Redirect
            link = f"{WEBSITE_URL}?id={short_id}&bot={client.me.username}"
        else:
            link = f"https://t.me/{client.me.username}?start={short_id}"
        
        await status.edit_text(f"✅ **Saved!**\n🔗 `{link}`", disable_web_page_preview=True)
        await message.delete() # Delete Original File
        
    except Exception as e:
        await status.edit_text(f"❌ Error: {e}")

# --- 5. WEB SERVER (Render Keep-Alive) ---
async def web_server():
    async def handle(request):
        return web.Response(text="Bot is Running Successfully!")

    app = web.Application()
    app.router.add_get("/", handle)
    return app

async def start_services():
    print("Bot Starting...")
    await bot.start()
    print("Bot Connected!")

    app = await web_server()
    runner = web.AppRunner(app)
    await runner.setup()
    bind_address = "0.0.0.0"
    PORT = int(os.environ.get("PORT", 8080))
    await web.TCPSite(runner, bind_address, PORT).start()
    print(f"Web Server Running on Port {PORT}")

    await idle()
    await bot.stop()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(start_services())
    
