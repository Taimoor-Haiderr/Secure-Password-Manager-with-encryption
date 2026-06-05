# ─── stdlib ───────────────────────────────────────────────────────────────────
import os, sys, time, random, string, hashlib, threading, base64, sqlite3
import datetime, subprocess, traceback
import tkinter as tk
from tkinter import ttk, messagebox

# ─── auto-install cryptography ────────────────────────────────────────────────muna1234@muna1234@
try:
    from cryptography.fernet import Fernet, InvalidToken
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install",
                           "cryptography", "-q"])
    from cryptography.fernet import Fernet, InvalidToken
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes

# ─── optional clipboard ───────────────────────────────────────────────────────
CLIP_OK = False
try:
    import pyperclip
    pyperclip.copy("")          # test it actually works
    CLIP_OK = True
except Exception:
    pass

# ══════════════════════════════════════════════════════════════════════════════
#  DESIGN TOKENS
# ══════════════════════════════════════════════════════════════════════════════
BG       = "#0A0D14"
SURFACE  = "#10151F"
CARD     = "#161D2E"
CARD2    = "#1C2438"
BORDER   = "#252E42"
ACCENT   = "#3B82F6"
ACCENT_H = "#2563EB"
GREEN    = "#22C55E"
RED      = "#EF4444"
AMBER    = "#F59E0B"
TEXT     = "#F1F5F9"
MUTED    = "#64748B"
INPUT    = "#0F1624"
SEL      = "#1E3A5F"

FH1  = ("Trebuchet MS", 20, "bold")
FH2  = ("Trebuchet MS", 14, "bold")
FB   = ("Trebuchet MS", 11)
FSM  = ("Trebuchet MS", 9)
FMONO= ("Courier New",  11)

APP_TITLE  = "Vault Pro"
DB_PATH    = "vault.db"
SALT_PATH  = "vault.key"
AUTO_LOCK  = 300    # seconds
CLIP_WIPE  = 15     # seconds

# ══════════════════════════════════════════════════════════════════════════════
#  CRYPTO ENGINE
# ══════════════════════════════════════════════════════════════════════════════
class Crypto:
    """Pure-static helpers + instance encrypt/decrypt via Fernet."""

    ITER = 390_000

    @staticmethod
    def new_salt() -> bytes:
        return os.urandom(32)

    @staticmethod
    def derive_key(password: str, salt: bytes) -> bytes:
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32,
                         salt=salt, iterations=Crypto.ITER)
        return base64.urlsafe_b64encode(kdf.derive(password.encode()))

    @staticmethod
    def hash_pw(password: str, salt: bytes) -> str:
        return hashlib.pbkdf2_hmac(
            "sha256", password.encode(), salt, Crypto.ITER).hex()

    def __init__(self, key: bytes):
        self._f = Fernet(key)

    def enc(self, text: str) -> str:
        return self._f.encrypt(text.encode()).decode()

    def dec(self, token: str) -> str:
        return self._f.decrypt(token.encode()).decode()

# ══════════════════════════════════════════════════════════════════════════════
#  DATABASE
# ══════════════════════════════════════════════════════════════════════════════
class DB:
    def __init__(self, path: str):
        self._c = sqlite3.connect(path, check_same_thread=False)
        self._c.execute("PRAGMA journal_mode=WAL")
        self._migrate()

    def _migrate(self):
        self._c.executescript("""
        CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS vault (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            site       TEXT NOT NULL,
            username   TEXT NOT NULL,
            password   TEXT NOT NULL,
            url        TEXT    DEFAULT '',
            notes      TEXT    DEFAULT '',
            category   TEXT    DEFAULT 'General',
            created    REAL    NOT NULL,
            updated    REAL    NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_site ON vault(site COLLATE NOCASE);
        """)
        self._c.commit()

    # kv helpers
    def set_kv(self, k, v): 
        self._c.execute("INSERT OR REPLACE INTO kv VALUES(?,?)", (k,v)); self._c.commit()
    def get_kv(self, k):
        r = self._c.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
        return r[0] if r else None
    def has_master(self): return self.get_kv("hash") is not None

    # CRUD
    def add(self, site, user, pwd, url="", notes="", cat="General") -> int:
        n = time.time()
        cur = self._c.execute(
            "INSERT INTO vault(site,username,password,url,notes,category,created,updated)"
            " VALUES(?,?,?,?,?,?,?,?)", (site,user,pwd,url,notes,cat,n,n))
        self._c.commit(); return cur.lastrowid

    def update(self, eid, site, user, pwd, url="", notes="", cat="General"):
        self._c.execute(
            "UPDATE vault SET site=?,username=?,password=?,url=?,notes=?,"
            "category=?,updated=? WHERE id=?",
            (site,user,pwd,url,notes,cat,time.time(),eid))
        self._c.commit()

    def delete(self, eid):
        self._c.execute("DELETE FROM vault WHERE id=?", (eid,)); self._c.commit()

    def all(self, q="") -> list:
        if q:
            p = f"%{q}%"
            rows = self._c.execute(
                "SELECT id,site,username,password,url,notes,category,created,updated"
                " FROM vault WHERE site LIKE ? OR username LIKE ? OR url LIKE ?"
                " OR notes LIKE ? ORDER BY site COLLATE NOCASE", (p,p,p,p)).fetchall()
        else:
            rows = self._c.execute(
                "SELECT id,site,username,password,url,notes,category,created,updated"
                " FROM vault ORDER BY site COLLATE NOCASE").fetchall()
        return [dict(id=r[0],site=r[1],username=r[2],password=r[3],
                     url=r[4],notes=r[5],category=r[6],
                     created=r[7],updated=r[8]) for r in rows]

    def close(self): self._c.close()

