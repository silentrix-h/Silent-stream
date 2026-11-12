#!/usr/bin/env python
import os
import re
import sys
import json
import base64
import tempfile
import subprocess
from urllib.parse import urlparse, parse_qs, unquote, quote
import requests
from bs4 import BeautifulSoup
import http.server
import socketserver
import threading

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

server_instance = None

def start_local_proxy(remote_url, referer_url, port=8888):
    """Proxy lokal sementara di 127.0.0.1 agar pemutar HP bisa memutar video CDN terproteksi."""
    global server_instance
    if server_instance:
        try:
            server_instance.shutdown()
        except Exception:
            pass

    class ProxyHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            req_headers = {
                "User-Agent": HEADERS["User-Agent"],
                "Referer": referer_url if referer_url else remote_url
            }
            if "Range" in self.headers:
                req_headers["Range"] = self.headers["Range"]

            try:
                resp = requests.get(remote_url, headers=req_headers, stream=True, timeout=15)
                self.send_response(resp.status_code)
                for k, v in resp.headers.items():
                    if k.lower() in ["content-type", "content-length", "accept-ranges", "content-range"]:
                        self.send_header(k, v)
                self.end_headers()

                for chunk in resp.iter_content(chunk_size=64 * 1024):
                    if chunk:
                        self.wfile.write(chunk)
            except Exception:
                pass

        def log_message(self, format, *args):
            return

    try:
        class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
            daemon_threads = True
            allow_reuse_address = True

        server_instance = ThreadedTCPServer(('127.0.0.1', port), ProxyHandler)
        t = threading.Thread(target=server_instance.serve_forever)
        t.daemon = True
        t.start()
        return f"http://127.0.0.1:{port}"
    except Exception:
        return remote_url

def is_youtube(url):
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    return any(yt in domain for yt in ["youtube.com", "youtu.be", "music.youtube.com"])

def is_spotify(url):
    parsed = urlparse(url)
    return "spotify.com" in parsed.netloc.lower()

def extract_yt_video_id(url):
    parsed = urlparse(url)
    if "youtu.be" in parsed.netloc.lower():
        return parsed.path.lstrip('/').split('/')[0]
    qs = parse_qs(parsed.query)
    if "v" in qs:
        return qs["v"][0]
    return None

def search_yt_video_id(query):
    try:
        cmd = ["yt-dlp", f"ytsearch1:{query}", "--print", "id", "--no-warnings"]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=12)
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip().split('\n')[0]
    except Exception:
        pass
    return None

def is_episode_url(url):
    url_lower = url.lower()
    patterns = [r'/episode/', r'-episode-', r'-ep-\d+', r'/ep-\d+', r'episode-\d+', r'eps-\d+']
    for p in patterns:
        if re.search(p, url_lower):
            return True
    return False

def normalize_spotify_url(url):
    """Membersihkan parameter ?si= dan prefix regional /intl-xx/ agar URL Spotify standar."""
    clean = url.split('?')[0]
    clean = re.sub(r'/intl-[a-zA-Z-]+/', '/', clean)
    return clean

