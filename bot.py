#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CPM TOOL - Telegram Bot
Para / Coin / King Rank + Admin Panel
"""

import os
import sys
import json
import time
import struct
import hashlib
import zlib
import sqlite3
import threading
import requests
import urllib3
import telebot
from telebot import types

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import unpad
except ImportError:
    print("❌ pip install pycryptodome")
    sys.exit(1)

try:
    import brotli
except ImportError:
    print("❌ pip install brotli")
    sys.exit(1)


# ═══════════════════════════════════════════════════════════
# ⚙️ AYARLAR
# ═══════════════════════════════════════════════════════════

BOT_TOKEN = "8630076957:AAG6W5x04nuVo9iwW6UFkGlZYxb8vpVW8XM"
ADMIN_ID = 8882473760
SUPPORT_USERNAME = "@derincpm"
CHANNEL_USERNAME = "@derincpmmain"
CLONE_BOT_URL = "https://t.me/derincpmclone_bot"

# ── King Rank API ──
RANK_API_URL = "https://cpm1-6nmh.onrender.com/rank"
RANK_COUNT_URL = "https://cpmgg20.free.nf/count/count.php?action=add&script=success"

FK = "AIzaSyAe_aOVT1gSfmHKBrorFvX4fRwN5nODXVA"
LOAD_URL = "https://europe-west1-cp-multiplayer.cloudfunctions.net/GetPlayerRecords3"
SAVE_URL = "https://europe-west1-cp-multiplayer.cloudfunctions.net/SavePlayerRecordsPartially8"

GAME_HEADERS = {
    "Accept": "*/*",
    "Accept-Encoding": "gzip",
    "Content-Type": "application/json",
    "User-Agent": "UnityPlayer/2022.3.62f2 (UnityWebRequest/1.0, libcurl/8.10.1-DEV)",
    "X-Unity-Version": "2022.3.62f2",
}

DB_PATH = "cpm_bot.db"

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="Markdown")


# ═══════════════════════════════════════════════════════════
# 🗄️ VERİTABANI
# ═══════════════════════════════════════════════════════════

def db_init():
    con = sqlite3.connect(DB_PATH)
    c = con.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users(
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        joined_at INTEGER,
        banned INTEGER DEFAULT 0,
        verified INTEGER DEFAULT 0
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS states(
        user_id INTEGER PRIMARY KEY,
        step TEXT,
        data TEXT
    )""")
    con.commit()
    con.close()


def db_exec(q, args=()):
    con = sqlite3.connect(DB_PATH)
    c = con.cursor()
    c.execute(q, args)
    con.commit()
    r = c.fetchall()
    con.close()
    return r


def db_user_add(uid, username, first_name):
    try:
        db_exec(
            "INSERT OR IGNORE INTO users(user_id, username, first_name, joined_at) VALUES(?,?,?,?)",
            (uid, username or "", first_name or "", int(time.time()))
        )
        db_exec("UPDATE users SET username=?, first_name=? WHERE user_id=?",
                (username or "", first_name or "", uid))
    except Exception:
        pass


def db_is_banned(uid):
    r = db_exec("SELECT banned FROM users WHERE user_id=?", (uid,))
    return bool(r and r[0][0] == 1)


def db_set_ban(uid, val):
    db_exec("UPDATE users SET banned=? WHERE user_id=?", (1 if val else 0, uid))


def db_get_users():
    return db_exec("SELECT user_id, username, first_name, banned FROM users")


def db_count_users():
    r = db_exec("SELECT COUNT(*) FROM users")
    return r[0][0] if r else 0


def db_set_state(uid, step, data=None):
    db_exec("INSERT OR REPLACE INTO states(user_id, step, data) VALUES(?,?,?)",
            (uid, step, json.dumps(data or {})))


def db_get_state(uid):
    r = db_exec("SELECT step, data FROM states WHERE user_id=?", (uid,))
    if not r:
        return None, {}
    try:
        return r[0][0], json.loads(r[0][1] or "{}")
    except Exception:
        return r[0][0], {}


def db_clear_state(uid):
    db_exec("DELETE FROM states WHERE user_id=?", (uid,))


# ═══════════════════════════════════════════════════════════
# 🔐 CRYPTO
# ═══════════════════════════════════════════════════════════

def make_xor_key(uid: str) -> bytes:
    chars = list(str(uid or ""))
    if len(chars) >= 9: chars[1], chars[8] = chars[8], chars[1]
    if len(chars) >= 3: chars.pop(2)
    if len(chars) >= 5: chars.append(chars[4])
    return "".join(chars).encode("utf-8") or b"0"


def xor_bytes(data: bytes, key: bytes) -> bytes:
    return bytes(data[i] ^ key[i % len(key)] for i in range(len(data)))


