import aiohttp
import asyncio
from typing import List
from pathlib import Path
from argparse import Namespace
from urllib.request import getproxies

from .util.stream import Stream
from .extractors.hls.parser import Parser as hls_parser


class Extractor:
    '''
    请求DASH/HLS链接内容，也就是下载元数据
    或者读取含有元数据的文件
    或者读取含有多个元数据文件的文件夹
    最终得到一个Stream（流）对象供Downloader（下载器）下载
    '''
    def __init__(self, args: Namespace):
        self.args = args
        self.proxies = getproxies()

    def fetch_metadata(self, uri: str):
        '''
        从链接/文件/文件夹等加载内容 解析metadata
        '''
        if uri.startswith('http://') or uri.startswith('https://') or uri.startswith('ftp://'):
            loop = asyncio.get_event_loop()
            return self.raw2streams('url', uri, loop.run_until_complete(self.fetch(uri)))
        illegal_symbols = ["\\", "/", ":", "：", "*", "?", "\"", "<", ">", "|", "\r", "\n", "\t"]
        is_illegal_path = True
        for illegal_symbol in illegal_symbols:
            if illegal_symbol in uri:
                is_illegal_path = False
                break
        if is_illegal_path is False:
            return
        if Path(uri).exists() is False:
            return
        if Path(uri).is_file():
            return self.raw2streams('path', uri, Path(uri).read_text(encoding='utf-8'))
        if Path(uri).is_dir() is False:
            return
        streams = []
        for path in Path(uri).iterdir():
            _streams = self.raw2streams('path', path.name, path.read_text(encoding='utf-8'))
            if _streams is None:
                continue
            streams.extend(_streams)
        return streams

    async def fetch(self, url: str) -> str:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                return await response.text(encoding='utf-8')

    def raw2streams(self, uri_type: str, uri: str, content: str) -> List[Stream]:
        '''
        解析解码后的返回结果
        '''
        if not content:
            return []
        if content.startswith('#EXTM3U'):
            return self.parse_as_hls(uri_type, uri, content)
        elif '<MPD' in content and '</MPD>' in content:
            return self.parse_as_dash(uri, content)
        else:
            return []

    def parse_as_hls(self, uri_type: str, uri: str, content: str) -> List[Stream]:
        _streams = hls_parser(self.args, uri_type).parse(uri, content)
        streams = []
        for stream in _streams:
            # 针对master类型加载详细内容
            if stream.tag != '#EXT-X-STREAM-INF' and stream.tag != '#EXT-X-MEDIA':
                streams.append(stream)
                continue
            new_streams = self.fetch_metadata(stream.origin_url)
            if new_streams is None:
                continue
            streams.extend(new_streams)
        # 在全部流解析完成后 再处理key
        for stream in streams:
            stream.try_fetch_key(self.args.b64key, self.args.hexiv)
        return streams

    def parse_as_dash(self, uri: str, content: str) -> List[Stream]:
        streams = []
        stream = Stream('dash')
        streams.append(stream)
        return streams