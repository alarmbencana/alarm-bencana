"""Buat draf ringkasan (teks + peta) dengan data terbaru, tanpa mengubah keadaan program.
Pakai (dari folder proyek): python alat-uji/buat_ringkasan.py
Hasil: latihan/ringkasan-uji.txt dan latihan/gambar/ringkasan-uji.png"""
import sys
from datetime import datetime, timezone
sys.path.insert(0, "program")
import alarm
sys.stdout.reconfigure(encoding="utf-8")
sekarang = datetime.now(timezone.utc)
w = alarm.Wilayah()
per_kab, ragu, stasiun = alarm.ambil_asap(alarm.baca_env()["WAQI_TOKEN"].strip(), w)
titik = alarm.ambil_api(w)
d = alarm.ringkasan(per_kab, titik, sekarang)
gb = alarm.buat_gambar(d, w, stasiun, titik, sekarang, alarm.FOLDER_DRAF / "gambar" / "ringkasan-uji.png")
(alarm.FOLDER_DRAF / "ringkasan-uji.txt").write_text(d["teks"], encoding="utf-8")
print(d["teks"])
print(f"\n[{alarm.panjang_x(d['teks'])}/{alarm.BATAS_KARAKTER} karakter · {gb}]")
