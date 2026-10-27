import sys, time
from datetime import datetime, timezone, timedelta
from pathlib import Path
sys.path.insert(0, "program")
import alarm, gambar
sys.stdout.reconfigure(encoding="utf-8")
t0 = time.time()
w = alarm.Wilayah()
per_kab, ragu, stasiun = alarm.ambil_asap(alarm.baca_env()["WAQI_TOKEN"].strip(), w)
titik = alarm.ambil_api(w)
sekarang = datetime.now(timezone.utc)
api24 = sorted({tuple(map(float, t["sel"].split(","))) for t in titik if t["waktu"] > sekarang - timedelta(hours=24)})
print("data", round(time.time() - t0, 1), "detik;", len(stasiun), "alat;", len(api24), "titik api")
keluar = Path("latihan/gambar")
nama = lambda h: alarm.tempat(h["kab"].removeprefix("Kab. "), h["prov"])
t = sekarang + timedelta(hours=7)
waktu = f"{t.day} {alarm.BULAN[t.month - 1]} {t.year}, {t:%H.%M} WIB"
t1 = time.time(); print(gambar.peta_ringkasan(w, stasiun, api24, waktu, keluar / "contoh-ringkasan.png", alarm.kategori, nama), round(time.time() - t1, 1))
# titik api: pakai yang terdeteksi di lintasan satelit terakhir sebagai "baru"
akhir = max(t["waktu"] for t in titik)
baru = [t for t in titik if t["waktu"] > akhir - timedelta(hours=3)]
from collections import defaultdict
kel = defaultdict(list)
for t in baru: kel[t["wilayah"]].append(tuple(map(float, t["sel"].split(","))))
daftar = sorted(((alarm.tempat(*k), len(v), (sum(a for a, _ in v) / len(v), sum(b for _, b in v) / len(v))) for k, v in kel.items()), key=lambda x: -x[1])
pb = sorted({tuple(map(float, t["sel"].split(","))) for t in baru})
t1 = time.time(); print(gambar.peta_api(w, pb, [p for p in api24 if p not in set(pb)], "TITIK API BARU", f"{len(pb)} titik · {alarm.jam_lokal(akhir, 'WIB')}", daftar, keluar / "contoh-api.png"), round(time.time() - t1, 1))
h = max(stasiun, key=lambda h: h["ug"])
lv = alarm.kategori(h["ug"]); _, nm, _, saran = alarm.KATEGORI[lv]
t1 = time.time(); print(gambar.kartu_asap(w, h, stasiun, api24, lv, nm, saran, alarm.tempat(h["kab"], h["prov"]), alarm.jam_lokal(h["waktu"], alarm.zona_dari(h["prov"])), keluar / "contoh-asap.png", alarm.kategori), round(time.time() - t1, 1))
