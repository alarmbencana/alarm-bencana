"""Buat foto profil (400x400) dan banner (1500x500) akun X, dengan gaya yang sama seperti gambar peringatan.
Banner memakai titik api 24 jam sungguhan saat skrip dijalankan.
Pakai (dari folder proyek): python alat-uji/buat_profil.py   -> hasil di aset/
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, "program")
import alarm
import gambar
from gambar import API_INTI, API_PIJAR, K, LAUT, REDUP, TEKS, huruf

ASET = Path("aset")
JINGGA = (255, 176, 72)


def foto_profil():
    """Titik api yang menyala dengan gelombang alarm di kiri-kanannya. Tetap terbaca walau sekecil 48 px."""
    n = 400 * K
    img = Image.new("RGBA", (n, n), LAUT + (255,))
    c = n / 2
    pijar = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(pijar).ellipse((c - 95 * K, c - 95 * K, c + 95 * K, c + 95 * K), fill=API_PIJAR + (200,))
    img.alpha_composite(pijar.filter(ImageFilter.GaussianBlur(42 * K)))
    gelombang = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(gelombang)
    for i, (r, a) in enumerate(((88, 255), (128, 190), (168, 120))):
        kotak = (c - r * K, c - r * K, c + r * K, c + r * K)
        for mulai in (-40, 140):  # busur kanan dan kiri
            d.arc(kotak, mulai, mulai + 80, fill=JINGGA + (a,), width=(15 - 2 * i) * K)
    img.alpha_composite(gelombang)
    ImageDraw.Draw(img).ellipse((c - 34 * K, c - 34 * K, c + 34 * K, c + 34 * K), fill=API_INTI)
    return img.convert("RGB").resize((400, 400), Image.LANCZOS)


def banner(wilayah, api24):
    """Peta Indonesia dengan titik api di kanan; nama dan keterangan di kiri atas
    (kiri bawah tertutup foto profil di tampilan X)."""
    gambar.LEBAR, gambar.TINGGI = 1500, 500
    kv = gambar.Kanvas((55.0, -13.0, 142.5, 9.0))  # ujung barat jauh ke kiri: peta Indonesia bergeser ke kanan
    kv.peta_dasar(wilayah)
    kv.api(api24)
    redup = Image.new("RGBA", kv.img.size, (0, 0, 0, 0))  # latar kiri digelapkan supaya tulisan jelas
    dr = ImageDraw.Draw(redup)
    for x in range(0, 780 * K):
        dr.line((x, 0, x, 500 * K), fill=LAUT + (int(255 * min(1, (780 * K - x) / (240 * K))),))
    kv.img.alpha_composite(redup)
    kv.teks((70, 128), "ALARM BENCANA", huruf(62, True), JINGGA, anchor="lm")
    kv.teks((72, 196), "Peringatan otomatis kabut asap & titik api", huruf(28), TEKS, anchor="lm")
    kv.teks((72, 236), "di seluruh Indonesia. Gratis untuk warga.", huruf(28), TEKS, anchor="lm")
    kv.teks((72, 290), "Data: alat ukur BMKG & KLH · satelit NASA", huruf(21), REDUP, anchor="lm")
    return kv.img.convert("RGB").resize((1500, 500), Image.LANCZOS)


if __name__ == "__main__":
    ASET.mkdir(exist_ok=True)
    w = alarm.Wilayah()
    sekarang = datetime.now(timezone.utc)
    api24 = sorted({tuple(map(float, t["sel"].split(","))) for t in alarm.ambil_api(w)
                    if t["waktu"] > sekarang - timedelta(hours=24)})
    foto_profil().save(ASET / "foto-profil.png", optimize=True)
    banner(w, api24).save(ASET / "banner.png", optimize=True)
    print("selesai:", ASET / "foto-profil.png", ASET / "banner.png", f"({len(api24)} titik api di banner)")
