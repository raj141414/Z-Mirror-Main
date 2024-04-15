from aiofiles.os import path as aiopath, makedirs
from aioshutil import move as aiomove
from os import path as ospath
from pyrogram.filters import command
from pyrogram.handlers import MessageHandler
from pyrogram.types import Message
from random import SystemRandom
from string import ascii_letters, digits

from bot import bot, config_dict, download_dict, download_dict_lock
from bot.helper.ext_utils.bot_utils import new_task
from bot.helper.ext_utils.fs_utils import get_path_size
from bot.helper.listeners.tasks_listener import MirrorLeechListener
from bot.helper.mirror_utils.status_utils.local_status import LocalStatus
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.message_utils import sendMessage, sendStatusMessage


@new_task
async def _upload(message: Message, isLeech=False):
    if len(message.command) > 1:
        file_ =  message.text.split(maxsplit=1)[1]
        if await aiopath.exists(file_):
            path = f'{config_dict["DOWNLOAD_DIR"]}{message.id}'
            name, size = ospath.basename(file_), await get_path_size(file_)
            await makedirs(path, exist_ok=True)
            await aiomove(file_, path)
            if username := message.from_user.username:
                tag = f"@{username}"
            else:
                tag = message.from_user.mention
            listener = MirrorLeechListener(message, isLeech=isLeech, tag=tag, upPath='gd')
            gid = ''.join(SystemRandom().choices(ascii_letters + digits, k=12))
            async with download_dict_lock:
                download_dict[listener.uid] = LocalStatus(name, size, gid, listener)
            await sendStatusMessage(message)
            await listener.onDownloadComplete()
        else:
            await sendMessage(message, f'{file_} does not exist!')
    else:
        await sendMessage(message, 'Send command along with file path!')


async def mirror_upload(_, message: Message):
    _upload(message)


async def leech_upload(_, message: Message):
    _upload(message, True)


bot.add_handler(MessageHandler(mirror_upload, filters=command(BotCommands.MLocalUploadCommand) & CustomFilters.authorized))
bot.add_handler(MessageHandler(leech_upload, filters=command(BotCommands.LLocalUploadCommand) & CustomFilters.authorized))
