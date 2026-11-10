#!/usr/bin/env python
import os
import re
import sys
import subprocess
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def is_youtube(url):
    """Mendeteksi link YouTube / YT Music."""
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    return any(yt in domain for yt in ["youtube.com", "youtu.be", "music.youtube.com"])

def unpack_js(html_text):
    """Mencari dan mendekode link video yang tersembunyi di dalam JavaScript packed/encoded."""
    # 1. Cari URL m3u8 atau mp4 dalam format mentah atau terenkripsi
    pattern = r'(https?://[^\s\'"]+\.(?:m3u8|mp4)[^\s\'"]*)'
    matches = re.findall(pattern, html_text)
    if matches:
        return matches[0]

    # 2. Cari pola file / sources di skrip player
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

def extract_video_link(page_url):
    """Mengekstrak link stream dari web utama & iframe player secara mendalam."""
    print("[*] Menganalisis halaman web...")
    try:
        res = requests.get(page_url, headers=HEADERS, timeout=10)
        
        # Cek link direct di halaman utama
        stream_url = unpack_js(res.text)
        if stream_url:
            print(f"[✓] Ditemukan direct stream: {stream_url}")
            return stream_url

        # Cari iframe pemutar (Playmogo, Doodstream, dll)
        soup = BeautifulSoup(res.text, 'html.parser')
        iframes = soup.find_all('iframe')
        
        for iframe in iframes:
            src = iframe.get('src')
            if not src:
                continue
            if src.startswith("//"):
                src = "https:" + src

            # Abaikan widget non-video seperti Discord/iklan
            if "discord.com" in src or "facebook.com" in src:
                continue

            print(f"[*] Menelusuri iframe player: {src}")
            try:
                iframe_headers = HEADERS.copy()
                iframe_headers["Referer"] = page_url
                iframe_res = requests.get(src, headers=iframe_headers, timeout=10)

                iframe_stream = unpack_js(iframe_res.text)
                if iframe_stream:
                    print(f"[✓] Ditemukan stream di dalam player: {iframe_stream}")
                    return iframe_stream
                
                # Jika iframe adalah player yang didukung yt-dlp langsung (misal doodstream/streamtape)
                if any(p in src for p in ["dood", "streamtape", "filemoon", "streamhider"]):
                    return src
            except Exception:
                continue

    except Exception as e:
        print(f"[!] Gagal ekstraksi web: {e}")
        
    return None

def stream_media(url, quality_choice="2", audio_only=False):
    target_url = url
    if not is_youtube(url) and not url.endswith(('.mp4', '.m3u8', '.mkv')):
        extracted = extract_video_link(url)
        if not extracted:
            print("\n[!] Gagal mengambil stream otomatis dari halaman ini.")
            print("[!] Penyebab: Server player menggunakan enkripsi JS tingkat tinggi.")
            print("[!] Solusi: Pilih server player lain di web tersebut (misal server Doodstream/Streamtape) lalu tempel link player-nya langsung.\n")
            return
        target_url = extracted

    print(f"\n[+] Membuka stream: {target_url}\n")
    
    if is_youtube(target_url):
        if audio_only:
            cmd = ["mpv", "--no-video", target_url]
        else:
            res_map = {"1": "1080", "2": "720", "3": "480", "4": "360"}
            res = res_map.get(quality_choice, "720")
            ytdl_format = f"bestvideo[height<={res}]+bestaudio/best[height<={res}]"
            cmd = ["mpv", f"--ytdl-format={ytdl_format}", target_url]
    else:
        referrer = url if target_url != url else ""
        http_header = f"User-Agent: {HEADERS['User-Agent']}"
        if referrer:
            http_header += f"\r\nReferer: {referrer}"

        cmd = [
            "mpv",
            f"--http-header-fields={http_header}",
            target_url
        ]
        if audio_only:
            cmd.append("--no-video")

    try:
        subprocess.run(cmd)
        print("\n[✓] Stream selesai/ditutup.\n")
    except FileNotFoundError:
        print("\n[!] Program 'mpv' belum terinstal.")
    except Exception as e:
        print(f"\n[!] Gagal memutar stream: {e}")

def main():
    while True:
        os.system('clear' if os.name == 'posix' else 'cls')
        print("==================================================")
        print("       SILENT-STREAM (AUTO WEB SCRAPER v2)        ")
        print("==================================================")
        print("1. Stream Video (YouTube / Link Web Halaman Film / .m3u8)")
        print("2. Stream Audio Saja (Latar Belakang / Music)")
        print("0. Keluar")
        
        choice = input("\nPilihan [1/2/0]: ").strip()

        if choice in ["0", "exit", "q"]:
            print("\nTerima kasih!")
            break
        
        elif choice == "1":
            print("\n--- MODE STREAM VIDEO ---")
            print("Pilih Limit Resolusi Video (Khusus YouTube):")
            print("1. 1080p (Full HD)")
            print("2. 720p (HD)")
            print("3. 480p")
            print("4. 360p (Hemat Kuota)")
            q_choice = input("Pilihan Resolusi [1-4] (default 2): ").strip() or "2"
            
            while True:
                print("\n--------------------------------------------------")
                url = input("Tempel Link (atau ketik 'q' untuk ke Menu Utama): ").strip()
                if url.lower() in ["q", "exit", "menu"]:
                    break
                if not url:
                    continue
                stream_media(url, quality_choice=q_choice, audio_only=False)

        elif choice == "2":
            print("\n--- MODE STREAM AUDIO SAJA ---")
            while True:
                print("\n--------------------------------------------------")
                url = input("Tempel Link (atau ketik 'q' untuk ke Menu Utama): ").strip()
                if url.lower() in ["q", "exit", "menu"]:
                    break
                if not url:
                    continue
                stream_media(url, audio_only=True)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[!] Program dihentikan.")
        sys.exit(0)
