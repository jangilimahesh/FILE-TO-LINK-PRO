import asyncio
import logging
import aiohttp
import traceback
import random
import string
from datetime import datetime, timedelta, date, time
import pytz
from database.users_db import db
from Script import script
from info import *
from shortzy import Shortzy

# -------------------------- LOGGER INITIALIZATION -------------------------- #
# Initializes the logger to track errors and informational logs.
logger = logging.getLogger(__name__)

# -------------------------- TEMPORARY DATA STORAGE -------------------------- #
# This class works as an in-memory temporary storage during bot runtime.
class temp:
    ME = None
    BOT = None
    U_NAME = None
    B_NAME = None
    TOKENS = {}      # Temporarily stores user tokens
    VERIFIED = {}    # Caches verified user information

# -------------------------- PING SERVER -------------------------- #
# Regularly pings the server to keep it active.
async def ping_server():
    while True:
        await asyncio.sleep(PING_INTERVAL)  # Runs every interval
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(URL) as resp:
                    logging.info(f"✅ Pinged server: {resp.status}")
        except asyncio.TimeoutError:
            logger.warning("⚠️ Timeout: Could not ping server!")
        except Exception as e:
            logger.error(f"❌ Exception while pinging server: {e}")
            traceback.print_exc()

# -------------------------- FILE SIZE CONVERTER -------------------------- #
# Converts file size from bytes to a human-readable format.
def get_size(size: int) -> str:
    units = ["Bytes", "KB", "MB", "GB", "TB", "PB", "EB"]
    size = float(size)
    i = 0
    while size >= 1024.0 and i < len(units) - 1:
        size /= 1024.0
        i += 1
    return f"{size:.2f} {units[i]}"

# -------------------------- READABLE TIME FORMATTER -------------------------- #
# Converts seconds into a readable time format (hh:mm:ss).
def get_readable_time(seconds: int) -> str:
    time_list = []
    time_suffix = ["s", "m", "h", " days"]
    count = 0
    while count < 4:
        count += 1
        if count < 3:
            seconds, result = divmod(seconds, 60)
        elif count == 3:
            seconds, result = divmod(seconds, 60)
        else:
            seconds, result = divmod(seconds, 24)
        if seconds == 0 and result == 0:
            break
        time_list.append(f"{int(result)}{time_suffix[count - 1]}")
    time_list.reverse()
    return ": ".join(time_list)

# -------------------------- SHORT LINK GENERATOR (For Verification) -------------------------- #
# Shortens the verification link so users can verify easily.
async def get_verify_shorted_link(link):
    API = SHORTLINK_API
    URL = SHORTLINK_URL
    if not link.startswith("https"):
        link = link.replace("http", "https", 1)

    if URL == "api.shareus.in":
        url = f"https://{URL}/shortLink"
        params = {"token": API, "format": "json", "link": link}
    else:
        url = f"https://{URL}/api"
        params = {"api": API, "url": link}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, ssl=False) as response:
                data = await response.json(content_type="text/html" if URL == "api.shareus.in" else None)
                if data["status"] == "success":
                    return data.get("shortlink") or data.get("shortenedUrl")
                else:
                    logger.error(f"Shorten Error: {data['message']}")
    except Exception as e:
        logger.error(f"Shorten Exception: {e}")

    return f"{url}?token={API}&link={link}"

# -------------------------- SHORT LINK GENERATOR (Normal) -------------------------- #
# Shortens a general link.
async def get_shortlink(link):
    API = SHORTLINK_API
    URL = SHORTLINK_URL
    if not link.startswith("https"):
        link = link.replace("http", "https", 1)

    if URL == "api.shareus.in":
        url = f"https://{URL}/shortLink"
        params = {"token": API, "format": "json", "link": link}
    else:
        url = f"https://{URL}/api"
        params = {"api": API, "url": link}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, ssl=False) as response:
                data = await response.json(content_type="text/html" if URL == "api.shareus.in" else None)
                if data["status"] == "success":
                    return data.get("shortlink") or data.get("shortenedUrl")
                else:
                    logger.error(f"Shorten Error: {data['message']}")
    except Exception as e:
        logger.error(f"Shorten Exception: {e}")

    return f"{url}?token={API}&link={link}"

# -------------------------- TOKEN VALIDITY CHECK -------------------------- #
# Checks whether a user's given token is still valid or not.
async def check_token(bot, userid, token):
    user = await bot.get_users(userid)
    tokens = temp.TOKENS.get(user.id, {})
    return tokens.get(token) == False

# -------------------------- TOKEN GENERATOR -------------------------- #
# Generates a unique verification token for the user and provides a short link.
async def get_token(bot, userid, link):
    user = await bot.get_users(userid)
    token = ''.join(random.choices(string.ascii_letters + string.digits, k=7))
    temp.TOKENS[user.id] = {token: False}
    full_link = f"{link}verify-{user.id}-{token}"
    short_link = await get_verify_shorted_link(full_link)
    return short_link

# -------------------------- GET VERIFICATION STATUS -------------------------- #
# Retrieves a user's verification status from cache or database.
async def get_verify_status(userid):
    status = temp.VERIFIED.get(userid)
    if not status:
        status = await db.get_verified(userid)
        temp.VERIFIED[userid] = status
    return status

# -------------------------- UPDATE VERIFICATION STATUS -------------------------- #
# Updates a user's verification expiry date and time.
async def update_verify_status(userid, date_temp, time_temp):
    status = await get_verify_status(userid)
    status["date"] = date_temp
    status["time"] = time_temp
    temp.VERIFIED[userid] = status
    await db.update_verification(userid, date_temp, time_temp)

# -------------------------- VERIFY USER -------------------------- #
# Marks the user as verified and sets their expiry date.
async def verify_user(bot, userid, token):
    user = await bot.get_users(int(userid))
    temp.TOKENS[user.id] = {token: True}
    tz = pytz.timezone('Asia/Kolkata')
    expiry = datetime.now(tz) + timedelta(seconds=VERIFY_EXPIRE)
    date_str = expiry.strftime("%Y-%m-%d")
    time_str = expiry.strftime("%H:%M:%S")
    await update_verify_status(user.id, date_str, time_str)

# -------------------------- CHECK USER VERIFICATION -------------------------- #
# Checks whether the user's verification is still valid or has expired.
async def check_verification(bot, userid):
    user = await bot.get_users(int(userid))
    tz = pytz.timezone("Asia/Kolkata")
    now = datetime.now(tz)
    current_time = time(now.hour, now.minute, now.second)
    today = date.today()
    status = await get_verify_status(user.id)
    if not status:
        return False
    try:
        exp_date = datetime.strptime(status["date"], "%Y-%m-%d").date()
        exp_time = datetime.strptime(status["time"], "%H:%M:%S").time()
    except Exception as e:
        logger.error(f"Invalid verification time format: {e}")
        return False
    if exp_date < today or (exp_date == today and exp_time < current_time):
        return False
    return True