def decompress(data: bytes):
    try: return brotli.decompress(data)
    except Exception: pass
    for args in ((zlib.MAX_WBITS | 16,), tuple()):
        try: return zlib.decompress(data, *args)
        except Exception: pass
    return None


def _md5(t): return hashlib.md5(str(t).encode()).digest()
def _sha1(t): return hashlib.sha1(str(t).encode()).digest()[:16]


def decrypt_aes(data: bytes, key: bytes):
    try:
        cipher = AES.new(key[:16], AES.MODE_CBC, b"\x00" * 16)
        return unpad(cipher.decrypt(data), 16)
    except Exception:
        return None


def build_aes_keys(uid, password=None, email=None):
    keys = [_md5("olzhas_carparking")]
    if password: keys += [_md5(password), _sha1(password)]
    if uid: keys += [_md5(uid), _sha1(uid)]
    if email: keys.append(_md5(email))
    return keys


# ═══════════════════════════════════════════════════════════
# 📖 READER
# ═══════════════════════════════════════════════════════════

class Reader:
    def __init__(self, data): self.buf, self.pos = data, 0
    def has(self, n): return self.pos + n <= len(self.buf)
    def byte(self):
        if not self.has(1): return 0
        v = self.buf[self.pos]; self.pos += 1; return v
    def i(self):
        if not self.has(4): self.pos = len(self.buf); return 0
        v = struct.unpack_from("<i", self.buf, self.pos)[0]; self.pos += 4; return v
    def f(self):
        if not self.has(4): self.pos = len(self.buf); return 0.0
        v = struct.unpack_from("<f", self.buf, self.pos)[0]; self.pos += 4; return v
    def s(self):
        m = self.i()
        if m in (0, -1): return ""
        ln = (-m) - 1 if m < -1 else m
        if m < -1: self.i()
        ln = max(0, min(ln, 1000000))
        if not self.has(ln): return ""
        t = self.buf[self.pos:self.pos+ln].decode("utf-8", errors="replace")
        self.pos += ln
        return t.replace("\x00", "").strip()
    def lst(self, fn):
        n = self.i()
        if n <= 0 or n > 1000000: return []
        out = []
        for _ in range(n):
            if self.pos >= len(self.buf): break
            v = fn()
            if v is not None: out.append(v)
        return out
    def dct(self):
        n = self.i()
        if n <= 0 or n > 1000000: return {}
        out = {}
        for _ in range(n):
            if self.pos >= len(self.buf): break
            out[self.i()] = self.i()
        return out
    def equip(self):
        if self.byte() == 0: return None
        return {k: self.lst(self.i) for k in
                ["hair","face","beard","cap","mask","top","gloves","bag",
                 "pants","shoes","glasses","SelectedEquipments"]} | {"Gender": self.i()}


def parse_player(buf):
    r = Reader(buf)
    if r.byte() == 0: return None
    p = {}
    p["Name"] = r.s(); p["money"] = r.i(); p["coin"] = r.i(); p["localID"] = r.s()
    p["boughtFsos"] = r.lst(r.i)
    p["FriendsID"] = r.lst(lambda: (r.byte(), {"id": r.s(), "Name": r.s(), "accountID": r.s()})[1])
    p["LevelsDoneTime"] = r.lst(r.f)
    p["floats"] = r.lst(r.f)
    p["integers"] = r.lst(r.i)
    p["fcar"] = r.lst(r.i)
    p["favouriteWheels"] = r.lst(r.i)
    p["favouriteVinyls"] = r.lst(r.i)
    p["favouriteEmojis"] = r.lst(r.i)
    p["personEquipmentsMale"] = r.equip()
    p["personEquipmentsFemale"] = r.equip()
    if r.byte() == 0:
        p["platesData"] = None
    else:
        def rv():
            fc = r.byte()
            return {"_fieldCount": fc,
                    "vectors": r.lst(lambda: {"x": r.f(), "y": r.f(), "z": r.f()}),
                    "v": r.lst(r.s), "floats": r.lst(r.f), "text": r.s()}
        def rp():
            fc = r.byte()
            return {"_fieldCount": fc, "plateId": r.i(), "frontCarId": r.i(),
                    "rearCarId": r.i(), "vinyls": r.lst(rv)}
        p["platesData"] = {"allPlates": r.lst(rp)}
    if r.byte() == 0:
        p["carIDnStatus"] = None
    else:
        p["carIDnStatus"] = {"carGeneratedIDs": r.lst(r.s), "carStatus": r.lst(r.i)}
    p["allData"] = r.s()
    p["flags"] = r.dct()
    p["animations"] = r.lst(r.i)
    p["emojiPacks"] = r.lst(r.i)
    p["wheels"] = r.lst(r.i)
    p["boughtPoliceLights"] = r.lst(r.i)
    p["boughtPoliceSirens"] = r.lst(r.i)
    return p


