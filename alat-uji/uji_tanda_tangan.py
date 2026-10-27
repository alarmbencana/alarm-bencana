# Contoh resmi X ("Creating a signature"): tanda tangan yang benar = hCtSmYh+iHYCEqBWrE7C7hYmtUk=
import sys, re, urllib.parse
sys.path.insert(0, "program")
import kirim_x
kirim_x.secrets.token_hex = lambda n: "kYjzVBB8Y0ZFabxSWbWovY3uYSQ2pTgmZeNu2VS4cg"
kirim_x.time.time = lambda: 1318622958
k = {"X_API_KEY": "xvz1evFS4wEEPTGEFPHBog", "X_API_SECRET": "kAcSOqF21Fu85e7zjz7ZN2U4ZRhfV3WpwPAoE3Z7kBw",
     "X_ACCESS_TOKEN": "370773112-GmHxMAgYyLbNEtIKZeRNFsMKPR9EyMZeS9weJAEb",
     "X_ACCESS_SECRET": "LswwdoUaIvS8ltyTt5jkRh4J50vUPVVHtR2YPi5kE"}
url = ("https://api.twitter.com/1.1/statuses/update.json?include_entities=true"
       "&status=Hello%20Ladies%20%2B%20Gentlemen%2C%20a%20signed%20OAuth%20request%21")
h = kirim_x.tanda_tangan("POST", url, k)
ttd = urllib.parse.unquote(re.search(r'oauth_signature="([^"]+)"', h).group(1))
print(ttd, "BENAR" if ttd == "hCtSmYh+iHYCEqBWrE7C7hYmtUk=" else "SALAH")
