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
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    return any(yt in domain for yt in ["youtube.com", "youtu.be", "music.youtube.com"])

def unpack_js_packer(html_text):
    # Cari regex m3u8 / mp4 mentah
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

def extract_video_link(page_url):
    print("[*] Menganalisis & membongkar halaman web...")
    try:
        res = requests.get(page_url, headers=HEADERS, timeout=10)
        
        stream_url = unpack_js_packer(res.text)
        if stream_url:
            print(f"[✓] Ditemukan direct stream: {stream_url}")
            return stream_url

        soup = BeautifulSoup(res.text, 'html.parser')
        for iframe in soup.find_all('iframe'):
            src = iframe.get('src', '')
            if not src:
                continue
            if src.startswith("//"):
                src = "https:" + src
            if any(ignore in src for ignore in ["discord.com", "facebook.com", "disqus.com"]):
                continue

            print(f"[*] Menelusuri iframe player: {src}")
            try:
                iframe_headers = HEADERS.copy()
                iframe_headers["Referer"] = page_url
                iframe_res = requests.get(src, headers=iframe_headers, timeout=10)
                iframe_stream = unpack_js_packer(iframe_res.text)
                if iframe_stream:
                    print(f"[✓] Berhasil membongkar stream: {iframe_stream}")
                    return iframe_stream
            except Exception:
                continue

    except Exception as e:
        print(f"[!] Gagal ekstraksi web: {e}")
        
    return None

def stream_media(url, player_mode="1"):
    target_url = url
    if not is_youtube(url) and not url.endswith(('.mp4', '.m3u8', '.mkv')):
        extracted = extract_video_link(url)
        if not extracted:
            print("\n[!] Gagal mengambil stream dari halaman ini.")
            return
        target_url = extracted

    print(f"\n[+] Membuka stream di Player HP: {target_url}\n")
    
    if player_mode == "1":
        # Membuka langsung ke aplikasi Pemutar Video HP (VLC / MX Player / Bawaan Android)
        cmd = ["am", "start", "-a", "android.intent.action.VIEW", "-d", target_url, "-t", "video/*"]
    else:
        # Membuka via MPV CLI Termux (Audio Only)
        cmd = ["mpv", target_url]

    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("[✓] Pemutar video berhasil dibuka di HP!\n")
    except Exception as e:
        print(f"[!] Gagal membuka player: {e}")

def main():
    while True:
        os.system('clear' if os.name == 'posix' else 'cls')
        print("==================================================")
        print("      SILENT-STREAM (ANDROID PLAYER LAUNCHER)     ")
        print("==================================================")
        print("1. Stream Video (Buka Aplikasi Video Player HP)")
        print("2. Stream Audio Saja (di Background Termux)")
        print("0. Keluar")
        
        choice = input("\nPilihan [1/2/0]: ").strip()

        if choice in ["0", "exit", "q"]:
            break
        elif choice in ["1", "2"]:
            while True:
                print("\n--------------------------------------------------")
                url = input("Tempel Link (atau ketik 'q' untuk ke Menu Utama): ").strip()
                if url.lower() in ["q", "exit", "menu"]:
                    break
                if url:
                    stream_media(url, player_mode=choice)

if __name__ == "__main__":
    main()