def try_parse(buf):
    cands = [buf]
    d1 = decompress(buf)
    if d1:
        cands.append(d1)
        d2 = decompress(d1)
        if d2: cands.append(d2)
    for c in cands:
        if not c: continue
        if c[0] in (17, 23, 24):
            try:
                p = parse_player(c)
                if p and p.get("Name") is not None: return p
            except Exception: pass
        try:
            clean = c[3:] if len(c) >= 3 and c[:2] == b"\xef\xbb" else c
            if clean and clean[0] == 123:
                return json.loads(clean.decode("utf-8"))
        except Exception: pass
    return None


def decrypt_record(b64_text, uid, password=None, email=None):
    import base64 as _b64
    try: buf = _b64.b64decode(b64_text)
    except Exception: return {"success": False, "message": "bad_base64"}
    if len(buf) < 10: return {"success": False, "message": "too_small"}

    direct = try_parse(buf)
    if direct: return {"success": True, "record": direct}

    try:
        decoded = decompress(xor_bytes(buf, make_xor_key(uid)))
        if decoded:
            p = try_parse(decoded)
            if p: return {"success": True, "record": p}
    except Exception: pass

    for k in build_aes_keys(uid, password, email):
        plain = decrypt_aes(buf, k)
        if not plain: continue
        p = try_parse(plain)
        if p: return {"success": True, "record": p}
    return {"success": False, "message": "decrypt_failed"}


# ═══════════════════════════════════════════════════════════
# ✍️ WRITER
# ═══════════════════════════════════════════════════════════

class Writer:
    def __init__(self): self._p = []
    def b(self, v): self._p.append(bytes([int(v or 0) & 0xFF]))
    def i(self, v): self._p.append(struct.pack("<i", int(v or 0)))
    def f(self, v): self._p.append(struct.pack("<f", float(v or 0.0)))
    def s(self, s):
        if s is None: self._p.append(struct.pack("<i", -1)); return
        s = str(s)
        if s == "": self._p.append(struct.pack("<i", 0)); return
        enc = s.encode("utf-8")
        self._p.append(struct.pack("<ii", -len(enc)-1, len(s)) + enc)
    def lst(self, l, fn):
        if l is None: self._p.append(struct.pack("<i", -1)); return
        self._p.append(struct.pack("<i", len(l)))
        for x in l: fn(x)
    def equip(self, d):
        if not d: self.b(0); return
        self.b(13)
        for k in ["hair","face","beard","cap","mask","top","gloves","bag",
                  "pants","shoes","glasses","SelectedEquipments"]:
            self.lst(d.get(k, []), self.i)
        self.i(d.get("Gender", 0))
    def plates(self, d):
        if not d: self.b(0); return
        self.b(1)
        pl = d.get("allPlates", [])
        self._p.append(struct.pack("<i", len(pl)))
        for p in pl:
            self.b(int(p.get("_fieldCount", 4) or 4))
            self.i(p.get("plateId", 0))
            self.i(p.get("frontCarId", 0))
            self.i(p.get("rearCarId", 0))
            vs = p.get("vinyls", [])
            self._p.append(struct.pack("<i", len(vs)))
            for v in vs:
                self.b(int(v.get("_fieldCount", 4) or 4))
                vecs = v.get("vectors", [])
                self._p.append(struct.pack("<i", len(vecs)))
                for vec in vecs:
                    self._p.append(struct.pack("<fff",
                        float(vec.get("x",0) or 0), float(vec.get("y",0) or 0), float(vec.get("z",0) or 0)))
                self.lst(v.get("v", []), self.s)
                self.lst(v.get("floats", []), self.f)
                self.s(v.get("text", ""))
    def carstat(self, d):
        if not d: self.b(0); return
        self.b(2)
        self.lst(d.get("carGeneratedIDs", []), self.s)
        self.lst(d.get("carStatus", []), self.i)
    def to_bytes(self): return b"".join(self._p)


FIELD_MAP = [
    (1,"localID"),(2,"money"),(3,"Name"),(4,"coin"),(5,"allData"),
    (6,"boughtFsos"),(7,"boughtPoliceLights"),(8,"boughtPoliceSirens"),
    (9,"FriendsID"),(10,"LevelsDoneTime"),(11,"floats"),(12,"integers"),
    (13,"fcar"),(14,"favouriteWheels"),(15,"favouriteVinyls"),
    (16,"favouriteEmojis"),(18,"emojiPacks"),
    (41,"personEquipmentsMale"),(42,"personEquipmentsFemale"),
    (43,"platesData"),(44,"carIDnStatus"),(45,"flags"),
    (46,"animations"),(48,"wheels"),
]
INT_LIST = {6,7,8,12,13,14,15,16,18,46,48}
FLOAT_LIST = {10,11}


