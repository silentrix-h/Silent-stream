#!/usr/bin/env python
import os
import sys
import subprocess
from datetime import datetime

def get_battery_info():
    """Mengambil status baterai HP jika termux-api terpasang."""
    try:
        res = subprocess.run(["termux-battery-status"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2)
        if res.returncode == 0:
            import json
            data = json.loads(res.stdout)
            return f"Baterai: {data.get('percentage', '?')}% ({data.get('status', 'N/A')})"
    except Exception:
        pass
    return None

def main():
    while True:
        os.system('clear' if os.name == 'posix' else 'cls')
        now_str = datetime.now().strftime("%A, %d %b %Y - %H:%M")
        bat_info = get_battery_info()
        
        print("==================================================")
        print("                 SILENT-HUB DASHBOARD             ")
        print("==================================================")
        print(f" Waktu   : {now_str}")
        if bat_info:
            print(f" Status  : {bat_info}")
        print("==================================================")
        print(" 1. 🎬 Nonton Streamer (Otakudesu / YT / Direct)")
        print(" 2. 📑 Anime Tracker & Watchlist (Auto Next Ep)")
        print(" 3. ⚡ Fast Downloader (YouTube / YT Music via aria2c)")
        print(" 0. 🚪 Keluar Terminal")
        print("==================================================")
        
        choice = input("\nPilih Menu [1/2/3/0]: ").strip()

        if choice == "1":
            subprocess.run(["nonton"])
        elif choice == "2":
            subprocess.run(["python", os.path.expanduser("~/silent-stream/tracker.py")])
        elif choice == "3":
            downloader_path = os.path.expanduser("~/silent-stream/fast_downloader.py")
            if os.path.exists(downloader_path):
                subprocess.run(["python", downloader_path])
            else:
                # Coba cek jika ada di home directory
                home_dl = os.path.expanduser("~/fast_downloader.py")
                if os.path.exists(home_dl):
                    subprocess.run(["python", home_dl])
                else:
                    print("\n[!] Script fast_downloader.py tidak ditemukan.")
                    input("\nTekan Enter untuk kembali...")
        elif choice in ["0", "q", "exit"]:
            print("\nSampai jumpa, Kim!\n")
            break

if __name__ == "__main__":
    main()
