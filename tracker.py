#!/usr/bin/env python
import os
import json
import subprocess
from datetime import datetime

DATA_FILE = os.path.expanduser("~/silent-stream/anime_watchlist.json")

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

def add_anime():
    print("\n--- TAMBAH ANIME BARU ---")
    title = input("Judul Anime: ").strip()
    if not title:
        return
    url = input("Link Web Anime (Misal Link Otakudesu): ").strip()
    if not url:
        return
    try:
        last_ep = int(input("Episode terakhir yang sudah ditonton (default 0): ").strip() or "0")
    except ValueError:
        last_ep = 0

    data = load_data()
    data[title] = {
        "url": url,
        "last_ep": last_ep,
        "updated": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    save_data(data)
    print(f"\n[✓] '{title}' berhasil disimpan di Watchlist!")

def list_and_play():
    data = load_data()
    if not data:
        print("\n[!] Watchlist masih kosong. Tambah anime dulu!")
        input("\nTekan Enter untuk kembali...")
        return

    print("\n==================================================")
    print("                DAFTAR ANIME WATCHLIST            ")
    print("==================================================")
    keys = list(data.keys())
    for idx, key in enumerate(keys, 1):
        item = data[key]
        print(f"{idx}. {key}")
        print(f"   └─ Terakhir Nonton : Ep {item['last_ep']} | Updated: {item['updated']}")
    
    print("\nPilihan:")
    print(" [1-N] Pilih anime untuk diputar")
    print(" [q]   Kembali")
    
    choice = input("\nPilihan: ").strip()
    if choice.lower() in ['q', 'exit']:
        return
    
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(keys):
            selected_title = keys[idx]
            selected_item = data[selected_title]
            
            print(f"\n[+] Memilih: {selected_title}")
            print(f"[*] Menjalankan 'nonton' untuk URL: {selected_item['url']}")
            
            # Panggil script nonton
            subprocess.run(["nonton"])
            
            # Update episode counter setelah selesai
            print("\n--------------------------------------------------")
            update_choice = input(f"Apakah kamu selesai menonton Ep {selected_item['last_ep'] + 1}? [y/N]: ").strip().lower()
            if update_choice == 'y':
                data[selected_title]['last_ep'] += 1
                data[selected_title]['updated'] = datetime.now().strftime("%Y-%m-%d %H:%M")
                save_data(data)
                print(f"[✓] Progres diperbarui: Ep {data[selected_title]['last_ep']}")
    except ValueError:
        print("[!] Input tidak valid.")

def delete_anime():
    data = load_data()
    if not data:
        print("\n[!] Watchlist kosong.")
        return
    
    keys = list(data.keys())
    for idx, key in enumerate(keys, 1):
        print(f"{idx}. {key}")
    
    try:
        choice = input("\nPilih nomor anime yang ingin dihapus (atau 'q' batal): ").strip()
        if choice.lower() in ['q', 'exit']:
            return
        idx = int(choice) - 1
        if 0 <= idx < len(keys):
            removed = keys[idx]
            del data[removed]
            save_data(data)
            print(f"[✓] '{removed}' berhasil dihapus.")
    except ValueError:
        pass

def main():
    while True:
        os.system('clear' if os.name == 'posix' else 'cls')
        print("==================================================")
        print("             ANIME TRACKER & WATCHLIST            ")
        print("==================================================")
        print("1. Lihat Watchlist & Lanjut Nonton")
        print("2. Tambah Anime Baru ke Watchlist")
        print("3. Hapus Anime dari Watchlist")
        print("0. Kembali ke Menu Utama")
        
        choice = input("\nPilihan [1/2/3/0]: ").strip()
        if choice == "1":
            list_and_play()
        elif choice == "2":
            add_anime()
            input("\nTekan Enter untuk kembali...")
        elif choice == "3":
            delete_anime()
            input("\nTekan Enter untuk kembali...")
        elif choice in ["0", "q", "exit"]:
            break

if __name__ == "__main__":
    main()
