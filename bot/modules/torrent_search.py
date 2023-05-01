from html import escape
from urllib.parse import quote

from aiohttp import ClientSession
from pyrogram.filters import command, regex
from pyrogram.handlers import CallbackQueryHandler, MessageHandler

from bot import LOGGER, bot, config_dict, get_client
from bot.helper.ext_utils.bot_utils import (checking_access,
                                            get_readable_file_size, new_task,
                                            sync_to_async)
from bot.helper.ext_utils.telegraph_helper import telegraph
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.message_utils import (anno_checker, deleteMessage,
                                                      editMessage, isAdmin,
                                                      auto_delete_message,
                                                      request_limiter,
                                                      sendMessage)

PLUGINS = []
SITES = None
TELEGRAPH_LIMIT = 300


async def initiate_search_tools():
    qbclient = await sync_to_async(get_client)
    qb_plugins = await sync_to_async(qbclient.search_plugins)
    if SEARCH_PLUGINS := config_dict['SEARCH_PLUGINS']:
        globals()['PLUGINS'] = []
        src_plugins = eval(SEARCH_PLUGINS)
        if qb_plugins:
            names = [plugin['name'] for plugin in qb_plugins]
            await sync_to_async(qbclient.search_uninstall_plugin, names=names)
        await sync_to_async(qbclient.search_install_plugin, src_plugins)
    elif qb_plugins:
        for plugin in qb_plugins:
            await sync_to_async(qbclient.search_uninstall_plugin, names=plugin['name'])
        globals()['PLUGINS'] = []
    await sync_to_async(qbclient.auth_log_out)

    if SEARCH_API_LINK := config_dict['SEARCH_API_LINK']:
        global SITES
        try:
            async with ClientSession(trust_env=True) as c:
                async with c.get(f'{SEARCH_API_LINK}/api/v1/sites') as res:
                    data = await res.json()
            SITES = {str(site): str(site).capitalize()
                     for site in data['supported_sites']}
            SITES['all'] = 'All'
        except Exception as e:
            LOGGER.error(
                f"{e} Can't fetching sites from SEARCH_API_LINK make sure use latest version of API")
            SITES = None


async def __search(key, site, message, method):
    if method.startswith('api'):
        SEARCH_API_LINK = config_dict['SEARCH_API_LINK']
        SEARCH_LIMIT = config_dict['SEARCH_LIMIT']
        if method == 'apisearch':
            LOGGER.info(f"API Searching: {key} from {site}")
            if site == 'all':
                api = f"{SEARCH_API_LINK}/api/v1/all/search?query={key}&limit={SEARCH_LIMIT}"
            else:
                api = f"{SEARCH_API_LINK}/api/v1/search?site={site}&query={key}&limit={SEARCH_LIMIT}"
        elif method == 'apitrend':
            LOGGER.info(f"API Trending from {site}")
            if site == 'all':
                api = f"{SEARCH_API_LINK}/api/v1/all/trending?limit={SEARCH_LIMIT}"
            else:
                api = f"{SEARCH_API_LINK}/api/v1/trending?site={site}&limit={SEARCH_LIMIT}"
        elif method == 'apirecent':
            LOGGER.info(f"API Recent from {site}")
            if site == 'all':
                api = f"{SEARCH_API_LINK}/api/v1/all/recent?limit={SEARCH_LIMIT}"
            else:
                api = f"{SEARCH_API_LINK}/api/v1/recent?site={site}&limit={SEARCH_LIMIT}"
        try:
            async with ClientSession(trust_env=True) as c:
                async with c.get(api) as res:
                    search_results = await res.json()
            if 'error' in search_results or search_results['total'] == 0:
                await editMessage(message, f"No result found for <i>{key}</i>\nTorrent Site:- <i>{SITES.get(site)}</i>")
                if config_dict['DELETE_LINKS']:
                    await deleteMessage(message.reply_to_message)
                return
            msg = f"<b>Found {min(search_results['total'], TELEGRAPH_LIMIT)}</b>"
            if method == 'apitrend':
                msg += f" <b>trending result(s)\nTorrent Site:- <i>{SITES.get(site)}</i></b>"
            elif method == 'apirecent':
                msg += f" <b>recent result(s)\nTorrent Site:- <i>{SITES.get(site)}</i></b>"
            else:
                msg += f" <b>result(s) for <i>{key}</i>\nTorrent Site:- <i>{SITES.get(site)}</i></b>"
            search_results = search_results['data']
        except Exception as e:
            await editMessage(message, str(e))
            if config_dict['DELETE_LINKS']:
                await deleteMessage(message.reply_to_message)
            return
    else:
        LOGGER.info(f"PLUGINS Searching: {key} from {site}")
        client = await sync_to_async(get_client)
        search = await sync_to_async(client.search_start, pattern=key, plugins=site, category='all')
        search_id = search.id
        while True:
            result_status = await sync_to_async(client.search_status, search_id=search_id)
            status = result_status[0].status
            if status != 'Running':
                break
        dict_search_results = await sync_to_async(client.search_results, search_id=search_id, limit=TELEGRAPH_LIMIT)
        search_results = dict_search_results.results
        total_results = dict_search_results.total
        if total_results == 0:
            await editMessage(message, f"No result found for <i>{key}</i>\nTorrent Site:- <i>{site.capitalize()}</i>")
            if config_dict['DELETE_LINKS']:
                await deleteMessage(message.reply_to_message)
            return
        msg = f"<b>Found {min(total_results, TELEGRAPH_LIMIT)}</b>"
        msg += f" <b>result(s) for <i>{key}</i>\nTorrent Site:- <i>{site.capitalize()}</i></b>"
        await sync_to_async(client.search_delete, search_id=search_id)
        await sync_to_async(client.auth_log_out)
    link = await __getResult(search_results, key, message, method)
    buttons = ButtonMaker()
    buttons.ubutton("🔎 VIEW", link)
    button = buttons.build_menu(1)
    await editMessage(message, msg, button)
    if config_dict['DELETE_LINKS']:
        await deleteMessage(message.reply_to_message)