def parse_spotify_url(spotify_url):
    """Mengambil daftar lagu dari Spotify (mendukung /intl-id/, single track, album, & playlist)."""
    print("[*] Membaca informasi lagu dari Spotify...")
    tracks = []
    clean_url = normalize_spotify_url(spotify_url)

    try:
        # 1. Coba melalui Spotify Embed (setelah /intl-id/ dibersihkan)
        embed_url = clean_url.replace("open.spotify.com/", "open.spotify.com/embed/")
        res = requests.get(embed_url, headers=HEADERS, timeout=12)
        soup = BeautifulSoup(res.text, 'html.parser')

        next_data = soup.find('script', id='__NEXT_DATA__')
        if next_data and next_data.string:
            data = json.loads(next_data.string)
            entity = data.get('props', {}).get('pageProps', {}).get('state', {}).get('data', {}).get('entity', {})
            
            # Jika berupa playlist / album
            track_list = entity.get('trackList', [])
            for item in track_list:
                title = item.get('title', '').strip()
                subtitle = item.get('subtitle', '').strip()
                if title:
                    tracks.append(f"{title} - {subtitle}" if subtitle else title)

            # Jika berupa single track di dalam entity
            if not tracks and entity.get('name'):
                t_name = entity.get('name', '').strip()
                artists = [a.get('name', '') for a in entity.get('artists', []) if a.get('name')]
                artist_str = ", ".join(artists)
                tracks.append(f"{t_name} - {artist_str}" if artist_str else t_name)

        # 2. Fallback via Endpoint Resmi oEmbed Spotify
        if not tracks:
            oembed_url = f"https://open.spotify.com/oembed?url={quote(clean_url)}"
            ores = requests.get(oembed_url, headers=HEADERS, timeout=10)
            if ores.status_code == 200:
                odata = ores.json()
                title = odata.get('title', '').strip()
                if title:
                    tracks.append(title)

        # 3. Fallback terakhir via <title> halaman HTML utama
        if not tracks:
            res_main = requests.get(clean_url, headers=HEADERS, timeout=12)
            soup_main = BeautifulSoup(res_main.text, 'html.parser')
            if soup_main.title and soup_main.title.string:
                # Biasanya format title: "Judul Lagu - song and lyrics by Nama Artis | Spotify"
                raw_title = soup_main.title.string.replace("| Spotify", "").strip()
                raw_title = re.sub(r'\s*-\s*song and lyrics by\s*', ' - ', raw_title, flags=re.IGNORECASE)
                raw_title = re.sub(r'\s*-\s*Single by\s*', ' - ', raw_title, flags=re.IGNORECASE)
                if raw_title and raw_title.lower() != "spotify":
                    tracks.append(raw_title)

    except Exception as e:
        print(f"[!] Gagal membaca data Spotify: {e}")

    return tracks

def build_m3u_from_tracks(tracks):
    fd, m3u_path = tempfile.mkstemp(suffix=".m3u", prefix="silent_spotify_")
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write("#EXTM3U\n")
        for query in tracks:
            f.write(f"#EXTINF:-1,{query}\n")
            f.write(f"ytdl://ytsearch1:{query}\n")
    return m3u_path

def play_audio_playlist(url, shuffle=False, auto_radio=True):
    mpv_cmd = [
        "mpv",
        "--no-video",
        "--ytdl-format=bestaudio/best",
        "--ytdl-raw-options=yes-playlist=",
        "--term-osd-bar"
    ]
    if shuffle:
        mpv_cmd.append("--shuffle")

    temp_m3u = None
    target_source = url

    if is_spotify(url):
        tracks = parse_spotify_url(url)
        if not tracks:
            print("[!] Lagu tidak ditemukan. Pastikan link Spotify valid & publik.\n")
            return

        if len(tracks) == 1 and auto_radio:
            print(f"[✓] Lagu ditemukan: '{tracks[0]}'")
            print("[*] Mengaktifkan Auto-Radio YouTube Music untuk lagu lanjutan...")
            vid_id = search_yt_video_id(tracks[0])
            if vid_id:
                target_source = f"https://www.youtube.com/watch?v={vid_id}&list=RD{vid_id}"
            else:
                temp_m3u = build_m3u_from_tracks(tracks)
                target_source = temp_m3u
        else:
            print(f"[✓] Berhasil memuat {len(tracks)} lagu dari Spotify!")
            temp_m3u = build_m3u_from_tracks(tracks)
            target_source = temp_m3u

    elif is_youtube(url):
        if "list=" in url:
            print("[*] Terdeteksi Playlist YouTube / YT Music! Lagu akan otomatis lanjut.")
        elif auto_radio:
            vid_id = extract_yt_video_id(url)
            if vid_id:
                print("[*] Lagu tunggal terdeteksi -> Mengaktifkan Auto-Radio (Mix Lanjutan)...")
                target_source = f"https://www.youtube.com/watch?v={vid_id}&list=RD{vid_id}"

    mpv_cmd.append(target_source)

    print("\n--- KONTROL PLAYER DI TERMINAL ---")
    print(" [Enter] / [>] : Lagu berikutnya   |   [<] : Lagu sebelumnya")
    print(" [Spasi]       : Pause / Resume    |   [q] : Berhenti\n")

    try:
        subprocess.run(mpv_cmd)
    except FileNotFoundError:
        print("[!] 'mpv' belum terpasang. Jalankan: pkg install mpv")
    finally:
        if temp_m3u and os.path.exists(temp_m3u):
            try:
                os.remove(temp_m3u)
            except Exception:
                pass

