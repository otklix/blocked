#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import json
import asyncio
import tempfile
import zipfile
from urllib.parse import quote

import requests
from aiohttp import web
import yt_dlp
from mutagen.id3 import ID3, TIT2, TPE1

# ========== КОНФИГ ==========
BOT_TOKEN = os.getenv('BOT_TOKEN', '')
WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = 8080

# ========== ХРАНИЛИЩЕ ==========
user_data = {}

# ========== ФУНКЦИИ ПАРСИНГА ==========

def extract_playlist_info(url: str) -> dict:
    """Парсит плейлист Яндекс Музыки без авторизации"""
    clean_url = re.sub(r'\?.*$', '', url)
    
    match = re.search(r'playlist[/](\d+)', clean_url)
    if not match:
        match = re.search(r'playlists[/](\d+)', clean_url)
    
    if not match:
        raise ValueError("Не удалось найти ID плейлиста")
    
    playlist_id = match.group(1)
    api_url = f"https://api.music.yandex.net/playlists/{playlist_id}"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json',
    }
    
    response = requests.get(api_url, headers=headers, timeout=10)
    response.raise_for_status()
    data = response.json()
    
    if 'playlist' not in data or 'tracks' not in data['playlist']:
        raise ValueError("Плейлист не найден или приватный")
    
    tracks = []
    for item in data['playlist']['tracks']:
        track = item.get('track', {})
        if track:
            title = track.get('title', 'Unknown')
            artists = track.get('artists', [])
            artist = artists[0].get('name', 'Unknown') if artists else 'Unknown'
            tracks.append({'title': title, 'artist': artist})
    
    if not tracks:
        raise ValueError("В плейлисте нет треков")
    
    return {
        'id': playlist_id,
        'title': data['playlist'].get('title', 'Без названия'),
        'tracks': tracks,
        'count': len(tracks)
    }

def search_vk_music(query: str) -> str:
    """Ищет трек на VK Музыке"""
    try:
        encoded_query = quote(query)
        search_url = f"https://vk.com/api.php?method=audio.search&q={encoded_query}&count=1"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(search_url, headers=headers, timeout=10)
        data = response.json()
        if 'response' in data and data['response']:
            items = data['response'].get('items', [])
            if items:
                return items[0].get('url')
        return None
    except:
        return None

def download_from_vk(vk_url: str, output_path: str) -> str:
    """Скачивает аудио с VK"""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    response = requests.get(vk_url, headers=headers, timeout=30, stream=True)
    response.raise_for_status()
    with open(output_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    return output_path

def download_from_youtube(query: str, output_path: str) -> str:
    """Скачивает аудио с YouTube"""
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'outtmpl': output_path.replace('.mp3', ''),
        'quiet': True,
        'no_warnings': True,
        'default_search': 'ytsearch',
        'noplaylist': True,
        'max_downloads': 1,
        'ignoreerrors': True,
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(f"ytsearch:{query}", download=True)
        if not info or 'entries' not in info or not info['entries']:
            raise Exception("Не найдено")
        
        base_name = output_path.replace('.mp3', '')
        mp3_file = output_path
        possible_files = [output_path, f"{base_name}.mp3", f"{base_name}.webm"]
        for f in possible_files:
            if os.path.exists(f):
                mp3_file = f
                break
        
        if not os.path.exists(mp3_file):
            dir_path = os.path.dirname(base_name)
            base_name_only = os.path.basename(base_name)
            for f in os.listdir(dir_path):
                if f.startswith(base_name_only) and (f.endswith('.mp3') or f.endswith('.webm')):
                    mp3_file = os.path.join(dir_path, f)
                    break
        
        if not os.path.exists(mp3_file):
            raise Exception("Файл не создался")
        
        return mp3_file

def download_track(track: dict, temp_dir: str) -> str:
    """Скачивает трек с VK или YouTube"""
    search_query = f"{track['artist']} {track['title']}"
    file_name = f"{track['artist']} - {track['title']}.mp3"
    file_name = re.sub(r'[<>:"/\\|?*]', '_', file_name)
    file_path = os.path.join(temp_dir, file_name)
    
    vk_url = search_vk_music(search_query)
    if vk_url:
        try:
            download_from_vk(vk_url, file_path)
            return file_path
        except:
            pass
    
    downloaded = download_from_youtube(search_query, file_path)
    return downloaded

# ========== HTTP API ==========

async def webapp_handler(request):
    """Отдаёт HTML страницу мини-приложения"""
    html_path = os.path.join(os.path.dirname(__file__), 'index.html')
    try:
        with open(html_path, 'r', encoding='utf-8') as f:
            html = f.read()
        return web.Response(text=html, content_type='text/html')
    except:
        return web.Response(text="Ошибка загрузки приложения", status=500)

async def webapp_api(request):
    """API для обработки запросов из мини-приложения"""
    try:
        data = await request.json()
        action = data.get('action')
        user_id = data.get('user_id')
        
        if action == 'parse_playlist':
            url = data.get('url')
            try:
                playlist = extract_playlist_info(url)
                user_data[user_id] = {
                    'playlist': playlist,
                    'tracks': playlist['tracks'],
                    'status': 'parsed'
                }
                return web.json_response({
                    'success': True,
                    'playlist': playlist
                })
            except Exception as e:
                return web.json_response({
                    'success': False,
                    'error': str(e)
                })
        
        elif action == 'search_track':
            query = data.get('query', '')
            try:
                vk_url = search_vk_music(query)
                if vk_url:
                    return web.json_response({
                        'success': True,
                        'url': vk_url
                    })
                else:
                    return web.json_response({
                        'success': False,
                        'error': 'Трек не найден'
                    })
            except Exception as e:
                return web.json_response({
                    'success': False,
                    'error': str(e)
                })
        
        elif action == 'download_track':
            if user_id not in user_data:
                return web.json_response({
                    'success': False,
                    'error': 'Плейлист не найден'
                })
            
            index = data.get('index', 0)
            track = user_data[user_id]['tracks'][index]
            
            with tempfile.TemporaryDirectory() as temp_dir:
                try:
                    file_path = download_track(track, temp_dir)
                    return web.json_response({
                        'success': True,
                        'track': track,
                        'message': f'Скачан: {track["artist"]} - {track["title"]}'
                    })
                except Exception as e:
                    return web.json_response({
                        'success': False,
                        'error': str(e)
                    })
        
        return web.json_response({'success': False, 'error': 'Неизвестное действие'})
    
    except Exception as e:
        return web.json_response({
            'success': False,
            'error': str(e)
        })

# ========== ЗАПУСК ==========

async def main():
    if not BOT_TOKEN:
        print("❌ Ошибка: BOT_TOKEN не найден!")
        print("Добавь секрет BOT_TOKEN в настройках GitHub")
        return
    
    # Создаём папки
    os.makedirs('downloads', exist_ok=True)
    
    # Запускаем веб-сервер
    app = web.Application()
    app.router.add_get('/', webapp_handler)
    app.router.add_post('/api', webapp_api)
    app.router.add_options('/api', lambda req: web.Response())
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=WEBAPP_HOST, port=WEBAPP_PORT)
    await site.start()
    
    print(f"🚀 Сервер запущен на порту {WEBAPP_PORT}")
    print("=" * 50)
    print("⚠️  GitHub Actions не может принимать внешние запросы!")
    print("📌 Используй Ngrok или Railway для публичного доступа")
    print("=" * 50)
    
    # Бесконечный цикл
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())