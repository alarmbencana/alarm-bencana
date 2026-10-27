"""Uji alur --sungguhan dengan X tiruan (tidak ada yang terunggah).
Jalan 1: tanpa keadaan -> ringkasan + dll; kiriman ke-2 dibuat gagal.
Jalan 2: kiriman tertunda harus dicoba lagi duluan, tanpa mengulang yang sudah terkirim."""
import sys, types, json
from pathlib import Path
KELUAR = Path(sys.argv[1])
sys.path.insert(0, "program")
import alarm
terkirim, panggilan = [], [0]
GAGAL_KE = int(sys.argv[2]) if len(sys.argv) > 2 else 2
def kirim(teks, gambar=None):
    panggilan[0] += 1
    if panggilan[0] == GAGAL_KE:
        raise RuntimeError("X menolak (402, saldo X habis): tiruan")
    terkirim.append(teks[:50])
    return str(1000 + panggilan[0])
sys.modules["kirim_x"] = types.SimpleNamespace(kirim=kirim)
alarm.BERKAS_KEADAAN = KELUAR / "keadaan.json"
alarm.FOLDER_DRAF = KELUAR
sys.argv = ["alarm.py", "--sungguhan"]
alarm.main()
k = json.loads(alarm.BERKAS_KEADAAN.read_text(encoding="utf-8"))
print("== setelah jalan 1: terkirim", len(terkirim), "| tertunda", len(k["tertunda"]))
sebelum = list(terkirim)
alarm.main()
k = json.loads(alarm.BERKAS_KEADAAN.read_text(encoding="utf-8"))
print("== setelah jalan 2: terkirim total", len(terkirim), "| tertunda", len(k["tertunda"]))
print("dobel?", len(terkirim) != len(set(terkirim)))
for t in terkirim: print("  -", t.replace("\n", " "))
