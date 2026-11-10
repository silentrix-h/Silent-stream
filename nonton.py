#!/usr/bin/env python
import os
import re
import sys
import base64
import subprocess
from urllib.parse import urlparse
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

def is_episode_url(url):
    url_lower = url.lower()
    patterns = [r'/episode/', r'-episode-', r'-ep-\d+', r'/ep-\d+', r'episode-\d+', r'eps-\d+']
    for p in patterns:
        if re.search(p, url_lower):
            return True
    return False

def is_valid_mirror_url(url):
    if not url or not url.startswith('http'):
        return False
    if is_episode_url(url) or '/anime/' in url:
        return False
    ignore_list = ['facebook.com', 'discord.com', 'twitter.com', 'disqus.com', 'whatsapp.com', 'otakudesu.blog/episode', 'kuronime.sbs/anime']
    if any(ign in url.lower() for ign in ignore_list):
        return False
    return True

def parse_mirror_value(val):
    if not val:
        return None
    val = val.strip()
    if val.startswith('http'):
        return val
    try:
        missing_padding = len(val) % 4
        if missing_padding:
            val += '=' * (4 - missing_padding)
        decoded = base64.b64decode(val).decode('utf-8', errors='ignore')
        
        iframe_match = re.search(r'src=["\'](https?://[^"\'\s]+)["\']', decoded)
        if iframe_match:
            return iframe_match.group(1)
            
        url_match = re.search(r'https?://[^\s\'"<>\\]+', decoded)
        if url_match:
            return url_match.group(1)
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
        r'source\s*src\s*=\s*["\'](https?://[^"\'\s]+)["\']'
    ]
    for p in js_patterns:
        found = re.findall(p, html_text, re.IGNORECASE)
        for link in found:
            if ".m3u8" in link or ".mp4" in link:
                return link
    return None

def extract_via_ytdlp(url):
    """Menggunakan yt-dlp untuk membongkar player seperti Blogger / Google Video / Doodstream."""
    try:
        cmd = ["yt-dlp", "-g", "--no-warnings", url]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=12)
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip().split('\n')[0]
    except Exception:
        pass
    return None

def extract_video_link(page_url):
    print("[*] Menganalisis player video & mirror server...")
    try:
        res = requests.get(page_url, headers=HEADERS, timeout=10)
        html = res.text
        soup = BeautifulSoup(html, 'html.parser')

        mirrors = []
        seen_urls = set()

        # 1. Cek iframe utama di halaman
        for iframe in soup.find_all('iframe'):
            src = iframe.get('src') or iframe.get('data-src') or ''
            if src.startswith('//'):
                src = 'https:' + src
            if is_valid_mirror_url(src):
                seen_urls.add(src)
                mirrors.append({'name': 'Default Main Player', 'url': src})

        # 2. Tangkap mirror khusus Otakudesu & Kuronime
        elements = soup.select('.mirrorstream a[data-content], select option[value], button[data-video]')
        for el in elements:
            raw_val = el.get('data-content') or el.get('value') or el.get('data-video') or ''
            extracted_url = parse_mirror_value(raw_val)

            if extracted_url and is_valid_mirror_url(extracted_url) and extracted_url not in seen_urls:
                seen_urls.add(extracted_url)

                server_name = el.get_text(strip=True)
                parent_ul = el.find_parent('ul')
                if parent_ul and parent_ul.get('class'):
                    res_tag = " ".join(parent_ul.get('class')).upper()
                    server_name = f"{res_tag} - {server_name}"

                mirrors.append({'name': server_name or 'Mirror Server', 'url': extracted_url})

        # Jika ditemukan mirror
        if mirrors:
            target_mirror = None

            if len(mirrors) == 1:
                target_mirror = mirrors[0]['url']
                print(f"[✓] Memakai player: {mirrors[0]['name']}")
            else:
                print(f"\n[✓] Ditemukan {len(mirrors)} Mirror Server Player:")
                for idx, m in enumerate(mirrors, 1):
                    print(f"  {idx}. {m['name']} -> ({m['url'][:45]}...)")

                try:
                    m_choice = input(f"\nPilih Mirror Server [1-{len(mirrors)}] (default 1): ").strip() or "1"
                    selected_m = int(m_choice) - 1
                    if 0 <= selected_m < len(mirrors):
                        target_mirror = mirrors[selected_m]['url']
                        print(f"\n[+] Menggunakan Server: {mirrors[selected_m]['name']}")
                except Exception:
                    target_mirror = mirrors[0]['url']

            if target_mirror:
                # Coba unpack direct link (.mp4 / .m3u8)
                try:
                    m_res = requests.get(target_mirror, headers=HEADERS, timeout=10)
                    unpacked = unpack_general_stream(m_res.text)
                    if unpacked:
                        return unpacked, target_mirror
                except Exception:
                    pass

                # Jika player berupa Blogger / Embed Web, paksa ekstrak lewat yt-dlp
                print("[*] Mengonversi embed player via yt-dlp engine...")
                ytdlp_url = extract_via_ytdlp(target_mirror)
                if ytdlp_url:
                    print(f"[✓] Direct Stream Google/Blogger berhasil diekstrak!")
                    return ytdlp_url, target_mirror

                return target_mirror, page_url

    except Exception as e:
        print(f"[!] Gagal ekstraksi web: {e}")

    ytdlp_fallback = extract_via_ytdlp(page_url)
    if ytdlp_fallback:
        return ytdlp_fallback, page_url

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

def stream_media(url, yt_mode="1", audio_only=False):
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
            print("\n[!] Gagal menemukan stream video otomatis dari web ini.\n")
            return
        
        # Jika hasil ekstraksi sudah murni direct link (misal googlevideo/mp4), tak perlu lewat 127.0.0.1
        if extracted.endswith(('.mp4', '.m3u8')) or 'googlevideo.com' in extracted:
            play_url = extracted
        else:
            print("[*] Menjalankan Local Relay Streamer...")
            play_url = start_local_proxy(extracted, referer)
    else:
        play_url = target_url

    print(f"\n[+] Membuka Video Player HP: {play_url}\n")
    
    if audio_only:
        cmd = ["mpv", "--no-video", target_url]
        subprocess.run(cmd)
    else:
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
        print("    SILENT-STREAM (BLOGGER & EMBED FIX v8)       ")
        print("==================================================")
        print("1. Stream Video (Halaman Utama Anime / Episode / YT)")
        print("2. Stream Audio Saja (di Background Termux)")
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
                    stream_media(url, yt_mode=yt_mode, audio_only=False)

        elif choice == "2":
            print("\n--- MODE STREAM AUDIO SAJA ---")
            while True:
                print("\n--------------------------------------------------")
                url = input("Tempel Link (atau ketik 'q' untuk ke Menu Utama): ").strip()
                if url.lower() in ["q", "exit", "menu"]:
                    break
                if url:
                    stream_media(url, audio_only=True)

if __name__ == "__main__":
    main()
