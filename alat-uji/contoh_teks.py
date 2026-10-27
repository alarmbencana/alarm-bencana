"""Cetak contoh semua jenis teks kiriman dengan data terbaru (tidak mengubah keadaan, tidak mengunggah).
Pakai (dari folder proyek): python alat-uji/contoh_teks.py"""
import sys
from datetime import datetime, timedelta, timezone
sys.path.insert(0, "program")
import alarm
sys.stdout.reconfigure(encoding="utf-8")
sekarang = datetime.now(timezone.utc)
w = alarm.Wilayah()
per_kab, ragu, stasiun = alarm.ambil_asap(alarm.baca_env()["WAQI_TOKEN"].strip(), w)
titik = alarm.ambil_api(w)
urut = sorted(per_kab.values(), key=lambda h: -h["ug"])


def tampil(judul, teks):
    print(f"--- {judul} [{alarm.panjang_x(teks)}/{alarm.BATAS_KARAKTER}] ---\n{teks}\n")


tampil("ringkasan", alarm.ringkasan(per_kab, titik, sekarang)["teks"])
tampil("asap (satu tempat)", alarm.unggahan_asap(urut[0]))
tampil("membaik", alarm.unggahan_asap({**urut[0], "ug": 30}, membaik=True))
# pura-pura 8 tempat terburuk baru saja memburuk semua -> 2 kiriman sendiri + 1 gabungan
keadaan = {"asap": {k: {"tingkat_unggah": 1, "turun": 0, "aman": 0} for k in per_kab}}
pilih = {k: per_kab[k] for k in sorted(per_kab, key=lambda k: -per_kab[k]["ug"])[:8]}
gabung = [d for d in alarm.aturan_asap(pilih, keadaan, False) if d["jenis"] == "asap_gabung"]
if gabung:
    tampil("asap gabungan", gabung[0]["teks"])
# pura-pura semua titik api 24 jam terakhir itu baru
keadaan = {"api": {"terakhir": {s: (sekarang - timedelta(hours=24)).isoformat() for s in alarm.FIRMS}, "sel": {}}}
api, n = alarm.aturan_api(titik, keadaan, sekarang)
if api:
    tampil("titik api baru", api[0]["teks"])
