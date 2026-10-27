"""Kirim unggahan ke akun X @AlarmBencana lewat API resmi (OAuth 1.0a, kunci dari .env).

Pakai (dari folder proyek):
  python program/kirim_x.py cek                      -> uji kunci tanpa mengunggah
  python program/kirim_x.py kirim "teks" [gambar.png] -> unggah satu kiriman (memakai saldo X)
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

AKAR = Path(__file__).resolve().parent.parent
API = "https://api.x.com/2"


class GagalX(Exception):
    def __init__(self, kode, isi):
        self.kode, self.isi = kode, isi
        super().__init__(f"X menolak ({kode}, {arti(kode, isi)}): {isi[:300]}")


def arti(kode, isi):
    """Penjelasan singkat untuk catatan, supaya tidak perlu menebak arti angka galat."""
    if kode == 401:
        return "kunci ditolak"
    if kode == 402 or "credit" in isi.lower():
        return "saldo X habis"
    if kode == 429:
        return "terlalu sering, tunggu sebentar"
    if kode == 403:
        return "tidak diizinkan"
    return "lainnya"


def kunci():
    """Dari berkas .env (laptop) atau dari brankas rahasia GitHub (variabel lingkungan)."""
    berkas = AKAR / ".env"
    isi = berkas.read_text(encoding="utf-8").splitlines() if berkas.exists() else []
    env = {**dict(b.split("=", 1) for b in isi if "=" in b and not b.startswith("#")), **os.environ}
    return {k: env[k].strip() for k in ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET")}


def kode_url(s):
    return urllib.parse.quote(str(s), safe="")


def tanda_tangan(metode, url, k):
    """Kepala Authorization OAuth 1.0a. Isi badan (JSON/multipart) memang tidak ikut ditandatangani."""
    oauth = {"oauth_consumer_key": k["X_API_KEY"], "oauth_nonce": secrets.token_hex(16),
             "oauth_signature_method": "HMAC-SHA1", "oauth_timestamp": str(int(time.time())),
             "oauth_token": k["X_ACCESS_TOKEN"], "oauth_version": "1.0"}
    alamat, _, tanya = url.partition("?")
    param = sorted((kode_url(a), kode_url(b)) for a, b in
                   list(oauth.items()) + urllib.parse.parse_qsl(tanya, keep_blank_values=True))
    dasar = "&".join([metode, kode_url(alamat), kode_url("&".join(f"{a}={b}" for a, b in param))])
    rahasia = f"{kode_url(k['X_API_SECRET'])}&{kode_url(k['X_ACCESS_SECRET'])}"
    oauth["oauth_signature"] = base64.b64encode(
        hmac.new(rahasia.encode(), dasar.encode(), hashlib.sha1).digest()).decode()
    return "OAuth " + ", ".join(f'{kode_url(a)}="{kode_url(b)}"' for a, b in sorted(oauth.items()))


def minta(metode, url, badan=None, jenis=None):
    kepala = {"Authorization": tanda_tangan(metode, url, kunci()), "User-Agent": "AlarmBencana/1.0"}
    if jenis:
        kepala["Content-Type"] = jenis
    try:
        with urllib.request.urlopen(urllib.request.Request(url, badan, kepala, method=metode), timeout=90) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise GagalX(e.code, e.read().decode("utf-8", "replace")) from None


def unggah_gambar(berkas):
    berkas = Path(berkas)
    batas = "AlarmBencana" + secrets.token_hex(12)
    badan = (f"--{batas}\r\nContent-Disposition: form-data; name=\"media_category\"\r\n\r\ntweet_image\r\n"
             f"--{batas}\r\nContent-Disposition: form-data; name=\"media\"; filename=\"{berkas.name}\"\r\n"
             "Content-Type: image/png\r\n\r\n").encode() + berkas.read_bytes() + f"\r\n--{batas}--\r\n".encode()
    return minta("POST", f"{API}/media/upload", badan, f"multipart/form-data; boundary={batas}")["data"]["id"]


def kirim(teks, gambar=None):
    """Unggah satu kiriman; mengembalikan nomor kirimannya di X."""
    isi = {"text": teks}
    if gambar:
        isi["media"] = {"media_ids": [unggah_gambar(gambar)]}
    return minta("POST", f"{API}/tweets", json.dumps(isi).encode(), "application/json")["data"]["id"]


def cek():
    return minta("GET", f"{API}/users/me")["data"]


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    perintah = sys.argv[1:2]
    try:
        if perintah == ["cek"]:
            d = cek()
            print(f"Kunci diterima. Akun: @{d['username']} ({d['name']})")
        elif perintah == ["kirim"] and len(sys.argv) >= 3:
            nomor = kirim(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
            print(f"Terkirim: https://x.com/AlarmBencana/status/{nomor}")
        else:
            print(__doc__)
    except GagalX as e:
        print(e)
        sys.exit(1)
