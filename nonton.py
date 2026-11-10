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
            return stream_url, page_url

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
                    return iframe_stream, page_url
            except Exception:
                continue

    except Exception as e:
        print(f"[!] Gagal ekstraksi web: {e}")
        
    return page_url, page_url

def get_youtube_stream_link(url, quality_choice="2"):
    """Mengambil direct stream link YouTube menggunakan yt-dlp sesuai resolusi."""
    print("[*] Mengambil link stream YouTube...")
    res_map = {"1": "1080", "2": "720", "3": "480", "4": "360"}
    res = res_map.get(quality_choice, "720")
    fmt = f"bestvideo[height<={res}]+bestaudio/best[height<={res}]/best"
    
    cmd = ["yt-dlp", "-g", "-f", fmt, url]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        links = result.stdout.strip().split('\n')
        return links[0] if links else url
    except Exception:
        return url

def stream_media(url, quality_choice="2", audio_only=False):
    referer = url
    target_url = url

    if is_youtube(url):
        target_url = get_youtube_stream_link(url, quality_choice)
    elif not url.endswith(('.mp4', '.m3u8', '.mkv')):
        target_url, referer = extract_video_link(url)

    print(f"\n[+] Membuka Video Player HP: {target_url}\n")
    
    if audio_only:
        cmd = ["mpv", "--no-video", target_url]
    else:
        # Kirim header Referer & User-Agent ke Intent Android agar tidak diblokir CDN server
        headers_str = f"Referer: {referer},User-Agent: {HEADERS['User-Agent']}"
        cmd = [
            "am", "start",
            "-a", "android.intent.action.VIEW",
            "-d", target_url,
            "-t", "video/*",
            "--esa", "headers", headers_str,
            "--esa", "input-headers", headers_str
        ]

    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("[✓] Video Player berhasil dipanggil!\n")
    except Exception as e:
        print(f"[!] Gagal membuka player: {e}")

def main():
    while True:
        os.system('clear' if os.name == 'posix' else 'cls')
        print("==================================================")
        print("      SILENT-STREAM (STREAM PLAYER FIX v4)        ")
        print("==================================================")
        print("1. Stream Video (Buka di Video Player HP)")
        print("2. Stream Audio Saja (Latar Belakang / MP3)")
        print("0. Keluar")
        
        choice = input("\nPilihan [1/2/0]: ").strip()

        if choice in ["0", "exit", "q"]:
            break

        elif choice == "1":
            print("\n--- MODE STREAM VIDEO ---")
            print("Pilih Resolusi Video (Khusus YouTube):")
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
                if url:
                    stream_media(url, quality_choice=q_choice, audio_only=False)

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
