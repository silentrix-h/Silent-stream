#!/usr/bin/env python
import os
import re
import sys
import json
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
    """Menembak AJAX wp-admin/admin-ajax.php Otakudesu untuk mendapatkan iframe player asli."""
    try:
        parsed_base = urlparse(page_url)
        ajax_url = f"{parsed_base.scheme}://{parsed_base.netloc}/wp-admin/admin-ajax.php"
        
        missing_padding = len(data_content) % 4
        if missing_padding:
            data_content += '=' * (4 - missing_padding)
        decoded = base64.b64decode(data_content).decode('utf-8', errors='ignore')

        payload = {}
        if decoded.startswith('{'):
            payload = json.loads(decoded)
        else:
            for pair in decoded.split('&'):
                if '=' in pair:
                    k, v = pair.split('=', 1)
                    payload[k] = v

        if not payload:
            return None

        ajax_headers = HEADERS.copy()
        ajax_headers.update({
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": page_url
        })

        resp = requests.post(ajax_url, data=payload, headers=ajax_headers, timeout=10)
        
        iframe_match = re.search(r'src=["\'](https?://[^"\'\s]+)["\']', resp.text)
        if iframe_match:
            return iframe_match.group(1)

        b64_iframe = re.search(r'aHR0c[A-Za-z0-9+/=]+', resp.text)
        if b64_iframe:
            b_str = b64_iframe.group(0)
            missing = len(b_str) % 4
            if missing:
                b_str += '=' * (4 - missing)
            dec_resp = base64.b64decode(b_str).decode('utf-8', errors='ignore')
            m = re.search(r'https?://[^\s\'"<>\\]+', dec_resp)
            if m:
                return m.group(0).replace('\\/', '/')

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
        seen = set()

        # 1. Pindai khusus elemen di dalam div.mirrorstream (Otakudesu)
        mirror_div = soup.find('div', class_='mirrorstream')
        if mirror_div:
            for ul in mirror_div.find_all('ul'):
                res_class = " ".join(ul.get('class', [])).upper()
                for a in ul.find_all('a'):
                    data_content = a.get('data-content', '')
                    name = a.get_text(strip=True)

                    if name.lower() in seen or 'episode' in name.lower():
                        continue

                    if data_content:
                        target_url = resolve_otakudesu_ajax(page_url, data_content)
                        if target_url:
                            seen.add(name.lower())
                            label = f"[{res_class}] {name}"
                            if any(fav in name.lower() or fav in target_url.lower() for fav in ['ondesuhd', 'desustream', 'odstream']):
                                mirrors.insert(0, {'name': label, 'url': target_url})
                            else:
                                mirrors.append({'name': label, 'url': target_url})

        # 2. Tangkap iframe utama jika mirrorstream kosong (Web Lain / Standar)
        if not mirrors:
            for iframe in soup.find_all('iframe'):
                src = iframe.get('src') or iframe.get('data-src') or ''
                if src.startswith('//'):
                    src = 'https:' + src
                if src.startswith('http') and 'blogger.com' not in src:
                    domain = urlparse(src).netloc
                    mirrors.append({'name': f"Main Player ({domain})", 'url': src})

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

            print(f"\n[*] Menguraikan stream dari player: {target_mirror[:55]}...")
            
            try:
                m_headers = HEADERS.copy()
                m_headers["Referer"] = page_url
                m_res = requests.get(target_mirror, headers=m_headers, timeout=10)

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
        print("    SILENT-STREAM (OTAKUDESU AJAX RESOLVER v14)   ")
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