# ══════════════════════════════════════════════════════════════════════════════
#  PASSWORD GENERATOR
# ══════════════════════════════════════════════════════════════════════════════
class PwGen:
    U = string.ascii_uppercase
    L = string.ascii_lowercase
    D = string.digits
    S = r"!@#$%^&*()_+-=[]{}|;:,.<>?"

    @classmethod
    def make(cls, n=20, up=True, lo=True, dg=True, sy=True) -> str:
        pool, req = "", []
        if up: pool+=cls.U; req.append(random.choice(cls.U))
        if lo: pool+=cls.L; req.append(random.choice(cls.L))
        if dg: pool+=cls.D; req.append(random.choice(cls.D))
        if sy: pool+=cls.S; req.append(random.choice(cls.S))
        if not pool: pool=cls.L; req=[random.choice(cls.L)]
        rest=[random.choice(pool) for _ in range(n-len(req))]
        chars=req+rest; random.shuffle(chars); return "".join(chars)

    @classmethod
    def score(cls, p: str) -> tuple:
        s=0
        if len(p)>=8:  s+=10
        if len(p)>=12: s+=15
        if len(p)>=16: s+=15
        if len(p)>=20: s+=10
        if any(c in cls.U for c in p): s+=12
        if any(c in cls.L for c in p): s+=8
        if any(c in cls.D for c in p): s+=13
        if any(c in cls.S for c in p): s+=17
        lb=("Very Weak" if s<25 else "Weak" if s<45 else
            "Fair" if s<65 else "Strong" if s<82 else "Very Strong")
        return min(s,100), lb

# ══════════════════════════════════════════════════════════════════════════════
#  WIDGET HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def mk_btn(parent, txt, cmd, bg=None, fg=TEXT, font=FB, pad=(14,7), **kw):
    b_bg = bg or ACCENT
    btn = tk.Button(parent, text=txt, command=cmd, bg=b_bg, fg=fg,
                    activebackground=b_bg, activeforeground=fg,
                    font=font, relief="flat", bd=0, cursor="hand2",
                    padx=pad[0], pady=pad[1], **kw)
    orig = b_bg
    lighter = _lc(b_bg)
    btn.bind("<Enter>", lambda _: btn.config(bg=lighter, activebackground=lighter))
    btn.bind("<Leave>", lambda _: btn.config(bg=orig,    activebackground=orig))
    return btn

def _lc(h, f=0.18):
    h=h.lstrip("#"); r,g,b=int(h[:2],16),int(h[2:4],16),int(h[4:],16)
    return "#{:02x}{:02x}{:02x}".format(
        min(255,int(r+(255-r)*f)), min(255,int(g+(255-g)*f)), min(255,int(b+(255-b)*f)))

def mk_entry(parent, show=None, font=FB, tvar=None, **kw):
    kw2 = {"textvariable": tvar} if tvar else {}
    e = tk.Entry(parent, bg=INPUT, fg=TEXT, insertbackground=TEXT,
                 relief="flat", bd=0, font=font,
                 highlightthickness=1, highlightcolor=ACCENT,
                 highlightbackground=BORDER,
                 **({"show": show} if show else {}), **kw2, **kw)
    return e

def divider(parent, bg=BORDER, **kw):
    return tk.Frame(parent, bg=bg, height=1, **kw)

def lbl(parent, text, font=FB, fg=TEXT, bg=None, **kw):
    return tk.Label(parent, text=text, font=font, fg=fg,
                    bg=bg or SURFACE, **kw)

# ══════════════════════════════════════════════════════════════════════════════
#  TOAST NOTIFICATION
# ══════════════════════════════════════════════════════════════════════════════
class Toast:
    _current = None

    @classmethod
    def show(cls, root, msg, kind="info", ms=3000):
        if cls._current:
            try: cls._current.destroy()
            except: pass
        color = {"info": ACCENT, "ok": GREEN, "err": RED, "warn": AMBER}.get(kind, ACCENT)
        w = tk.Toplevel(root)
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.configure(bg=CARD2)
        tk.Frame(w, bg=color, width=4).pack(side="left", fill="y")
        tk.Label(w, text=msg, font=FSM, bg=CARD2, fg=TEXT,
                 padx=14, pady=10).pack(side="left")
        w.update_idletasks()
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        tw = w.winfo_width(); th = w.winfo_height()
        w.geometry(f"+{sw-tw-24}+{sh-th-60}")
        cls._current = w
        root.after(ms, lambda: cls._safe_destroy(w))

    @staticmethod
    def _safe_destroy(w):
        try: w.destroy()
        except: pass