def serialize(fid, v):
    w = Writer()
    if fid in (1,3,5): w.s(v); return w.to_bytes()
    if fid in (2,4): w.i(v or 0); return w.to_bytes()
    if fid == 9:
        fr = v or []
        w._p.append(struct.pack("<i", len(fr)))
        for f in fr:
            f = f or {}
            w.b(3); w.s(f.get("id","")); w.s(f.get("Name","")); w.s(f.get("accountID",""))
        return w.to_bytes()
    if fid in INT_LIST: w.lst(v or [], w.i); return w.to_bytes()
    if fid in FLOAT_LIST: w.lst(v or [], w.f); return w.to_bytes()
    if fid in (41,42): w.equip(v); return w.to_bytes()
    if fid == 43: w.plates(v); return w.to_bytes()
    if fid == 44: w.carstat(v); return w.to_bytes()
    if fid == 45:
        fl = v or {}
        w._p.append(struct.pack("<i", len(fl)))
        for k, val in fl.items():
            w.i(int(k)); w.i(int(val))
        return w.to_bytes()
    return None


def build_payload(record, uid, force_fields=None):
    import base64 as _b64
    force = set(force_fields or [])
    fields = []
    for fid, key in FIELD_MAP:
        if key not in force: continue
        v = record.get(key)
        if v is None: continue
        raw = serialize(fid, v)
        if raw is not None:
            fields.append((fid, raw))
    parts = [struct.pack("<i", len(fields))]
    for fid, raw in fields:
        parts.append(struct.pack("<hi", fid, len(raw)))
        parts.append(raw)
    combined = b"".join(parts)
    compressed = brotli.compress(combined)
    encrypted = xor_bytes(compressed, make_xor_key(uid))
    return _b64.b64encode(encrypted).decode("ascii")


# ═══════════════════════════════════════════════════════════
# 🌐 API
# ═══════════════════════════════════════════════════════════

def login(email, password):
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FK}"
    h = {"Content-Type": "application/json",
         "User-Agent": "UnityPlayer/2022.3.62f2 (UnityWebRequest/1.0, libcurl/8.10.1-DEV)",
         "X-Unity-Version": "2022.3.62f2"}
    payload = {"email": email, "password": password,
               "returnSecureToken": True, "clientType": "CLIENT_TYPE_ANDROID"}
    try:
        r = requests.post(url, json=payload, headers=h, timeout=30, verify=False)
        data = r.json()
    except Exception as e:
        return {"ok": False, "msg": f"network: {e}"}
    if "idToken" in data:
        return {"ok": True, "auth": data["idToken"],
                "fuid": data.get("localId",""), "refresh": data.get("refreshToken","")}
    return {"ok": False, "msg": str(data.get("error",{}).get("message","")).upper() or "login_failed"}


def fetch_record(auth, fuid):
    h = {**GAME_HEADERS, "Authorization": f"Bearer {auth}"}
    try:
        r = requests.post(LOAD_URL, json={"data": {"data": fuid}}, headers=h, timeout=30, verify=False)
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def find_encrypted(resp):
    if resp is None: return None
    if isinstance(resp, str): return resp if len(resp) > 50 else None
    if isinstance(resp, dict):
        for k in ("result", "data", "record", "PlayerRecord", "playerRecord"):
            v = resp.get(k)
            if isinstance(v, str) and len(v) > 50: return v
            if isinstance(v, dict):
                r = find_encrypted(v)
                if r: return r
        for v in resp.values():
            if isinstance(v, str) and len(v) > 200: return v
    return None


def _ok(v):
    if v in (1, True): return True
    if v in (0, False, None): return False
    if isinstance(v, str):
        t = v.strip()
        if t == "1": return True
        if t == "0": return False
        try: return _ok(json.loads(t))
        except Exception: return False
    if isinstance(v, dict):
        for k in ("result","ok","success"):
            if k in v: return _ok(v[k])
    return False


def save_record(auth, fuid, record, force_fields):
    payload = build_payload(record, fuid, force_fields)
    h = {**GAME_HEADERS, "Authorization": f"Bearer {auth}", "Connection": "Keep-Alive"}
    body = {"data": {"data": payload, "deviceId": fuid[:8]}}
    try:
        r = requests.post(SAVE_URL, json=body, headers=h, timeout=30, verify=False)
        try: j = r.json()
        except Exception: j = {"raw": r.text}
        return {"ok": _ok(j), "status": r.status_code, "resp": j}
    except Exception as e:
        return {"ok": False, "msg": str(e)}


# ═══════════════════════════════════════════════════════════
# 👑 KING RANK API
# ═══════════════════════════════════════════════════════════