def extract_blogger_stream(url):
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        text = res.text.replace('\\/', '/').replace('\\u003d', '=').replace('\\u0026', '&')
        matches = re.findall(r'https?://[^\s\'"\\]*googlevideo\.com/videoplayback[^\s\'"\\]*', text)
        if matches:
            return matches[0]
    except Exception:
        pass
    return None

def scan_anime_episodes(anime_url):
    print("\n[*] Menganalisis halaman anime & memindai daftar episode...")
    try:
        res = requests.get(anime_url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        episodes = []
        seen_urls = set()

        links = soup.select('.episodelist ul li span a, .lister ul li a, .listeps ul li a, .episode_list a, .eplister ul li a')
        if not links:
            links = soup.find_all('a', href=True)

        for a in links:
            href = a.get('href', '')
            text = a.get_text(strip=True)
            text_lower = text.lower()
            
            if any(nav in text_lower for nav in ["next", "prev", "sebelumnya", "selanjutnya", "berikutnya", "batch", "lengkap", "pdf", "zip"]):
                continue

            if is_episode_url(href) and href not in seen_urls:
                if text and len(text) < 100:
                    seen_urls.add(href)
                    episodes.append({'title': text, 'url': href})

        if len(episodes) > 1:
            episodes.reverse()
        return episodes
    except Exception as e:
        print(f"[!] Gagal memindai episode: {e}")
        return []

def unpack_general_stream(html_text):
    direct_links = re.findall(r'https?://[^\s\'"]+\.(?:m3u8|mp4)[^\s\'"]*', html_text)
    if direct_links:
        return direct_links[0]

    js_patterns = [
        r'file\s*:\s*["\'](https?://[^"\'\s]+)["\']',
        r'src\s*:\s*["\'](https?://[^"\'\s]+)["\']',
        r'sources\s*:\s*\[\{\s*file\s*:\s*["\'](https?://[^"\'\s]+)["\']',
        r'source\s*src\s*=\s*["\'](https?://[^"\'\s]+)["\']'
    ]
    for p in js_patterns:
        found = re.findall(p, html_text, re.IGNORECASE)
        for link in found:
            if ".m3u8" in link or ".mp4" in link or "googlevideo" in link:
                return link
    return None

def resolve_otakudesu_ajax(page_url, data_content):
    if not data_content:
        return None
    try:
        raw_decoded = data_content
        try:
            missing_padding = len(data_content) % 4
            if missing_padding:
                data_content += '=' * (4 - missing_padding)
            raw_decoded = base64.b64decode(data_content).decode('utf-8', errors='ignore')
            raw_decoded = raw_decoded.replace('\\/', '/')
        except Exception:
            pass

        if raw_decoded.startswith('http'):
            return raw_decoded

        payload = {}
        if raw_decoded.startswith('{'):
            payload = json.loads(raw_decoded)
        else:
            for pair in raw_decoded.split('&'):
                if '=' in pair:
                    k, v = pair.split('=', 1)
                    payload[k] = unquote(v)

        if not payload:
            return None

        parsed_base = urlparse(page_url)
        ajax_url = f"{parsed_base.scheme}://{parsed_base.netloc}/wp-admin/admin-ajax.php"

        ajax_headers = HEADERS.copy()
        ajax_headers.update({
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": page_url,
            "Origin": f"{parsed_base.scheme}://{parsed_base.netloc}"
        })

        resp = requests.post(ajax_url, data=payload, headers=ajax_headers, timeout=10)
        resp_text = resp.text.replace('\\/', '/')

        iframe_match = re.search(r'src=["\'](https?://[^"\'\s]+)["\']', resp_text)
        if iframe_match:
            return iframe_match.group(1)

        b64_matches = re.findall(r'aHR0c[A-Za-z0-9+/=]+', resp_text)
        for b_str in b64_matches:
            missing = len(b_str) % 4
            if missing:
                b_str += '=' * (4 - missing)
            try:
                dec_resp = base64.b64decode(b_str).decode('utf-8', errors='ignore')
                m = re.search(r'https?://[^\s\'"<>\\]+', dec_resp)
                if m:
                    return m.group(0).replace('\\/', '/')
            except Exception:
                continue

    except Exception:
        pass
    return None

def extract_via_ytdlp(url):
    try:
        cmd = ["yt-dlp", "-g", "--no-warnings", url]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=12)
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip().split('\n')[0]
    except Exception:
        pass
    return None

