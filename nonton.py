#!/usr/bin/env python
import os
import re
import sys
import base64
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

def decode_base64_stream(text):
    """Mencari dan mendekode string Base64 yang berisi link https://...m3u8 / mp4."""
    # Cari pola Base64 yang diawali 'aHR0cHM' (artinya 'https://' dalam Base64)
    b64_matches = re.findall(r'aHR0cHM[A-Za-z0-9+/=]+', text)
    for b64_str in b64_matches:
        try:
            missing_padding = len(b64_str) % 4
            if missing_padding:
                b64_str += '=' * (4 - missing_padding)
            decoded = base64.b64decode(b64_str).decode('utf-8', errors='ignore')
            if 'http' in decoded and ('.m3u8' in decoded or '.mp4' in decoded or 'stream' in decoded or 'master' in decoded):
                return decoded
        except Exception:
            continue
    return None

def unpack_js_packer(html_text):
    """Membongkar JavaScript packed/eval pada player web."""
    # 1. Coba decode string Base64
    b64_res = decode_base64_stream(html_text)
    if b64_res:
        return b64_res

    # 2. Cari regex m3u8 / mp4 mentah
    direct_links = re.findall(r'https?://[^\s\'"]+\.(?:m3u8|mp4)[^\s\'"]*', html_text)
    if direct_links:
        return direct_links[0]

    # 3. Cari pola file/sources di JavaScript
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
    """Mengekstrak link stream secara mendalam dari halaman web utama & iframe player."""
    print("[*] Menganalisis halaman web...")
    try:
        res = requests.get(page_url, headers=HEADERS, timeout=10)
        
        # Cek link direct di halaman utama
        stream_url = unpack_js_packer(res.text)
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

            if any(ignore in src for ignore in ["discord.com", "facebook.com", "disqus.com"]):
                continue

            print(f"[*] Menelusuri iframe player: {src}")
            try:
                iframe_headers = HEADERS.copy()
                iframe_headers["Referer"] = page_url
                iframe_res = requests.get(src, headers=iframe_headers, timeout=10)

                # Dekode isi HTML/JS di dalam iframe (Playmogo, dll)
                iframe_stream = unpack_js_packer(iframe_res.text)
                if iframe_stream:
                    print(f"[✓] Berhasil membongkar stream: {iframe_stream}")
                    return iframe_stream
                
                # Jika provider dikenal yt-dlp secara native
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
            print("\n[!] Gagal membongkar stream dari halaman ini.")
            print("[!] Solusi: Tempelkan link server player lain (misal Doodstream/Streamtape) secara langsung.\n")
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
        # Gunakan User-Agent & Referer agar server video tidak menolak mpv
        http_header = f"User-Agent: {HEADERS['User-Agent']}\r\nReferer: https://playmogo.com/"
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
        print("       SILENT-STREAM (AUTO DECODER v3)            ")
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
