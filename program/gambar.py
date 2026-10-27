"""Gambar peta untuk unggahan Alarm Bencana: titik api yang menyala dan alat ukur berwarna."""
import json
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

DATA = Path(__file__).resolve().parent / "data"
K = 2  # digambar 2x lebih besar lalu diperkecil, supaya garis dan lingkaran halus
LEBAR, TINGGI = 1600, 900
KAKI = 44  # tinggi pita sumber di bawah

LAUT = (10, 17, 30)
DARAT_LAIN = (27, 33, 46)
DARAT = (40, 49, 68)
BATAS_PROV = (84, 98, 128)
BATAS_KAB = (56, 67, 90)
TEKS = (236, 239, 245)
REDUP = (150, 160, 182)
PANEL = (6, 10, 20, 232)
WARNA_TINGKAT = [(46, 204, 113), (52, 152, 219), (241, 196, 15), (231, 76, 60), (12, 12, 12)]
NAMA_TINGKAT = ["Baik", "Sedang", "Tidak sehat", "Sangat tidak sehat", "Berbahaya"]
API_INTI = (255, 226, 130)
API_PIJAR = (255, 84, 0)
API_LAMA = (196, 112, 50)
SUMBER_PETA = "Batas wilayah: BPS via geoBoundaries, Natural Earth"


HURUF = [  # (biasa, tebal): Segoe UI di laptop Windows, Noto Sans di GitHub (Linux)
    ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/segoeuib.ttf"),
    ("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf", "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
]


def huruf(ukuran, tebal=False):
    for pasangan in HURUF:
        try:
            return ImageFont.truetype(pasangan[tebal], ukuran * K)
        except OSError:
            continue
    return ImageFont.load_default(ukuran * K)


@lru_cache(maxsize=1)
def daratan():
    hasil = []
    for f in json.loads((DATA / "daratan.geojson").read_text(encoding="utf-8"))["features"]:
        g = f["geometry"]
        for p in (g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]):
            xs, ys = [t[0] for t in p[0]], [t[1] for t in p[0]]
            hasil.append(((min(xs), min(ys), max(xs), max(ys)), p[0]))
    return hasil