async def __getResult(search_results, key, message, method):
    telegraph_content = []
    if method == 'apirecent':
        msg = "<h4>API Recent Results</h4>"
    elif method == 'apisearch':
        msg = f"<h4>API Search Result(s) For {key}</h4>"
    elif method == 'apitrend':
        msg = "<h4>API Trending Results</h4>"
    else:
        msg = f"<h4>PLUGINS Search Result(s) For {key}</h4>"
    for index, result in enumerate(search_results, start=1):
        if method.startswith('api'):
            try:
                if 'name' in result.keys():
                    msg += f"<code><a href='{result['url']}'>{escape(result['name'])}</a></code><br>"
                if 'torrents' in result.keys():
                    for subres in result['torrents']:
                        msg += f"<b>Quality: </b>{subres['quality']} | <b>Type: </b>{subres['type']} | "
                        msg += f"<b>Size: </b>{subres['size']}<br>"
                        if 'torrent' in subres.keys():
                            msg += f"<a href='{subres['torrent']}'>Direct Link</a><br>"
                        elif 'magnet' in subres.keys():
                            msg += "<b>Share Magnet to</b> "
                            msg += f"<a href='http://t.me/share/url?url={subres['magnet']}'>Telegram</a><br>"
                    msg += '<br>'
                else:
                    msg += f"<b>Size: </b>{result['size']}<br>"
                    try:
                        msg += f"<b>Seeders: </b>{result['seeders']} | <b>Leechers: </b>{result['leechers']}<br>"
                    except:
                        pass
                    if 'torrent' in result.keys():
                        msg += f"<a href='{result['torrent']}'>Direct Link</a><br><br>"
                    elif 'magnet' in result.keys():
                        msg += "<b>Share Magnet to</b> "
                        msg += f"<a href='http://t.me/share/url?url={quote(result['magnet'])}'>Telegram</a><br><br>"
                    else:
                        msg += '<br>'
            except:
                continue
        else:
            msg += f"<a href='{result.descrLink}'>{escape(result.fileName)}</a><br>"
            msg += f"<b>Size: </b>{get_readable_file_size(result.fileSize)}<br>"
            msg += f"<b>Seeders: </b>{result.nbSeeders} | <b>Leechers: </b>{result.nbLeechers}<br>"
            link = result.fileUrl
            if link.startswith('magnet:'):
                msg += f"<b>Share Magnet to</b> <a href='http://t.me/share/url?url={quote(link)}'>Telegram</a><br><br>"
            else:
                msg += f"<a href='{link}'>Direct Link</a><br><br>"

        if len(msg.encode('utf-8')) > 39000:
            telegraph_content.append(msg)
            msg = ""

        if index == TELEGRAPH_LIMIT:
            break

    if msg != "":
        telegraph_content.append(msg)

    await editMessage(message, f"<b>Creating</b> {len(telegraph_content)} <b>Telegraph pages.</b>")
    path = [(await telegraph.create_page(title='Z Torrent Search',
                                         content=content))["path"] for content in telegraph_content]
    if len(path) > 1:
        await editMessage(message, f"<b>Editing</b> {len(telegraph_content)} <b>Telegraph pages.</b>")
        await telegraph.edit_telegraph(path, telegraph_content)
    return f"https://graph.org/{path[0]}"


def __api_buttons(user_id, method):
    buttons = ButtonMaker()
    for data, name in SITES.items():
        buttons.ibutton(name, f"torser {user_id} {data} {method}")
    buttons.ibutton("Cancel", f"torser {user_id} cancel")
    return buttons.build_menu(2)


