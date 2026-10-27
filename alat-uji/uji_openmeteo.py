"""Bandingkan perkiraan PM2.5 Open-Meteo dengan alat ukur (WAQI) di Indonesia.

Pakai: python -I uji_openmeteo.py <folder proyek> <folder keluaran>
"""
import json
import sys
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

PROYEK, KELUAR = Path(sys.argv[1]), Path(sys.argv[2])
KELUAR.mkdir(parents=True, exist_ok=True)
TOKEN = next(l.split("=", 1)[1].strip() for l in (PROYEK / ".env").read_text().splitlines()
             if l.startswith("WAQI_TOKEN="))

# Batas AQI Amerika lama (yang dipakai WAQI) -> konsentrasi PM2.5 ug/m3
AQI_KE_UG = [(0, 50, 0.0, 12.0), (51, 100, 12.1, 35.4), (101, 150, 35.5, 55.4),
             (151, 200, 55.5, 150.4), (201, 300, 150.5, 250.4),
             (301, 400, 250.5, 350.4), (401, 500, 350.5, 500.4)]

# Kategori PM2.5 BMKG (ug/m3)
KATEGORI = [(15.5, "Baik"), (55.4, "Sedang"), (150.4, "Tidak Sehat"),
            (250.4, "Sangat Tidak Sehat"), (float("inf"), "Berbahaya")]
URUT = [k for _, k in KATEGORI]


def ambil(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.load(r)


def aqi_ke_ug(aqi):
    for alo, ahi, clo, chi in AQI_KE_UG:
        if aqi <= ahi:
            return clo + (aqi - alo) * (chi - clo) / (ahi - alo)
    return 500.4


def kategori(ug):
    return next(k for batas, k in KATEGORI if ug <= batas)


# 1. Semua stasiun di kotak peta Indonesia
peta = ambil(f"https://api.waqi.info/map/bounds?latlng=-11.5,94,6.5,141.5&networks=all&token={TOKEN}")["data"]

stasiun = []
for s in peta:
    uid = s["uid"]
    kode = f"@{uid}" if uid > 0 else f"A{-uid}"
    try:
        d = ambil(f"https://api.waqi.info/feed/{kode}/?token={TOKEN}")
    except Exception as e:
        print("gagal", kode, e)
        continue
    if d.get("status") != "ok":
        continue
    x = d["data"]
    sumber = " / ".join(a["name"] for a in x.get("attributions", []) if "World Air" not in a["name"])
    if not any(k in sumber for k in ("BMKG", "Lingkungan", "Indonesia")) and "Indonesia" not in x["city"]["name"]:
        continue
    pm = x.get("iaqi", {}).get("pm25", {}).get("v")
    if pm is None:
        continue
    waktu = datetime.fromisoformat(x["time"]["iso"]).astimezone(timezone.utc)
    stasiun.append({"nama": x["city"]["name"], "lat": s["lat"], "lon": s["lon"], "aqi": pm,
                    "ukur": round(aqi_ke_ug(pm), 1), "waktu": waktu, "sumber": sumber})

print("stasiun Indonesia dengan PM2.5:", len(stasiun))
print("pemilik alat:", Counter("BMKG" if "BMKG" in s["sumber"] else
                               "KLH" if "Lingkungan" in s["sumber"] else s["sumber"][:30]
                               for s in stasiun))

# 2. Perkiraan Open-Meteo di titik yang sama, jam yang sama
for i in range(0, len(stasiun), 50):
    grup = stasiun[i:i + 50]
    url = ("https://air-quality-api.open-meteo.com/v1/air-quality?"
           f"latitude={','.join(str(s['lat']) for s in grup)}"
           f"&longitude={','.join(str(s['lon']) for s in grup)}"
           "&hourly=pm2_5&past_days=2&forecast_days=1&timezone=GMT")
    hasil = ambil(url)
    if isinstance(hasil, dict):
        hasil = [hasil]
    for s, h in zip(grup, hasil):
        jam = s["waktu"].strftime("%Y-%m-%dT%H:00")
        t = h["hourly"]["time"]
        s["model"] = h["hourly"]["pm2_5"][t.index(jam)] if jam in t else None

pakai = [s for s in stasiun if s.get("model") is not None]
segar = [s for s in pakai if (datetime.now(timezone.utc) - s["waktu"]).total_seconds() < 6 * 3600]
print("bisa dibandingkan:", len(pakai), "| data segar (<6 jam):", len(segar))

# 3. Ringkasan
sama = sum(kategori(s["ukur"]) == kategori(s["model"]) for s in segar)
beda1 = sum(abs(URUT.index(kategori(s["ukur"])) - URUT.index(kategori(s["model"]))) <= 1 for s in segar)
bahaya = [s for s in segar if URUT.index(kategori(s["ukur"])) >= 2]
lolos = [s for s in bahaya if URUT.index(kategori(s["model"])) < 2]
palsu = [s for s in segar if URUT.index(kategori(s["ukur"])) < 2 and URUT.index(kategori(s["model"])) >= 2]
rasio = [s["model"] / s["ukur"] for s in segar if s["ukur"] > 5]

print(f"kategori persis sama   : {sama}/{len(segar)}")
print(f"meleset maks 1 tingkat : {beda1}/{len(segar)}")
print(f"alat bilang >= Tidak Sehat: {len(bahaya)} ; model bilang aman (lolos): {len(lolos)}")
print(f"alat bilang aman, model bilang >= Tidak Sehat (alarm palsu): {len(palsu)}")
print(f"rasio model/alat: median {median(rasio):.2f}, "
      f"kuartil {sorted(rasio)[len(rasio)//4]:.2f}-{sorted(rasio)[3*len(rasio)//4]:.2f}")

print("\nContoh (alat vs model, ug/m3):")
for s in sorted(segar, key=lambda s: -s["ukur"])[:15]:
    print(f"  {s['nama'][:42]:42} alat {s['ukur']:6.1f} {kategori(s['ukur']):18} model {s['model']:6.1f} {kategori(s['model'])}")
print("Lolos (alat bahaya, model aman):")
for s in lolos:
    print(f"  {s['nama'][:42]:42} alat {s['ukur']:6.1f}  model {s['model']:6.1f}")

(KELUAR / "hasil.json").write_text(json.dumps(
    [{**s, "waktu": s["waktu"].isoformat()} for s in stasiun], ensure_ascii=False, indent=1), encoding="utf-8")
