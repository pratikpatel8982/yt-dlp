import re

from yt_dlp.extractor.common import InfoExtractor
from yt_dlp.utils import (
    ExtractorError,
    get_element_by_class,
)

data_id_to_number = {}

def _get_elements_by_tag_and_attrib(html, tag=None, attribute=None, value=None, escape_value=True):
    """Return the content of the tag with the specified attribute in the passed HTML document"""

    if tag is None:
        tag = '[a-zA-Z0-9:._-]+'
    if attribute is None:
        attribute = ''
    else:
        attribute = rf'\s+(?P<attribute>{re.escape(attribute)})'
    if value is None:
        value = ''
    else:
        value = re.escape(value) if escape_value else value
        value = f'=[\'"]?(?P<value>{value})[\'"]?'

    retlist = []
    for m in re.finditer(rf'''(?xs)
        <(?P<tag>{tag})
         (?:\s+[a-zA-Z0-9:._-]+(?:=[a-zA-Z0-9:._-]*|="[^"]*"|='[^']*'|))*?
         {attribute}{value}
         (?:\s+[a-zA-Z0-9:._-]+(?:=[a-zA-Z0-9:._-]*|="[^"]*"|='[^']*'|))*?
        \s*>
        (?P<content>.*?)
        </\1>
    ''', html):
        retlist.append(m)

    return retlist


def _get_element_by_tag_and_attrib(html, tag=None, attribute=None, value=None, escape_value=True):
    retval = _get_elements_by_tag_and_attrib(html, tag, attribute, value, escape_value)
    return retval[0] if retval else None



def _get_title_for_single_episode(self, slug, playlist_id, episode_id, url):
    data=_extract_playlist(self, slug, playlist_id, url)
    number=int(data_id_to_number.get(episode_id))
    for entry in data['entries']:
        if entry['id'] == episode_id:
            title=entry['title']
            return title,number
    return None,None




def _get_anime_title(self, slug, playlist_id):
    webpage = self._download_webpage(f'https://hianime.to/{slug}-{playlist_id}', playlist_id)
    return get_element_by_class('film-name dynamic-name',webpage)




def _extract_playlist(self, slug, playlist_id, url):

    animeTitle =  _get_anime_title(self, slug, playlist_id)
    playlist_url = f'https://hianime.to/ajax/v2/episode/list/{playlist_id}'
    playlist_data = self._download_json(playlist_url, playlist_id)
    episodes = _get_elements_by_tag_and_attrib(playlist_data['html'], tag='a', attribute='class', value='ssl-item  ep-item')

    entries = []
    for episode in episodes:
        # Get the entire match string
        episode_html = episode.group(0)

        # Extract the required attributes using re.search
        title_match = re.search(r'title="([^"]+)"', episode_html)
        data_number_match = re.search(r'data-number="([^"]+)"', episode_html)
        data_id_match = re.search(r'data-id="([^"]+)"', episode_html)
        href_match = re.search(r'href="([^"]+)"', episode_html)

        title = title_match.group(1) if title_match else None
        data_number = data_number_match.group(1) if data_number_match else None
        data_id = data_id_match.group(1) if data_id_match else None
        href = href_match.group(1) if href_match else None

        if data_id and data_number:
            data_id_to_number[data_id] = data_number

        # Create a dictionary for each episode
        entries.append(self.url_result(
            f'https://hianime.to{href}',
            ie=HiAnimeIE.ie_key(),
            video_id=data_id,
            video_title=title,
        ))

    return self.playlist_result(entries, playlist_id, animeTitle)