async def __plugin_buttons(user_id):
    buttons = ButtonMaker()
    if not PLUGINS:
        qbclient = await sync_to_async(get_client)
        pl = await sync_to_async(qbclient.search_plugins)
        for name in pl:
            PLUGINS.append(name['name'])
        await sync_to_async(qbclient.auth_log_out)
    for siteName in PLUGINS:
        buttons.ibutton(siteName.capitalize(),
                        f"torser {user_id} {siteName} plugin")
    buttons.ibutton('All', f"torser {user_id} all plugin")
    buttons.ibutton("Cancel", f"torser {user_id} cancel")
    return buttons.build_menu(2)


async def torrentSearch(client, message):
    if not message.from_user:
        message.from_user = await anno_checker(message)
    if not message.from_user:
        return
    if sender_chat := message.sender_chat:
        tag = sender_chat.title
    elif username := message.from_user.username:
        tag = f"@{username}"
    else:
        tag = message.from_user.mention
    if reply_to := message.reply_to_message:
        if len(link) == 0:
            link = reply_to.text.split('\n', 1)[0].strip()
        if sender_chat := reply_to.sender_chat:
            tag = sender_chat.title
        elif not reply_to.from_user.is_bot:
            if username := reply_to.from_user.username:
                tag = f"@{username}"
            else:
                tag = reply_to.from_user.mention
    user_id = message.from_user.id
    buttons = ButtonMaker()
    if not await isAdmin(message, user_id):
        if await request_limiter(message):
            return
        if message.chat.type != message.chat.type.PRIVATE:
            msg, buttons = checking_access(user_id, buttons)
            if msg is not None:
                msg += f'\n\n<b>User</b>: {tag}'
                msg += f'\n<b>Timeout</b>: {config_dict["AUTO_DELETE_MESSAGE_DURATION"]}'
                reply_message = await sendMessage(message, msg, buttons.build_menu(1))
                await auto_delete_message(message, reply_message)
                return
    key = message.text.split()
    SEARCH_PLUGINS = config_dict['SEARCH_PLUGINS']
    if SITES is None and not SEARCH_PLUGINS:
        await sendMessage(message, "No API link or search PLUGINS added for this function")
    elif len(key) == 1 and SITES is None:
        await sendMessage(message, "Send a search key along with command")
    elif len(key) == 1:
        buttons.ibutton('Trending', f"torser {user_id} apitrend")
        buttons.ibutton('Recent', f"torser {user_id} apirecent")
        buttons.ibutton("Cancel", f"torser {user_id} cancel")
        button = buttons.build_menu(2)
        await sendMessage(message, "Send a search key along with command", button)
    elif SITES is not None and SEARCH_PLUGINS:
        buttons.ibutton('Api', f"torser {user_id} apisearch")
        buttons.ibutton('Plugins', f"torser {user_id} plugin")
        buttons.ibutton("Cancel", f"torser {user_id} cancel")
        button = buttons.build_menu(2)
        await sendMessage(message, 'Choose tool to search:', button)
    elif SITES is not None:
        button = __api_buttons(user_id, "apisearch")
        await sendMessage(message, 'Choose site to search | API:', button)
    else:
        button = await __plugin_buttons(user_id)
        await sendMessage(message, 'Choose site to search | Plugins:', button)


@new_task
async def torrentSearchUpdate(client, query):
    user_id = query.from_user.id
    message = query.message
    key = message.reply_to_message.text.split(maxsplit=1)
    key = key[1].strip() if len(key) > 1 else None
    data = query.data.split()
    if user_id != int(data[1]):
        await query.answer("Not Yours!", show_alert=True)
    elif data[2].startswith('api'):
        await query.answer()
        button = __api_buttons(user_id, data[2])
        await editMessage(message, 'Choose site:', button)
    elif data[2] == 'plugin':
        await query.answer()
        button = await __plugin_buttons(user_id)
        await editMessage(message, 'Choose site:', button)
    elif data[2] != "cancel":
        await query.answer()
        site = data[2]
        method = data[3]
        if method.startswith('api'):
            if key is None:
                if method == 'apirecent':
                    endpoint = 'Recent'
                elif method == 'apitrend':
                    endpoint = 'Trending'
                await editMessage(message, f"<b>Listing {endpoint} Items...\nTorrent Site:- <i>{SITES.get(site)}</i></b>")
            else:
                await editMessage(message, f"<b>Searching for <i>{key}</i>\nTorrent Site:- <i>{SITES.get(site)}</i></b>")
        else:
            await editMessage(message, f"<b>Searching for <i>{key}</i>\nTorrent Site:- <i>{site.capitalize()}</i></b>")
        await __search(key, site, message, method)
    else:
        await query.answer()
        await editMessage(message, "Search has been canceled!")


bot.add_handler(MessageHandler(torrentSearch, filters=command(
    BotCommands.SearchCommand) & CustomFilters.authorized))
bot.add_handler(CallbackQueryHandler(
    torrentSearchUpdate, filters=regex("^torser")))
