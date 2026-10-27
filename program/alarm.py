"""Alarm Bencana.

Mengambil data asap (alat ukur BMKG & KLH lewat WAQI) dan titik api (satelit
NASA FIRMS), memutuskan apa yang layak diunggah, lalu menulis drafnya ke layar
dan ke folder latihan/.

Pakai (dari folder proyek):
  python program/alarm.py              -> latihan: hanya draf, tidak mengunggah
  python program/alarm.py --sungguhan  -> draf juga diunggah ke X (memakai saldo X)
(Butuh Pillow untuk gambar peta; tanpa Pillow drafnya tetap jadi, hanya tanpa gambar.)
"""
import csv
import io
import json
import os
import sys
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

AKAR = Path(__file__).resolve().parent.parent
DATA = AKAR / "program" / "data"
BERKAS_KEADAAN = AKAR / "program" / "keadaan.json"
FOLDER_DRAF = AKAR / "latihan"

BATAS_KARAKTER = 280
MAKS_UNGGAHAN_SEHARI = 30
JAM_RINGKASAN_WIB = 7
DATA_BASI_JAM = 3          # data alat ukur lebih tua dari ini diabaikan
TURUN_BERTURUT = 3         # berapa kali berturut-turut membaik sebelum dianggap turun tingkat
AMAN_BERTURUT = 2          # berapa kali berturut-turut aman sebelum diumumkan "membaik"
AMBANG_API_TOTAL = 20      # minimal titik api baru se-Indonesia agar diunggah
AMBANG_API_KAB = 5         # minimal titik api baru di satu kabupaten agar namanya disebut
INGAT_SEL_API_HARI = 7     # sel yang sudah pernah terbakar tidak dihitung "baru" selama ini
TUNDA_MAKS_JAM = 3         # kiriman yang gagal dicoba lagi di jalan berikutnya, asal belum setua ini
JEDA_ASAP_MENIT = 55       # WAQI dicek kira-kira sejam sekali (janji kita ke WAQI); titik api tiap jalan

WAQI_KOTAK = "-11.5,94,6.5,141.5"
FIRMS = {  # nama satelit -> berkas 24 jam Asia Tenggara (tanpa kunci)
    "NOAA-20": "noaa-20-viirs-c2/csv/J1_VIIRS_C2_SouthEast_Asia_24h.csv",
    "NOAA-21": "noaa-21-viirs-c2/csv/J2_VIIRS_C2_SouthEast_Asia_24h.csv",
    "S-NPP": "suomi-npp-viirs-c2/csv/SUOMI_VIIRS_C2_SouthEast_Asia_24h.csv",
    "MODIS": "modis-c6.1/csv/MODIS_C6_1_SouthEast_Asia_24h.csv",
}

# Kategori PM2.5 BMKG: batas atas (µg/m³), nama, warna resmi, saran
KATEGORI = [
    (15.5, "BAIK", "🟢", ""),
    (55.4, "SEDANG", "🔵", ""),
    (150.4, "TIDAK SEHAT", "🟡", "Kurangi kegiatan di luar rumah, pakai masker"),
    (250.4, "SANGAT TIDAK SEHAT", "🔴", "Pakai masker (sebaiknya KN95), anak & lansia di dalam rumah, tutup jendela"),
    (float("inf"), "BERBAHAYA", "⚫", "Hindari keluar rumah. Kalau terpaksa, pakai masker KN95"),
]

# Batas AQI Amerika lama (dipakai WAQI) -> PM2.5 µg/m³. Sudah dicocokkan dengan angka BMKG.
AQI_KE_UG = [(0, 50, 0.0, 12.0), (51, 100, 12.1, 35.4), (101, 150, 35.5, 55.4),
             (151, 200, 55.5, 150.4), (201, 300, 150.5, 250.4),
             (301, 400, 250.5, 350.4), (401, 500, 350.5, 500.4)]

