#!/usr/bin/env python3
"""DITTO! prototype server: two real users, one wall.

Run:  python server.py [port]
Then open http://<your-lan-ip>:<port>/  on both devices.
"""
import json
import os
import random
import socket
import sys
import threading
import time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

BASE = os.path.dirname(os.path.abspath(__file__))
LOCK = threading.Lock()

CARDS = {}      # id -> {"num","words","channel","handle","ts"}
NOTES = []      # {"id","frm","to","word","text","status","ts"}
SEQ = [1000]
NOTE_SEQ = [0]

CONTACTS = {}   # "<noteId>:<cardId>" -> {"channel","handle"}
MSGS = []       # {"id","note","frm","text","ts"}
MSG_SEQ = [0]

DATA_FILE = os.path.join(BASE, "data.json")


def save_state():
    """Write everything to disk (atomic) so a restart never wipes the wall."""
    try:
        payload = {"cards": CARDS, "notes": NOTES, "msgs": MSGS, "contacts": CONTACTS,
                   "seq": SEQ[0], "note_seq": NOTE_SEQ[0], "msg_seq": MSG_SEQ[0]}
        tmp = DATA_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        os.replace(tmp, DATA_FILE)
    except Exception as e:
        print("save_state failed:", e)


def load_state():
    if not os.path.exists(DATA_FILE):
        return False
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            d = json.load(f)
        CARDS.update(d.get("cards") or {})
        NOTES.extend(d.get("notes") or [])
        MSGS.extend(d.get("msgs") or [])
        CONTACTS.update(d.get("contacts") or {})
        SEQ[0] = d.get("seq") or 1000
        NOTE_SEQ[0] = d.get("note_seq") or 0
        MSG_SEQ[0] = d.get("msg_seq") or 0
        return True
    except Exception as e:
        print("load_state failed:", e)
        return False