# ══════════════════════════════════════════════════════════════════════════════
#  MASTER PASSWORD DIALOG
# ══════════════════════════════════════════════════════════════════════════════
class MasterDlg(tk.Toplevel):
    def __init__(self, parent, is_new: bool):
        super().__init__(parent)
        self.result = None
        self.is_new = is_new
        self.configure(bg=BG)
        self.title("Vault Pro — " + ("Setup" if is_new else "Unlock"))
        self.resizable(False, False)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self._build()
        self.update_idletasks()
        self.geometry(f"440x{'390' if is_new else '320'}")
        self._center(parent)
        self.bind("<Return>", lambda _: self._ok())
        self.bind("<Escape>", lambda _: self._cancel())

    def _center(self, p):
        self.update_idletasks()
        x = p.winfo_x() + p.winfo_width()//2  - self.winfo_width()//2
        y = p.winfo_y() + p.winfo_height()//2 - self.winfo_height()//2
        self.geometry(f"+{max(0,x)}+{max(0,y)}")

    def _build(self):
        # top accent stripe
        tk.Frame(self, bg=ACCENT, height=3).pack(fill="x")

        wrap = tk.Frame(self, bg=BG)
        wrap.pack(fill="both", expand=True, padx=40, pady=30)

        # icon + title
        icon_lbl = tk.Label(wrap, text="🔐", font=("Segoe UI Emoji", 36),
                            bg=BG, fg=ACCENT)
        icon_lbl.pack(pady=(0,8))
        tk.Label(wrap,
                 text="Create Your Vault" if self.is_new else "Unlock Your Vault",
                 font=FH2, bg=BG, fg=TEXT).pack()
        tk.Label(wrap,
                 text=("Choose a strong master password — keep it safe."
                       if self.is_new else
                       "Enter your master password to continue."),
                 font=FSM, bg=BG, fg=MUTED, wraplength=340).pack(pady=(4,16))

        # field helper
        def field(frm, txt, show=None):
            tk.Label(frm, text=txt, font=FSM, bg=BG, fg=MUTED).pack(anchor="w")
            e = mk_entry(frm, show=show)
            e.pack(fill="x", ipady=8, pady=(2,10))
            return e

        self._e1 = field(wrap, "Master Password", show="●")
        self._e1.focus()
        if self.is_new:
            self._e2 = field(wrap, "Confirm Password", show="●")

        self._err = tk.Label(wrap, text="", font=FSM, bg=BG, fg=RED)
        self._err.pack()

        bf = tk.Frame(wrap, bg=BG)
        bf.pack(pady=(6,0))
        mk_btn(bf, "  Create Vault" if self.is_new else "  Unlock",
               self._ok, bg=ACCENT).pack(side="left", padx=(0,8))
        mk_btn(bf, "Cancel", self._cancel, bg=CARD2).pack(side="left")

    def _ok(self):
        p1 = self._e1.get()
        if not p1:
            self._err.config(text="Password cannot be empty."); return
        if self.is_new:
            if len(p1) < 8:
                self._err.config(text="Minimum 8 characters required."); return
            if p1 != self._e2.get():
                self._err.config(text="Passwords do not match."); return
        self.result = p1
        self.destroy()

    def _cancel(self):
        self.destroy()