def king_rank_send(email, password):
    """King Rank API'sine istek gönder"""
    try:
        res = requests.post(
            RANK_API_URL,
            json={"email": email, "password": password},
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        data = res.json()
    except Exception as e:
        return {"ok": False, "msg": f"Network: {e}"}

    status = data.get("status")
    message = data.get("message", "Unknown issue")

    if status == "success":
        try:
            requests.get(RANK_COUNT_URL, timeout=10)
        except Exception:
            pass
        return {"ok": True, "msg": message}
    elif status == "error":
        return {"ok": False, "msg": message}
    return {"ok": False, "msg": message}


# ═══════════════════════════════════════════════════════════
# 🛠️ YARDIMCILAR
# ═══════════════════════════════════════════════════════════

def do_login_and_get_record(email, password):
    lg = login(email, password)
    if not lg.get("ok"):
        return None, None, None, f"Giriş hatası: `{lg.get('msg')}`"
    auth = lg["auth"]; fuid = lg["fuid"]

    resp = fetch_record(auth, fuid)
    enc = find_encrypted(resp)
    if not enc:
        return None, None, None, "Şifreli veri bulunamadı."

    dec = decrypt_record(enc, fuid, password, email)
    if not dec.get("success"):
        return None, None, None, f"Çözülemedi: `{dec.get('message')}`"
    return auth, fuid, dec["record"], None


# ═══════════════════════════════════════════════════════════
# 🎨 UI
# ═══════════════════════════════════════════════════════════

BANNER = (
    "┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓\n"
    "┃     🚗 *CPM TOOL*  🚗            ┃\n"
    "┣━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┫\n"
    "┃  📢 Kanal: @derincpmmain         ┃\n"
    "┃  💬 Destek: @derincpm            ┃\n"
    "┃  🔄 Clone: @derincpmclone_bot    ┃\n"
    "┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛"
)

MAIN_TEXT = (
    f"{BANNER}\n\n"
    "✅ *Katılımınız onaylandı!*\n"
    "👇 İşlem yapmak istediğiniz menüyü seçin:"
)

SUB_TEXT = (
    f"{BANNER}\n\n"
    f"⚠️ Önce *{CHANNEL_USERNAME}* kanalına katılmalısın."
)


def kb_main():
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("💰 Para Ekle", callback_data="menu_money"))
    kb.add(types.InlineKeyboardButton("🪙 Coin Ekle", callback_data="menu_coin"))
    kb.add(types.InlineKeyboardButton("👑 King Rank", callback_data="menu_rank"))
    kb.add(types.InlineKeyboardButton("📊 Hesap Ayrıntıları", callback_data="menu_details"))
    kb.add(types.InlineKeyboardButton("🔄 Hesap Kopyala", url=CLONE_BOT_URL))
    return kb


def kb_back():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("⬅️ Geri", callback_data="menu_main"))
    return kb


def kb_sub_check():
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("✅ Kanala Katıldım", callback_data="check_subs"))
    kb.add(types.InlineKeyboardButton("📢 Kanala Git", url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}"))
    return kb


def is_user_subscribed(uid):
    if not CHANNEL_USERNAME: return True
    try:
        m = bot.get_chat_member(CHANNEL_USERNAME, uid)
        return m.status in ("member", "administrator", "creator")
    except Exception:
        return True


def guard(func):
    def wrapper(*args, **kwargs):
        if args and isinstance(args[0], types.CallbackQuery):
            cb = args[0]
            uid = cb.from_user.id
            if db_is_banned(uid):
                try: bot.answer_callback_query(cb.id, "🚫 Yasaklısınız.", show_alert=True)
                except Exception: pass
                return
        else:
            msg = args[0] if args else None
            if msg is not None and hasattr(msg, "from_user") and msg.from_user:
                if db_is_banned(msg.from_user.id):
                    bot.reply_to(msg, "🚫 *Hesabınız yasaklandı.* Destek: " + SUPPORT_USERNAME)
                    return
        return func(*args, **kwargs)
    return wrapper


# ═══════════════════════════════════════════════════════════
# 🤖 KOMUTLAR
# ═══════════════════════════════════════════════════════════

@bot.message_handler(commands=["start"])
@guard
def cmd_start(msg):
    u = msg.from_user
    db_user_add(u.id, u.username, u.first_name)
    db_clear_state(u.id)

    if CHANNEL_USERNAME and not is_user_subscribed(u.id):
        bot.send_message(msg.chat.id, SUB_TEXT, reply_markup=kb_sub_check())
        return

    bot.send_message(msg.chat.id, MAIN_TEXT, reply_markup=kb_main())


@bot.message_handler(commands=["id"])
def cmd_id(msg):
    bot.reply_to(msg, f"🆔 `{msg.from_user.id}`")


@bot.message_handler(commands=["destek", "support"])
def cmd_support(msg):
    bot.reply_to(msg, f"🆘 Destek: {SUPPORT_USERNAME}")


@bot.message_handler(commands=["admin"])
def cmd_admin(msg):
    if msg.from_user.id != ADMIN_ID:
        return
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("📢 Duyuru Gönder", callback_data="adm_broadcast"))
    kb.add(types.InlineKeyboardButton("📊 İstatistik", callback_data="adm_stats"))
    kb.add(types.InlineKeyboardButton("🚫 Kullanıcı Yasakla", callback_data="adm_ban"))
    kb.add(types.InlineKeyboardButton("✅ Yasak Kaldır", callback_data="adm_unban"))
    kb.add(types.InlineKeyboardButton("📋 Kullanıcı Listesi", callback_data="adm_list"))
    bot.send_message(msg.chat.id, "🛡️ *Admin Paneli*", reply_markup=kb)