def _extract_episode(self, slug, playlist_id, episode_id, url):
    servers_url = f'https://hianime.to/ajax/v2/episode/servers?episodeId={episode_id}'
    servers_data = self._download_json(servers_url, episode_id)

    formats = []
    subtitles = {}

    for server_type in ['sub', 'dub']:
        server_items = _get_elements_by_tag_and_attrib(servers_data['html'], tag='div', attribute='data-type', value=f'{server_type}', escape_value=False)

        server_id = None
        if server_items:
            server_html = server_items[0].group(0)
            data_id_match = re.search(r'data-id="([^"]+)"', server_html)
            if data_id_match:
                server_id = data_id_match.group(1)

        if server_id:
            sources_url = f'https://hianime.to/ajax/v2/episode/sources?id={server_id}'
            sources_data = self._download_json(sources_url, server_id)
            link = sources_data.get('link')
            if link:
                # Extract video id from the link URL
                sources_id_match = re.search(r'/embed-2/[^/]+/([^?]+)\?', link)
                if sources_id_match:
                    sources_id = sources_id_match.group(1)

                    video_url = f'https://megacloud.tv/embed-2/ajax/e-1/getSources?id={sources_id}'
                    video_data = self._download_json(video_url, sources_id)


                    sources = video_data.get('sources', [])
                    tracks = video_data.get('tracks', [])
                    language = 'Japanese' if server_type == 'sub' else 'English'
                    for source in sources:
                        file_url = source.get('file')
                        if file_url:
                            if file_url.endswith('.m3u8'):
                                extracted_formats = self._extract_m3u8_formats(
                                    file_url, episode_id, 'mp4', entry_protocol='m3u8_native',
                                    m3u8_id=f'{server_type}', fatal=False,
                                )
                                for f in extracted_formats:
                                    f['language'] = language
                                formats.extend(extracted_formats)

                    # Process subtitle tracks
                    tracks = video_data.get('tracks', [])
                    for track in tracks:
                        if track.get('kind') == 'captions':
                            file_url = track.get('file')
                            label = server_type
                            if file_url:
                                if label not in subtitles:
                                    subtitles[label] = []  # Initialize list if not exists
                                subtitles[label].append({
                                    'ext': 'vtt',
                                    'url': file_url,
                                })

    title, episode_number = _get_title_for_single_episode(self, slug, playlist_id, episode_id, url)
    return {
        'id': episode_id,
        'title': title,
        'formats': formats,
        'subtitles': subtitles,
        'series': _get_anime_title(self, slug, playlist_id),
        'series_id': playlist_id,
        'episode': title,
        'episode_number': episode_number,
        'episode_id': episode_id,
    }



class HiAnimeIE(InfoExtractor):
    _VALID_URL = r'https?://hianime\.to/(?:watch/)?(?P<slug>[^/?]+)(?:-\d+)?-(?P<playlist_id>\d+)(?:\?ep=(?P<episode_id>\d+))?$'

    _TESTS = [
        {
            'url': 'https://hianime.to/demon-slayer-kimetsu-no-yaiba-hashira-training-arc-19107',
            'info_dict': {
                'id': '19107',
                'title': 'Demon Slayer: Kimetsu no Yaiba Hashira Training Arc',
            },
            'playlist_count': 8,
        },
        {
            'url': 'https://hianime.to/watch/demon-slayer-kimetsu-no-yaiba-hashira-training-arc-19107?ep=124260',
            'info_dict': {
                'id': '124260',
                'title': 'To Defeat Muzan Kibutsuji',
                'ext': 'mp4',
                'series': 'Demon Slayer: Kimetsu no Yaiba Hashira Training Arc',
                'series_id': '19107',
                'episode': 'To Defeat Muzan Kibutsuji',
                'episode_number': 1,
                'episode_id': '124260',
            },
        },
        {
            'url': 'https://hianime.to/the-eminence-in-shadow-17473',
            'info_dict': {
                'id': '17473',
                'title': 'The Eminence in Shadow',
            },
            'playlist_count': 20,
        },
        {
            'url': 'https://hianime.to/watch/the-eminence-in-shadow-17473?ep=94440',
            'info_dict': {
                'id': '94440',
                'title': 'The Hated Classmate',
                'ext': 'mp4',
                'series': 'The Eminence in Shadow',
                'series_id': '17473',
                'episode': 'The Hated Classmate',
                'episode_number': 1,
                'episode_id': '94440',
            },
        },
    ]

    def _real_extract(self, url):
        mobj = self._match_valid_url(url)
        playlist_id = mobj.group('playlist_id')
        episode_id = mobj.group('episode_id')
        slug = mobj.group('slug')
        if episode_id:
            return _extract_episode(self, slug, playlist_id, episode_id,url)
        elif playlist_id:
            return _extract_playlist(self, slug, playlist_id, url)
        else:
            raise ExtractorError('Unsupported URL format')