# ══════════════════════════════════════════════════════════════════════════════
#  PASSWORD GENERATOR DIALOG
# ══════════════════════════════════════════════════════════════════════════════
class GenDlg(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.result = None
        self.configure(bg=SURFACE)
        self.title("Password Generator")
        self.resizable(False, False)
        self.grab_set()
        self.geometry("460x440")
        self._center(parent)
        self._build()
        self._regen()

    def _center(self, p):
        self.update_idletasks()
        x = p.winfo_x() + p.winfo_width()//2  - self.winfo_width()//2
        y = p.winfo_y() + p.winfo_height()//2 - self.winfo_height()//2
        self.geometry(f"+{max(0,x)}+{max(0,y)}")

    def _build(self):
        tk.Frame(self, bg=ACCENT, height=3).pack(fill="x")
        tk.Label(self, text="⚡  Password Generator",
                 font=FH2, bg=SURFACE, fg=TEXT).pack(padx=24, pady=(18,12), anchor="w")

        # output box
        of = tk.Frame(self, bg=CARD, padx=12, pady=10)
        of.pack(fill="x", padx=24)
        self._gv = tk.StringVar()
        ge = mk_entry(of, tvar=self._gv, font=FMONO)
        ge.config(state="readonly", bg=CARD, highlightbackground=BORDER)
        ge.pack(fill="x", ipady=7)

        # strength
        sf = tk.Frame(self, bg=SURFACE)
        sf.pack(fill="x", padx=24, pady=(6,0))
        self._sb = tk.Canvas(sf, height=6, bg=BORDER, highlightthickness=0)
        self._sb.pack(fill="x")
        self._sl = tk.Label(sf, text="", font=FSM, bg=SURFACE, fg=MUTED)
        self._sl.pack(anchor="e")

        body = tk.Frame(self, bg=SURFACE)
        body.pack(fill="x", padx=24, pady=8)

        # length row
        lf = tk.Frame(body, bg=SURFACE)
        lf.pack(fill="x", pady=(4,8))
        tk.Label(lf, text="Length:", font=FB, bg=SURFACE, fg=TEXT).pack(side="left")
        self._lv = tk.IntVar(value=20)
        tk.Label(lf, textvariable=self._lv, width=3,
                 font=("Trebuchet MS",11,"bold"), bg=SURFACE, fg=ACCENT).pack(side="right")

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("G.Horizontal.TScale", background=SURFACE,
                        troughcolor=BORDER, sliderlength=16)
        ttk.Scale(lf, from_=8, to=64, variable=self._lv, style="G.Horizontal.TScale",
                  orient="horizontal",
                  command=lambda _: self._regen()).pack(side="left", fill="x",
                                                        expand=True, padx=8)

        self._up = self._cb(body, "Uppercase  A–Z",  True)
        self._lo = self._cb(body, "Lowercase  a–z",  True)
        self._dg = self._cb(body, "Digits  0–9",     True)
        self._sy = self._cb(body, "Symbols  !@#…",   True)

        bf = tk.Frame(self, bg=SURFACE)
        bf.pack(padx=24, pady=(4,20), fill="x")
        mk_btn(bf, "↻  Regenerate", self._regen, bg=CARD2).pack(side="left")
        mk_btn(bf, "✓  Use This",  self._use,   bg=ACCENT).pack(side="left", padx=8)
        mk_btn(bf, "Cancel",       self.destroy, bg=CARD2).pack(side="right")

    def _cb(self, p, txt, val):
        v = tk.BooleanVar(value=val)
        tk.Checkbutton(p, text=txt, variable=v, bg=SURFACE, fg=TEXT,
                       activebackground=SURFACE, selectcolor=INPUT,
                       font=FB, command=self._regen).pack(anchor="w", pady=1)
        return v

    def _regen(self, *_):
        p = PwGen.make(self._lv.get(),
                       self._up.get(), self._lo.get(),
                       self._dg.get(), self._sy.get())
        self._gv.set(p)
        s, lb = PwGen.score(p)
        c = RED if s<35 else AMBER if s<65 else GREEN
        self.after(20, lambda: self._draw_bar(s, c, lb))

    def _draw_bar(self, s, c, lb):
        w = self._sb.winfo_width() or 400
        self._sb.delete("all")
        self._sb.create_rectangle(0,0, int(w*s/100), 6, fill=c, outline="")
        self._sl.config(text=lb, fg=c)

    def _use(self):
        self.result = self._gv.get(); self.destroy()

# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY DIALOG  (Add / Edit)
# ══════════════════════════════════════════════════════════════════════════════
CATS = ["General","Social","Banking","Work","Shopping","Email","Gaming","Other"]

class EntryDlg(tk.Toplevel):
    def __init__(self, parent, crypto: Crypto, entry: dict = None):
        super().__init__(parent)
        self.crypto  = crypto
        self.entry   = entry
        self.saved   = False
        self.out     = {}
        edit = entry is not None
        self.configure(bg=SURFACE)
        self.title("Edit Entry" if edit else "Add New Entry")
        self.resizable(False, False)
        self.grab_set()
        self.geometry("540x640")
        self._center(parent)
        self._build()
        if edit:
            self._populate()
        self.bind("<Escape>", lambda _: self.destroy())

    def _center(self, p):
        self.update_idletasks()
        x = p.winfo_x() + p.winfo_width()//2  - self.winfo_width()//2
        y = p.winfo_y() + p.winfo_height()//2 - self.winfo_height()//2
        self.geometry(f"+{max(0,x)}+{max(0,y)}")

    def _build(self):
        # header
        hdr = tk.Frame(self, bg=CARD)
        hdr.pack(fill="x")
        tk.Frame(hdr, bg=ACCENT, height=3).pack(fill="x")
        icon = "✏️" if self.entry else "➕"
        tk.Label(hdr, text=f"{icon}  {'Edit' if self.entry else 'New'} Entry",
                 font=FH2, bg=CARD, fg=TEXT).pack(padx=20, pady=14, anchor="w")

        body = tk.Frame(self, bg=SURFACE)
        body.pack(fill="both", expand=True, padx=24, pady=8)

        def row(label_txt, show=None, bg_ov=None):
            tk.Label(body, text=label_txt, font=FSM, bg=SURFACE, fg=MUTED).pack(
                anchor="w", pady=(10,1))
            e = mk_entry(body, show=show)
            if bg_ov: e.config(bg=bg_ov)
            e.pack(fill="x", ipady=8)
            return e

        self._site = row("Website / App Name  *")
        self._user = row("Username / Email  *")

        # password row
        tk.Label(body, text="Password  *", font=FSM, bg=SURFACE, fg=MUTED).pack(
            anchor="w", pady=(10,1))
        pr = tk.Frame(body, bg=SURFACE)
        pr.pack(fill="x")
        self._pv  = tk.StringVar()
        self._pshow = False
        self._pe = mk_entry(pr, show="●", tvar=self._pv)
        self._pe.pack(side="left", fill="x", expand=True, ipady=8)
        self._eye = tk.Button(pr, text="👁", bg=INPUT, fg=MUTED,
                              relief="flat", bd=0, cursor="hand2",
                              font=("Segoe UI Emoji",12),
                              command=self._toggle_eye)
        self._eye.pack(side="left", padx=(4,0))
        mk_btn(pr, "⚡", self._pick_gen, bg=CARD2,
               font=("Trebuchet MS",11), pad=(10,7)).pack(side="left", padx=(4,0))

        # strength bar
        sf = tk.Frame(body, bg=SURFACE)
        sf.pack(fill="x", pady=(4,0))
        self._sbar = tk.Canvas(sf, height=4, bg=BORDER, highlightthickness=0)
        self._sbar.pack(fill="x")
        self._slbl = tk.Label(sf, text="", font=FSM, bg=SURFACE, fg=MUTED)
        self._slbl.pack(anchor="e")
        self._pv.trace_add("write", self._upd_str)

        # category
        tk.Label(body, text="Category", font=FSM, bg=SURFACE, fg=MUTED).pack(
            anchor="w", pady=(10,1))
        self._cat = ttk.Combobox(body, values=CATS, state="readonly",
                                 font=FB)
        style = ttk.Style()
        style.configure("TCombobox", fieldbackground=INPUT, background=CARD2,
                        foreground=TEXT, selectbackground=SEL,
                        arrowcolor=MUTED)
        self._cat.set("General")
        self._cat.pack(fill="x", ipady=4)

        self._url   = row("URL  (optional)")
        tk.Label(body, text="Notes  (optional)", font=FSM, bg=SURFACE, fg=MUTED).pack(
            anchor="w", pady=(10,1))
        self._notes = tk.Text(body, height=3, bg=INPUT, fg=TEXT,
                              insertbackground=TEXT, relief="flat", bd=0,
                              font=FB, highlightthickness=1,
                              highlightcolor=ACCENT, highlightbackground=BORDER)
        self._notes.pack(fill="x")

        self._errlbl = tk.Label(body, text="", font=FSM, bg=SURFACE, fg=RED)
        self._errlbl.pack(pady=(6,0))

        # footer buttons
        ft = tk.Frame(self, bg=SURFACE)
        ft.pack(fill="x", padx=24, pady=(4,20))
        mk_btn(ft, "💾  Save", self._save, bg=ACCENT).pack(side="left")
        mk_btn(ft, "Cancel",   self.destroy, bg=CARD2).pack(side="left", padx=10)

        self._site.focus()

    def _toggle_eye(self):
        self._pshow = not self._pshow
        self._pe.config(show="" if self._pshow else "●")
        self._eye.config(text="🙈" if self._pshow else "👁")

    def _upd_str(self, *_):
        p = self._pv.get()
        if not p:
            self._sbar.delete("all"); self._slbl.config(text=""); return
        s, lb = PwGen.score(p)
        c = RED if s<35 else AMBER if s<65 else GREEN
        w = self._sbar.winfo_width() or 440
        self._sbar.delete("all")
        self._sbar.create_rectangle(0,0, int(w*s/100), 4, fill=c, outline="")
        self._slbl.config(text=lb, fg=c)

    def _pick_gen(self):
        d = GenDlg(self); self.wait_window(d)
        if d.result: self._pv.set(d.result)

    def _populate(self):
        e = self.entry
        try: pw = self.crypto.dec(e["password"])
        except: pw = ""
        self._site.insert(0, e["site"])
        self._user.insert(0, e["username"])
        self._pv.set(pw)
        self._url.insert(0, e.get("url",""))
        self._notes.insert("1.0", e.get("notes",""))
        cat = e.get("category","General")
        self._cat.set(cat if cat in CATS else "General")

    def _save(self):
        site = self._site.get().strip()
        user = self._user.get().strip()
        pw   = self._pv.get()
        if not site: self._errlbl.config(text="Site name is required."); return
        if not user: self._errlbl.config(text="Username is required.");   return
        if not pw:   self._errlbl.config(text="Password is required.");   return
        self.out = dict(site=site, username=user,
                        password=self.crypto.enc(pw),
                        url=self._url.get().strip(),
                        notes=self._notes.get("1.0","end-1c").strip(),
                        category=self._cat.get())
        self.saved = True
        self.destroy()

# ══════════════════════════════════════════════════════════════════════════════
#  DETAIL PANEL
# ══════════════════════════════════════════════════════════════════════════════
class DetailPanel(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=SURFACE)
        self._app = app
        self._show_empty()

    def _clear(self):
        for w in self.winfo_children(): w.destroy()

    def _show_empty(self):
        self._clear()
        tk.Label(self, text="🔒", font=("Segoe UI Emoji",48),
                 bg=SURFACE, fg=BORDER).pack(pady=(100,12))
        tk.Label(self, text="Select an entry to view details",
                 font=FB, bg=SURFACE, fg=MUTED).pack()
        tk.Label(self, text="or press  ➕ Add Entry  to get started",
                 font=FSM, bg=SURFACE, fg=MUTED).pack(pady=4)

    def show(self, entry: dict, crypto: Crypto):
        self._clear()

        # site header card
        hdr = tk.Frame(self, bg=CARD)
        hdr.pack(fill="x")
        tk.Frame(hdr, bg=ACCENT, height=3).pack(fill="x")

        inner_h = tk.Frame(hdr, bg=CARD)
        inner_h.pack(fill="x", padx=20, pady=(14,14))
        # category pill
        cat_col = {"Banking": "#F59E0B","Social":"#8B5CF6","Work":"#3B82F6",
                   "Email":"#EC4899","Gaming":"#10B981"}.get(entry.get("category",""), MUTED)
        tk.Label(inner_h, text=f"  {entry.get('category','General')}  ",
                 font=FSM, bg=cat_col, fg=BG).pack(anchor="w")
        tk.Label(inner_h, text=entry["site"][:44],
                 font=FH1, bg=CARD, fg=TEXT).pack(anchor="w", pady=(4,0))
        if entry.get("url"):
            tk.Label(inner_h, text=entry["url"],
                     font=FSM, bg=CARD, fg=ACCENT).pack(anchor="w")

        body = tk.Frame(self, bg=SURFACE)
        body.pack(fill="both", expand=True, padx=20, pady=8)

        def field(name, val, mono=False, secret=False):
            if not val: return
            tk.Label(body, text=name, font=FSM, bg=SURFACE, fg=MUTED).pack(
                anchor="w", pady=(12,2))
            rf = tk.Frame(body, bg=CARD)
            rf.pack(fill="x")

            disp = "●"*len(val) if secret else val
            sv   = tk.StringVar(value=disp)
            shown= [False]

            tk.Label(rf, textvariable=sv, font=FMONO if mono else FB,
                     bg=CARD, fg=TEXT, anchor="w",
                     padx=12, pady=9).pack(side="left", fill="x", expand=True)

            bgrp = tk.Frame(rf, bg=CARD)
            bgrp.pack(side="right", padx=6)

            if secret:
                def _toggle(v=val, sv=sv, shown=shown):
                    shown[0] = not shown[0]
                    sv.set(v if shown[0] else "●"*len(v))
                    eye_b.config(text="🙈" if shown[0] else "👁")
                eye_b = tk.Button(bgrp, text="👁", bg=CARD, fg=MUTED,
                                  relief="flat", bd=0, cursor="hand2",
                                  font=("Segoe UI Emoji",11), command=_toggle)
                eye_b.pack(side="left")

            def _copy(v=val):
                self._app.do_copy(v)
            tk.Button(bgrp, text="📋", bg=CARD, fg=MUTED,
                      relief="flat", bd=0, cursor="hand2",
                      font=("Segoe UI Emoji",11), command=_copy).pack(side="left")

        try: plain = crypto.dec(entry["password"])
        except InvalidToken: plain = "(decryption failed)"

        field("Username / Email", entry["username"])
        field("Password",         plain, mono=True, secret=True)
        if entry.get("notes"):
            field("Notes", entry["notes"])

        ts = datetime.datetime.fromtimestamp(entry["updated"]).strftime("%d %b %Y, %H:%M")
        tk.Label(body, text=f"Updated {ts}", font=FSM,
                 bg=SURFACE, fg=MUTED).pack(anchor="w", pady=(14,4))

        divider(body).pack(fill="x", pady=8)

        af = tk.Frame(body, bg=SURFACE)
        af.pack(anchor="w")
        mk_btn(af, "✏️  Edit",   lambda: self._app.do_edit(entry),   bg=ACCENT).pack(side="left")
        mk_btn(af, "🗑  Delete", lambda: self._app.do_delete(entry), bg=RED).pack(side="left", padx=10)

# ══════════════════════════════════════════════════════════════════════════════
#  CHANGE MASTER PASSWORD DIALOG
# ══════════════════════════════════════════════════════════════════════════════
class ChangeMasterDlg(tk.Toplevel):
    def __init__(self, parent, crypto: Crypto, db: DB):
        super().__init__(parent)
        self.crypto = crypto
        self.db = db
        self.configure(bg=BG)
        self.title("Change Master Password")
        self.resizable(False, False)
        self.grab_set()
        self.geometry("420x380")
        self._center(parent)
        self._build()
        self.bind("<Return>", lambda _: self._ok())
        self.bind("<Escape>", lambda _: self.destroy())

    def _center(self, p):
        self.update_idletasks()
        x = p.winfo_x() + p.winfo_width()//2  - self.winfo_width()//2
        y = p.winfo_y() + p.winfo_height()//2 - self.winfo_height()//2
        self.geometry(f"+{max(0,x)}+{max(0,y)}")

    def _build(self):
        tk.Frame(self, bg=ACCENT, height=3).pack(fill="x")
        wrap = tk.Frame(self, bg=BG)
        wrap.pack(fill="both", expand=True, padx=36, pady=24)

        tk.Label(wrap, text="🔑  Change Master Password",
                 font=FH2, bg=BG, fg=TEXT).pack(pady=(0,16))

        def row(txt, s="●"):
            tk.Label(wrap, text=txt, font=FSM, bg=BG, fg=MUTED).pack(anchor="w")
            e = mk_entry(wrap, show=s)
            e.pack(fill="x", ipady=7, pady=(2,10))
            return e

        self._old = row("Current Password")
        self._new = row("New Password")
        self._cfm = row("Confirm New Password")
        self._old.focus()

        self._err = tk.Label(wrap, text="", font=FSM, bg=BG, fg=RED)
        self._err.pack()

        bf = tk.Frame(wrap, bg=BG)
        bf.pack(pady=8)
        mk_btn(bf, "✓  Change", self._ok, bg=ACCENT).pack(side="left", padx=(0,8))
        mk_btn(bf, "Cancel", self.destroy, bg=CARD2).pack(side="left")

    def _ok(self):
        old = self._old.get()
        new = self._new.get()
        cfm = self._cfm.get()
        # verify old
        try:
            with open(SALT_PATH,"rb") as f: salt = f.read()
        except FileNotFoundError:
            self._err.config(text="Salt file missing."); return
        stored = self.db.get_kv("hash")
        if Crypto.hash_pw(old, salt) != stored:
            self._err.config(text="Current password is incorrect."); return
        if len(new) < 8:
            self._err.config(text="New password must be 8+ characters."); return
        if new != cfm:
            self._err.config(text="New passwords do not match."); return
        # re-derive and re-encrypt everything
        new_salt = Crypto.new_salt()
        new_key  = Crypto.derive_key(new, new_salt)
        new_hash = Crypto.hash_pw(new, new_salt)
        new_crypto = Crypto(new_key)
        entries = self.db.all()
        for e in entries:
            try:
                plain = self.crypto.dec(e["password"])
                new_enc = new_crypto.enc(plain)
                self.db._c.execute("UPDATE vault SET password=? WHERE id=?",
                                   (new_enc, e["id"]))
            except Exception:
                pass
        self.db._c.commit()
        with open(SALT_PATH,"wb") as f: f.write(new_salt)
        self.db.set_kv("hash", new_hash)
        # update live crypto in app
        self._parent_app = self.master
        messagebox.showinfo("Success","Master password changed successfully!\nPlease re-lock and unlock to continue.")
        self.destroy()

# ══════════════════════════════════════════════════════════════════════════════
#  MAIN APP WINDOW
# ══════════════════════════════════════════════════════════════════════════════
class VaultApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.withdraw()
        self.title(APP_TITLE)
        self.configure(bg=BG)
        self.geometry("1120x700")
        self.minsize(860, 560)

        self._db     : DB     = None
        self._crypto : Crypto = None
        self._locked = True
        self._last_t = time.time()
        self._rows   : list   = []
        self._clip_t          = None

        # global ttk styling
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("Vertical.TScrollbar", background=BORDER,
                    troughcolor=SURFACE, arrowcolor=MUTED,
                    borderwidth=0, relief="flat")

        self._startup()

    # ── Auth ──────────────────────────────────────────────────────────────────
    def _startup(self):
        self._db = DB(DB_PATH)
        if self._db.has_master():
            self._do_unlock()
        else:
            self._do_setup()

    def _do_setup(self):
        d = MasterDlg(self, is_new=True)
        self.wait_window(d)
        if not d.result: self.destroy(); return
        salt = Crypto.new_salt()
        with open(SALT_PATH,"wb") as f: f.write(salt)
        key = Crypto.derive_key(d.result, salt)
        self._db.set_kv("hash", Crypto.hash_pw(d.result, salt))
        self._crypto = Crypto(key)
        self._locked = False
        self._build_ui()
        self.deiconify()
        self._start_watcher()

    def _do_unlock(self):
        d = MasterDlg(self, is_new=False)
        self.wait_window(d)
        if not d.result: self.destroy(); return
        try:
            with open(SALT_PATH,"rb") as f: salt = f.read()
        except FileNotFoundError:
            messagebox.showerror("Error","vault.key file missing — cannot decrypt.")
            self.destroy(); return
        if Crypto.hash_pw(d.result, salt) != self._db.get_kv("hash"):
            messagebox.showerror("Wrong Password","Incorrect master password.")
            self._do_unlock(); return
        key = Crypto.derive_key(d.result, salt)
        self._crypto = Crypto(key)
        self._locked = False
        self._build_ui()
        self.deiconify()
        self._start_watcher()

    # ── Build UI ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        # ── top bar ───────────────────────────────────────────────────────────
        top = tk.Frame(self, bg=CARD, height=58)
        top.pack(fill="x", side="top"); top.pack_propagate(False)
        tk.Frame(top, bg=ACCENT, width=4).pack(side="left", fill="y")

        tk.Label(top, text="🔐  Vault Pro",
                 font=("Trebuchet MS",16,"bold"), bg=CARD, fg=TEXT).pack(
                 side="left", padx=18)

        right = tk.Frame(top, bg=CARD)
        right.pack(side="right", padx=12)
        mk_btn(right,"🔒  Lock",    self._lock,        bg=CARD2, font=FSM).pack(side="right",padx=3)
        mk_btn(right,"⚙  Settings",self._settings_menu,bg=CARD2, font=FSM).pack(side="right",padx=3)
        mk_btn(right,"⚡ Generator",self._standalone_gen, bg=CARD2, font=FSM).pack(side="right",padx=3)
        mk_btn(right,"➕  Add",     self.do_add,        bg=ACCENT, font=FSM).pack(side="right",padx=3)

        # ── status bar ────────────────────────────────────────────────────────
        self._stat = tk.Label(self, text="", font=FSM, bg=BG, fg=MUTED,
                              anchor="w", padx=16)
        self._stat.pack(fill="x", side="bottom", pady=(0,3))

        # ── main layout ───────────────────────────────────────────────────────
        pane = tk.Frame(self, bg=BG)
        pane.pack(fill="both", expand=True)

        # sidebar
        side = tk.Frame(pane, bg=SURFACE, width=320)
        side.pack(fill="y", side="left"); side.pack_propagate(False)

        # search bar
        sf = tk.Frame(side, bg=SURFACE, pady=10, padx=10)
        sf.pack(fill="x")
        tk.Label(sf, text="🔍", font=("Segoe UI Emoji",13),
                 bg=SURFACE, fg=MUTED).pack(side="left")
        self._sv = tk.StringVar()
        se = mk_entry(sf, tvar=self._sv)
        se.pack(side="left", fill="x", expand=True, padx=6, ipady=6)
        self._sv.trace_add("write", lambda *_: self._reload())
        # clear button
        tk.Button(sf, text="✕", bg=SURFACE, fg=MUTED, relief="flat", bd=0,
                  cursor="hand2", font=FSM,
                  command=lambda: self._sv.set("")).pack(side="left")

        divider(side).pack(fill="x")

        # category filter tabs
        self._cat_filter = tk.StringVar(value="All")
        cf = tk.Frame(side, bg=SURFACE)
        cf.pack(fill="x", padx=6, pady=6)
        for cat in ["All"] + CATS[:5]:
            rb = tk.Radiobutton(cf, text=cat, variable=self._cat_filter,
                                value=cat, bg=SURFACE, fg=MUTED,
                                activebackground=SURFACE,
                                selectcolor=SEL,
                                indicatoron=False,
                                relief="flat", bd=0,
                                font=("Trebuchet MS",8),
                                padx=6, pady=3, cursor="hand2",
                                command=self._reload)
            rb.pack(side="left", padx=2)

        divider(side).pack(fill="x")

        self._cnt = tk.Label(side, text="", font=FSM, bg=SURFACE, fg=MUTED,
                             anchor="w", padx=12)
        self._cnt.pack(fill="x", pady=(6,2))

        # listbox
        lf = tk.Frame(side, bg=SURFACE)
        lf.pack(fill="both", expand=True)

        style = ttk.Style()
        style.configure("Vault.Vertical.TScrollbar",
                        background=BORDER, troughcolor=SURFACE,
                        arrowcolor=MUTED, borderwidth=0)

        self._lb = tk.Listbox(lf, bg=SURFACE, fg=TEXT,
                              selectbackground=SEL, selectforeground=TEXT,
                              activestyle="none", relief="flat", bd=0,
                              highlightthickness=0, font=FB,
                              selectmode="browse")
        sb = ttk.Scrollbar(lf, orient="vertical",
                           command=self._lb.yview,
                           style="Vault.Vertical.TScrollbar")
        self._lb.config(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._lb.pack(side="left", fill="both", expand=True)
        self._lb.bind("<<ListboxSelect>>", self._on_sel)
        self._lb.bind("<Double-Button-1>",  self._on_sel)

        # vertical divider
        tk.Frame(pane, bg=BORDER, width=1).pack(fill="y", side="left")

        # detail area
        self._detail = DetailPanel(pane, self)
        self._detail.pack(fill="both", expand=True, side="left")

        self._reload()
        self._bind_activity()

    # ── List ──────────────────────────────────────────────────────────────────
    def _reload(self, sel_id=None):
        q = self._sv.get().strip() if hasattr(self,"_sv") else ""
        cat = self._cat_filter.get() if hasattr(self,"_cat_filter") else "All"
        rows = self._db.all(q)
        if cat != "All":
            rows = [r for r in rows if r.get("category","General")==cat]
        self._rows = rows
        self._lb.delete(0,"end")
        for r in rows:
            self._lb.insert("end", f"  {r['site']}")
        n = len(rows)
        self._cnt.config(text=f"  {n} item{'s' if n!=1 else ''}")
        if sel_id:
            for i,r in enumerate(self._rows):
                if r["id"]==sel_id:
                    self._lb.selection_set(i); self._lb.see(i)
                    self._detail.show(r, self._crypto); break

    def _on_sel(self, _=None):
        sel = self._lb.curselection()
        if sel: self._detail.show(self._rows[sel[0]], self._crypto)

    # ── CRUD ──────────────────────────────────────────────────────────────────
    def do_add(self):
        self._touch()
        d = EntryDlg(self, self._crypto)
        self.wait_window(d)
        if d.saved:
            eid = self._db.add(**d.out)
            self._reload(sel_id=eid)
            Toast.show(self, f"✓  '{d.out['site']}' saved.", "ok")

    def do_edit(self, entry):
        self._touch()
        d = EntryDlg(self, self._crypto, entry=entry)
        self.wait_window(d)
        if d.saved:
            self._db.update(entry["id"], **d.out)
            self._reload(sel_id=entry["id"])
            Toast.show(self, f"✓  '{d.out['site']}' updated.", "ok")

    def do_delete(self, entry):
        self._touch()
        if messagebox.askyesno("Delete",
                               f"Permanently delete '{entry['site']}'?",
                               icon="warning", parent=self):
            self._db.delete(entry["id"])
            self._detail._show_empty()
            self._reload()
            Toast.show(self, f"Deleted '{entry['site']}'.", "warn")

    # ── Clipboard ─────────────────────────────────────────────────────────────
    def do_copy(self, text: str):
        if CLIP_OK:
            try:
                pyperclip.copy(text)
                self._stat.config(text=f"📋  Copied! Auto-clears in {CLIP_WIPE}s")
                if self._clip_t: self._clip_t.cancel()
                self._clip_t = threading.Timer(CLIP_WIPE, self._wipe_clip)
                self._clip_t.daemon = True
                self._clip_t.start()
                Toast.show(self, f"Copied — clears in {CLIP_WIPE}s", "info")
            except Exception:
                Toast.show(self, "Clipboard error.", "err")
        else:
            Toast.show(self, "pyperclip not available — install it for clipboard.", "warn")

    def _wipe_clip(self):
        try: pyperclip.copy("")
        except: pass
        self.after(0, lambda: (
            self._stat.config(text="🧹  Clipboard cleared."),
            self.after(3000, lambda: self._stat.config(text=""))
        ))

    # ── Generator standalone ──────────────────────────────────────────────────
    def _standalone_gen(self):
        self._touch()
        d = GenDlg(self); self.wait_window(d)
        if d.result:
            self.do_copy(d.result)
            Toast.show(self,"⚡  Generated password copied!","ok")

    # ── Settings ──────────────────────────────────────────────────────────────
    def _settings_menu(self):
        self._touch()
        menu = tk.Menu(self, tearoff=False, bg=CARD2, fg=TEXT,
                       activebackground=SEL, activeforeground=TEXT,
                       font=FB, relief="flat", bd=0)
        menu.add_command(label="🔑  Change Master Password",
                         command=self._change_master)
        menu.add_separator()
        menu.add_command(label="📤  Export (plaintext JSON)  ⚠",
                         command=self._export)
        menu.add_command(label="ℹ️  About", command=self._about)
        try:
            btn = self.winfo_containing(
                self.winfo_pointerx(), self.winfo_pointery())
            x = btn.winfo_rootx()
            y = btn.winfo_rooty() + btn.winfo_height()
        except: x=y=100
        menu.tk_popup(x, y)

    def _change_master(self):
        ChangeMasterDlg(self, self._crypto, self._db)

    def _export(self):
        if not messagebox.askyesno("Export Warning",
            "This will export ALL passwords in PLAIN TEXT.\n"
            "Only do this if you understand the security risk.\n\nContinue?",
            icon="warning"): return
        import json, tkinter.filedialog as fd
        path = fd.asksaveasfilename(defaultextension=".json",
            filetypes=[("JSON","*.json")], title="Export Vault")
        if not path: return
        rows = self._db.all()
        out = []
        for r in rows:
            try: pw = self._crypto.dec(r["password"])
            except: pw = "(error)"
            out.append(dict(site=r["site"], username=r["username"],
                            password=pw, url=r["url"],
                            notes=r["notes"], category=r["category"]))
        with open(path,"w") as f: json.dump(out, f, indent=2)
        Toast.show(self, f"Exported {len(out)} entries.", "ok")

    def _about(self):
        messagebox.showinfo("About Vault Pro",
            "Vault Pro — Secure Password Manager\n"
            "Encryption: Fernet (AES-128-CBC + HMAC)\n"
            "KDF: PBKDF2-HMAC-SHA256 (390,000 rounds)\n"
            "Storage: SQLite3\n\n"
            f"Auto-lock: {AUTO_LOCK}s  |  Clipboard wipe: {CLIP_WIPE}s")

    # ── Lock / Inactivity ─────────────────────────────────────────────────────
    def _lock(self):
        self._locked = True
        self._crypto = None
        self._rows   = []
        if self._clip_t: self._clip_t.cancel()
        try: pyperclip.copy("")
        except: pass
        for w in self.winfo_children(): w.destroy()
        self.withdraw()
        self._do_unlock()

    def _start_watcher(self):
        def _run():
            while True:
                time.sleep(15)
                if self._locked: break
                if time.time() - self._last_t > AUTO_LOCK:
                    self.after(0, self._lock); break
        threading.Thread(target=_run, daemon=True).start()

    def _bind_activity(self):
        self.bind_all("<Motion>",  lambda _: self._touch())
        self.bind_all("<Key>",     lambda _: self._touch())
        self.bind_all("<Button>",  lambda _: self._touch())

    def _touch(self): self._last_t = time.time()

    # ── Cleanup ───────────────────────────────────────────────────────────────
    def on_close(self):
        if self._clip_t: self._clip_t.cancel()
        try: pyperclip.copy("")
        except: pass
        if self._db: self._db.close()
        self.destroy()

# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = VaultApp()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()