# ═══════════════════════════════════════════════════════════
# 🔘 CALLBACK HANDLER
# ═══════════════════════════════════════════════════════════

@bot.callback_query_handler(func=lambda c: True)
@guard
def cb_handler(cb):
    uid = cb.from_user.id
    data = cb.data
    chat_id = cb.message.chat.id
    msg_id = cb.message.message_id

    if data == "check_subs":
        if CHANNEL_USERNAME and not is_user_subscribed(uid):
            bot.answer_callback_query(cb.id, "❌ Henüz kanala katılmadınız!", show_alert=True)
            return
        bot.answer_callback_query(cb.id, "✅ Onaylandı!")
        bot.edit_message_text(MAIN_TEXT, chat_id=chat_id, message_id=msg_id, reply_markup=kb_main())
        return

    if data == "menu_main":
        db_clear_state(uid)
        bot.edit_message_text(MAIN_TEXT, chat_id=chat_id, message_id=msg_id, reply_markup=kb_main())
        bot.answer_callback_query(cb.id)
        return

    if data == "menu_money":
        db_set_state(uid, "money_email")
        bot.edit_message_text(
            "💰 *PARA EKLE*\n\n📧 E-posta adresinizi girin:",
            chat_id=chat_id, message_id=msg_id, reply_markup=kb_back())
        bot.answer_callback_query(cb.id)
        return

    if data == "menu_coin":
        db_set_state(uid, "coin_email")
        bot.edit_message_text(
            "🪙 *COIN EKLE*\n\n📧 E-posta adresinizi girin:",
            chat_id=chat_id, message_id=msg_id, reply_markup=kb_back())
        bot.answer_callback_query(cb.id)
        return

    if data == "menu_rank":
        db_set_state(uid, "rank_email")
        bot.edit_message_text(
            "👑 *KING RANK*\n\n"
            "🏆 Hesabınıza *King Rank* vermek için\n"
            "📧 E-posta adresinizi girin:",
            chat_id=chat_id, message_id=msg_id, reply_markup=kb_back())
        bot.answer_callback_query(cb.id)
        return

    if data == "menu_details":
        db_set_state(uid, "details_email")
        bot.edit_message_text(
            "📊 *HESAP AYRINTILARI*\n\n📧 E-posta adresinizi girin:",
            chat_id=chat_id, message_id=msg_id, reply_markup=kb_back())
        bot.answer_callback_query(cb.id)
        return

    # ── ADMIN ──
    if uid != ADMIN_ID:
        bot.answer_callback_query(cb.id, "Yetkiniz yok.", show_alert=True)
        return

    if data == "adm_broadcast":
        db_set_state(uid, "adm_broadcast")
        bot.edit_message_text("📢 Duyuru metnini gönderin:", chat_id=chat_id, message_id=msg_id)
        bot.answer_callback_query(cb.id)
        return

    if data == "adm_stats":
        total = db_count_users()
        banned = sum(1 for u in db_get_users() if u[3])
        bot.edit_message_text(
            f"📊 *İstatistikler*\n\n"
            f"👥 Toplam: `{total}`\n"
            f"🚫 Yasaklı: `{banned}`\n"
            f"✅ Aktif: `{total - banned}`",
            chat_id=chat_id, message_id=msg_id,
            reply_markup=types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton("⬅️ Admin", callback_data="adm_home")))
        bot.answer_callback_query(cb.id)
        return

    if data == "adm_ban":
        db_set_state(uid, "adm_ban")
        bot.edit_message_text("🚫 Yasaklanacak kullanıcının ID'sini girin:", chat_id=chat_id, message_id=msg_id)
        bot.answer_callback_query(cb.id)
        return

    if data == "adm_unban":
        db_set_state(uid, "adm_unban")
        bot.edit_message_text("✅ Yasağı kaldırılacak kullanıcının ID'sini girin:", chat_id=chat_id, message_id=msg_id)
        bot.answer_callback_query(cb.id)
        return

    if data == "adm_list":
        users = db_get_users()
        lines = ["📋 *Kullanıcılar*\n"]
        for u in users[:50]:
            mark = "🚫" if u[3] else "✅"
            lines.append(f"{mark} `{u[0]}` | @{u[1] or '-'} | {u[2] or '-'}")
        if len(users) > 50:
            lines.append(f"\n… +{len(users)-50} daha")
        bot.edit_message_text("\n".join(lines), chat_id=chat_id, message_id=msg_id,
                              reply_markup=types.InlineKeyboardMarkup().add(
                                  types.InlineKeyboardButton("⬅️ Admin", callback_data="adm_home")))
        bot.answer_callback_query(cb.id)
        return

    if data == "adm_home":
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(types.InlineKeyboardButton("📢 Duyuru Gönder", callback_data="adm_broadcast"))
        kb.add(types.InlineKeyboardButton("📊 İstatistik", callback_data="adm_stats"))
        kb.add(types.InlineKeyboardButton("🚫 Kullanıcı Yasakla", callback_data="adm_ban"))
        kb.add(types.InlineKeyboardButton("✅ Yasak Kaldır", callback_data="adm_unban"))
        kb.add(types.InlineKeyboardButton("📋 Kullanıcı Listesi", callback_data="adm_list"))
        bot.edit_message_text("🛡️ *Admin Paneli*", chat_id=chat_id, message_id=msg_id, reply_markup=kb)
        bot.answer_callback_query(cb.id)
        return