def wall():
    counts = {}
    for c in CARDS.values():
        for w in c["words"]:
            counts[w] = counts.get(w, 0) + 1
    return [{"word": w, "n": n} for w, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    # ---------- helpers ----------
    def _send(self, obj, code=200, ctype="application/json"):
        if code == 200 and not (isinstance(obj, dict) and obj.get("keep") is True):
            try:
                save_state()
            except Exception:
                pass
        body = obj if isinstance(obj, bytes) else json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _file(self, name, ctype):
        p = os.path.join(BASE, name)
        if not os.path.exists(p):
            self._send({"error": "not found"}, 404)
            return
        with open(p, "rb") as f:
            self._send(f.read(), 200, ctype)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            return {}

    # ---------- routes ----------
    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        p = u.path
        # heartbeat: any request that carries my card id marks me as "here"
        _hb = (q.get("id") or [""])[0]
        if _hb and _hb in CARDS:
            with LOCK:
                CARDS[_hb]["seen"] = time.time()
        if p in ("/", "/index.html", "/test", "/two"):
            return self._file("test.html", "text/html")
        if p in ("/en", "/english"):
            return self._file("test-en.html", "text/html")
        if p == "/api/wall":
            with LOCK:
                return self._send({"words": wall()})
        if p == "/api/card":
            cid = (q.get("id") or [""])[0]
            with LOCK:
                c = CARDS.get(cid)
                return self._send({"ok": bool(c), "card": c})
        if p == "/api/inbox":
            cid = (q.get("id") or [""])[0]
            with LOCK:
                out = [{"id": n["id"], "word": n["word"], "text": n["text"],
                        "from": CARDS.get(n["frm"], {}).get("num", "?")}
                       for n in NOTES if n["to"] == cid and n["status"] == "pending"]
                return self._send({"notes": out})
        if p == "/api/sent":
            cid = (q.get("id") or [""])[0]
            with LOCK:
                mine = [n for n in NOTES if n["frm"] == cid]
                if not mine:
                    return self._send({"note": None})
                n = mine[-1]
                their = CARDS.get(n["to"], {})
                res = {"id": n["id"], "word": n["word"], "status": n["status"],
                       "their": their.get("num"), "channel": their.get("channel"),
                       "handle": their.get("handle")}
                return self._send({"note": res})
        if p == "/api/threads":
            ids = set(x for x in (q.get("ids") or [""])[0].split(",") if x)
            out = []
            with LOCK:
                for n in NOTES:
                    if n["status"] != "accepted":
                        continue
                    if n["frm"] in ids:
                        mine_id, peer_id = n["frm"], n["to"]
                    elif n["to"] in ids:
                        mine_id, peer_id = n["to"], n["frm"]
                    else:
                        continue
                    peer = CARDS.get(peer_id) or {}
                    mine_card = CARDS.get(mine_id) or {}
                    thread_msgs = [m for m in MSGS if m["note"] == n["id"]]
                    last = max([m["id"] for m in thread_msgs], default=0)
                    last_msg = thread_msgs[-1] if thread_msgs else None
                    out.append({"card": mine_id, "noteId": n["id"], "word": n["word"],
                                "words": n.get("words") or [n["word"]],
                                "num": mine_card.get("num"), "peer": peer.get("num"),
                                "peerSubmitted": ("%d:%s" % (n["id"], peer_id)) in CONTACTS,
                                "mineSubmitted": ("%d:%s" % (n["id"], mine_id)) in CONTACTS,
                                "lastId": last, "ts": n["ts"],
                                "lastText": (last_msg["text"][:40] if last_msg else ""),
                                "lastMine": bool(last_msg and last_msg["frm"] == mine_id)})
                out.sort(key=lambda t: (-(t["lastId"] or 0), -t["ts"]))
            return self._send({"threads": out})
        if p == "/api/msgs":
            nid = int((q.get("noteId") or ["0"])[0] or 0)
            after = int((q.get("after") or ["0"])[0] or 0)
            with LOCK:
                out = [m for m in MSGS if m["note"] == nid and m["id"] > after]
                return self._send({"msgs": out})
        if p == "/api/contact":
            cid = (q.get("id") or [""])[0]
            nid = int((q.get("noteId") or ["0"])[0] or 0)
            with LOCK:
                me_card = CARDS.get(cid) or {}
                n = next((x for x in NOTES if x["id"] == nid and cid in (x["frm"], x["to"])
                          and x["status"] == "accepted"), None)
                if not n:
                    return self._send({"noteId": None, "word": None,
                                       "mine": {"num": me_card.get("num"), "words": me_card.get("words", [])},
                                       "peer": None, "mineSubmitted": False, "peerSubmitted": False,
                                       "both": False, "theirs": None})
                peer_id = n["to"] if n["frm"] == cid else n["frm"]
                peer_card = CARDS.get(peer_id) or {}
                mine = CONTACTS.get("%d:%s" % (nid, cid))
                theirs = CONTACTS.get("%d:%s" % (nid, peer_id))
                both = bool(mine and theirs)
                return self._send({
                    "noteId": nid, "word": n["word"],
                    "mine": {"num": me_card.get("num"), "words": me_card.get("words", []),
                             "channel": mine.get("channel") if mine else None,
                             "handle": mine.get("handle") if mine else None},
                    "peer": {"num": peer_card.get("num"), "words": peer_card.get("words", [])},
                    "mineSubmitted": bool(mine), "peerSubmitted": bool(theirs),
                    "theirs": ({"channel": theirs.get("channel"), "handle": theirs.get("handle")}
                               if both else None),
                    "both": both})
        return self._send({"error": "no route"}, 404)

    def do_POST(self):
        u = urlparse(self.path)
        p = u.path
        b = self._body()

        if p == "/api/card":
            words = [str(w).strip()[:18] for w in (b.get("words") or []) if str(w).strip()][:3]
            if not words:
                return self._send({"ok": False, "error": "no words"}, 400)
            with LOCK:
                existing = b.get("id")
                if existing and existing in CARDS and not existing.startswith("s"):
                    # same person, edited words: keep the card number and the history
                    CARDS[existing]["words"] = words
                    return self._send({"ok": True, "id": existing, "num": CARDS[existing]["num"],
                                       "words": words, "updated": True})
                SEQ[0] += 1
                cid = "c%d" % SEQ[0]
                CARDS[cid] = {"num": "#%d" % SEQ[0], "words": words,
                              "channel": None, "handle": None,
                              "ts": time.time(), "seen": time.time()}
                return self._send({"ok": True, "id": cid, "num": CARDS[cid]["num"], "words": words})

        if p == "/api/note":
            cid, word, text = b.get("id"), b.get("word"), str(b.get("text") or "").strip()[:160]
            if not (cid in CARDS and word and text):
                return self._send({"ok": False, "error": "bad note"}, 400)
            exclude = set(b.get("exclude") or [])
            with LOCK:
                # never route to a seeded (fake) card: nobody is behind it
                already = set()
                for n in NOTES:
                    if n["word"] == word and cid in (n["frm"], n["to"]) and n["status"] in ("pending", "accepted"):
                        already.add(n["to"] if n["frm"] == cid else n["frm"])

                def pair_of(n):
                    return {n["frm"], n["to"]}

                def existing_thread_with(other, w):
                    """a conversation is unique per (pair, word): 电影 opens a new one"""
                    for n in NOTES:
                        if pair_of(n) != {cid, other} or n["status"] not in ("pending", "accepted"):
                            continue
                        if w in (n.get("words") or [n["word"]]):
                            return n
                    return None

                now = time.time()
                pool = [k for k, c in CARDS.items()
                        if k != cid and word in c["words"] and not k.startswith("s")
                        and k not in exclude and k not in already
                        and (now - c.get("seen", c.get("ts", 0)) < 300)]
                if not pool:
                    return self._send({"ok": False, "error": "no-one"}, 200)

                # prefer somebody I have no conversation with yet
                fresh = [k for k in pool if existing_thread_with(k, word) is None]
                to = random.choice(fresh or pool)
                old_thread = existing_thread_with(to, word)
                if old_thread:
                    words = old_thread.get("words") or [old_thread["word"]]
                    if word not in words:
                        words.append(word)
                    old_thread["words"] = words
                    return self._send({"ok": True, "to": CARDS[to]["num"], "card": to,
                                       "noteId": old_thread["id"], "rejoin": True,
                                       "accepted": old_thread["status"] == "accepted"})
                NOTE_SEQ[0] += 1
                NOTES.append({"id": NOTE_SEQ[0], "frm": cid, "to": to, "word": word,
                              "words": [word], "text": text, "status": "pending", "ts": time.time()})
                return self._send({"ok": True, "to": CARDS[to]["num"], "card": to})

        if p == "/api/answer":
            note_id, cid, accept = b.get("noteId"), b.get("id"), bool(b.get("accept"))
            with LOCK:
                for n in NOTES:
                    if n["id"] == note_id and n["to"] == cid:
                        n["status"] = "accepted" if accept else "declined"
                        return self._send({"ok": True, "status": n["status"]})
            return self._send({"ok": False}, 404)

        if p == "/api/msg":
            nid, cid = b.get("noteId"), b.get("id")
            text = str(b.get("text") or "").strip()[:200]
            if not (nid and cid and text):
                return self._send({"ok": False, "error": "bad msg"}, 400)
            with LOCK:
                note = next((n for n in NOTES if n["id"] == nid and n["status"] == "accepted"
                             and cid in (n["frm"], n["to"])), None)
                if not note:
                    return self._send({"ok": False, "error": "no room"}, 403)
                MSG_SEQ[0] += 1
                MSGS.append({"id": MSG_SEQ[0], "note": nid, "frm": cid, "text": text, "ts": time.time()})
                return self._send({"ok": True, "id": MSG_SEQ[0]})

        if p == "/api/contact":
            cid, nid = b.get("id"), int(b.get("noteId") or 0)
            with LOCK:
                n = next((x for x in NOTES if x["id"] == nid and cid in (x["frm"], x["to"])
                          and x["status"] == "accepted"), None)
                if not n:
                    return self._send({"ok": False, "error": "no thread"}, 404)
                CONTACTS["%d:%s" % (nid, cid)] = {"channel": b.get("channel") or "微信",
                                                  "handle": str(b.get("handle") or "")[:40]}
                return self._send({"ok": True})
        return self._send({"error": "no route"}, 404)


def lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("PORT", 8099))
    restored = load_state()
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    ip = lan_ip()
    print("DITTO server running (%s)" % ("data.json restored" if restored else "fresh, no data.json"))
    print("  local : http://127.0.0.1:%d/" % port)
    print("  LAN   : http://%s:%d/   (phone / other device)" % (ip, port))
    print("  zh    : /        en: /en")
    sys.stdout.flush()
    srv.serve_forever()


if __name__ == "__main__":
    main()