# Kode provinsi -> (nama, tagar, zona waktu)
PROVINSI = {
    "ID-AC": ("Aceh", "Aceh", "WIB"), "ID-SU": ("Sumatera Utara", "Sumut", "WIB"),
    "ID-SB": ("Sumatera Barat", "Sumbar", "WIB"), "ID-RI": ("Riau", "Riau", "WIB"),
    "ID-JA": ("Jambi", "Jambi", "WIB"), "ID-SS": ("Sumatera Selatan", "Sumsel", "WIB"),
    "ID-BE": ("Bengkulu", "Bengkulu", "WIB"), "ID-LA": ("Lampung", "Lampung", "WIB"),
    "ID-BB": ("Kepulauan Bangka Belitung", "Babel", "WIB"), "ID-KR": ("Kepulauan Riau", "Kepri", "WIB"),
    "ID-JK": ("DKI Jakarta", "Jakarta", "WIB"), "ID-JB": ("Jawa Barat", "Jabar", "WIB"),
    "ID-JT": ("Jawa Tengah", "Jateng", "WIB"), "ID-YO": ("DI Yogyakarta", "Jogja", "WIB"),
    "ID-JI": ("Jawa Timur", "Jatim", "WIB"), "ID-BT": ("Banten", "Banten", "WIB"),
    "ID-KB": ("Kalimantan Barat", "Kalbar", "WIB"), "ID-KT": ("Kalimantan Tengah", "Kalteng", "WIB"),
    "ID-KS": ("Kalimantan Selatan", "Kalsel", "WITA"), "ID-KI": ("Kalimantan Timur", "Kaltim", "WITA"),
    "ID-KU": ("Kalimantan Utara", "Kaltara", "WITA"), "ID-BA": ("Bali", "Bali", "WITA"),
    "ID-NB": ("Nusa Tenggara Barat", "NTB", "WITA"), "ID-NT": ("Nusa Tenggara Timur", "NTT", "WITA"),
    "ID-SA": ("Sulawesi Utara", "Sulut", "WITA"), "ID-ST": ("Sulawesi Tengah", "Sulteng", "WITA"),
    "ID-SN": ("Sulawesi Selatan", "Sulsel", "WITA"), "ID-SG": ("Sulawesi Tenggara", "Sultra", "WITA"),
    "ID-GO": ("Gorontalo", "Gorontalo", "WITA"), "ID-SR": ("Sulawesi Barat", "Sulbar", "WITA"),
    "ID-MA": ("Maluku", "Maluku", "WIT"), "ID-MU": ("Maluku Utara", "Malut", "WIT"),
    "ID-PA": ("Papua", "Papua", "WIT"), "ID-PB": ("Papua Barat", "PapuaBarat", "WIT"),
}
ZONA = {"WIB": 7, "WITA": 8, "WIT": 9}
BULAN = "Jan Feb Mar Apr Mei Jun Jul Agu Sep Okt Nov Des".split()


# ---------- alat bantu ----------

def baca_env():
    """Kunci dari berkas .env (laptop) atau dari brankas rahasia GitHub (variabel lingkungan)."""
    berkas = AKAR / ".env"
    isi = berkas.read_text(encoding="utf-8").splitlines() if berkas.exists() else []
    return {**dict(b.split("=", 1) for b in isi if "=" in b and not b.startswith("#")),
            **{k: v for k, v in os.environ.items() if k.startswith(("WAQI_", "X_"))}}


def ambil(url, json_=True):
    with urllib.request.urlopen(url, timeout=60) as r:
        isi = r.read().decode("utf-8")
    return json.loads(isi) if json_ else isi


def panjang_x(teks):
    """Panjang menurut hitungan X (huruf biasa 1, emoji dan sejenisnya 2). Sengaja agak boros."""
    return sum(1 if (o <= 4351 or 8192 <= o <= 8205 or 8208 <= o <= 8223 or 8242 <= o <= 8247) else 2
               for o in map(ord, teks))


def jam_lokal(waktu_utc, zona):
    return (waktu_utc + timedelta(hours=ZONA[zona])).strftime("%H.%M") + f" {zona}"


def kategori(ug):
    return next(i for i, k in enumerate(KATEGORI) if ug <= k[0])