# ═══════════════════════════════════════════════════════════
# 📨 MESAJ AKIŞI
# ═══════════════════════════════════════════════════════════

@bot.message_handler(func=lambda m: True, content_types=["text"])
@guard
def msg_handler(msg):
    uid = msg.from_user.id
    db_user_add(uid, msg.from_user.username, msg.from_user.first_name)
    step, data = db_get_state(uid)

    if uid == ADMIN_ID and step == "adm_broadcast":
        db_clear_state(uid)
        users = db_get_users()
        ok, fail = 0, 0
        bot.reply_to(msg, f"📢 Gönderiliyor... ({len(users)} kullanıcı)")
        for u in users:
            try:
                bot.send_message(u[0], f"📢 *DUYURU*\n\n{msg.text}")
                ok += 1
                time.sleep(0.05)
            except Exception:
                fail += 1
        bot.send_message(msg.chat.id, f"✅ Tamamlandı.\n\nBaşarılı: `{ok}`\nHata: `{fail}`")
        return

    if uid == ADMIN_ID and step == "adm_ban":
        db_clear_state(uid)
        try:
            tid = int(msg.text.strip())
            db_set_ban(tid, True)
            bot.reply_to(msg, f"🚫 `{tid}` yasaklandı.")
            try: bot.send_message(tid, "🚫 Hesabınız yasaklandı.")
            except Exception: pass
        except Exception:
            bot.reply_to(msg, "❌ Geçersiz ID.")
        return

    if uid == ADMIN_ID and step == "adm_unban":
        db_clear_state(uid)
        try:
            tid = int(msg.text.strip())
            db_set_ban(tid, False)
            bot.reply_to(msg, f"✅ `{tid}` yasağı kaldırıldı.")
        except Exception:
            bot.reply_to(msg, "❌ Geçersiz ID.")
        return

    if not step:
        bot.reply_to(msg, "ℹ️ Menü için /start")
        return

    # ── Email adımı ──
    if step.endswith("_email"):
        action = step.replace("_email", "")
        data = {"email": msg.text.strip()}
        db_set_state(uid, f"{action}_password", data)
        bot.send_message(msg.chat.id, "🔒 Şifrenizi girin:", reply_markup=kb_back())
        return

    # ── Şifre adımı ──
    if step.endswith("_password"):
        action = step.replace("_password", "")
        data["password"] = msg.text.strip()
        try: bot.delete_message(msg.chat.id, msg.message_id)
        except Exception: pass

        th = threading.Thread(target=process_action, args=(msg.chat.id, uid, action, data))
        th.daemon = True
        th.start()
        db_clear_state(uid)
        return

    # ── Miktar adımı ──
    if step in ("money_amount", "coin_amount"):
        action = step.split("_")[0]
        try:
            amt = int(msg.text.strip().replace(",", "").replace(".", ""))
        except Exception:
            bot.reply_to(msg, "❌ Geçersiz miktar. Tekrar girin:")
            return
        data["amount"] = amt
        th = threading.Thread(target=process_amount, args=(msg.chat.id, uid, action, data))
        th.daemon = True
        th.start()
        db_clear_state(uid)
        return

    bot.reply_to(msg, "ℹ️ Menü için /start")


# ═══════════════════════════════════════════════════════════
# ⚙️ İŞLEM MOTORU
# ═══════════════════════════════════════════════════════════

