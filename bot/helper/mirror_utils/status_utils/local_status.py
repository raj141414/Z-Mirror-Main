from bot import LOGGER
from bot.helper.ext_utils.bot_utils import (get_readable_file_size, MirrorStatus)



class LocalStatus:
    def __init__(self, name, size, gid, listener):
        self.__name = name
        self.__gid = gid
        self.__size = size
        self.__listener = listener
        self.message = listener.message
        self.extra_details = self.__listener.extra_details
        self.engine = 'Local'

    def gid(self):
        return self.__gid

    def progress(self):
        return '0%'

    def speed(self):
        return '0/s'

    def name(self):
        return self.__name

    def size(self):
        return get_readable_file_size(self.__size)

    def eta(self):
        return '-'

    def status(self):
        return MirrorStatus.STATUS_LOCAL

    def download(self):
        return self

    async def cancel_download(self):
        LOGGER.info(f'Cancelling Local Upload: {self.__name}')
        self.__listener.suproc = 'cancelled'
        await self.__listener.onUploadError('Local upload stopped by user!')