def aqi_ke_ug(aqi):
    for alo, ahi, clo, chi in AQI_KE_UG:
        if aqi <= ahi:
            return clo + (aqi - alo) * (chi - clo) / (ahi - alo)
    return 500.4


def angka(n):
    return f"{n:,}".replace(",", ".")


# ---------- peta wilayah ----------

def di_dalam(x, y, cincin):
    hasil, j = False, len(cincin) - 1
    for i in range(len(cincin)):
        xi, yi = cincin[i][0], cincin[i][1]
        xj, yj = cincin[j][0], cincin[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            hasil = not hasil
        j = i
    return hasil


class Peta:
    """Mencari nama wilayah dari koordinat, memakai peta batas (GeoJSON)."""

    def __init__(self, berkas, sel=0.5):
        self.sel, self.bagian, self.grid = sel, [], defaultdict(list)
        for f in json.loads(berkas.read_text(encoding="utf-8"))["features"]:
            g = f["geometry"]
            cincin = [p[0] for p in (g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]])]
            xs = [t[0] for c in cincin for t in c]
            ys = [t[1] for c in cincin for t in c]
            kotak = (min(xs), min(ys), max(xs), max(ys))
            self.bagian.append((f["properties"]["shapeName"], f["properties"]["shapeISO"], kotak, cincin))
            for gx in range(int(kotak[0] // sel), int(kotak[2] // sel) + 1):
                for gy in range(int(kotak[1] // sel), int(kotak[3] // sel) + 1):
                    self.grid[gx, gy].append(len(self.bagian) - 1)

    def cari(self, lat, lon):
        for i in self.grid.get((int(lon // self.sel), int(lat // self.sel)), ()):
            nama, kode, (x0, y0, x1, y1), cincin = self.bagian[i]
            if x0 <= lon <= x1 and y0 <= lat <= y1 and any(di_dalam(lon, lat, c) for c in cincin):
                return nama, kode
        return None


class Wilayah:
    def __init__(self):
        self.kab = Peta(DATA / "kabupaten.geojson")
        self.prov = Peta(DATA / "provinsi.geojson")

    def cari(self, lat, lon):
        """-> (nama tampilan kabupaten/kota, kode provinsi) atau None kalau di luar Indonesia."""
        kab = self.kab.cari(lat, lon)
        if not kab:
            return None
        prov = self.prov.cari(lat, lon)
        nama = kab[0] if kab[0].startswith("Kota ") else f"Kab. {kab[0]}"
        return nama, prov[1] if prov else None


def tempat(nama, kode):
    return f"{nama}, {PROVINSI[kode][1]}" if kode in PROVINSI else nama


def zona_dari(kode):
    return PROVINSI[kode][2] if kode in PROVINSI else "WIB"


# ---------- sumber data ----------

def ambil_asap(token, wilayah):
    """Alat ukur di Indonesia, dikelompokkan per kabupaten (diambil yang terburuk)."""
    peta = ambil(f"https://api.waqi.info/map/bounds?latlng={WAQI_KOTAK}&networks=all&token={token}")["data"]
    calon = []
    for s in peta:
        w = wilayah.cari(s["lat"], s["lon"])
        if w or "Indonesia" in s["station"]["name"]:
            calon.append((s, w))

    def rinci(item):
        s, w = item
        kode = f"@{s['uid']}" if s["uid"] > 0 else f"A{-s['uid']}"
        try:
            d = ambil(f"https://api.waqi.info/feed/{kode}/?token={token}")
        except Exception:
            return None
        if d.get("status") != "ok" or d["data"].get("iaqi", {}).get("pm25", {}).get("v", 0) < 1:
            return None  # tidak ada PM2.5, atau angkanya 0 (alat kemungkinan rusak)
        x = d["data"]
        pemilik = " ".join(a["name"] for a in x.get("attributions", []))
        sumber = "BMKG" if "BMKG" in pemilik else "KLH" if "Lingkungan" in pemilik else "alat ukur lokal"
        nama, prov = w if w else (x["city"]["name"].replace(", Indonesia", ""), None)
        return {"kab": nama, "prov": prov, "ug": round(aqi_ke_ug(x["iaqi"]["pm25"]["v"]), 1),
                "waktu": datetime.fromisoformat(x["time"]["iso"]).astimezone(timezone.utc), "sumber": sumber,
                "stasiun": x["city"]["name"], "lat": s["lat"], "lon": s["lon"]}

    with ThreadPoolExecutor(8) as kerja:
        hasil = [h for h in kerja.map(rinci, calon) if h]

    sekarang = datetime.now(timezone.utc)
    segar = [h for h in hasil if -1 <= (sekarang - h["waktu"]).total_seconds() / 3600 <= DATA_BASI_JAM]
    ragu = [h for h in segar if diragukan(h, segar)]
    dipakai = [h for h in segar if h not in ragu]
    per_kab = {}
    for h in dipakai:
        if h["kab"] not in per_kab or h["ug"] > per_kab[h["kab"]]["ug"]:
            per_kab[h["kab"]] = h
    return per_kab, ragu, dipakai


def diragukan(h, semua):
    """Angka sangat tinggi padahal semua alat tetangga (≤60 km) jauh lebih rendah: kemungkinan alatnya bermasalah.

    Keputusan user (27 Okt 2026): kalau salah satunya alat BMKG, ikuti BMKG. Kalau dua-duanya KLH, tahan.
    """
    if kategori(h["ug"]) < 3 or h["sumber"] == "BMKG":
        return False
    tetangga = [s for s in semua if s is not h
                and ((s["lat"] - h["lat"]) ** 2 + (s["lon"] - h["lon"]) ** 2) ** 0.5 * 111 <= 60]
    return bool(tetangga) and all(s["ug"] < h["ug"] / 4 for s in tetangga)


def ambil_api(wilayah):
    """Semua deteksi titik api keyakinan tinggi di Indonesia, 24 jam terakhir."""
    titik, gagal = [], []
    for satelit, jalur in FIRMS.items():
        try:
            teks = ambil(f"https://firms.modaps.eosdis.nasa.gov/data/active_fire/{jalur}", json_=False)
        except Exception:
            gagal.append(satelit)  # satu satelit gagal tidak apa-apa, ambil sisanya
            continue
        for b in csv.DictReader(io.StringIO(teks)):
            yakin = b["confidence"]
            tinggi = yakin.startswith("h") if satelit != "MODIS" else yakin.isdigit() and int(yakin) >= 80
            lat, lon = float(b["latitude"]), float(b["longitude"])
            if not tinggi or not (-11.5 <= lat <= 6.5 and 94 <= lon <= 141.5):
                continue
            waktu = datetime.strptime(f"{b['acq_date']} {b['acq_time'].zfill(4)}", "%Y-%m-%d %H%M").replace(tzinfo=timezone.utc)
            titik.append({"satelit": satelit, "waktu": waktu, "sel": f"{lat:.2f},{lon:.2f}"})
    if len(gagal) == len(FIRMS):
        raise RuntimeError("semua berkas satelit gagal diambil")
    # Satu sel ±1 km = satu titik api; cari wilayahnya sekali per sel
    sel_wilayah = {}
    for t in titik:
        if t["sel"] not in sel_wilayah:
            lat, lon = map(float, t["sel"].split(","))
            sel_wilayah[t["sel"]] = wilayah.cari(lat, lon)
    return [dict(t, wilayah=sel_wilayah[t["sel"]]) for t in titik if sel_wilayah[t["sel"]]]


# ---------- aturan & bentuk unggahan ----------

# Semua teks dibuat untuk dibaca sekilas: tempat dan warna dulu, tanpa angka teknis (angkanya ada di gambar).

def unggahan_asap(h, membaik=False):
    batas, nama, warna, saran = KATEGORI[kategori(h["ug"])]
    jam = jam_lokal(h["waktu"], zona_dari(h["prov"]))
    tagar = "#KabutAsap" + (f" #{PROVINSI[h['prov']][1]}" if h["prov"] in PROVINSI else "")
    tempatnya = tempat(h["kab"].removeprefix("Kab. "), h["prov"])
    sumber = f"🕐 {jam} · alat ukur {h['sumber']} via WAQI"
    if membaik:
        return f"{warna} Udara MEMBAIK di {tempatnya}\nSekarang: {nama.capitalize()}\n{sumber}\n{tagar}"
    return f"{warna} Udara {nama} di {tempatnya}\n😷 {saran}\n{sumber}\n{tagar}"


def susun_daftar(kepala, baris, ekor, satuan="lokasi"):
    """Isi baris sebanyak mungkin tanpa melewati batas karakter X."""
    isi, sisa = [], len(baris)
    for b in baris:
        lain = sisa - 1
        calon = "\n".join([kepala, *isi, b] + ([f"+ {lain} {satuan} lain"] if lain else []) + [ekor])
        if panjang_x(calon) > BATAS_KARAKTER:
            break
        isi.append(b)
        sisa -= 1
    return "\n".join([kepala, *isi] + ([f"+ {sisa} {satuan} lain"] if sisa else []) + [ekor])


def susun_per_warna(kepala, daftar, ekor):
    """Tempat dikelompokkan per warna. Kalau kepanjangan, nama dari warna teringan dipangkas duluan."""
    per_tingkat = defaultdict(list)
    for h in sorted(daftar, key=lambda h: -h["ug"]):
        per_tingkat[kategori(h["ug"])].append(h)

    def susun(maks):  # maks: berapa nama tempat untuk (berbahaya, sangat tidak sehat, tidak sehat)
        baris = []
        for i, m in zip((4, 3, 2), maks):
            semua = per_tingkat[i]
            if semua:
                nama = [h["kab"].removeprefix("Kab. ") for h in semua[:m]]
                lain = len(semua) - len(nama)
                isi = ", ".join(nama) + (f" +{lain} lagi" if lain else "") if nama else f"{lain} lokasi"
                baris.append(f"{KATEGORI[i][2]} {KATEGORI[i][1].capitalize()}: {isi}")
        if not baris:
            baris = ["🟢 Belum ada alat ukur yang menunjukkan udara tidak sehat"]
        return "\n".join([kepala, "", *baris, "", *ekor])

    pilihan = [(3, 3, 3), (3, 3, 2), (3, 3, 0), (3, 2, 0), (2, 2, 0), (2, 1, 0), (1, 1, 0), (1, 0, 0), (0, 0, 0)]
    return next((t for t in map(susun, pilihan) if panjang_x(t) <= BATAS_KARAKTER), susun((0, 0, 0)))


def aturan_asap(per_kab, keadaan, pertama):
    """Kapan memburuk/membaik diumumkan. Mengubah keadaan."""
    simpan = keadaan.setdefault("asap", {})
    memburuk, membaik = [], []
    for kab, h in per_kab.items():
        tingkat = kategori(h["ug"])
        # Naik tingkat baru dihitung kalau 10% di atas batasnya, supaya angka yang mondar-mandir
        # di sekitar batas tidak membuat unggahan berulang-ulang
        naik = max(i for i in range(len(KATEGORI)) if i == 0 or h["ug"] >= KATEGORI[i - 1][0] * 1.1)
        k = simpan.setdefault(kab, {"tingkat_unggah": tingkat if pertama else 1, "turun": 0, "aman": 0})
        if naik >= 2 and naik > k["tingkat_unggah"]:
            memburuk.append(h)
            k.update(tingkat_unggah=naik, turun=0, aman=0)
        elif k["tingkat_unggah"] >= 2 and tingkat <= 1:
            k["aman"] += 1
            if k["aman"] >= AMAN_BERTURUT:
                membaik.append(h)
                k.update(tingkat_unggah=tingkat, turun=0, aman=0)
        elif tingkat < k["tingkat_unggah"]:
            k["turun"] += 1
            if k["turun"] >= TURUN_BERTURUT:  # diam-diam turunkan, supaya kalau memburuk lagi diumumkan lagi
                k.update(tingkat_unggah=tingkat, turun=0)
        else:
            k.update(turun=0, aman=0)

    memburuk.sort(key=lambda h: -h["ug"])
    sendiri = memburuk[:3] if len(memburuk) == 3 else memburuk[:2]
    hasil = [{"jenis": "asap", "teks": unggahan_asap(h), "fokus": h} for h in sendiri]
    if len(memburuk) > 3:
        sisanya = memburuk[2:]
        hasil.append({"jenis": "asap_gabung", "teks": susun_per_warna(
            f"⚠️ Udara MEMBURUK di {len(sisanya)} lokasi lain", sisanya,
            ["😷 Pakai masker, kurangi kegiatan di luar rumah", "Data: BMKG & KLH via WAQI #KabutAsap"])})
    hasil += [{"jenis": "membaik", "teks": unggahan_asap(h, membaik=True), "fokus": h} for h in membaik]
    return hasil


def aturan_api(titik, keadaan, sekarang):
    """Titik api BARU = deteksi setelah jalan terakhir, di sel yang belum pernah terbakar seminggu ini."""
    simpan = keadaan.setdefault("api", {"terakhir": {}, "sel": {}})
    terakhir, pernah = simpan["terakhir"], simpan["sel"]
    if not terakhir:  # jalan pertama: anggap yang lebih lama dari 1 jam sudah "lama"
        batas = sekarang - timedelta(hours=1)
        for t in titik:
            if t["waktu"] <= batas:
                pernah[t["sel"]] = t["waktu"].isoformat()
        terakhir.update({s: batas.isoformat() for s in FIRMS})

    baru = {}
    for t in titik:
        if t["waktu"] > datetime.fromisoformat(terakhir.get(t["satelit"], "2000-01-01T00:00:00+00:00")):
            if t["sel"] not in pernah and t["sel"] not in baru:
                baru[t["sel"]] = t
    for t in titik:
        s = t["satelit"]
        if t["waktu"].isoformat() > terakhir.get(s, ""):
            terakhir[s] = t["waktu"].isoformat()
        pernah.setdefault(t["sel"], t["waktu"].isoformat())
    lupa = (sekarang - timedelta(days=INGAT_SEL_API_HARI)).isoformat()
    simpan["sel"] = {k: v for k, v in pernah.items() if v >= lupa}

    if len(baru) < AMBANG_API_TOTAL:
        return [], len(baru)
    per_kab = defaultdict(int)
    for t in baru.values():
        per_kab[t["wilayah"]] += 1
    urut = sorted(per_kab.items(), key=lambda x: -x[1])
    baris = [f"📍 {tempat(*w).removeprefix('Kab. ')}: {n}" for w, n in urut if n >= AMBANG_API_KAB] or \
        [f"📍 {tempat(*w).removeprefix('Kab. ')}: {n}" for w, n in urut[:3]]  # api tersebar: sebut 3 teratas saja
    jam = jam_lokal(max(t["waktu"] for t in baru.values()), "WIB")
    teks = susun_daftar(f"🔥 {angka(len(baru))} TITIK API BARU terpantau satelit\n",
                        baris, f"\n🕐 {jam} · NASA, keyakinan tinggi\n#Karhutla", satuan="kabupaten")
    titik_baru = [tuple(map(float, s.split(","))) for s in baru]
    tengah = defaultdict(list)
    for s, t in baru.items():
        tengah[t["wilayah"]].append(tuple(map(float, s.split(","))))
    daftar = [(tempat(*w), n, (sum(p[0] for p in tengah[w]) / n, sum(p[1] for p in tengah[w]) / n)) for w, n in urut]
    return [{"jenis": "api", "teks": teks, "baru": titik_baru, "daftar": daftar,
             "keterangan": f"{angka(len(baru))} titik · {jam}"}], len(baru)


def ringkasan(per_kab, titik, sekarang):
    tgl = sekarang + timedelta(hours=7)
    sel24 = {t["sel"] for t in titik if t["waktu"] > sekarang - timedelta(hours=24)}
    parah = any(kategori(h["ug"]) >= 3 for h in per_kab.values())
    ekor = [f"🔥 {angka(len(sel24))} titik api dalam 24 jam"] + \
        (["😷 Zona hitam/merah: pakai masker, tutup jendela"] if parah else []) + ["#KabutAsap #Karhutla"]
    return {"jenis": "ringkasan", "teks": susun_per_warna(
        f"🌫️ KABUT ASAP HARI INI · {tgl.day} {BULAN[tgl.month - 1]}, {tgl:%H.%M} WIB", per_kab.values(), ekor)}


def buat_gambar(d, wilayah, stasiun, titik, sekarang, berkas):
    """Gambar peta untuk satu draf. Gagal menggambar tidak boleh menghentikan teksnya."""
    import gambar  # butuh Pillow
    api24 = sorted({tuple(map(float, t["sel"].split(","))) for t in titik
                    if t["waktu"] > sekarang - timedelta(hours=24)})
    if d["jenis"] in ("ringkasan", "asap_gabung"):
        t = sekarang + timedelta(hours=7)
        return gambar.peta_ringkasan(wilayah, stasiun, api24, f"{t.day} {BULAN[t.month - 1]} {t.year}, {t:%H.%M} WIB",
                                     berkas, kategori, lambda h: tempat(h["kab"].removeprefix("Kab. "), h["prov"]))
    if d["jenis"] == "api":
        baru = set(d["baru"])
        return gambar.peta_api(wilayah, d["baru"], [p for p in api24 if p not in baru], "TITIK API BARU",
                               d["keterangan"], d["daftar"], berkas)
    h = d["fokus"]
    tingkat = kategori(h["ug"])
    saran = KATEGORI[tingkat][3] if d["jenis"] == "asap" else "Udara membaik. Tetap pantau, keadaan bisa cepat berubah."
    nama = ("MEMBAIK · " if d["jenis"] == "membaik" else "") + KATEGORI[tingkat][1]
    return gambar.kartu_asap(wilayah, h, stasiun, api24, tingkat, nama, saran, tempat(h["kab"], h["prov"]),
                             jam_lokal(h["waktu"], zona_dari(h["prov"])), berkas, kategori)


# ---------- jalan sekali ----------

def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sungguhan = "--sungguhan" in sys.argv
    sekarang = datetime.now(timezone.utc)
    keadaan = json.loads(BERKAS_KEADAAN.read_text(encoding="utf-8")) if BERKAS_KEADAAN.exists() else {}
    pertama = not keadaan
    gagal = keadaan.setdefault("gagal", {"WAQI": 0, "NASA": 0})
    wilayah = Wilayah()
    peringatan = []

    per_kab, stasiun = {}, []
    terakhir_asap = keadaan.get("cek_asap")
    if not terakhir_asap or sekarang - datetime.fromisoformat(terakhir_asap) >= timedelta(minutes=JEDA_ASAP_MENIT):
        keadaan["cek_asap"] = sekarang.isoformat()
        try:
            per_kab, ragu, stasiun = ambil_asap(baca_env()["WAQI_TOKEN"].strip(), wilayah)
            gagal["WAQI"] = 0
            for h in ragu:
                peringatan.append(f"Diragukan, tidak diunggah: {h['stasiun']} ({h['sumber']}) {h['ug']:.0f} µg/m³, "
                                  "padahal alat-alat di sekitarnya jauh lebih rendah. Perlu dicek manusia.")
        except Exception as e:
            gagal["WAQI"] += 1
            peringatan.append(f"WAQI gagal ({e})")
    else:
        peringatan.append("Asap tidak dicek kali ini (sudah dicek kurang dari sejam lalu); hanya titik api.")
    try:
        titik = ambil_api(wilayah)
        gagal["NASA"] = 0
    except Exception as e:
        titik = []
        gagal["NASA"] += 1
        peringatan.append(f"NASA gagal ({e})")
    for nama, n in gagal.items():
        if n >= 3:
            peringatan.append(f"⚠ {nama} sudah gagal {n} kali berturut-turut. Akun sedang 'buta' untuk sumber ini.")

    draf = []
    hari_wib = (sekarang + timedelta(hours=7)).date().isoformat()
    # ">=" bukan "==": kalau jalan jam 7 terlambat atau gagal, ringkasan tetap keluar di jalan berikutnya
    if pertama or ((sekarang + timedelta(hours=7)).hour >= JAM_RINGKASAN_WIB and keadaan.get("ringkasan") != hari_wib):
        if per_kab:
            draf.append(ringkasan(per_kab, titik, sekarang))
            keadaan["ringkasan"] = hari_wib
    if per_kab:
        draf += aturan_asap(per_kab, keadaan, pertama)
    api_baru = 0
    if titik:
        unggah_api, api_baru = aturan_api(titik, keadaan, sekarang)
        draf += unggah_api

    hitung = keadaan.setdefault("unggahan", {})
    sudah = hitung.get(hari_wib, 0)
    lewat = max(0, sudah + len(draf) - MAKS_UNGGAHAN_SEHARI)
    if lewat:
        peringatan.append(f"Batas {MAKS_UNGGAHAN_SEHARI} unggahan/hari tercapai, {lewat} draf dibuang.")
        draf = draf[:len(draf) - lewat]
    hitung[hari_wib] = sudah + len(draf)
    keadaan["unggahan"] = {k: v for k, v in hitung.items() if k >= (sekarang - timedelta(days=7)).date().isoformat()}

    # laporan
    jam = (sekarang + timedelta(hours=7)).strftime("%Y-%m-%d %H.%M WIB")
    laporan = [f"===== Jalan {jam} · {len(per_kab)} lokasi alat ukur · "
               f"{len({t['sel'] for t in titik})} titik api 24 jam · {api_baru} titik api baru · "
               f"{len(draf)} draf (hari ini {hitung[hari_wib]}) ====="]
    laporan += [f"!! {p}" for p in peringatan]
    antre = [x for x in keadaan.get("tertunda", [])
             if datetime.fromisoformat(x["waktu"]) > sekarang - timedelta(hours=TUNDA_MAKS_JAM)] if sungguhan else []
    if antre:
        laporan.append(f"(mencoba lagi {len(antre)} kiriman yang tadi gagal)")
    for i, d in enumerate(draf, 1):
        berkas = FOLDER_DRAF / "gambar" / f"{sekarang + timedelta(hours=7):%Y%m%d-%H%M}-{i}-{d['jenis']}.png"
        try:
            gb = buat_gambar(d, wilayah, stasiun, titik, sekarang, berkas)
            ket_gambar = f"gambar: latihan/gambar/{gb.name}"
        except Exception as e:
            gb, ket_gambar = None, f"gambar GAGAL dibuat ({e}); teks tetap bisa diunggah"
        antre.append({"teks": d["teks"], "gambar": str(gb) if gb else None, "waktu": sekarang.isoformat()})
        laporan += ["", d["teks"], f"   [{panjang_x(d['teks'])}/{BATAS_KARAKTER} karakter · {ket_gambar}]"]
    if not draf:
        laporan.append("(tidak ada yang perlu diunggah)")
    if sungguhan:
        import kirim_x
        for n, x in enumerate(antre):
            try:
                nomor = kirim_x.kirim(x["teks"], x["gambar"] if x["gambar"] and Path(x["gambar"]).exists() else None)
                laporan.append(f">> TERKIRIM https://x.com/AlarmBencana/status/{nomor}  ({x['teks'][:40]}…)")
            except Exception as e:
                laporan.append(f"!! GAGAL kirim ke X: {e}. {len(antre) - n} kiriman dicoba lagi di jalan berikutnya.")
                antre = antre[n:]
                break
        else:
            antre = []
        keadaan["tertunda"] = antre
    teks = "\n".join(laporan) + "\n\n"
    print(teks)
    FOLDER_DRAF.mkdir(exist_ok=True)
    with open(FOLDER_DRAF / f"draf-{hari_wib}.txt", "a", encoding="utf-8") as f:
        f.write(teks)
    BERKAS_KEADAAN.write_text(json.dumps(keadaan, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