def process_action(chat_id, uid, action, data):
    email = data.get("email", "")
    password = data.get("password", "")

    # ── KING RANK (ayrı API) ──
    if action == "rank":
        m = bot.send_message(chat_id, "⏳ King Rank gönderiliyor...")
        res = king_rank_send(email, password)
        if res.get("ok"):
            txt = (
                "👑 *KING RANK BAŞARILI!*\n\n"
                f"📧 `{email}`\n"
                f"🏆 Mesaj: `{res.get('msg')}`\n\n"
                "🎮 Oyuna girip kontrol edin!"
            )
        else:
            txt = f"❌ *KING RANK HATASI*\n\n`{res.get('msg')}`"
        try:
            bot.edit_message_text(txt, chat_id, m.message_id,
                                  reply_markup=types.InlineKeyboardMarkup().add(
                                      types.InlineKeyboardButton("⬅️ Ana Menü", callback_data="menu_main")))
        except Exception: pass
        return

    # ── Diğer işlemler (Para / Coin / Detay) ──
    m = bot.send_message(chat_id, "⏳ Giriş yapılıyor...")

    auth, fuid, record, err = do_login_and_get_record(email, password)
    if err:
        try: bot.edit_message_text(f"❌ {err}", chat_id, m.message_id)
        except Exception: pass
        return

    name = record.get("Name", "?")
    money = record.get("money", 0)
    coin = record.get("coin", 0)

    if action == "details":
        txt = (
            f"📊 *HESAP AYRINTILARI*\n\n"
            f"👤 İsim: `{name}`\n"
            f"🆔 UID: `{fuid}`\n"
            f"💰 Para: `{money:,}`\n"
            f"🪙 Coin: `{coin:,}`\n"
        )
        try:
            bot.edit_message_text(txt, chat_id, m.message_id,
                                  reply_markup=types.InlineKeyboardMarkup().add(
                                      types.InlineKeyboardButton("⬅️ Ana Menü", callback_data="menu_main")))
        except Exception as e:
            bot.send_message(chat_id, f"❌ {e}")
        return

    if action == "money":
        data["_auth"] = auth; data["_fuid"] = fuid
        data["_money"] = money; data["_name"] = name
        db_set_state(uid, "money_amount", data)
        try:
            bot.edit_message_text(
                f"👤 `{name}`\n💰 Mevcut: `{money:,}`\n\n💵 Eklenecek miktarı girin:",
                chat_id, m.message_id, reply_markup=kb_back())
        except Exception: pass
        return

    if action == "coin":
        data["_auth"] = auth; data["_fuid"] = fuid
        data["_coin"] = coin; data["_name"] = name
        db_set_state(uid, "coin_amount", data)
        try:
            bot.edit_message_text(
                f"👤 `{name}`\n🪙 Mevcut: `{coin:,}`\n\n🪙 Eklenecek miktarı girin:",
                chat_id, m.message_id, reply_markup=kb_back())
        except Exception: pass
        return


def process_amount(chat_id, uid, action, data):
    amt = data.get("amount", 0)
    email = data.get("email", ""); password = data.get("password", "")

    m = bot.send_message(chat_id, "⏳ Kaydediliyor...")

    auth, fuid, record, err = do_login_and_get_record(email, password)
    if err:
        try: bot.edit_message_text(f"❌ {err}", chat_id, m.message_id)
        except Exception: pass
        return

    name = record.get("Name", "?")
    MAX = 2_147_483_647

    if action == "money":
        old = int(record.get("money", 0) or 0)
        new = max(0, min(old + amt, MAX))
        record["money"] = new
        res = save_record(auth, fuid, record, {"money"})
        field_txt = f"💰 `{old:,}` → `{new:,}`"
    else:
        old = int(record.get("coin", 0) or 0)
        new = max(0, min(old + amt, MAX))
        record["coin"] = new
        res = save_record(auth, fuid, record, {"coin"})
        field_txt = f"🪙 `{old:,}` → `{new:,}`"

    if res.get("ok"):
        txt = f"✅ *BAŞARILI!*\n\n👤 `{name}`\n{field_txt}"
    else:
        txt = f"❌ *HATA*\n\n`{str(res)[:200]}`"
    try:
        bot.edit_message_text(txt, chat_id, m.message_id,
                              reply_markup=types.InlineKeyboardMarkup().add(
                                  types.InlineKeyboardButton("⬅️ Ana Menü", callback_data="menu_main")))
    except Exception: pass


# ═══════════════════════════════════════════════════════════
# 🚀 BAŞLAT
# ═══════════════════════════════════════════════════════════

def main():
    db_init()
    print("🤖 CPM Bot başlatıldı...")
    while True:
        try:
            bot.infinity_polling(timeout=30, long_polling_timeout=20)
        except Exception as e:
            print(f"⚠️ Polling hata: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
