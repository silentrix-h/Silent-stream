#!/usr/bin/env python
import os
import sys
import subprocess
from urllib.parse import urlparse

def is_youtube(url):
    """Mendeteksi link YouTube / YT Music."""
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    return any(yt in domain for yt in ["youtube.com", "youtu.be", "music.youtube.com"])

def stream_media(url, quality_choice="2", audio_only=False):
    print(f"\n[+] Membuka stream untuk: {url}\n")
    
    if is_youtube(url):
        if audio_only:
            cmd = ["mpv", "--no-video", url]
        else:
            res_map = {"1": "1080", "2": "720", "3": "480", "4": "360"}
            res = res_map.get(quality_choice, "720")
            ytdl_format = f"bestvideo[height<={res}]+bestaudio/best[height<={res}]"
            cmd = ["mpv", f"--ytdl-format={ytdl_format}", url]
    else:
        # Link direct (.m3u8 film bioskop, .mp4, .mkv, dll)
        if audio_only:
            cmd = ["mpv", "--no-video", url]
        else:
            cmd = ["mpv", url]

    try:
        subprocess.run(cmd)
        print("\n[✓] Stream selesai/ditutup.\n")
    except FileNotFoundError:
        print("\n[!] Program 'mpv' belum terinstal. Jalankan 'pkg install mpv -y'.")
    except Exception as e:
        print(f"\n[!] Gagal memutar stream: {e}")

def main():
    while True:
        os.system('clear' if os.name == 'posix' else 'cls')
        print("==================================================")
        print("          SILENT-STREAM (NONTON PLAYER)           ")
        print("==================================================")
        print("1. Stream Video (YouTube / Link Film .m3u8 / MP4 Direct)")
        print("2. Stream Audio Saja (Latar Belakang / Music)")
        print("0. Keluar")
        
        choice = input("\nPilihan [1/2/0]: ").strip()

        if choice in ["0", "exit", "q"]:
            print("\nTerima kasih! Sampai jumpa.")
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