def extract_video_link(page_url):
    print("[*] Menganalisis player video & mirror server Otakudesu...")
    try:
        res = requests.get(page_url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')

        mirrors = []
        seen_urls = set()

        elements = soup.select('[data-content]')
        for el in elements:
            data_content = el.get('data-content', '')
            name = el.get_text(strip=True)

            if not name or 'episode' in name.lower() or name.lower() in ["next", "prev", "home"]:
                continue

            if data_content:
                target_url = resolve_otakudesu_ajax(page_url, data_content)
                if target_url and target_url not in seen_urls:
                    seen_urls.add(target_url)

                    res_prefix = ""
                    parent_ul = el.find_parent('ul')
                    if parent_ul and parent_ul.get('class'):
                        classes = [c.upper() for c in parent_ul.get('class') if 'm' in c.lower()]
                        if classes:
                            res_prefix = f"[{classes[0]}] "

                    label = f"{res_prefix}{name}"
                    
                    if any(fav in name.lower() or fav in target_url.lower() for fav in ['ondesuhd', 'desustream', 'odstream']):
                        mirrors.insert(0, {'name': label, 'url': target_url})
                    else:
                        mirrors.append({'name': label, 'url': target_url})

        for iframe in soup.find_all('iframe'):
            src = iframe.get('src') or iframe.get('data-src') or ''
            if src.startswith('//'):
                src = 'https:' + src
            if src.startswith('http') and src not in seen_urls:
                if not any(ign in src.lower() for ign in ['facebook.com', 'discord.com', 'disqus.com']):
                    seen_urls.add(src)
                    domain = urlparse(src).netloc
                    mirrors.append({'name': f"Default Player ({domain})", 'url': src})

        if mirrors:
            print(f"\n[✓] Ditemukan {len(mirrors)} Mirror Server Player:")
            for idx, m in enumerate(mirrors, 1):
                print(f"  {idx}. {m['name']}")

            target_mirror = mirrors[0]['url']
            if len(mirrors) > 1:
                try:
                    m_choice = input(f"\nPilih Player [1-{len(mirrors)}] (default 1): ").strip() or "1"
                    selected_m = int(m_choice) - 1
                    if 0 <= selected_m < len(mirrors):
                        target_mirror = mirrors[selected_m]['url']
                except Exception:
                    pass

            print(f"\n[*] Menguraikan stream dari player: {target_mirror[:60]}...")

            if 'blogger.com' in target_mirror:
                print("[*] Membedah stream googlevideo (.mp4) dari Blogger...")
                b_direct = extract_blogger_stream(target_mirror)
                if b_direct:
                    print(f"[✓] Direct Stream Google Video berhasil diekstrak!")
                    return b_direct, target_mirror

            try:
                m_headers = HEADERS.copy()
                m_headers["Referer"] = page_url
                m_res = requests.get(target_mirror, headers=m_headers, timeout=10)

                if 'blogger.com' in m_res.text:
                    b_match = re.search(r'src=["\'](https?://www\.blogger\.com/[^"\'\s]+)["\']', m_res.text)
                    if b_match:
                        b_direct = extract_blogger_stream(b_match.group(1))
                        if b_direct:
                            print(f"[✓] Direct Stream Google Video berhasil diekstrak!")
                            return b_direct, target_mirror

                unpacked = unpack_general_stream(m_res.text)
                if unpacked:
                    print(f"[✓] Direct Stream (.m3u8/.mp4) berhasil diekstrak!")
                    return unpacked, target_mirror
            except Exception:
                pass

            ytdlp_url = extract_via_ytdlp(target_mirror)
            if ytdlp_url:
                print(f"[✓] Direct Stream berhasil diekstrak via yt-dlp!")
                return ytdlp_url, target_mirror

            return target_mirror, page_url

    except Exception as e:
        print(f"[!] Gagal ekstraksi web: {e}")

    return None, page_url

def get_youtube_direct_stream(url, mode="1"):
    if mode == "2":
        print("[*] Mengambil format single-stream 360p (Audio + Video)...")
        cmd = ["yt-dlp", "-g", "-f", "18", url]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            return res.stdout.strip().split('\n')[0]
        except Exception:
            return url
    return url

def stream_media(url, yt_mode="1"):
    target_url = url
    
    if not is_youtube(url) and not url.endswith(('.mp4', '.m3u8', '.mkv')):
        if is_episode_url(url):
            print("[*] Terdeteksi halaman episode langsung.")
            target_url = url
        else:
            episodes = scan_anime_episodes(url)
            if episodes:
                print(f"\n[✓] Ditemukan {len(episodes)} Episode:")
                for idx, ep in enumerate(episodes, 1):
                    print(f"  {idx}. {ep['title']}")
                
                try:
                    ep_choice = input(f"\nPilih Episode [1-{len(episodes)}] (atau 'q' batal): ").strip()
                    if ep_choice.lower() in ['q', 'exit']:
                        return
                    selected_idx = int(ep_choice) - 1
                    if 0 <= selected_idx < len(episodes):
                        target_url = episodes[selected_idx]['url']
                        print(f"\n[+] Memilih: {episodes[selected_idx]['title']}")
                    else:
                        print("[!] Pilihan tidak valid.")
                        return
                except ValueError:
                    print("[!] Input harus angka.")
                    return

    referer = target_url

    if is_youtube(target_url):
        target_url = get_youtube_direct_stream(target_url, yt_mode)
        play_url = target_url
    elif not target_url.endswith(('.mp4', '.m3u8', '.mkv')):
        extracted, referer = extract_video_link(target_url)
        if not extracted:
            print("\n[!] Gagal menemukan stream video murni (.m3u8 / .mp4) dari web ini.\n")
            return
        
        if extracted.endswith(('.mp4', '.m3u8')) or 'googlevideo.com' in extracted:
            play_url = extracted
        else:
            print("[*] Menjalankan Local Relay Streamer...")
            play_url = start_local_proxy(extracted, referer)
    else:
        play_url = target_url

    print(f"\n[+] Membuka Video Player HP: {play_url}\n")
    
    cmd = ["am", "start", "-a", "android.intent.action.VIEW", "-d", play_url, "-t", "video/*"]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("[✓] Pemutar Video berhasil dibuka!\n")
    except Exception as e:
        print(f"[!] Gagal membuka player: {e}")

def main():
    while True:
        os.system('clear' if os.name == 'posix' else 'cls')
        print("==================================================")
        print("     SILENT-STREAM (SPOTIFY INTL-ID & RADIO v19)  ")
        print("==================================================")
        print("1. Stream Video (Otakudesu / Episode / YT)")
        print("2. Stream Audio & Auto-Radio (YT Music / Spotify)")
        print("0. Keluar")
        
        choice = input("\nPilihan [1/2/0]: ").strip()

        if choice in ["0", "exit", "q"]:
            break

        elif choice == "1":
            print("\n--- OPSI YOUTUBE ---")
            print("1. Kualitas HD (Disarankan pakai MPV / VLC App di HP)")
            print("2. Single Stream 360p (Cocok untuk semua player HP)")
            yt_mode = input("Pilih Opsi [1-2] (default 1): ").strip() or "1"
            
            while True:
                print("\n--------------------------------------------------")
                url = input("Tempel Link (atau ketik 'q' untuk ke Menu Utama): ").strip()
                if url.lower() in ["q", "exit", "menu"]:
                    break
                if url:
                    stream_media(url, yt_mode=yt_mode)

        elif choice == "2":
            print("\n--- MODE STREAM AUDIO & AUTO-RADIO ---")
            radio_ans = input("Aktifkan Auto-Radio (lanjut lagu otomatis jika link tunggal)? [Y/n]: ").strip().lower()
            is_radio = (radio_ans != 'n')

            shuffle_ans = input("Aktifkan mode Shuffle / Acak? [y/N]: ").strip().lower()
            is_shuffle = (shuffle_ans == 'y')

            while True:
                print("\n--------------------------------------------------")
                url = input("Tempel Link Lagu/Playlist YT Music atau Spotify ('q' kembali): ").strip()
                if url.lower() in ["q", "exit", "menu"]:
                    break
                if url:
                    play_audio_playlist(url, shuffle=is_shuffle, auto_radio=is_radio)

if __name__ == "__main__":
    main()
