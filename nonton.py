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

def find_stream_in_html(html_text):
    """Mencari pola file video .m3u8 atau .mp4 di dalam HTML/JS."""
    # 1. Cari URL berakhiran .m3u8 atau .mp4
    direct_links = re.findall(r'https?://[^\s\'"]+\.(?:m3u8|mp4)[^\s\'"]*', html_text)
    if direct_links:
        return direct_links[0]

    # 2. Cari pola file: "http..." atau src: "http..." di dalam tag JavaScript player
    js_sources = re.findall(r'(?:file|src|source)\s*[:=]\s*["\'](https?://[^"\'\s]+\.(?:m3u8|mp4|mkv)[^"\'\s]*)["\']', html_text, re.IGNORECASE)
    if js_sources:
        return js_sources[0]

    # 3. Cari URL apapun yang mengandung m3u8
    m3u8_any = re.findall(r'https?://[^\s\'"]+m3u8[^\s\'"]*', html_text)
    if m3u8_any:
        return m3u8_any[0]

    return None

def extract_video_link(page_url):
    """Mengekstrak link stream secara mendalam dari halaman web utama & iframe player."""
    print("[*] Menganalisis halaman web...")
    try:
        res = requests.get(page_url, headers=HEADERS, timeout=10)
        
        # Cek 1: Apakah ada link stream langsung di halaman utama?
        stream_url = find_stream_in_html(res.text)
        if stream_url:
            print(f"[✓] Ditemukan direct stream: {stream_url}")
            return stream_url

        # Cek 2: Jika tidak ada, cari iframe pemutar (seperti playmogo, doodstream, dll)
        soup = BeautifulSoup(res.text, 'html.parser')
        iframes = soup.find_all('iframe')
        
        for iframe in iframes:
            src = iframe.get('src')
            if not src:
                continue
            if src.startswith("//"):
                src = "https:" + src

            print(f"[*] Menelusuri iframe player: {src}")
            try:
                # Request ke dalam iframe dengan Referer dari web utama
                iframe_headers = HEADERS.copy()
                iframe_headers["Referer"] = page_url
                iframe_res = requests.get(src, headers=iframe_headers, timeout=10)

                # Cari stream di dalam kode HTML/JS iframe
                iframe_stream = find_stream_in_html(iframe_res.text)
                if iframe_stream:
                    print(f"[✓] Ditemukan stream di dalam player: {iframe_stream}")
                    return iframe_stream
            except Exception:
                continue

    except Exception as e:
        print(f"[!] Gagal mengekstrak web: {e}")
        
    return page_url

def stream_media(url, quality_choice="2", audio_only=False):
    target_url = url
    if not is_youtube(url) and not url.endswith(('.mp4', '.m3u8', '.mkv')):
        target_url = extract_video_link(url)

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
        # Gunakan User-Agent & Referer agar server video tidak memblokir akses mpv
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
        print("       SILENT-STREAM (DEEP WEB SCRAPER)           ")
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