def tumpang(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


class Kanvas:
    """Semua ukuran yang diterima dan dikembalikan memakai ukuran akhir (1600x900)."""

    def __init__(self, kotak):
        lon0, lat0, lon1, lat1 = kotak
        self.s = min(LEBAR / (lon1 - lon0), TINGGI / (lat1 - lat0))
        self.clon, self.clat = (lon0 + lon1) / 2, (lat0 + lat1) / 2
        w, h = LEBAR / self.s / 2, TINGGI / self.s / 2
        self.lihat = (self.clon - w, self.clat - h, self.clon + w, self.clat + h)
        self.img = Image.new("RGBA", (LEBAR * K, TINGGI * K), LAUT + (255,))
        self.d = ImageDraw.Draw(self.img)
        self.terlarang = [(0, TINGGI - KAKI, LEBAR, TINGGI)]  # area panel: penanda & label tidak ditaruh di sini
        self.label_ada = []
        self.titik_api = []  # posisi titik api, supaya tanda air tidak menutupinya

    # --- dasar ---
    def xy(self, lon, lat):
        return LEBAR / 2 + (lon - self.clon) * self.s, TINGGI / 2 - (lat - self.clat) * self.s

    def tampak(self, kotak):
        x0, y0, x1, y1 = kotak
        a, b, c, d = self.lihat
        return x1 >= a and x0 <= c and y1 >= b and y0 <= d

    def bebas(self, x, y, jarak=0):
        return 0 <= x <= LEBAR and 0 <= y <= TINGGI and \
            not any(tumpang((x - jarak, y - jarak, x + jarak, y + jarak), t) for t in self.terlarang)

    def lapis(self):
        return Image.new("RGBA", self.img.size, (0, 0, 0, 0))

    def cincin(self, titik, isi=None, garis=None, tebal=1.0):
        p = [(x * K, y * K) for x, y in (self.xy(t[0], t[1]) for t in titik)]
        if len(p) < 3:
            return
        if isi:
            self.d.polygon(p, fill=isi)
        if garis:
            self.d.line(p + [p[0]], fill=garis, width=max(1, round(tebal * K)), joint="curve")

    def peta_dasar(self, wilayah, batas_kab=False):
        for kotak, titik in daratan():
            if self.tampak(kotak):
                self.cincin(titik, isi=DARAT_LAIN)
        prov = [(kotak, semua) for _, _, kotak, semua in wilayah.prov.bagian if self.tampak(kotak)]
        for _, semua in prov:
            for c in semua:
                self.cincin(c, isi=DARAT)
        if batas_kab:
            for _, _, kotak, semua in wilayah.kab.bagian:
                if self.tampak(kotak):
                    for c in semua:
                        self.cincin(c, garis=BATAS_KAB, tebal=0.8)
        for _, semua in prov:
            for c in semua:
                self.cincin(c, garis=BATAS_PROV, tebal=1.2)

    def tanda_air(self, x, y):
        """@AlarmBencana transparan di dekat pokok gambar, supaya tidak bisa dipotong tanpa ikut memotong isinya."""
        f, isi = huruf(30, True), "@AlarmBencana"
        lebar = self.lebar_teks(isi, f)
        calon = []
        for jarak in (70, 110, 160, 220):  # makin jauh kalau dekat-dekat penuh titik api
            for ax, ay in ((0, 1), (0, -1), (1, 0.6), (-1, 0.6), (1, -0.6), (-1, -0.6)):
                dx = ax * (jarak + lebar / 2)
                dy = ay * jarak
                kotak = [v / K for v in self.d.textbbox(((x + dx) * K, (y + dy) * K), isi, font=f, anchor="mm")]
                if kotak[0] < 10 or kotak[2] > LEBAR - 10 or kotak[1] < 10 or kotak[3] > TINGGI - KAKI - 10:
                    continue
                if any(tumpang(kotak, t) for t in self.terlarang + self.label_ada):
                    continue
                longgar = (kotak[0] - 18, kotak[1] - 18, kotak[2] + 18, kotak[3] + 18)
                kena = sum(longgar[0] <= px <= longgar[2] and longgar[1] <= py <= longgar[3] for px, py in self.titik_api)
                calon.append((kena, jarak, dx, dy, kotak))
                if kena == 0:
                    break
            if calon and calon[-1][0] == 0:
                break
        if calon:
            _, _, dx, dy, kotak = min(calon, key=lambda c: (c[0], c[1]))  # paling sedikit menutupi titik api
        else:
            dx, dy = 0, 70
            kotak = [v / K for v in self.d.textbbox(((x + dx) * K, (y + dy) * K), isi, font=f, anchor="mm")]
        self.label_ada.append(kotak)
        l = self.lapis()
        ImageDraw.Draw(l).text(((x + dx) * K, (y + dy) * K), isi, font=f, fill=(255, 255, 255, 100), anchor="mm")
        self.img.alpha_composite(l)

    def nama_wilayah(self, wilayah):
        """Nama kabupaten/kota redup di tengah wilayahnya (dipanggil setelah label penting)."""
        f = huruf(15)
        for nama, _, kotak, semua in wilayah.kab.bagian:
            if not self.tampak(kotak):
                continue
            c = max(semua, key=len)
            x = sum(t[0] for t in c) / len(c)
            y = sum(t[1] for t in c) / len(c)
            px, py = self.xy(x, y)
            kotak_teks = [v / K for v in self.d.textbbox((px * K, py * K), nama, font=f, anchor="mm")]
            if kotak_teks[0] < 6 or kotak_teks[2] > LEBAR - 6 or kotak_teks[1] < 6 or kotak_teks[3] > TINGGI - 6:
                continue
            if any(tumpang(kotak_teks, t) for t in self.terlarang + self.label_ada):
                continue
            self.label_ada.append(kotak_teks)
            self.d.text((px * K, py * K), nama, font=f, fill=(118, 130, 158), anchor="mm")

    # --- isi peta ---
    def api(self, titik, terang=True):
        """titik: daftar (lat, lon). Yang terang (baru) diberi cahaya berpijar dan cincin."""
        titik = [self.xy(lon, lat) for lat, lon in titik]
        self.titik_api += titik
        if not titik:
            return
        if terang:
            l = self.lapis()
            d = ImageDraw.Draw(l)
            for x, y in titik:
                d.ellipse(((x - 12) * K, (y - 12) * K, (x + 12) * K, (y + 12) * K), fill=API_PIJAR + (160,))
            self.img.alpha_composite(l.filter(ImageFilter.GaussianBlur(8 * K)))
        r = 3.4 if terang else 2.0
        for x, y in titik:
            self.d.ellipse(((x - r) * K, (y - r) * K, (x + r) * K, (y + r) * K), fill=API_INTI if terang else API_LAMA)

    def alat(self, lon, lat, tingkat, besar=False):
        x, y = self.xy(lon, lat)
        r = 15 if besar else 8
        if not self.bebas(x, y, r):
            return None
        self.d.ellipse(((x - r) * K, (y - r) * K, (x + r) * K, (y + r) * K), fill=WARNA_TINGKAT[tingkat],
                       outline=TEKS, width=(3 if besar else 2) * K)
        self.label_ada.append((x - r, y - r, x + r, y + r))
        return x, y, r

    def label(self, x, y, r, isi, font):
        """Taruh label di kanan/kiri/atas/bawah penanda, di tempat yang tidak bertabrakan."""
        for jx, jy, anchor in ((x + r + 6, y, "lm"), (x - r - 6, y, "rm"), (x, y - r - 4, "mb"), (x, y + r + 4, "mt")):
            kotak = [v / K for v in self.d.textbbox((jx * K, jy * K), isi, font=font, anchor=anchor, stroke_width=3 * K)]
            if kotak[0] < 6 or kotak[2] > LEBAR - 6 or kotak[1] < 6 or kotak[3] > TINGGI - 6:
                continue
            if any(tumpang(kotak, t) for t in self.terlarang + self.label_ada):
                continue
            self.label_ada.append(kotak)
            self.d.text((jx * K, jy * K), isi, font=font, fill=TEKS, anchor=anchor, stroke_width=3 * K, stroke_fill=LAUT)
            return True
        return False

    # --- panel ---
    def teks(self, xy, isi, font, warna=TEKS, anchor="la"):
        self.d.text((xy[0] * K, xy[1] * K), isi, font=font, fill=warna, anchor=anchor)

    def lebar_teks(self, isi, font):
        return self.d.textlength(isi, font=font) / K

    def panel(self, kotak, sudut=18, warna=PANEL):
        l = self.lapis()
        ImageDraw.Draw(l).rounded_rectangle([v * K for v in kotak], radius=sudut * K, fill=warna)
        self.img.alpha_composite(l)

    def kaki(self, sumber):
        l = self.lapis()
        ImageDraw.Draw(l).rectangle((0, (TINGGI - KAKI) * K, LEBAR * K, TINGGI * K), fill=(6, 10, 20, 240))
        self.img.alpha_composite(l)
        self.teks((24, TINGGI - KAKI / 2), sumber, huruf(16), REDUP, anchor="lm")

    def simpan(self, berkas):
        berkas.parent.mkdir(parents=True, exist_ok=True)
        self.img.convert("RGB").resize((LEBAR, TINGGI), Image.LANCZOS).save(berkas, optimize=True)
        return berkas


class Kotak:
    """Panel teks: diukur dulu (supaya areanya bisa dikosongkan), digambar paling akhir."""

    def __init__(self, kv, isi, x, y, kanan=False, bawah=False, jarak=30, lebar_min=0):
        self.kv, self.isi = kv, isi  # isi: daftar (teks, font, warna, tinggi_baris)
        lebar = max([lebar_min] + [kv.lebar_teks(t, f) for t, f, _, _ in isi if t]) + 48
        tinggi = sum(h for *_, h in isi) + 40
        x0 = LEBAR - x - lebar if kanan else x
        y0 = TINGGI - KAKI - y - tinggi if bawah else y
        self.kotak = (x0, y0, x0 + lebar, y0 + tinggi)
        kv.terlarang.append(self.kotak)

    def gambar(self, sebelum_teks=None):
        kv = self.kv
        kv.panel(self.kotak)
        if sebelum_teks:
            sebelum_teks(self.kotak)
        y = self.kotak[1] + 20
        for t, f, w, h in self.isi:
            if t:
                kv.teks((self.kotak[0] + 24, y + h / 2), t, f, w, anchor="lm")
            y += h


def baris_merek():
    """Nama akun di dalam panel judul: ikut terbawa ke mana pun isi pentingnya disebar."""
    return ("@AlarmBencana", huruf(23, True), TEKS, 36)


def legenda(kv, isi):
    """isi: daftar (jenis, warna, keterangan); jenis 'alat', 'api', atau 'api_lama'. Pojok kanan bawah."""
    f = huruf(18)
    p = Kotak(kv, [(f"     {ket}", f, TEKS, 30) for _, _, ket in isi], 24, 18, kanan=True, bawah=True)

    def penanda(kotak):
        for i, (jenis, warna, _) in enumerate(isi):
            cx, cy = kotak[0] + 34, kotak[1] + 35 + 30 * i
            if jenis == "api":
                l = kv.lapis()
                ImageDraw.Draw(l).ellipse(((cx - 10) * K, (cy - 10) * K, (cx + 10) * K, (cy + 10) * K), fill=API_PIJAR + (170,))
                kv.img.alpha_composite(l.filter(ImageFilter.GaussianBlur(5 * K)))
                kv.d.ellipse(((cx - 3.4) * K, (cy - 3.4) * K, (cx + 3.4) * K, (cy + 3.4) * K), fill=API_INTI)
            elif jenis == "api_lama":
                kv.d.ellipse(((cx - 2.4) * K, (cy - 2.4) * K, (cx + 2.4) * K, (cy + 2.4) * K), fill=API_LAMA)
            else:
                kv.d.ellipse(((cx - 8) * K, (cy - 8) * K, (cx + 8) * K, (cy + 8) * K), fill=warna, outline=TEKS, width=2 * K)
    return p, penanda


def isi_tingkat():
    return [("alat", WARNA_TINGKAT[i], NAMA_TINGKAT[i]) for i in range(4, -1, -1)]


def kotak_sekitar(titik, min_lon=7.0, min_lat=4.0, pinggir=1.2):
    """Kotak peta yang memuat semua titik (lat, lon), dengan ruang kosong di kiri untuk panel judul."""
    lats, lons = [t[0] for t in titik], [t[1] for t in titik]
    lon0, lon1 = min(lons) - pinggir, max(lons) + pinggir
    lat0, lat1 = min(lats) - pinggir, max(lats) + pinggir
    if lon1 - lon0 < min_lon:
        c = (lon0 + lon1) / 2
        lon0, lon1 = c - min_lon / 2, c + min_lon / 2
    if lat1 - lat0 < min_lat:
        c = (lat0 + lat1) / 2
        lat0, lat1 = c - min_lat / 2, c + min_lat / 2
    return lon0 - (lon1 - lon0) * 0.45, lat0 - (lat1 - lat0) * 0.08, lon1 + (lon1 - lon0) * 0.05, lat1 + (lat1 - lat0) * 0.08


# ---------- tiga jenis gambar ----------

def peta_ringkasan(wilayah, stasiun, api24, waktu, berkas, kategori, nama_tempat):
    kv = Kanvas((91.0, -12.5, 141.5, 8.5))
    judul = Kotak(kv, [("KUALITAS UDARA & TITIK API", huruf(42, True), TEKS, 56), (waktu, huruf(24), REDUP, 36), baris_merek()], 28, 24)
    urut = sorted(stasiun, key=lambda h: h["ug"])
    terburuk = list(reversed(urut[-5:]))
    daftar = Kotak(kv, [("Udara terburuk saat ini (PM2.5)", huruf(20, True), REDUP, 34)] +
                   [(f"{i + 1}.  {nama_tempat(h)}  —  {h['ug']:.0f} µg/m³", huruf(21), TEKS, 32)
                    for i, h in enumerate(terburuk)], 28, 18, bawah=True)
    leg, penanda = legenda(kv, isi_tingkat() + [("api", None, f"Titik api 24 jam ({len(api24)})")])

    kv.peta_dasar(wilayah)
    kv.api(api24)
    posisi = {id(h): kv.alat(h["lon"], h["lat"], kategori(h["ug"])) for h in urut}
    for h in terburuk:  # angka untuk 5 terburuk
        if posisi[id(h)]:
            kv.label(*posisi[id(h)], f"{h['ug']:.0f}", huruf(18, True))
    pokok = posisi[id(terburuk[0])] if terburuk and posisi[id(terburuk[0])] else (LEBAR / 2, TINGGI / 2)
    kv.tanda_air(pokok[0], pokok[1])
    judul.gambar()
    daftar.gambar()
    leg.gambar(penanda)
    kv.kaki(f"Udara: alat ukur BMKG & KLH via World Air Quality Index Project (aqicn.org) · Titik api: NASA FIRMS · {SUMBER_PETA}")
    return kv.simpan(berkas)


def peta_api(wilayah, baru, lama, judul_teks, keterangan, daftar, berkas):
    """baru/lama: daftar (lat, lon); daftar: [(nama, jumlah, (lat, lon) tengah)] urut terbanyak."""
    kotak = kotak_sekitar(baru)
    kv = Kanvas(kotak)
    judul = Kotak(kv, [(judul_teks, huruf(44, True), (255, 176, 72), 58), (keterangan, huruf(24), REDUP, 40), baris_merek()] +
                  [(f"{n}: {j} titik", huruf(21), TEKS, 31) for n, j, _ in daftar[:5]] +
                  ([(f"+ {len(daftar) - 5} kabupaten lain", huruf(19), REDUP, 30)] if len(daftar) > 5 else []),
                  28, 24)
    leg, penanda = legenda(kv, [("api", None, "Titik api baru"), ("api_lama", None, "Titik api 24 jam terakhir")])

    kv.peta_dasar(wilayah, batas_kab=(kotak[2] - kotak[0]) < 18)
    kv.api(lama, terang=False)
    kv.api(baru)
    for nama, _, (lat, lon) in daftar[:5]:
        x, y = kv.xy(lon, lat)
        kv.label(x, y, 6, nama, huruf(18, True))
    kv.tanda_air(*kv.xy(daftar[0][2][1], daftar[0][2][0]))  # dekat kumpulan api terbanyak
    judul.gambar()
    leg.gambar(penanda)
    kv.kaki(f"Titik api: NASA FIRMS (VIIRS & MODIS, keyakinan tinggi) · {SUMBER_PETA}")
    return kv.simpan(berkas)


def kartu_asap(wilayah, h, stasiun, api24, tingkat, nama_tingkat, saran, tempat_teks, jam, berkas, kategori):
    kv = Kanvas((h["lon"] - 4.6, h["lat"] - 1.75, h["lon"] + 1.9, h["lat"] + 1.75))
    fs = huruf(21)
    saran_baris = [""]
    for k in saran.split():
        if kv.lebar_teks(f"{saran_baris[-1]} {k}".strip(), fs) > 440:
            saran_baris.append(k)
        else:
            saran_baris[-1] = f"{saran_baris[-1]} {k}".strip()
    warna = WARNA_TINGKAT[tingkat]
    fb = huruf(34, True)
    panel = Kotak(kv, [("", fb, TEKS, 84), (tempat_teks, huruf(28, True), TEKS, 44),
                       (f"PM2.5  {h['ug']:.0f} µg/m³", huruf(42, True), warna if tingkat != 4 else TEKS, 58),
                       (f"{jam} · alat ukur {h['sumber']}", huruf(20), REDUP, 36), baris_merek(),
                       ("Yang perlu dilakukan:", huruf(19, True), REDUP, 32)] +
                  [(b, fs, TEKS, 30) for b in saran_baris], 28, 24, lebar_min=440)
    leg, penanda = legenda(kv, isi_tingkat() + [("api", None, "Titik api 24 jam")])

    kv.peta_dasar(wilayah, batas_kab=True)
    kv.api([t for t in api24 if kv.tampak((t[1], t[0], t[1], t[0]))])
    utama = kv.alat(h["lon"], h["lat"], tingkat, besar=True)
    lain = []
    for s in sorted(stasiun, key=lambda s: -s["ug"]):
        if s is not h and kv.tampak((s["lon"], s["lat"], s["lon"], s["lat"])):
            p = kv.alat(s["lon"], s["lat"], kategori(s["ug"]))
            if p:
                lain.append((p, s))
    if utama:
        kv.label(*utama, f"{h['ug']:.0f}", huruf(24, True))
    for p, s in lain:
        kv.label(*p, f"{s['ug']:.0f}", huruf(17, True))
    kv.tanda_air(*(utama[:2] if utama else kv.xy(h["lon"], h["lat"])))
    kv.nama_wilayah(wilayah)

    def lencana(kotak):
        x, y = kotak[0] + 24, kotak[1] + 24
        lb = kv.lebar_teks(nama_tingkat, fb) + 40
        kv.d.rounded_rectangle((x * K, y * K, (x + lb) * K, (y + 62) * K), radius=12 * K, fill=warna,
                               outline=TEKS if tingkat == 4 else None, width=2 * K)
        kv.teks((x + 20, y + 31), nama_tingkat, fb, (20, 20, 20) if tingkat in (0, 2) else TEKS, anchor="lm")
    panel.gambar(lencana)
    leg.gambar(penanda)
    kv.kaki(f"Udara: alat ukur BMKG & KLH via World Air Quality Index Project (aqicn.org) · Titik api: NASA FIRMS · {SUMBER_PETA}")
    return kv.simpan(berkas)
