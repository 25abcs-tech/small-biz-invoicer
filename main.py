# ============================================================
# InvoBiz — Invoicing and Business Management made Easy
# Copyright (c) 2026 Anna Elusini — 25ABCs. All rights reserved.
#
# This software is proprietary and confidential.
# Unauthorized copying, distribution, or modification
# of this file, via any medium, is strictly prohibited.
# ============================================================

import customtkinter as ctk
import sqlite3, json, os, sys
from datetime import datetime, timedelta
from tkinter import messagebox, filedialog
import tkinter as tk
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER

# ── THEME ──────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

RED    = "#E63B2E"
DARK   = "#1a1a2e"
GREEN  = "#16A34A"
AMBER  = "#d97706"
BLUE   = "#2563EB"
GRAY   = "#6b7280"
LIGHT  = "#f3f4f6"
WHITE  = "#ffffff"
BORDER = "#e5e7eb"

# ── DATABASE ───────────────────────────────────────────────────────────────
def db_path():
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "invoicer.db")

def get_db():
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA cache_size=-64000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn

def init_db():
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, company TEXT, address TEXT,
            city TEXT, province TEXT, postal TEXT,
            country TEXT DEFAULT 'Canada', email TEXT, phone TEXT,
            starred INTEGER DEFAULT 0, payment_method TEXT DEFAULT 'e-transfer',
            payment_last4 TEXT, follow_up_date TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_number TEXT UNIQUE NOT NULL, client_id INTEGER,
            issue_date TEXT, due_date TEXT, status TEXT DEFAULT 'unpaid',
            notes TEXT, items TEXT, subtotal REAL,
            discount_type TEXT DEFAULT 'flat', discount_value REAL DEFAULT 0,
            discount_amount REAL DEFAULT 0, shipping REAL DEFAULT 0,
            shipping_type TEXT DEFAULT 'none', tax REAL DEFAULT 0, total REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (client_id) REFERENCES clients(id)
        );
        CREATE TABLE IF NOT EXISTS crm_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER NOT NULL, note TEXT NOT NULL,
            note_type TEXT DEFAULT 'call',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (client_id) REFERENCES clients(id)
        );
        CREATE TABLE IF NOT EXISTS follow_ups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER NOT NULL, title TEXT NOT NULL,
            due_date TEXT NOT NULL, done INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (client_id) REFERENCES clients(id)
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
    ''')
    migrations = [
        'ALTER TABLE clients ADD COLUMN starred INTEGER DEFAULT 0',
        'ALTER TABLE clients ADD COLUMN payment_method TEXT DEFAULT "e-transfer"',
        'ALTER TABLE clients ADD COLUMN payment_last4 TEXT',
        'ALTER TABLE clients ADD COLUMN follow_up_date TEXT',
        'ALTER TABLE invoices ADD COLUMN discount_type TEXT DEFAULT "flat"',
        'ALTER TABLE invoices ADD COLUMN discount_value REAL DEFAULT 0',
        'ALTER TABLE invoices ADD COLUMN discount_amount REAL DEFAULT 0',
        'ALTER TABLE invoices ADD COLUMN shipping REAL DEFAULT 0',
        'ALTER TABLE invoices ADD COLUMN shipping_type TEXT DEFAULT "none"',
        'ALTER TABLE crm_notes ADD COLUMN note_date TEXT',
        'ALTER TABLE clients ADD COLUMN ship_address TEXT',
        'ALTER TABLE clients ADD COLUMN ship_city TEXT',
        'ALTER TABLE clients ADD COLUMN ship_province TEXT',
        'ALTER TABLE clients ADD COLUMN ship_postal TEXT',
        'ALTER TABLE clients ADD COLUMN pipeline_stage TEXT DEFAULT "cold_lead"',
        'ALTER TABLE clients ADD COLUMN sample_sent INTEGER DEFAULT 0',
        '''CREATE TABLE IF NOT EXISTS fulfilment (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER,
            client_id INTEGER,
            carrier TEXT DEFAULT "Canada Post",
            tracking_number TEXT,
            stage TEXT DEFAULT "ordered",
            ordered_at TEXT,
            packed_at TEXT,
            shipped_at TEXT,
            delivered_at TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''',
        '''CREATE TABLE IF NOT EXISTS carriers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            tracking_url TEXT NOT NULL
        )''',
    ]
    for m in migrations:
        try: conn.execute(m)
        except: pass
    # Seed default carriers if table is empty
    if not conn.execute('SELECT 1 FROM carriers LIMIT 1').fetchone():
        default_carriers = [
            ('Canada Post',  'https://www.canadapost-postescanada.ca/track-reperage/en#/search?searchFor={tracking}'),
            ('UPS',          'https://www.ups.com/track?tracknum={tracking}'),
            ('FedEx',        'https://www.fedex.com/fedextrack/?tracknumbers={tracking}'),
            ('Purolator',    'https://www.purolator.com/en/shipping/tracker?pins={tracking}'),
            ('DHL',          'https://www.dhl.com/en/express/tracking.html?AWB={tracking}'),
        ]
        conn.executemany('INSERT OR IGNORE INTO carriers (name, tracking_url) VALUES (?,?)', default_carriers)
    conn.commit()
    conn.close()

def next_invoice_number():
    conn = get_db()
    year = datetime.now().year
    row = conn.execute(
        "SELECT invoice_number FROM invoices WHERE invoice_number LIKE ? ORDER BY id DESC LIMIT 1",
        (f'INV-{year}-%',)
    ).fetchone()
    conn.close()
    if row:
        last = int(row['invoice_number'].split('-')[-1])
        return f"INV-{year}-{str(last+1).zfill(3)}"
    return f"INV-{year}-001"

_settings_cache = [None, 0.0]
def get_settings(force=False):
    import time as _t
    if not force and _settings_cache[0] is not None and (_t.time()-_settings_cache[1]) < 2.0:
        return _settings_cache[0]
    conn = get_db()
    rows = conn.execute('SELECT key, value FROM settings').fetchall()
    conn.close()
    defaults = {
        'biz_name': 'My Business',
        'biz_address': '',
        'biz_city': '',
        'biz_email': '',
        'biz_website': '',
        'biz_phone': '',
        'payment_instructions': 'E-Transfer',
        'invoice_prefix': 'INV',
        'currency': 'CA$',
        'tagline': '',
        'logo_path': '',
        'etransfer_email': '',
        'period_reset_date': '',
    }
    for row in rows:
        defaults[row['key']] = row['value']
    _settings_cache[0] = defaults
    _settings_cache[1] = _t.time()
    return defaults

def save_setting(key, value):
    conn = get_db()
    conn.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)', (key, value))
    conn.commit()
    conn.close()
    _settings_cache[0] = None

def is_first_run():
    conn = get_db()
    row = conn.execute("SELECT value FROM settings WHERE key='biz_name'").fetchone()
    conn.close()
    return row is None

def fmt(n): return f"CA${float(n or 0):.2f}"
def today(): return datetime.now().strftime('%Y-%m-%d')
def in_days(n): return (datetime.now() + timedelta(days=n)).strftime('%Y-%m-%d')
def fmt_date(s):
    if not s: return "—"
    try:
        d = datetime.strptime(s, '%Y-%m-%d')
        return d.strftime('%b %d, %Y')
    except: return s


# ── PIPELINE ──────────────────────────────────────────────────────────────────
PIPELINE_STAGES = [
    ("cold_lead",   "Cold Lead",   "#6b7280", "#f3f4f6"),
    ("contacted",   "Contacted",   "#1d4ed8", "#dbeafe"),
    ("discovery",   "Discovery",   "#6d28d9", "#ede9fe"),
    ("onboarded",   "Onboarded",   "#166534", "#dcfce7"),
]
STAGE_KEYS   = [s[0] for s in PIPELINE_STAGES]
STAGE_LABELS = {s[0]: s[1] for s in PIPELINE_STAGES}
STAGE_COLORS = {s[0]: (s[2], s[3]) for s in PIPELINE_STAGES}

def get_all_pipeline_stages():
    """One query fetches ALL client stages — use for any bulk rendering."""
    conn = get_db()
    clients = conn.execute("SELECT id, pipeline_stage FROM clients").fetchall()
    invoiced = set(
        r[0] for r in conn.execute(
            "SELECT DISTINCT client_id FROM invoices WHERE client_id IS NOT NULL"
        ).fetchall()
    )
    conn.close()
    result = {}
    upgrades = []
    for row in clients:
        cid = row["id"]
        stage = row["pipeline_stage"] or "cold_lead"
        if cid in invoiced and stage in ("cold_lead","contacted","discovery"):
            stage = "onboarded"
            upgrades.append(cid)
        result[cid] = stage
    if upgrades:
        conn2 = get_db()
        conn2.executemany("UPDATE clients SET pipeline_stage='onboarded' WHERE id=?",
                          [(i,) for i in upgrades])
        conn2.commit(); conn2.close()
    return result

def get_client_pipeline_stage(client_id):
    conn = get_db()
    c = conn.execute('SELECT pipeline_stage, sample_sent FROM clients WHERE id=?', (client_id,)).fetchone()
    has_inv = conn.execute('SELECT 1 FROM invoices WHERE client_id=? LIMIT 1', (client_id,)).fetchone()
    conn.close()
    stage = (c['pipeline_stage'] if c else None) or 'cold_lead'
    if has_inv and stage in ('cold_lead', 'contacted', 'discovery'):
        conn2 = get_db()
        conn2.execute('UPDATE clients SET pipeline_stage="onboarded" WHERE id=?', (client_id,))
        conn2.commit(); conn2.close()
        return 'onboarded'
    return stage

def set_client_pipeline_stage(client_id, stage):
    conn = get_db()
    conn.execute('UPDATE clients SET pipeline_stage=? WHERE id=?', (stage, client_id))
    conn.commit(); conn.close()

def is_local_client(client_city):
    if not client_city: return False
    s = get_settings()
    user_city = (s.get('biz_city', '') or '').split(',')[0].strip().lower()
    client_city_clean = client_city.strip().lower()
    if not user_city: return False
    if user_city == client_city_clean: return True
    DISTANCES = {
        frozenset(['vancouver', 'burnaby']): 15,
        frozenset(['vancouver', 'surrey']): 30,
        frozenset(['vancouver', 'richmond']): 20,
        frozenset(['vancouver', 'coquitlam']): 25,
        frozenset(['vancouver', 'langley']): 50,
        frozenset(['vancouver', 'abbotsford']): 80,
        frozenset(['vancouver', 'victoria']): 110,
        frozenset(['toronto', 'mississauga']): 30,
        frozenset(['toronto', 'brampton']): 40,
        frozenset(['toronto', 'hamilton']): 70,
        frozenset(['calgary', 'edmonton']): 300,
    }
    key = frozenset([user_city, client_city_clean])
    dist = DISTANCES.get(key)
    if dist is not None: return dist <= 150
    return False

# ── PDF GENERATOR ──────────────────────────────────────────────────────────
def generate_pdf(inv_id, save_path, ship_to_override=None):
    """
    ship_to_override: dict with keys address, city, province, postal (optional)
                      If None, defaults to same as SOLD TO address.
    """
    from reportlab.platypus import Image as RLImage
    conn = get_db()
    inv = conn.execute('''SELECT i.*, c.name as client_name, c.company as client_company,
        c.address as client_address, c.city as client_city, c.province as client_province,
        c.postal as client_postal, c.email as client_email, c.phone as client_phone
        FROM invoices i LEFT JOIN clients c ON i.client_id=c.id WHERE i.id=?''', (inv_id,)).fetchone()
    conn.close()
    if not inv: return False
    inv = dict(inv)
    items = json.loads(inv['items']) if inv['items'] else []

    doc = SimpleDocTemplate(save_path, pagesize=letter,
        rightMargin=0.65*inch, leftMargin=0.65*inch,
        topMargin=0.65*inch, bottomMargin=0.65*inch)
    brand_red   = colors.HexColor('#E63B2E')
    brand_dark  = colors.HexColor('#1a1a2e')
    brand_light = colors.HexColor('#f9fafb')
    styles = getSampleStyleSheet()
    R  = ParagraphStyle('R', alignment=TA_RIGHT)
    story = []

    s            = get_settings()
    biz_name     = s.get('biz_name', 'My Business')
    biz_addr     = s.get('biz_address', '')
    biz_city     = s.get('biz_city', '')
    biz_email    = s.get('biz_email', '')
    biz_website  = s.get('biz_website', '')
    biz_phone    = s.get('biz_phone', '')
    biz_tagline  = s.get('tagline', '')
    logo_path    = s.get('logo_path', '')
    pay_instructions = s.get('payment_instructions', 'E-Transfer')
    currency     = s.get('currency', 'CA$')
    # Use dedicated e-transfer email if set, otherwise fall back to business email
    etransfer_email = s.get('etransfer_email', '').strip() or biz_email

    # ── HEADER ROW: logo/name left | INVOICE right ────────────────────────
    if logo_path and os.path.isfile(logo_path):
        try:
            logo_img = RLImage(logo_path, width=1.4*inch, height=0.7*inch, kind='proportional')
            left_cell = logo_img
        except Exception:
            left_cell = Paragraph(f'<font size="22" color="#E63B2E"><b>{biz_name}</b></font>',
                                  ParagraphStyle("logo", parent=styles["Normal"], spaceBefore=6, spaceAfter=6))
    else:
        left_cell = Paragraph(f'<font size="22" color="#E63B2E"><b>{biz_name}</b></font>',
                              ParagraphStyle("logo", parent=styles["Normal"], spaceBefore=6, spaceAfter=6))

    right_cell = Paragraph('<font size="30" color="#1a1a2e"><b>INVOICE</b></font>', R)
    ht = Table([[left_cell, right_cell]], colWidths=[3.6*inch, 3.6*inch])
    ht.setStyle(TableStyle([
        ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ('BOTTOMPADDING',(0,0),(-1,-1),10),
        ('TOPPADDING',(0,0),(-1,-1),6),
    ]))
    story.append(ht)
    story.append(HRFlowable(width="52%", thickness=2, color=brand_red, spaceBefore=0, spaceAfter=8, hAlign="LEFT"))

    # ── SUB-HEADER: biz info left | invoice meta right ────────────────────
    # Single-line address (no country)
    addr_parts = [p for p in [biz_addr, biz_city] if p]
    contact_parts = [p for p in [biz_phone, biz_email, biz_website] if p]
    biz_lines  = f'<font size="9"><b>{biz_name}</b></font>'
    if addr_parts:
        biz_lines += f'<br/><font size="8" color="#6b7280">{" | ".join(addr_parts)}</font>'
    if contact_parts:
        biz_lines += f'<br/><font size="8" color="#6b7280">{" | ".join(contact_parts)}</font>'
    if biz_tagline:
        biz_lines += f'<br/><font size="8" color="#6b7280"><i>{biz_tagline}</i></font>'

    # Payment terms = days between issue and due
    terms_str = "Net 30"
    try:
        d1 = datetime.strptime(inv["issue_date"], "%Y-%m-%d")
        d2 = datetime.strptime(inv["due_date"],   "%Y-%m-%d")
        diff = (d2 - d1).days
        terms_str = f"{diff} Days" if diff != 30 else "Net 30"
    except Exception:
        pass

    meta_html = (
        f'<font size="8" color="#6b7280">INVOICE NO</font>'
        f'<font size="8" color="#6b7280">   |   ISSUE DATE</font><br/>'
        f'<font size="9"><b>{inv["invoice_number"]}</b></font>'
        f'<font size="9">   |   {inv["issue_date"]}</font><br/><br/>'
        f'<font size="8" color="#6b7280">DUE DATE</font>'
        f'<font size="8" color="#6b7280">   |   PAYMENT TERMS</font><br/>'
        f'<font size="9"><b>{inv["due_date"]}</b></font>'
        f'<font size="9">   |   {terms_str}</font>'
    )
    mt = Table([[Paragraph(biz_lines, styles['Normal']), Paragraph(meta_html, R)]],
               colWidths=[3.6*inch, 3.6*inch])
    mt.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP')]))
    story.append(mt)
    story.append(Spacer(1, 0.2*inch))

    # ── SOLD TO / SHIP TO boxes ───────────────────────────────────────────
    def _addr_block(header, company, name, address, city, province, postal, email, phone):
        html = f'<font size="9" color="#E63B2E"><b>{header}</b></font><br/>'
        if company: html += f'<font size="9"><b>{company}</b></font><br/>'
        if name:    html += f'<font size="9">{name}</font><br/>'
        addr_line = ' '.join(filter(None, [address]))
        city_line = ', '.join(filter(None, [city, province, postal]))
        for line in [addr_line, city_line]:
            if line: html += f'<font size="8" color="#6b7280">{line}</font><br/>'
        if email: html += f'<font size="8" color="#6b7280">{email}</font><br/>'
        if phone: html += f'<font size="8" color="#6b7280">{phone}</font><br/>'
        return Paragraph(html, styles['Normal'])

    sold_cell = _addr_block(
        "SOLD TO",
        inv.get('client_company', ''), inv.get('client_name', ''),
        inv.get('client_address', ''), inv.get('client_city', ''),
        inv.get('client_province', ''), inv.get('client_postal', ''),
        inv.get('client_email', ''), inv.get('client_phone', '')
    )

    if ship_to_override:
        ship_cell = _addr_block(
            "SHIP TO",
            ship_to_override.get('company', inv.get('client_company', '')),
            ship_to_override.get('name',    inv.get('client_name', '')),
            ship_to_override.get('address', ''),
            ship_to_override.get('city',    ''),
            ship_to_override.get('province',''),
            ship_to_override.get('postal',  ''),
            ship_to_override.get('email',   ''),
            ship_to_override.get('phone',   ''),
        )
    else:
        ship_cell = _addr_block(
            "SHIP TO",
            inv.get('client_company', ''), inv.get('client_name', ''),
            inv.get('client_address', ''), inv.get('client_city', ''),
            inv.get('client_province', ''), inv.get('client_postal', ''),
            inv.get('client_email', ''), inv.get('client_phone', '')
        )

    addr_tbl = Table([[sold_cell, ship_cell]], colWidths=[3.6*inch, 3.6*inch])
    addr_tbl.setStyle(TableStyle([
        ('VALIGN',(0,0),(-1,-1),'TOP'),
        ('BACKGROUND',(0,0),(-1,-1),brand_light),
        ('PADDING',(0,0),(-1,-1),10),
        ('LINEAFTER',(0,0),(0,-1),0.5,colors.HexColor('#e5e7eb')),
    ]))
    story.append(addr_tbl)
    story.append(Spacer(1, 0.2*inch))

    # ── LINE ITEMS TABLE ──────────────────────────────────────────────────
    ih = [Paragraph(f'<font size="9" color="#ffffff"><b>{t}</b></font>', ParagraphStyle('h', alignment=a))
          for t,a in [('DESCRIPTION',TA_LEFT),('QTY',TA_CENTER),('RATE',TA_RIGHT),('AMOUNT',TA_RIGHT)]]
    irows = [ih]
    for item in items:
        amt = float(item['qty']) * float(item['rate'])
        irows.append([
            Paragraph(f'<font size="9">{item["description"]}</font>', styles['Normal']),
            Paragraph(f'<font size="9">{item["qty"]}</font>', ParagraphStyle('c',alignment=TA_CENTER)),
            Paragraph(f'<font size="9">${float(item["rate"]):.2f}</font>', ParagraphStyle('r',alignment=TA_RIGHT)),
            Paragraph(f'<font size="9">${amt:.2f}</font>', ParagraphStyle('r',alignment=TA_RIGHT)),
        ])
    it = Table(irows, colWidths=[3.5*inch,0.8*inch,1.0*inch,1.2*inch])
    it.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),brand_dark),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,brand_light]),
        ('GRID',(0,0),(-1,-1),0.5,colors.HexColor('#e5e7eb')),
        ('PADDING',(0,0),(-1,-1),8),
    ]))
    story.append(it)
    story.append(Spacer(1, 0.15*inch))

    # ── TOTALS ────────────────────────────────────────────────────────────
    td = [['', 'Subtotal', f'{currency}{inv["subtotal"]:.2f}']]
    if inv.get('discount_amount') and float(inv['discount_amount']) > 0:
        td.append(['', 'Discount', f'-{currency}{float(inv["discount_amount"]):.2f}'])
    if inv.get('shipping_type') == 'free':
        td.append(['', 'Shipping', 'FREE'])
    elif inv.get('shipping') and float(inv['shipping']) > 0:
        td.append(['', 'Shipping', f'{currency}{float(inv["shipping"]):.2f}'])
    if inv.get('tax') and float(inv['tax']) > 0:
        td.append(['', 'Tax', f'{currency}{float(inv["tax"]):.2f}'])
    td.append(['',
        Paragraph('<font size="11" color="#ffffff"><b>TOTAL DUE</b></font>', styles['Normal']),
        Paragraph(f'<font size="11" color="#ffffff"><b>{currency}{inv["total"]:.2f}</b></font>', R)])
    tt = Table(td, colWidths=[3.5*inch,1.8*inch,1.2*inch])
    tt.setStyle(TableStyle([
        ('ALIGN',(1,0),(2,-1),'RIGHT'),('FONTSIZE',(0,0),(-1,-1),9),
        ('PADDING',(0,0),(-1,-1),6),
        ('LINEABOVE',(1,-1),(2,-1),1,brand_red),
        ('BACKGROUND',(1,-1),(2,-1),brand_dark),
    ]))
    story.append(tt)

    # ── PAYMENT INFO + NOTES ──────────────────────────────────────────────
    story.append(Spacer(1,0.15*inch))
    pay_html = (f'<font size="8" color="#6b7280">PAYMENT INFO: </font>'
                f'<font size="8">{pay_instructions}</font>'
                + (f'<font size="8" color="#6b7280">  |  {etransfer_email}</font>' if etransfer_email else ''))
    story.append(Paragraph(pay_html, styles['Normal']))

    if inv.get('notes'):
        story.append(Spacer(1,0.08*inch))
        story.append(Paragraph(f'<font size="8" color="#6b7280"><i>Notes: {inv["notes"]}</i></font>', styles['Normal']))

    # ── FOOTER ────────────────────────────────────────────────────────────
    story.append(Spacer(1,0.25*inch))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#e5e7eb')))
    story.append(Spacer(1,0.08*inch))
    footer_parts = ['Thank you for your business!', f'— {biz_name}']
    if biz_website: footer_parts.append(biz_website)
    if biz_tagline: footer_parts.append(biz_tagline)
    story.append(Paragraph(
        f'<font size="8" color="#6b7280">{" | ".join(footer_parts)}</font>',
        ParagraphStyle('footer', alignment=TA_CENTER)))
    doc.build(story)
    return True

# ── REUSABLE UI HELPERS ────────────────────────────────────────────────────
def label(parent, text, size=13, weight="normal", color=DARK, **kw):
    return ctk.CTkLabel(parent, text=text, font=ctk.CTkFont(size=size, weight=weight), text_color=color, **kw)

def entry(parent, placeholder="", width=200, **kw):
    return ctk.CTkEntry(parent, placeholder_text=placeholder, width=width,
                        fg_color=WHITE, border_color=BORDER, text_color=DARK, **kw)

def btn(parent, text, command, color=DARK, text_color=WHITE, width=120, **kw):
    return ctk.CTkButton(parent, text=text, command=command, fg_color=color,
                         hover_color=RED if color==RED else "#374151",
                         text_color=text_color, width=width, corner_radius=8, **kw)

def separator(parent, **kw):
    return ctk.CTkFrame(parent, height=1, fg_color=BORDER, **kw)

def scrollframe(parent, **kw):
    return ctk.CTkScrollableFrame(parent, fg_color=WHITE, **kw)

# ── SPLASH SCREEN ─────────────────────────────────────────────────────────────
class SplashScreen(tk.Toplevel):
    """
    Branded loading screen shown while the main App window builds.
    Uses a canvas for rock-solid rendering — no partial-load flicker.
    """
    WIDTH  = 440
    HEIGHT = 270

    def __init__(self, master):
        super().__init__(master)
        self.overrideredirect(True)
        self.configure(bg="#1a1a2e")
        self.attributes("-topmost", True)
        self.resizable(False, False)

        # Centre on screen
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x  = (sw - self.WIDTH)  // 2
        y  = (sh - self.HEIGHT) // 2
        self.geometry(f"{self.WIDTH}x{self.HEIGHT}+{x}+{y}")

        self._build()
        # Force full render before anything else happens
        self.update()
        self.lift()

    def _build(self):
        BG = "#1a1a2e"
        W, H = self.WIDTH, self.HEIGHT
        cx = W // 2
        c = tk.Canvas(self, width=W, height=H, bg=BG, highlightthickness=0)
        c.pack(fill="both", expand=True)
        self._canvas = c

        # ── Logo — draw Invo (white) and Biz (blue) side by side ──────────
        # Use anchor="e" and anchor="w" from the centre so they always
        # butt up perfectly regardless of font rendering
        FONT_LOGO = ("Segoe UI", 32, "bold")
        c.create_text(cx - 2, 80, text="Invo",
                      font=FONT_LOGO, fill="#ffffff", anchor="e")
        c.create_text(cx + 2, 80, text="Biz",
                      font=FONT_LOGO, fill="#3b82f6", anchor="w")

        # ── Tagline ───────────────────────────────────────────────────────
        c.create_text(cx, 118,
                      text="Chaos managed. Business organized.",
                      font=("Segoe UI", 10), fill="#6b7280", anchor="center")

        # ── Divider line ──────────────────────────────────────────────────
        c.create_line(cx-120, 138, cx+120, 138, fill="#2d2d4e", width=1)

        # ── Progress bar track ────────────────────────────────────────────
        bx1, by1, bx2, by2 = cx-140, 158, cx+140, 164
        c.create_rectangle(bx1, by1, bx2, by2, fill="#2d2d4e", outline="")
        self._bar_rect = c.create_rectangle(bx1, by1, bx1, by2,
                                             fill="#3b82f6", outline="")
        self._bar_x1 = bx1
        self._bar_x2 = bx2

        # ── Status label ──────────────────────────────────────────────────
        self._status_id = c.create_text(cx, 180, text="Starting up...",
                                         font=("Segoe UI", 9), fill="#6b7280",
                                         anchor="center")

        # ── Version ───────────────────────────────────────────────────────
        c.create_text(cx, H - 16, text="v1.0 Beta",
                      font=("Segoe UI", 8), fill="#374151", anchor="center")

        self._progress = 0

    def set_progress(self, pct: int, status: str = ""):
        """Update the progress bar and status text."""
        self._progress = pct
        bar_width = int((self._bar_x2 - self._bar_x1) * pct / 100)
        self._canvas.coords(self._bar_rect,
                            self._bar_x1, 162,
                            self._bar_x1 + bar_width, 168)
        if status:
            self._canvas.itemconfig(self._status_id, text=status)
        self.update()

# ── MAIN APPLICATION ───────────────────────────────────────────────────────
class App(ctk.CTk):
    def _set_icon(self, window):
        """Apply the InvoBiz icon to any toplevel window."""
        try:
            import sys, os
            base = sys._MEIPASS if getattr(sys,"frozen",False) else os.path.dirname(os.path.abspath(__file__))
            ico = os.path.join(base, "invobiz.ico")
            if os.path.exists(ico):
                window.after(100, lambda: window.iconbitmap(ico))
        except: pass

    def _debounce(self, fn, delay=220):
        _pending = [None]
        def wrapper(*args, **kwargs):
            if _pending[0] is not None:
                try: self.after_cancel(_pending[0])
                except: pass
            _pending[0] = self.after(delay, lambda: fn())
        return wrapper

    def __init__(self):
        super().__init__()
        self.withdraw()   # hide main window while splash is showing

        # ── Show splash immediately ───────────────────────────────────────
        splash = SplashScreen(self)
        splash.set_progress(5,  "Initialising...")

        # ── Setup main window ─────────────────────────────────────────────
        self.title("InvoBiz")
        # Set taskbar + title bar icon
        try:
            import sys, os
            _base = sys._MEIPASS if getattr(sys,"frozen",False) else os.path.dirname(os.path.abspath(__file__))
            _ico = os.path.join(_base, "invobiz.ico")
            if os.path.exists(_ico):
                self.iconbitmap(_ico)
        except: pass
        self.geometry("1200x750")
        self.minsize(900, 600)
        self.configure(fg_color=LIGHT)
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x  = (sw - 1200) // 2
        y  = (sh - 750)  // 2
        self.geometry(f"1200x750+{x}+{y}")

        splash.set_progress(20, "Setting up database...")
        init_db()

        splash.set_progress(50, "Building interface...")
        self._build_ui()

        splash.set_progress(85, "Loading your data...")
        get_all_pipeline_stages()  # warm pipeline cache
        if is_first_run():
            splash.set_progress(100, "Ready!")
            self.after(350, self.deiconify)          # show main window first
            self.after(380, splash.destroy)           # then remove splash — no gap
            self.after(400, lambda: self.show_page("settings"))
            self.after(450, lambda: messagebox.showinfo("Welcome to InvoBiz! 🎉",
                "Thanks for trying InvoBiz v1.0 Beta!\n\nTo get started, fill in your business\ndetails in Settings — your name, address,\nand email will appear on every invoice.\n\nHappy invoicing!"))
        else:
            splash.set_progress(100, "Ready!")
            self.after(350, self.deiconify)          # show main window first
            self.after(380, splash.destroy)           # then remove splash — no gap
            self.after(400, lambda: self.show_page("dashboard"))
            self.after(900, self._prerender_pipeline)  # pre-render pipeline in background

    def _build_ui(self):
        # Sidebar
        self.sidebar = ctk.CTkFrame(self, width=200, fg_color=DARK, corner_radius=0)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        # Logo — centered, white / blue / green
        logo_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        logo_frame.pack(pady=(20,4))
        ctk.CTkLabel(logo_frame, text="Invo", font=ctk.CTkFont(size=24, weight="bold"), text_color=WHITE).pack(side="left")
        ctk.CTkLabel(logo_frame, text="Biz",  font=ctk.CTkFont(size=24, weight="bold"), text_color="#3b82f6").pack(side="left")

        ctk.CTkLabel(self.sidebar, text="Chaos managed.\nBusiness organized.",
                     font=ctk.CTkFont(size=10), text_color="gray60",
                     justify="center").pack(pady=(0,20))
        separator(self.sidebar).pack(fill="x", padx=16, pady=(0,16))

        self.nav_btns = {}
        nav_items = [("🏠  Dashboard","dashboard"),("📄  Invoices","invoices"),("👥  Clients & CRM","clients"),("📦  Fulfilment","fulfilment"),("⚙️  Settings","settings")]
        for label_text, page in nav_items:
            b = ctk.CTkButton(self.sidebar, text=label_text, command=lambda p=page: self.show_page(p),
                              fg_color="transparent", hover_color="#2d2d44",
                              text_color="gray70", anchor="w", height=40,
                              font=ctk.CTkFont(size=13), corner_radius=8)
            b.pack(fill="x", padx=12, pady=2)
            self.nav_btns[page] = b

        # Version at bottom
        ctk.CTkLabel(self.sidebar, text="v1.0 Beta — InvoBiz", font=ctk.CTkFont(size=10),
                     text_color="gray50").pack(side="bottom", pady=(0,4))
        ctk.CTkLabel(self.sidebar, text="© 2026 Anna Elusini — 25ABCs. All rights reserved.",
                     font=ctk.CTkFont(size=9), text_color="gray40",
                     wraplength=180, justify="center").pack(side="bottom", pady=(0,4))

        # Main content area
        self.content = ctk.CTkFrame(self, fg_color=LIGHT, corner_radius=0)
        self.content.pack(side="left", fill="both", expand=True)

        self.pages = {}
        for page in ["dashboard","invoices","clients","fulfilment","settings"]:
            frame = ctk.CTkFrame(self.content, fg_color=LIGHT, corner_radius=0)
            self.pages[page] = frame

        self._build_dashboard()
        self._build_invoices()
        self._build_clients()
        self._build_fulfilment()
        self._build_settings()

    def show_page(self, page):
        for p, f in self.pages.items():
            f.pack_forget()
            self.nav_btns[p].configure(fg_color="transparent", text_color="gray70")
        self.pages[page].pack(fill="both", expand=True)
        self.nav_btns[page].configure(fg_color="#2d2d44", text_color=WHITE)
        if page == "dashboard": self.refresh_dashboard()
        elif page == "invoices": self.refresh_invoices()
        elif page == "clients": self.refresh_clients()
        elif page == "fulfilment": self.refresh_fulfilment()
        elif page == "settings": self.refresh_settings()

    # ── DASHBOARD ────────────────────────────────────────────────────────
    def _build_dashboard(self):
        p = self.pages["dashboard"]
        header = ctk.CTkFrame(p, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(20,0))
        label(header, "Dashboard", size=22, weight="bold").pack(side="left")
        btn(header, "+ New Invoice", lambda: self.open_invoice_dialog(), color=RED, width=130).pack(side="right")
        btn(header, "🔄 Reset Period", self._reset_period, color="#374151", width=130).pack(side="right", padx=(0,8))

        # Stats row
        self.dash_stats = ctk.CTkFrame(p, fg_color="transparent")
        self.dash_stats.pack(fill="x", padx=24, pady=16)

        # Two column layout
        cols = ctk.CTkFrame(p, fg_color="transparent")
        cols.pack(fill="both", expand=True, padx=24, pady=(0,16))
        cols.columnconfigure(0, weight=3)
        cols.columnconfigure(1, weight=2)

        # Recent invoices
        left = ctk.CTkFrame(cols, fg_color=WHITE, corner_radius=12, border_width=1, border_color=BORDER)
        left.grid(row=0, column=0, sticky="nsew", padx=(0,8))
        lh = ctk.CTkFrame(left, fg_color="transparent")
        lh.pack(fill="x", padx=16, pady=(12,6))
        label(lh, "Recent Invoices", size=14, weight="bold").pack(side="left")
        self.dash_inv_search = entry(lh, "Search invoice #...", width=160)
        self.dash_inv_search.pack(side="right")
        self.dash_inv_search.bind("<KeyRelease>", self._debounce(lambda *_: self._refresh_dash_invoices()))
        self.dash_inv_frame = scrollframe(left)
        self.dash_inv_frame.pack(fill="both", expand=True, padx=8, pady=(0,8))

        # Follow-ups
        right = ctk.CTkFrame(cols, fg_color=WHITE, corner_radius=12, border_width=1, border_color=BORDER)
        right.grid(row=0, column=1, sticky="nsew", padx=(8,0))
        rh = ctk.CTkFrame(right, fg_color="transparent")
        rh.pack(fill="x", padx=16, pady=12)
        label(rh, "Upcoming Follow-ups", size=14, weight="bold").pack(side="left")
        self.dash_fup_frame = scrollframe(right)
        self.dash_fup_frame.pack(fill="both", expand=True, padx=8, pady=(0,8))

        # Yearly income chart
        chart_card = ctk.CTkFrame(p, fg_color=WHITE, corner_radius=12,
                                   border_width=1, border_color=BORDER)
        chart_card.pack(fill="x", padx=24, pady=(0,16))
        ch = ctk.CTkFrame(chart_card, fg_color="transparent")
        ch.pack(fill="x", padx=16, pady=(12,4))
        label(ch, "Yearly Revenue", size=14, weight="bold").pack(side="left")
        self.dash_chart_frame = ctk.CTkFrame(chart_card, fg_color="transparent", height=180)
        self.dash_chart_frame.pack(fill="x", padx=16, pady=(0,12))
        self.dash_chart_frame.pack_propagate(False)

    def _reset_period(self):
        reset_date = get_settings().get('period_reset_date', '')
        if reset_date:
            # Already in a period — offer revert or new reset
            choice = messagebox.askyesnocancel(
                "Period Options",
                f"You're currently viewing from {fmt_date(reset_date)}.\n\n"
                "• Click YES to revert to full history (show all time)\n"
                "• Click NO to start a new period from today\n"
                "• Click Cancel to do nothing"
            )
            if choice is None:
                return
            elif choice:
                # YES — revert to full history
                save_setting('period_reset_date', '')
                self.refresh_dashboard()
                messagebox.showinfo("Reverted", "Dashboard now shows full all-time history. ✓")
                return
        # NO or no existing period — start fresh from today
        if not messagebox.askyesno("Reset Period",
            "This will archive the current stats display so your new period starts fresh.\n\n"
            "Your invoice and client data is NOT deleted — it stays in the database.\n\n"
            "Start a new period from today?"):
            return
        from datetime import datetime as _dt
        save_setting('period_reset_date', _dt.now().strftime('%Y-%m-%d'))
        self.refresh_dashboard()
        messagebox.showinfo("Period Reset", "Dashboard stats now reflect your new period. ✓")

    def _refresh_dash_invoices(self):
        """Refresh only the recent invoices list — fast, called on search keypress."""
        dash_q = self.dash_inv_search.get().lower().strip() if hasattr(self, 'dash_inv_search') else ""
        conn = get_db()
        recent_invs = conn.execute('''SELECT i.*, c.name as cn, c.company as cc
            FROM invoices i LEFT JOIN clients c ON i.client_id=c.id
            ORDER BY i.id DESC LIMIT 50''').fetchall()
        conn.close()
        if dash_q:
            recent_invs = [i for i in recent_invs if dash_q in (i['invoice_number'] or '').lower()]
        else:
            recent_invs = list(recent_invs)[:8]
        for w in self.dash_inv_frame.winfo_children(): w.destroy()
        if recent_invs:
            hdr = ctk.CTkFrame(self.dash_inv_frame, fg_color="transparent")
            hdr.pack(fill="x", pady=(0,2))
            label(hdr, "Invoice", size=10, color=GRAY, weight="bold").pack(side="left")
            label(hdr, "Download", size=10, color=GRAY, weight="bold").pack(side="right", padx=(0,4))
            label(hdr, "Status", size=10, color=GRAY, weight="bold").pack(side="right", padx=8)
            label(hdr, "Total", size=10, color=GRAY, weight="bold").pack(side="right", padx=8)
            separator(self.dash_inv_frame).pack(fill="x", pady=(0,4))
            for inv in recent_invs:
                row = ctk.CTkFrame(self.dash_inv_frame, fg_color="transparent")
                row.pack(fill="x", pady=3)
                client_name = inv['cc'] or inv['cn'] or "—"
                inv_id = inv['id']; inv_num = inv['invoice_number']
                dl_col = ctk.CTkFrame(row, fg_color="transparent")
                dl_col.pack(side="right", padx=(6,0))
                ctk.CTkButton(
                    dl_col, text="Download PDF",
                    command=lambda i=inv_id, n=inv_num: self.save_pdf(i, n),
                    fg_color="#e5e7eb", hover_color="#d1d5db",
                    text_color=DARK, width=105, height=28,
                    corner_radius=4,
                    font=ctk.CTkFont(size=11)
                ).pack()
                status_col = GREEN if inv['status']=='paid' else RED
                label(row, inv['status'].upper(), size=10, color=status_col).pack(side="right", padx=8)
                label(row, fmt(inv['total']), size=12, weight="bold").pack(side="right", padx=8)
                label(row, inv['invoice_number'], size=12, weight="bold").pack(side="left")
                label(row, client_name, size=11, color=GRAY).pack(side="left", padx=8)
        else:
            label(self.dash_inv_frame,
                  "No invoices found" if dash_q else "No invoices yet",
                  color=GRAY).pack(pady=20)

    def refresh_dashboard(self):
        conn = get_db()
        reset_date = get_settings().get('period_reset_date', '')
        _date_filter = f'AND created_at >= "{reset_date}"' if reset_date else ''
        total_inv = conn.execute(f'SELECT COUNT(*) FROM invoices WHERE 1=1 {_date_filter}').fetchone()[0]
        unpaid = conn.execute(f'SELECT COUNT(*), SUM(total) FROM invoices WHERE status="unpaid" {_date_filter}').fetchone()
        paid   = conn.execute(f'SELECT COUNT(*), SUM(total) FROM invoices WHERE status="paid" {_date_filter}').fetchone()
        clients_count = conn.execute('SELECT COUNT(*) FROM clients').fetchone()[0]
        fup_count = conn.execute('SELECT COUNT(*) FROM follow_ups WHERE done=0').fetchone()[0]
        fups = conn.execute('''SELECT f.*, c.name as cn, c.company as cc
            FROM follow_ups f JOIN clients c ON f.client_id=c.id
            WHERE f.done=0 ORDER BY f.due_date LIMIT 10''').fetchall()
        conn.close()

        # Stat cards
        for w in self.dash_stats.winfo_children(): w.destroy()
        if reset_date:
            badge = ctk.CTkFrame(self.dash_stats, fg_color="#eff6ff", corner_radius=6)
            badge.pack(fill="x", pady=(0,6))
            label(badge, f"📅  Period from {fmt_date(reset_date)}  •  Click 'Reset Period' to start a new one",
                  size=10, color=BLUE).pack(padx=10, pady=4)
        stats = [("Total Invoices", str(total_inv), DARK),
                 ("Unpaid", fmt(unpaid[1]), RED),
                 ("Collected", fmt(paid[1]), GREEN),
                 ("Clients", str(clients_count), BLUE),
                 ("Follow-ups Due", str(fup_count), AMBER)]
        for lbl, val, col in stats:
            card = ctk.CTkFrame(self.dash_stats, fg_color=WHITE, corner_radius=10, border_width=1, border_color=BORDER)
            card.pack(side="left", expand=True, fill="x", padx=4)
            label(card, lbl, size=11, color=GRAY).pack(pady=(10,2), padx=12)
            label(card, val, size=20, weight="bold", color=col).pack(pady=(0,10), padx=12)

        self._refresh_dash_invoices()

        # ── Yearly revenue bar chart ──────────────────────────────────────
        for w in self.dash_chart_frame.winfo_children(): w.destroy()
        year_data_raw = conn.execute(
            "SELECT strftime('%Y', issue_date) as yr, SUM(total) "
            "FROM invoices WHERE issue_date IS NOT NULL GROUP BY yr ORDER BY yr"
        ).fetchall() if False else []
        conn2 = get_db()
        year_data_raw = conn2.execute(
            "SELECT strftime('%Y', issue_date) as yr, SUM(total) "
            "FROM invoices WHERE issue_date IS NOT NULL GROUP BY yr ORDER BY yr"
        ).fetchall()
        conn2.close()
        if year_data_raw:
            year_data = [(r[0], float(r[1] or 0)) for r in year_data_raw if r[0]]
            max_val = max(v for _, v in year_data) if year_data else 1
            cur = get_settings().get('currency','CA$')
            chart_h = 130          # drawable bar area
            label_gap = 22         # space above bars for dollar labels
            year_label_h = 20      # space below bars for year labels
            total_h = chart_h + label_gap + year_label_h
            bar_w = max(36, min(70, (800 // max(len(year_data), 1)) - 10))
            canvas_frame = tk.Frame(self.dash_chart_frame, bg=WHITE)
            canvas_frame.pack(fill="both", expand=True)
            import tkinter as _tk
            c = _tk.Canvas(canvas_frame, bg=WHITE, highlightthickness=0,
                           height=total_h)
            c.pack(fill="x", expand=True, padx=8)
            c.update_idletasks()
            cw = c.winfo_width() or 700
            n = len(year_data)
            spacing = cw / (n + 1)
            bar_top = label_gap           # top of the bar zone
            bar_bottom = label_gap + chart_h  # bottom of the bar zone
            for i, (yr, val) in enumerate(year_data):
                x_centre = int(spacing * (i + 1))
                bar_h = int((val / max_val) * chart_h) if max_val > 0 else 2
                x0 = x_centre - bar_w // 2
                x1 = x_centre + bar_w // 2
                y0 = bar_bottom - bar_h
                y1 = bar_bottom
                # Bar with rounded top feel (draw slightly rounded via two rects)
                c.create_rectangle(x0, y0, x1, y1, fill="#3b82f6", outline="", width=0)
                # Highlight strip on left edge
                c.create_rectangle(x0, y0, x0+3, y1, fill="#60a5fa", outline="", width=0)
                # Dollar label — always above the bar, never clipped
                val_text = f"{cur}{int(val):,}"
                c.create_text(x_centre, y0 - 4,
                              text=val_text,
                              font=("Segoe UI", 8, "bold"),
                              fill="#1a1a2e", anchor="s")
                # Year label below bar
                c.create_text(x_centre, y1 + 4,
                              text=yr,
                              font=("Segoe UI", 9, "bold"),
                              fill="#6b7280", anchor="n")
            # Baseline
            c.create_line(8, bar_bottom, cw - 8, bar_bottom,
                          fill="#e5e7eb", width=1)
        else:
            label(self.dash_chart_frame, "No invoice data yet — revenue chart will appear here.",
                  size=11, color=GRAY).pack(pady=20)

        # Follow-ups — double-click any row to jump to that client's CRM
        for w in self.dash_fup_frame.winfo_children(): w.destroy()
        if fups:
            label(self.dash_fup_frame,
                  "💡 Double-click a row to open the client",
                  size=10, color=GRAY).pack(anchor="w", pady=(0,4))
            for f in fups:
                cid = f['client_id']
                row = ctk.CTkFrame(self.dash_fup_frame,
                                   fg_color=WHITE, corner_radius=6,
                                   border_width=1, border_color=BORDER,
                                   cursor="hand2")
                row.pack(fill="x", pady=2)
                client_name = f['cc'] or f['cn'] or "—"
                is_overdue = f['due_date'] < today()
                date_col = RED if is_overdue else GRAY
                label(row, f['title'], size=12, weight="bold").pack(side="left", padx=(10,4), pady=6)
                label(row, client_name, size=11, color=GRAY).pack(side="left", padx=4)
                label(row, fmt_date(f['due_date']), size=11, color=date_col).pack(side="right", padx=10)
                # Bind double-click on row and all its children
                def _go(event, client_id=cid):
                    self.show_page("clients")
                    self.after(50, lambda: self.open_crm_detail(client_id))
                row.bind("<Double-Button-1>", _go)
                for child in row.winfo_children():
                    child.bind("<Double-Button-1>", _go)
        else:
            label(self.dash_fup_frame, "No upcoming follow-ups", color=GRAY).pack(pady=20)

    # ── INVOICES ─────────────────────────────────────────────────────────
    def _build_invoices(self):
        p = self.pages["invoices"]
        header = ctk.CTkFrame(p, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(20,12))
        label(header, "Invoices", size=22, weight="bold").pack(side="left")
        btn(header, "+ New Invoice", lambda: self.open_invoice_dialog(), color=RED, width=130).pack(side="right")

        # Search + filter bar
        bar = ctk.CTkFrame(p, fg_color="transparent")
        bar.pack(fill="x", padx=24, pady=(0,12))
        self.inv_search = entry(bar, "Search invoices...", width=260)
        self.inv_search.pack(side="left")
        self.inv_search.bind("<KeyRelease>", self._debounce(lambda *_: self.refresh_invoices()))
        self.inv_status_filter = ctk.CTkComboBox(bar, values=["All","unpaid","paid","overdue"], width=110,
                                                  fg_color=WHITE, border_color=BORDER, text_color=DARK,
                                                  command=lambda _: self.refresh_invoices())
        self.inv_status_filter.set("All")
        self.inv_status_filter.pack(side="left", padx=8)
        # Year picker — decade selector + 10 individual year buttons
        import datetime as _dt
        _cur_year  = _dt.datetime.now().year
        _year_min  = _cur_year - 100
        _year_max  = _cur_year + 200
        # decade_start is always a multiple of 10 (e.g. 2020, 2010, 1990)
        _dec_start = (_cur_year // 10) * 10

        self._inv_year_selected  = [None]        # None = All Years
        self._inv_decade_start   = [_dec_start]  # e.g. 2020

        # Outer wrapper — decade pill + year buttons side by side
        yr_outer = ctk.CTkFrame(bar, fg_color="transparent")
        yr_outer.pack(side="left", padx=(0,4))

        # ── Decade pill (dark) ────────────────────────────────────────────
        dec_pill = ctk.CTkFrame(yr_outer, fg_color=DARK, corner_radius=8)
        dec_pill.pack(side="left", padx=(0,6))

        ctk.CTkButton(dec_pill, text="‹", width=26, height=30,
                      fg_color="transparent", hover_color="#2d2d44",
                      text_color="#9ca3af", font=ctk.CTkFont(size=13),
                      command=lambda: _decade_shift(-1)).pack(side="left")

        self._dec_label = ctk.CTkLabel(dec_pill, text=f"{_dec_start}s",
                                       font=ctk.CTkFont(size=11, weight="bold"),
                                       text_color=WHITE, width=52)
        self._dec_label.pack(side="left")

        ctk.CTkButton(dec_pill, text="›", width=26, height=30,
                      fg_color="transparent", hover_color="#2d2d44",
                      text_color="#9ca3af", font=ctk.CTkFont(size=13),
                      command=lambda: _decade_shift(1)).pack(side="left")

        # ── 10 year buttons ───────────────────────────────────────────────
        self._yr_pills_frame = ctk.CTkFrame(yr_outer, fg_color="transparent")
        self._yr_pills_frame.pack(side="left")

        def _render_years():
            for w in self._yr_pills_frame.winfo_children():
                w.destroy()
            start = self._inv_decade_start[0]
            sel   = self._inv_year_selected[0]
            for i in range(10):
                yr = start + i
                is_sel = (yr == sel)
                ctk.CTkButton(
                    self._yr_pills_frame,
                    text=str(yr),
                    width=46, height=30,
                    fg_color=RED if is_sel else WHITE,
                    hover_color="#c4312a" if is_sel else LIGHT,
                    text_color=WHITE if is_sel else DARK,
                    border_width=0 if is_sel else 1,
                    border_color=BORDER,
                    font=ctk.CTkFont(size=11, weight="bold" if is_sel else "normal"),
                    corner_radius=6,
                    command=lambda y=yr: _yr_select(y)
                ).pack(side="left", padx=1)

        def _decade_shift(direction):
            new_dec = self._inv_decade_start[0] + (direction * 10)
            new_dec = max(_year_min, min(_year_max - 9, new_dec))
            # snap to decade boundary
            new_dec = (new_dec // 10) * 10
            self._inv_decade_start[0] = new_dec
            self._dec_label.configure(text=f"{new_dec}s")
            # clear year selection if it's no longer in view
            sel = self._inv_year_selected[0]
            if sel is not None and not (new_dec <= sel <= new_dec + 9):
                self._inv_year_selected[0] = None
                self.refresh_invoices()
            _render_years()

        def _yr_select(yr):
            if self._inv_year_selected[0] == yr:
                self._inv_year_selected[0] = None   # deselect → All Years
            else:
                self._inv_year_selected[0] = yr
            _render_years()
            self.refresh_invoices()

        _render_years()

        # Table header — sortable columns
        self._inv_sort_col = [None]   # [column_key]
        self._inv_sort_asc = [True]

        th = ctk.CTkFrame(p, fg_color=DARK, corner_radius=8)
        th.pack(fill="x", padx=24, pady=(0,2))
        sort_cols = [
            ("Invoice #","invoice_number",120),
            ("Client","client",200),
            ("Issue Date","issue_date",100),
            ("Due Date","due_date",100),
            ("Total","total",100),
            ("Status","status",80),
            ("",None,180),
        ]
        for col_lbl, col_key, w in sort_cols:
            if col_key:
                def make_sort(k):
                    def _sort(_e=None):
                        if self._inv_sort_col[0] == k:
                            self._inv_sort_asc[0] = not self._inv_sort_asc[0]
                        else:
                            self._inv_sort_col[0] = k
                            self._inv_sort_asc[0] = True
                        self.refresh_invoices()
                    return _sort
                lbl_w = ctk.CTkLabel(th, text=col_lbl, font=ctk.CTkFont(size=11, weight="bold"),
                                     text_color=WHITE, width=w, anchor="w", cursor="hand2")
                lbl_w.pack(side="left", padx=8, pady=8)
                lbl_w.bind("<Button-1>", make_sort(col_key))
            else:
                label(th, col_lbl, size=11, color=WHITE, weight="bold", width=w, anchor="w").pack(side="left", padx=8, pady=8)

        # Invoice list
        self.inv_list = scrollframe(p)
        self.inv_list.pack(fill="both", expand=True, padx=24, pady=(0,16))

    def refresh_invoices(self):
        q = self.inv_search.get().lower() if hasattr(self,'inv_search') else ""
        s = self.inv_status_filter.get() if hasattr(self,'inv_status_filter') else "All"
        conn = get_db()
        invoices = conn.execute('''SELECT i.*, c.name as cn, c.company as cc
            FROM invoices i LEFT JOIN clients c ON i.client_id=c.id
            ORDER BY i.id DESC''').fetchall()
        conn.close()
        invoices = [dict(i) for i in invoices]
        # Apply sort
        sc = getattr(self, '_inv_sort_col', [None])[0]
        asc = getattr(self, '_inv_sort_asc', [True])[0]
        if sc:
            def _key(i):
                if sc == 'client': return (i.get('cc') or i.get('cn') or "").lower()
                if sc == 'total':  return float(i.get('total') or 0)
                return str(i.get(sc) or "").lower()
            invoices.sort(key=_key, reverse=not asc)
        yr = self._inv_year_selected[0] if hasattr(self,'_inv_year_selected') else None
        for w in self.inv_list.winfo_children(): w.destroy()
        shown = 0
        for inv in invoices:
            client_name = inv['cc'] or inv['cn'] or "—"
            if q and q not in inv['invoice_number'].lower() and q not in client_name.lower(): continue
            if s != "All" and inv['status'] != s: continue
            if yr is not None:
                inv_year = str(inv.get('issue_date',''))[:4]
                if inv_year != str(yr): continue
            shown += 1
            row = ctk.CTkFrame(self.inv_list, fg_color=WHITE if shown%2==0 else "#fafafa",
                               corner_radius=6, border_width=1, border_color=BORDER)
            row.pack(fill="x", pady=2)
            # Action buttons packed FIRST so they always have space on right
            inv_id = inv['id']; inv_num = inv['invoice_number']
            acts = ctk.CTkFrame(row, fg_color="transparent")
            acts.pack(side="right", padx=6, pady=4)
            btn(acts, "✕", lambda i=inv_id: self.delete_invoice(i), color=RED, width=30).pack(side="right", padx=2)
            if inv['status'] != 'paid':
                btn(acts, "✓ Paid", lambda i=inv_id: self.mark_paid(i), color=GREEN, width=60).pack(side="right", padx=2)
            btn(acts, "Edit", lambda i=inv_id: self.open_invoice_dialog(i), color="#374151", width=42).pack(side="right", padx=2)
            btn(acts, "PDF", lambda i=inv_id, n=inv_num: self.save_pdf(i,n), color="#374151", width=42).pack(side="right", padx=2)
            label(row, inv['invoice_number'], size=12, weight="bold", width=120, anchor="w").pack(side="left", padx=8, pady=8)
            label(row, client_name, size=12, color=DARK, width=180, anchor="w").pack(side="left", padx=4)
            label(row, inv['issue_date'] or "—", size=11, color=GRAY, width=100, anchor="w").pack(side="left", padx=4)
            label(row, inv['due_date'] or "—", size=11, color=GRAY, width=100, anchor="w").pack(side="left", padx=4)
            label(row, fmt(inv['total']), size=12, weight="bold", width=90, anchor="w").pack(side="left", padx=4)
            status_col = GREEN if inv['status']=='paid' else RED
            label(row, inv['status'].upper(), size=10, color=status_col, width=70, anchor="w").pack(side="left", padx=4)
        if shown == 0:
            label(self.inv_list, "No invoices found", color=GRAY).pack(pady=40)

    def mark_paid(self, inv_id):
        conn = get_db()
        conn.execute('UPDATE invoices SET status="paid" WHERE id=?', (inv_id,))
        conn.commit(); conn.close()
        self.refresh_invoices(); self.refresh_dashboard()

    def delete_invoice(self, inv_id):
        if messagebox.askyesno("Delete Invoice", "Delete this invoice permanently?"):
            conn = get_db()
            conn.execute('DELETE FROM invoices WHERE id=?', (inv_id,))
            conn.commit(); conn.close()
            self.refresh_invoices(); self.refresh_dashboard()

    def save_pdf(self, inv_id, inv_num, client_id=None):
        path = filedialog.asksaveasfilename(defaultextension=".pdf",
            filetypes=[("PDF files","*.pdf")], initialfile=f"{inv_num}.pdf")
        if path:
            ship_to = None
            if client_id:
                conn = get_db()
                c = conn.execute('SELECT ship_address,ship_city,ship_province,ship_postal FROM clients WHERE id=?',(client_id,)).fetchone()
                conn.close()
                if c and any(c):
                    ship_to = {"address": c[0] or "", "city": c[1] or "",
                               "province": c[2] or "", "postal": c[3] or ""}
            generate_pdf(inv_id, path, ship_to_override=ship_to)
            messagebox.showinfo("PDF Saved", f"Saved to:\n{path}")

    def preview_pdf(self, inv_id, inv_num, client_id=None):
        """Generate PDF to a temp file and open it with the system viewer (no save dialog)."""
        import tempfile, subprocess, platform
        ship_to = None
        if client_id:
            conn = get_db()
            c = conn.execute(
                'SELECT ship_address,ship_city,ship_province,ship_postal FROM clients WHERE id=?',
                (client_id,)
            ).fetchone()
            conn.close()
            if c and any(c):
                ship_to = {"address": c[0] or "", "city": c[1] or "",
                           "province": c[2] or "", "postal": c[3] or ""}
        tmp = tempfile.NamedTemporaryFile(
            delete=False, suffix=".pdf",
            prefix=f"{inv_num}_preview_"
        )
        tmp.close()
        ok = generate_pdf(inv_id, tmp.name, ship_to_override=ship_to)
        if not ok:
            messagebox.showerror("Error", "Could not generate preview."); return
        try:
            system = platform.system()
            if system == "Windows":
                os.startfile(tmp.name)
            elif system == "Darwin":
                subprocess.Popen(["open", tmp.name])
            else:
                subprocess.Popen(["xdg-open", tmp.name])
        except Exception as e:
            messagebox.showerror("Preview Error",
                f"Could not open PDF viewer.\n{e}\n\nFile saved at:\n{tmp.name}")

    # ── INVOICE DIALOG ────────────────────────────────────────────────────
    def open_invoice_dialog(self, inv_id=None):
        dlg = ctk.CTkToplevel(self)
        dlg.title("Edit Invoice" if inv_id else "New Invoice")
        self._set_icon(dlg)
        dlg.geometry("750x700")
        dlg.grab_set()
        dlg.configure(fg_color=WHITE)

        conn = get_db()
        clients = conn.execute('SELECT * FROM clients ORDER BY name').fetchall()
        inv = dict(conn.execute('SELECT * FROM invoices WHERE id=?', (inv_id,)).fetchone()) if inv_id else {}
        conn.close()

        sf = scrollframe(dlg)
        sf.pack(fill="both", expand=True, padx=20, pady=16)

        # Row 1 - Invoice number + client
        r1 = ctk.CTkFrame(sf, fg_color="transparent"); r1.pack(fill="x", pady=4)
        label(r1, "Invoice Number").pack(anchor="w")
        inv_num_var = ctk.StringVar(value=inv.get('invoice_number', next_invoice_number()))
        ctk.CTkEntry(sf, textvariable=inv_num_var, fg_color=WHITE, border_color=BORDER, text_color=DARK).pack(fill="x", pady=(2,8))

        label(sf, "Client").pack(anchor="w")
        client_names = ["— No Client —"] + [c['company'] or c['name'] for c in clients]
        client_ids = [None] + [c['id'] for c in clients]
        client_combo = ctk.CTkComboBox(sf, values=client_names, fg_color=WHITE, border_color=BORDER, text_color=DARK, width=400)
        client_combo.pack(fill="x", pady=(2,8))
        if inv.get('client_id'):
            for i, cid in enumerate(client_ids):
                if cid == inv['client_id']:
                    client_combo.set(client_names[i]); break
        else: client_combo.set(client_names[0])

        # Dates + status
        r2 = ctk.CTkFrame(sf, fg_color="transparent"); r2.pack(fill="x", pady=4)
        for lbl_text, key, default in [("Issue Date","issue_date",today()),("Due Date","due_date",in_days(7))]:
            col = ctk.CTkFrame(r2, fg_color="transparent"); col.pack(side="left", expand=True, fill="x", padx=(0,8))
            label(col, lbl_text).pack(anchor="w")
        issue_var = ctk.StringVar(value=inv.get('issue_date', today()))
        due_var = ctk.StringVar(value=inv.get('due_date', in_days(7)))
        ctk.CTkEntry(r2, textvariable=issue_var, placeholder_text="YYYY-MM-DD", fg_color=WHITE, border_color=BORDER, text_color=DARK, width=160).pack(side="left", padx=(0,8))
        ctk.CTkEntry(r2, textvariable=due_var, placeholder_text="YYYY-MM-DD", fg_color=WHITE, border_color=BORDER, text_color=DARK, width=160).pack(side="left", padx=(0,8))
        status_combo = ctk.CTkComboBox(r2, values=["unpaid","paid","overdue"], fg_color=WHITE, border_color=BORDER, text_color=DARK, width=120)
        status_combo.set(inv.get('status','unpaid'))
        status_combo.pack(side="left")

        separator(sf).pack(fill="x", pady=12)
        label(sf, "Line Items", size=13, weight="bold").pack(anchor="w", pady=(0,6))

        # Items
        items_frame = ctk.CTkFrame(sf, fg_color=LIGHT, corner_radius=8)
        items_frame.pack(fill="x", pady=(0,8))

        item_rows = []
        _recalc_ref = [None]   # filled once recalc_totals is defined below

        def add_item_row(desc="", qty="1", rate=""):
            row = ctk.CTkFrame(items_frame, fg_color="transparent")
            row.pack(fill="x", padx=8, pady=3)
            d = ctk.CTkEntry(row, placeholder_text="Description", fg_color=WHITE, border_color=BORDER, text_color=DARK, width=300)
            d.pack(side="left", padx=(0,4)); d.insert(0, desc)
            q = ctk.CTkEntry(row, placeholder_text="Qty", fg_color=WHITE, border_color=BORDER, text_color=DARK, width=60)
            q.pack(side="left", padx=(0,4)); q.insert(0, qty)
            r = ctk.CTkEntry(row, placeholder_text="Rate", fg_color=WHITE, border_color=BORDER, text_color=DARK, width=80)
            r.pack(side="left", padx=(0,4)); r.insert(0, rate)
            amt_lbl = label(row, "$0.00", size=12, color=DARK, width=80)
            amt_lbl.pack(side="left", padx=4)
            def update_amt(*_):
                try: amt_lbl.configure(text=f"${float(q.get() or 0)*float(r.get() or 0):.2f}")
                except: pass
                if _recalc_ref[0]: _recalc_ref[0]()
            q.bind("<KeyRelease>", update_amt); r.bind("<KeyRelease>", update_amt)
            update_amt()
            def remove():
                item_rows.remove(ir); row.destroy()
                if _recalc_ref[0]: _recalc_ref[0]()
            ir = (d,q,r,amt_lbl)
            rem_btn = btn(row, "✕", remove, color=RED, width=30)
            rem_btn.pack(side="left")
            item_rows.append(ir)
            if _recalc_ref[0]: _recalc_ref[0]()

        existing_items = json.loads(inv.get('items','[]')) if inv.get('items') else []
        if existing_items:
            for it in existing_items: add_item_row(it['description'], str(it['qty']), str(it['rate']))
        else: add_item_row()

        btn(sf, "+ Add Item", add_item_row, color="#374151", width=110).pack(anchor="w", pady=(4,8))
        separator(sf).pack(fill="x", pady=8)

        # Discount + shipping + tax
        label(sf, "Adjustments", size=13, weight="bold").pack(anchor="w", pady=(0,6))
        adj = ctk.CTkFrame(sf, fg_color="transparent"); adj.pack(fill="x")

        label(adj, "Discount").grid(row=0,column=0,sticky="w",padx=4,pady=2)
        disc_type = ctk.CTkComboBox(adj, values=["flat ($)","percent (%)"], width=110, fg_color=WHITE, border_color=BORDER, text_color=DARK)
        disc_type.set("flat ($)" if inv.get('discount_type','flat')=='flat' else "percent (%)")
        disc_type.grid(row=1,column=0,padx=4,pady=2)
        disc_val = ctk.CTkEntry(adj, placeholder_text="0", width=80, fg_color=WHITE, border_color=BORDER, text_color=DARK)
        disc_val.insert(0, str(inv.get('discount_value',0))); disc_val.grid(row=1,column=1,padx=4,pady=2)

        label(adj, "Shipping").grid(row=0,column=2,sticky="w",padx=4,pady=2)
        ship_type = ctk.CTkComboBox(adj, values=["none","flat ($)","free"], width=110, fg_color=WHITE, border_color=BORDER, text_color=DARK)
        st = inv.get('shipping_type','none')
        ship_type.set("flat ($)" if st=='flat' else st); ship_type.grid(row=1,column=2,padx=4,pady=2)
        ship_val = ctk.CTkEntry(adj, placeholder_text="0.00", width=80, fg_color=WHITE, border_color=BORDER, text_color=DARK)
        ship_val.insert(0, str(inv.get('shipping',0))); ship_val.grid(row=1,column=3,padx=4,pady=2)

        label(adj, "Tax (%)").grid(row=0,column=4,sticky="w",padx=4,pady=2)
        tax_val = ctk.CTkEntry(adj, placeholder_text="0", width=80, fg_color=WHITE, border_color=BORDER, text_color=DARK)
        # Convert stored tax $ back to % for display
        _tax_pct = 0.0
        if inv.get('tax') and inv.get('subtotal') and float(inv.get('subtotal',0)) > 0:
            try: _tax_pct = round(float(inv['tax']) / float(inv['subtotal']) * 100, 4)
            except: _tax_pct = 0.0
        tax_val.insert(0, str(_tax_pct)); tax_val.grid(row=1,column=4,padx=4,pady=2)

        separator(sf).pack(fill="x", pady=12)

        # ── LIVE TOTALS PANEL ─────────────────────────────────────────────
        totals_card = ctk.CTkFrame(sf, fg_color="#f0f9ff", corner_radius=10, border_width=1, border_color="#bae6fd")
        totals_card.pack(fill="x", pady=(0,10))
        totals_card_inner = ctk.CTkFrame(totals_card, fg_color="transparent")
        totals_card_inner.pack(fill="x", padx=14, pady=10)

        def _tot_row(parent, label_text, value_text, bold=False, color=DARK):
            r = ctk.CTkFrame(parent, fg_color="transparent")
            r.pack(fill="x", pady=1)
            ctk.CTkLabel(r, text=label_text, font=ctk.CTkFont(size=11), text_color=GRAY, anchor="w").pack(side="left")
            lbl = ctk.CTkLabel(r, text=value_text,
                               font=ctk.CTkFont(size=12, weight="bold" if bold else "normal"),
                               text_color=color, anchor="e")
            lbl.pack(side="right")
            return lbl

        lbl_subtotal  = _tot_row(totals_card_inner, "Subtotal",  "$0.00")
        lbl_discount  = _tot_row(totals_card_inner, "Discount",  "—")
        lbl_shipping  = _tot_row(totals_card_inner, "Shipping",  "—")
        lbl_tax       = _tot_row(totals_card_inner, "Tax",       "—")
        ctk.CTkFrame(totals_card_inner, fg_color=BORDER, height=1).pack(fill="x", pady=4)
        lbl_total     = _tot_row(totals_card_inner, "TOTAL DUE", "$0.00", bold=True, color=RED)

        def recalc_totals(*_):
            try:
                subtotal = 0.0
                for _d, _q, _r, _ in item_rows:
                    try: subtotal += float(_q.get() or 0) * float(_r.get() or 0)
                    except: pass
                dt = 'flat' if 'flat' in disc_type.get() else 'percent'
                dv = float(disc_val.get() or 0)
                da = min(dv if dt=='flat' else subtotal*(dv/100), subtotal)
                st_raw = ship_type.get()
                st_val = 'flat' if 'flat' in st_raw else ('free' if 'free' in st_raw else 'none')
                ship = float(ship_val.get() or 0) if st_val=='flat' else 0
                tax_pct = float(tax_val.get() or 0)
                tax = (subtotal - da + ship) * (tax_pct / 100)
                total = subtotal - da + ship + tax
                cur = get_settings().get('currency','CA$')
                lbl_subtotal.configure(text=f"{cur}{subtotal:.2f}")
                lbl_discount.configure(text=f"-{cur}{da:.2f}" if da > 0 else "—")
                lbl_shipping.configure(text=("FREE" if st_val=='free' else (f"{cur}{ship:.2f}" if ship > 0 else "—")))
                lbl_tax.configure(text=f"{cur}{tax:.2f} ({tax_pct}%)" if tax_pct > 0 else "—")
                lbl_total.configure(text=f"{cur}{total:.2f}")
            except Exception:
                pass

        # Wire recalc to adjustment fields
        for _w in [disc_val, ship_val, tax_val]:
            _w.bind("<KeyRelease>", recalc_totals)
        disc_type.configure(command=lambda _: recalc_totals())
        ship_type.configure(command=lambda _: recalc_totals())

        # Register recalc with the shared ref so add_item_row can call it
        _recalc_ref[0] = recalc_totals
        recalc_totals()

        separator(sf).pack(fill="x", pady=12)
        label(sf, "Notes (optional)").pack(anchor="w")
        notes_box = ctk.CTkTextbox(sf, height=60, fg_color=WHITE, border_color=BORDER, text_color=DARK, border_width=1)
        notes_box.pack(fill="x", pady=(4,8))
        if inv.get('notes'): notes_box.insert("1.0", inv['notes'])

        # Save button
        def save():
            items = []
            for d,q,r,_ in item_rows:
                if d.get().strip():
                    items.append({"description":d.get(),"qty":q.get() or "1","rate":r.get() or "0"})
            if not items:
                messagebox.showwarning("No Items","Please add at least one line item."); return

            subtotal = sum(float(i['qty'])*float(i['rate']) for i in items)
            dt = 'flat' if 'flat' in disc_type.get() else 'percent'
            dv = float(disc_val.get() or 0)
            da = min(dv if dt=='flat' else subtotal*(dv/100), subtotal)
            st_raw = ship_type.get()
            st_val = 'flat' if 'flat' in st_raw else ('free' if 'free' in st_raw else 'none')
            ship = float(ship_val.get() or 0) if st_val=='flat' else 0
            tax_pct = float(tax_val.get() or 0)
            tax = (subtotal - da + ship) * (tax_pct / 100)
            total = subtotal - da + ship + tax

            client_idx = client_names.index(client_combo.get())
            cid = client_ids[client_idx]

            conn = get_db()
            if inv_id:
                conn.execute('''UPDATE invoices SET invoice_number=?,client_id=?,issue_date=?,due_date=?,
                    status=?,notes=?,items=?,subtotal=?,discount_type=?,discount_value=?,discount_amount=?,
                    shipping=?,shipping_type=?,tax=?,total=? WHERE id=?''',
                    (inv_num_var.get(), cid, issue_var.get(), due_var.get(), status_combo.get(),
                     notes_box.get("1.0","end").strip(), json.dumps(items), subtotal,
                     dt, dv, da, ship, st_val, tax, total, inv_id))
            else:
                conn.execute('''INSERT INTO invoices (invoice_number,client_id,issue_date,due_date,status,
                    notes,items,subtotal,discount_type,discount_value,discount_amount,shipping,shipping_type,tax,total)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (inv_num_var.get(), cid, issue_var.get(), due_var.get(), status_combo.get(),
                     notes_box.get("1.0","end").strip(), json.dumps(items), subtotal,
                     dt, dv, da, ship, st_val, tax, total))
            conn.commit(); conn.close()
            dlg.destroy()
            self.refresh_invoices(); self.refresh_dashboard()

        def save_with_confirm():
            # Check if user has disabled the prompt
            conn_s = get_db()
            skip = conn_s.execute("SELECT value FROM settings WHERE key='skip_save_confirm'").fetchone()
            conn_s.close()
            if skip and skip[0] == '1':
                save(); return
            # Show confirm dialog
            cdlg = ctk.CTkToplevel(dlg)
            cdlg.title("Confirm Save")
            cdlg.geometry("360x180")
            cdlg.resizable(False, False)
            cdlg.grab_set()
            cdlg.configure(fg_color=WHITE)
            label(cdlg, "Save this invoice?", size=14, weight="bold").pack(pady=(20,4))
            label(cdlg, "Please confirm you want to save.", size=12, color=GRAY).pack()
            skip_var = ctk.IntVar(value=0)
            ctk.CTkCheckBox(cdlg, text="Don't ask me again", variable=skip_var,
                            fg_color=GRAY, hover_color=GRAY, text_color=DARK,
                            font=ctk.CTkFont(size=11)).pack(pady=12)
            def confirm_save():
                if skip_var.get():
                    save_setting('skip_save_confirm', '1')
                cdlg.destroy(); save()
            br = ctk.CTkFrame(cdlg, fg_color="transparent"); br.pack()
            btn(br, "✅ Yes, Save", confirm_save, color=GREEN, width=120).pack(side="left", padx=6)
            btn(br, "Cancel", cdlg.destroy, color=GRAY, width=90).pack(side="left")

        btn(sf, "💾  Save Invoice", save_with_confirm, color=RED, width=180).pack(pady=8)

    # ── CLIENTS & CRM ─────────────────────────────────────────────────────
    def _build_clients(self):
        p = self.pages["clients"]
        self.clients_pane = ctk.CTkFrame(p, fg_color="transparent")
        self.clients_pane.pack(fill="both", expand=True)
        self.crm_pane = ctk.CTkFrame(p, fg_color="transparent")
        self._build_clients_list()
        self._build_crm_detail()

    def _build_clients_list(self):
        pane = self.clients_pane
        header = ctk.CTkFrame(pane, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(20,12))
        label(header, "Clients & CRM", size=22, weight="bold").pack(side="left")
        btn(header, "+ Add Client", lambda: self.open_client_dialog(), color=RED, width=130).pack(side="right")

        bar = ctk.CTkFrame(pane, fg_color="transparent")
        bar.pack(fill="x", padx=24, pady=(0,12))
        self.client_search = entry(bar, "Search by name, company, phone, city...", width=380)
        self.client_search.pack(side="left")
        self.client_search.bind("<KeyRelease>", self._debounce(lambda *_: self.refresh_clients()))
        self.client_filter = ctk.CTkComboBox(bar, values=["All","Starred","Has Follow-up"], width=140,
                                              fg_color=WHITE, border_color=BORDER, text_color=DARK,
                                              command=lambda _: self.refresh_clients())
        self.client_filter.set("All")
        self.client_filter.pack(side="left", padx=8)
        _stage_opts = ["All Stages"] + [s[1] for s in PIPELINE_STAGES]
        self.pipeline_filter = ctk.CTkComboBox(bar, values=_stage_opts, width=130,
                                               fg_color=WHITE, border_color=BORDER, text_color=DARK,
                                               command=lambda _: self.refresh_clients())
        self.pipeline_filter.set("All Stages")
        self.pipeline_filter.pack(side="left", padx=(0,8))
        btn(bar, "📊 Pipeline", self._show_pipeline_view, color="#374151", width=100).pack(side="left")
        btn(bar, "🗺 By Territory", self._show_territory_view, color="#374151", width=110).pack(side="left", padx=(6,0))

        self.clients_list = scrollframe(pane)
        self.clients_list.pack(fill="both", expand=True, padx=24, pady=(0,16))

    def _get_filtered_client_ids(self):
        """Return ordered list of client IDs matching current search/filter — for CRM nav."""
        q  = self.client_search.get().lower() if hasattr(self, "client_search") else ""
        f  = self.client_filter.get() if hasattr(self, "client_filter") else "All"
        pf = self.pipeline_filter.get() if hasattr(self, "pipeline_filter") else "All Stages"
        conn = get_db()
        clients = [dict(c) for c in conn.execute("SELECT * FROM clients ORDER BY starred DESC, company, name").fetchall()]
        conn.close()
        _sm = get_all_pipeline_stages()
        ids = []
        for c in clients:
            name = c.get("company") or c.get("name", "")
            searchable = " ".join(filter(None, [
                c.get("name",""), c.get("company",""), c.get("phone",""),
                c.get("city",""), c.get("email",""), c.get("province","")
            ])).lower()
            if q and q not in searchable: continue
            if f == "Starred" and not c.get("starred"): continue
            if f == "Has Follow-up" and not c.get("follow_up_date"): continue
            stage = _sm.get(c["id"], "cold_lead")
            if pf != "All Stages" and STAGE_LABELS.get(stage,"") != pf: continue
            ids.append(c["id"])
        return ids

    def refresh_clients(self):
        q  = self.client_search.get().lower() if hasattr(self,'client_search') else ""
        f  = self.client_filter.get() if hasattr(self,'client_filter') else "All"
        pf = self.pipeline_filter.get() if hasattr(self,'pipeline_filter') else "All Stages"
        conn = get_db()
        clients = conn.execute('SELECT * FROM clients ORDER BY starred DESC, name').fetchall()
        conn.close()
        _stage_map_cache = get_all_pipeline_stages()
        for w in self.clients_list.winfo_children(): w.destroy()
        shown = 0
        for c in clients:
            c = dict(c)
            name = c.get('company') or c.get('name','')
            searchable = ' '.join(filter(None,[
                c.get('name',''), c.get('company',''), c.get('phone',''),
                c.get('city',''), c.get('email',''), c.get('province','')
            ])).lower()
            if q and q not in searchable: continue
            if f == "Starred" and not c.get('starred'): continue
            if f == "Has Follow-up" and not c.get('follow_up_date'): continue
            stage = _stage_map_cache.get(c['id'], 'cold_lead')
            if pf != "All Stages" and STAGE_LABELS.get(stage,'') != pf: continue
            shown += 1
            card = ctk.CTkFrame(self.clients_list, fg_color=WHITE, corner_radius=10,
                               border_width=2 if c['starred'] else 1,
                               border_color=AMBER if c['starred'] else BORDER)
            card.pack(fill="x", pady=4)
            row_inner = ctk.CTkFrame(card, fg_color="transparent")
            row_inner.pack(fill="x", padx=12, pady=(8,4))
            star = "⭐" if c['starred'] else "☆"
            cid = c['id']
            left_block = ctk.CTkFrame(row_inner, fg_color="transparent")
            left_block.pack(side="left")
            label(left_block, f"{star}  {name}", size=13, weight="bold").pack(anchor="w")
            contact_name = c.get('name','')
            if contact_name and contact_name.lower() != name.lower():
                label(left_block, f"    👤 {contact_name}", size=11, color=GRAY).pack(anchor="w")
            # Pipeline stage badge
            s_text_col, s_bg = STAGE_COLORS.get(stage, ("#6b7280","#f3f4f6"))
            badge_frame = ctk.CTkFrame(row_inner, fg_color=s_bg, corner_radius=6)
            badge_frame.pack(side="left", padx=(10,0))
            ctk.CTkLabel(badge_frame, text=STAGE_LABELS.get(stage,'?'),
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=s_text_col).pack(padx=6, pady=2)
            acts = ctk.CTkFrame(row_inner, fg_color="transparent"); acts.pack(side="right")
            btn(acts, "CRM →", lambda i=cid, nl=None: self.open_crm_detail(i, nav_list=self._get_filtered_client_ids()), color=DARK, width=70).pack(side="left", padx=2)
            btn(acts, "Edit", lambda i=cid: self.open_client_dialog(i), color="#374151", width=50).pack(side="left", padx=2)
            btn(acts, "✕", lambda i=cid: self.delete_client(i), color=RED, width=30).pack(side="left", padx=2)
            has_info = c.get('email') or c.get('phone') or c.get('follow_up_date')
            if has_info:
                info_row = ctk.CTkFrame(card, fg_color="transparent")
                info_row.pack(fill="x", padx=12, pady=(0,8))
                if c.get('email'): label(info_row, f"✉ {c['email']}", size=11, color=RED).pack(side="left", padx=(0,12))
                if c.get('phone'): label(info_row, f"📞 {c['phone']}", size=11, color=GRAY).pack(side="left", padx=(0,12))
                if c.get('follow_up_date'):
                    is_over = c['follow_up_date'] < today()
                    label(info_row, f"📅 {fmt_date(c['follow_up_date'])}", size=11,
                          color=RED if is_over else GRAY).pack(side="left")

        if shown == 0:
            label(self.clients_list, "No clients found", color=GRAY).pack(pady=40)

    def _build_crm_detail(self):
        pane = self.crm_pane
        back_bar = ctk.CTkFrame(pane, fg_color="transparent")
        back_bar.pack(fill="x", padx=24, pady=(20,8))
        ctk.CTkButton(back_bar, text="← Back to Clients", command=self.show_clients_list,
                      fg_color=GREEN, hover_color="#15803d", text_color=WHITE,
                      width=180, height=36, corner_radius=8,
                      font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")
        self.crm_client_title = label(back_bar, "", size=18, weight="bold")
        self.crm_client_title.pack(side="left", padx=16)
        # Prev / Next navigation — respects active filter list
        nav_right = ctk.CTkFrame(back_bar, fg_color="transparent")
        nav_right.pack(side="right")
        self._crm_nav_counter = label(nav_right, "", size=11, color=GRAY)
        self._crm_nav_counter.pack(side="left", padx=(0,8))
        self._crm_prev_btn = ctk.CTkButton(
            nav_right, text="‹ Prev", width=80, height=32,
            fg_color=DARK, hover_color="#2d2d44", text_color=WHITE,
            corner_radius=8, font=ctk.CTkFont(size=12),
            command=self._crm_nav_prev)
        self._crm_prev_btn.pack(side="left", padx=(0,4))
        self._crm_next_btn = ctk.CTkButton(
            nav_right, text="Next ›", width=80, height=32,
            fg_color=DARK, hover_color="#2d2d44", text_color=WHITE,
            corner_radius=8, font=ctk.CTkFont(size=12),
            command=self._crm_nav_next)
        self._crm_next_btn.pack(side="left")

        cols = ctk.CTkFrame(pane, fg_color="transparent")
        cols.pack(fill="both", expand=True, padx=24, pady=(0,16))
        cols.columnconfigure(0, weight=1)
        cols.columnconfigure(1, weight=2)

        # Left panel
        left = ctk.CTkFrame(cols, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(0,8))

        self.crm_info_card = ctk.CTkFrame(left, fg_color=WHITE, corner_radius=12, border_width=1, border_color=BORDER)
        self.crm_info_card.pack(fill="x", pady=(0,8))
        self.crm_pay_card = ctk.CTkFrame(left, fg_color=WHITE, corner_radius=12, border_width=1, border_color=BORDER)
        self.crm_pay_card.pack(fill="x", pady=(0,8))
        self.crm_inv_card = ctk.CTkFrame(left, fg_color=WHITE, corner_radius=12, border_width=1, border_color=BORDER)
        self.crm_inv_card.pack(fill="both", expand=True)

        # Right panel — tabs
        # Use a fixed outer frame so tab switching never causes left panel to reflow
        right = ctk.CTkFrame(cols, fg_color=WHITE, corner_radius=12, border_width=1, border_color=BORDER)
        right.grid(row=0, column=1, sticky="nsew", padx=(8,0))
        right.grid_propagate(False)
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        # Tab bar — light blue / light yellow colour coded
        tab_bar = ctk.CTkFrame(right, fg_color="#f1f5f9", corner_radius=0, height=44)
        tab_bar.grid(row=0, column=0, sticky="ew")
        tab_bar.grid_propagate(False)
        tab_bar.columnconfigure(0, weight=1)
        tab_bar.columnconfigure(1, weight=1)
        tab_bar.columnconfigure(2, weight=1)

        self.crm_tab_btns = {}
        tab_configs = {
            "notes":     ("📞 Call Notes",   "#dbeafe", "#1e40af", "#bfdbfe"),
            "followups": ("📅 Follow-ups",   "#fef9c3", "#854d0e", "#fde68a"),
            "purchases": ("🛍 Purchases",    "#dcfce7", "#166534", "#bbf7d0"),
        }
        for col_idx, (tab_name, (tab_lbl, active_bg, active_fg, hover_bg)) in enumerate(tab_configs.items()):
            b = ctk.CTkButton(
                tab_bar, text=tab_lbl,
                command=lambda t=tab_name: self.switch_crm_tab(t),
                fg_color=active_bg if tab_name=="notes" else "#f1f5f9",
                hover_color=hover_bg,
                text_color=active_fg if tab_name=="notes" else GRAY,
                corner_radius=0, height=44,
                font=ctk.CTkFont(size=13, weight="bold" if tab_name=="notes" else "normal"),
                border_width=0
            )
            b.grid(row=0, column=col_idx, sticky="nsew")
            self.crm_tab_btns[tab_name] = b

        # Panel container — fixed, tabs swap inside here without reflowing left panel
        panel_container = ctk.CTkFrame(right, fg_color="transparent")
        panel_container.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        panel_container.rowconfigure(0, weight=1)
        panel_container.columnconfigure(0, weight=1)

        self.crm_panels = {}

        # Notes panel
        np = ctk.CTkFrame(panel_container, fg_color="transparent")
        np.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        self.crm_panels["notes"] = np
        note_input_row = ctk.CTkFrame(np, fg_color="transparent")
        note_input_row.pack(fill="x", pady=(0,4))
        self.note_type_combo = ctk.CTkComboBox(note_input_row, values=["📞 Call","📧 Email","🤝 Meeting","📝 Other"],
                                                width=120, fg_color=WHITE, border_color=BORDER, text_color=DARK)
        self.note_type_combo.set("📞 Call")
        self.note_type_combo.pack(side="left", padx=(0,8))

        # Date/time row for notes
        note_dt_row = ctk.CTkFrame(np, fg_color="transparent")
        note_dt_row.pack(fill="x", pady=(0,4))
        label(note_dt_row, "Date/Time:", size=11, color=GRAY).pack(side="left", padx=(0,4))
        self.note_dt_var = tk.StringVar(value=datetime.now().strftime('%Y-%m-%d %H:%M'))
        note_dt_display = tk.Label(note_dt_row, textvariable=self.note_dt_var,
                                   font=("Segoe UI", 11), fg=DARK, bg=LIGHT)
        note_dt_display.pack(side="left", padx=(0,6))
        btn(note_dt_row, "📅 Change", lambda: self._pick_datetime(self.note_dt_var), color="#374151", width=100).pack(side="left")
        btn(note_input_row, "Add Note", self.add_note, color=RED, width=100).pack(side="right")

        self.note_text = ctk.CTkTextbox(np, height=80, fg_color=WHITE, border_color=BORDER, text_color=DARK, border_width=1)
        self.note_text.pack(fill="x", pady=(0,8))
        separator(np).pack(fill="x", pady=(0,8))
        self.notes_scroll = scrollframe(np)
        self.notes_scroll.pack(fill="both", expand=True)

        # Follow-ups panel — mirrors Call Notes layout exactly
        fp = ctk.CTkFrame(panel_container, fg_color="transparent")
        fp.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        fp.grid_remove()
        self.crm_panels["followups"] = fp

        # Row 1: type label + Add Follow-Up button (mirrors note_input_row)
        fup_input_row = ctk.CTkFrame(fp, fg_color="transparent")
        fup_input_row.pack(fill="x", pady=(0,4))
        self.fup_type_combo = ctk.CTkComboBox(
            fup_input_row,
            values=["📅 Task","📞 Call Back","📧 Email","🤝 Meeting","⚠ Urgent"],
            width=130, fg_color=WHITE, border_color=BORDER, text_color=DARK)
        self.fup_type_combo.set("📅 Task")
        self.fup_type_combo.pack(side="left", padx=(0,8))
        btn(fup_input_row, "Add Follow-Up", self.add_followup, color=RED, width=120).pack(side="right")

        # Row 2: date/time picker (mirrors note_dt_row)
        fup_dt_row = ctk.CTkFrame(fp, fg_color="transparent")
        fup_dt_row.pack(fill="x", pady=(0,4))
        label(fup_dt_row, "Scheduled for:", size=11, color=GRAY).pack(side="left", padx=(0,4))
        self.fup_dt_var = tk.StringVar(value=datetime.now().strftime('%Y-%m-%d %H:%M'))
        fup_dt_display = tk.Label(fup_dt_row, textvariable=self.fup_dt_var,
                                  font=("Segoe UI", 11), fg=DARK, bg=WHITE)
        fup_dt_display.pack(side="left", padx=(0,6))
        btn(fup_dt_row, "📅 Change", lambda: self._pick_datetime(self.fup_dt_var),
            color="#374151", width=100).pack(side="left")

        # Row 3: text box (mirrors self.note_text)
        self.fup_text = ctk.CTkTextbox(
            fp, height=80, fg_color=WHITE,
            border_color=BORDER, text_color=DARK, border_width=1)
        self.fup_text.pack(fill="x", pady=(0,8))

        separator(fp).pack(fill="x", pady=(0,8))
        self.fups_scroll = scrollframe(fp)
        self.fups_scroll.pack(fill="both", expand=True)

        # Purchase History panel
        pp = ctk.CTkFrame(panel_container, fg_color="transparent")
        pp.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        pp.grid_remove()
        self.crm_panels["purchases"] = pp
        label(pp, "Items ordered across all invoices", size=11, color=GRAY).pack(anchor="w", pady=(0,8))
        separator(pp).pack(fill="x", pady=(0,8))
        self.purchases_scroll = scrollframe(pp)
        self.purchases_scroll.pack(fill="both", expand=True)

    def refresh_purchases(self):
        for w in self.purchases_scroll.winfo_children(): w.destroy()
        conn = get_db()
        invs = conn.execute(
            'SELECT items, issue_date FROM invoices WHERE client_id=? ORDER BY issue_date DESC',
            (self.current_client_id,)
        ).fetchall()
        conn.close()
        seen = set()
        all_items = []
        for inv in invs:
            try:
                items = json.loads(inv['items']) if inv['items'] else []
            except: items = []
            for item in items:
                desc = item.get('description','').strip()
                if desc and desc.lower() not in seen:
                    seen.add(desc.lower())
                    all_items.append((desc, inv['issue_date'] or ''))
        if all_items:
            for desc, date in all_items:
                row = ctk.CTkFrame(self.purchases_scroll, fg_color=LIGHT, corner_radius=6)
                row.pack(fill="x", pady=2)
                inner = ctk.CTkFrame(row, fg_color="transparent")
                inner.pack(fill="x", padx=10, pady=6)
                label(inner, f"📦  {desc}", size=12, color=DARK).pack(side="left", anchor="w")
                if date:
                    label(inner, fmt_date(date), size=10, color=GRAY).pack(side="right")
        else:
            label(self.purchases_scroll, "No purchase history yet.", color=GRAY).pack(pady=20)

    def switch_crm_tab(self, tab):
        tab_configs = {
            "notes":     ("#dbeafe", "#1e40af", "#bfdbfe", True),
            "followups": ("#fef9c3", "#854d0e", "#fde68a", False),
            "purchases": ("#dcfce7", "#166534", "#bbf7d0", False),
        }
        for t, b in self.crm_tab_btns.items():
            active_bg, active_fg, hover_bg, _ = tab_configs[t]
            if t == tab:
                b.configure(fg_color=active_bg, text_color=active_fg,
                            font=ctk.CTkFont(size=13, weight="bold"))
                self.crm_panels[t].grid(row=0, column=0, sticky="nsew",
                                         padx=12, pady=12)
                self.crm_panels[t].lift()
            else:
                b.configure(fg_color="#f1f5f9", text_color=GRAY,
                            font=ctk.CTkFont(size=13, weight="normal"))
                self.crm_panels[t].grid_remove()

    def open_crm_detail(self, client_id, nav_list=None):
        self.current_client_id = client_id
        # Store the navigation list (respects active filter/search)
        if nav_list is not None:
            self._crm_nav_list = nav_list
        elif not hasattr(self, "_crm_nav_list") or not self._crm_nav_list:
            # Build full list as fallback
            conn0 = get_db()
            self._crm_nav_list = [r["id"] for r in
                conn0.execute("SELECT id FROM clients ORDER BY company, name").fetchall()]
            conn0.close()
        self.clients_pane.pack_forget()
        self.crm_pane.pack(fill="both", expand=True)
        conn = get_db()
        c = dict(conn.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone())
        invs = conn.execute('''SELECT i.* FROM invoices i WHERE i.client_id=? ORDER BY i.id DESC''', (client_id,)).fetchall()
        conn.close()

        self.crm_client_title.configure(text=f"{'⭐ ' if c['starred'] else ''}{c['company'] or c['name']}")
        # Update nav counter and button states
        self._update_crm_nav_state()

        # Client info — locked by default, unlocked on Edit click
        for w in self.crm_info_card.winfo_children(): w.destroy()
        info_header = ctk.CTkFrame(self.crm_info_card, fg_color="transparent")
        info_header.pack(fill="x", padx=12, pady=(10,4))
        label(info_header, "Client Info", size=13, weight="bold").pack(side="left")

        # Edit toggle button — dark blue = locked, green = editing
        edit_active = [False]
        edit_toggle_btn = ctk.CTkButton(
            info_header, text="✏ Edit", width=70,
            fg_color=DARK, hover_color="#2d2d44",
            text_color=WHITE, corner_radius=8,
            font=ctk.CTkFont(size=12)
        )
        edit_toggle_btn.pack(side="right")

        crm_fields = {}
        edit_defs = [
            ("name",    "Name",         c.get("name",""),         200),
            ("company", "Company",      c.get("company",""),      200),
            ("phone",   "Phone",        c.get("phone",""),        160),
            ("email",   "Email",        c.get("email",""),        200),
            ("city",    "City",         c.get("city",""),         130),
            ("province","Province",     c.get("province",""),     80),
            ("follow_up_date","Follow-up Date", c.get("follow_up_date",""), 130),
        ]
        for key, lbl_text, val, w in edit_defs:
            row = ctk.CTkFrame(self.crm_info_card, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=2)
            label(row, f"{lbl_text}:", size=11, color=GRAY, width=90, anchor="w").pack(side="left")
            e = ctk.CTkEntry(row, width=w, fg_color=LIGHT, border_color=LIGHT,
                             text_color=DARK, font=ctk.CTkFont(size=12), height=26,
                             state="disabled")
            e.configure(state="normal"); e.insert(0, val or ""); e.configure(state="disabled")
            e.pack(side="left")
            crm_fields[key] = e

        save_row = ctk.CTkFrame(self.crm_info_card, fg_color="transparent")
        save_row.pack(fill="x", padx=12, pady=(4,8))
        save_btn = ctk.CTkButton(save_row, text="💾 Save Changes", width=130,
                                  fg_color=GRAY, hover_color=GRAY,
                                  text_color=WHITE, corner_radius=8,
                                  font=ctk.CTkFont(size=12), state="disabled")
        save_btn.pack(side="left")
        save_status = label(save_row, "", size=11, color=GREEN)
        save_status.pack(side="left", padx=8)

        def set_edit_mode(active):
            edit_active[0] = active
            if active:
                # Unlock — green button, fields editable
                edit_toggle_btn.configure(
                    text="🔒 Lock", fg_color="#16A34A",
                    hover_color="#15803d"
                )
                save_btn.configure(
                    fg_color=RED, hover_color="#c4312a", state="normal"
                )
                for e in crm_fields.values():
                    e.configure(state="normal", fg_color=WHITE, border_color=BORDER)
            else:
                # Lock — dark button, fields read-only
                edit_toggle_btn.configure(
                    text="✏ Edit", fg_color=DARK,
                    hover_color="#2d2d44"
                )
                save_btn.configure(
                    fg_color=GRAY, hover_color=GRAY, state="disabled"
                )
                for e in crm_fields.values():
                    e.configure(state="disabled", fg_color=LIGHT, border_color=LIGHT)

        edit_toggle_btn.configure(command=lambda: set_edit_mode(not edit_active[0]))

        # Pipeline stage + sample sent row
        pipe_row = ctk.CTkFrame(self.crm_info_card, fg_color="transparent")
        pipe_row.pack(fill="x", padx=12, pady=(4,4))
        label(pipe_row, "Pipeline:", size=11, color=GRAY, width=70, anchor="w").pack(side="left")
        _cur_stage = get_client_pipeline_stage(client_id)
        _stage_label_list = [s[1] for s in PIPELINE_STAGES]
        pipe_combo = ctk.CTkComboBox(pipe_row, values=_stage_label_list, width=140,
                                     fg_color=WHITE, border_color=BORDER, text_color=DARK,
                                     font=ctk.CTkFont(size=11))
        pipe_combo.set(STAGE_LABELS.get(_cur_stage, "Cold Lead"))
        pipe_combo.pack(side="left", padx=(0,8))
        sample_var = ctk.IntVar(value=c.get('sample_sent', 0))
        _is_local = is_local_client(c.get('city',''))

        def _save_sample_and_stage(*_):
            """Save pipeline stage + sample sent instantly on change."""
            sel = pipe_combo.get()
            ns = next((k for k,v in STAGE_LABELS.items() if v == sel), 'cold_lead')
            conn_s = get_db()
            conn_s.execute('UPDATE clients SET pipeline_stage=?, sample_sent=? WHERE id=?',
                           (ns, sample_var.get(), client_id))
            conn_s.commit(); conn_s.close()
            self.refresh_clients()

        # Bind pipeline combo to auto-save on change
        pipe_combo.configure(command=_save_sample_and_stage)

        if _is_local:
            chk = ctk.CTkCheckBox(pipe_row, text="📦 Sample sent", variable=sample_var,
                            fg_color=AMBER, hover_color=AMBER, text_color=DARK,
                            font=ctk.CTkFont(size=11),
                            command=_save_sample_and_stage)  # save on tick
            chk.pack(side="left")
        else:
            label(pipe_row, "Remote client", size=10, color=GRAY).pack(side="left")

        def save_crm_info():
            conn2 = get_db()
            selected_label = pipe_combo.get()
            new_stage = next((k for k,v in STAGE_LABELS.items() if v == selected_label), 'cold_lead')
            conn2.execute('UPDATE clients SET pipeline_stage=?, sample_sent=? WHERE id=?',
                         (new_stage, sample_var.get(), client_id))
            conn2.execute("""UPDATE clients SET name=?,company=?,phone=?,email=?,city=?,province=?,follow_up_date=? WHERE id=?""",
                (crm_fields["name"].get().strip(),
                 crm_fields["company"].get().strip() or None,
                 crm_fields["phone"].get().strip() or None,
                 crm_fields["email"].get().strip() or None,
                 crm_fields["city"].get().strip() or None,
                 crm_fields["province"].get().strip() or None,
                 crm_fields["follow_up_date"].get().strip() or None,
                 client_id))
            conn2.commit(); conn2.close()
            self.crm_client_title.configure(
                text=f"{'⭐ ' if c['starred'] else ''}{crm_fields['company'].get() or crm_fields['name'].get()}"
            )
            save_status.configure(text="✓ Saved!")
            set_edit_mode(False)
            self.after(2000, lambda: save_status.configure(text=""))
            self.refresh_clients()

        save_btn.configure(command=save_crm_info)

        # Payment info
        for w in self.crm_pay_card.winfo_children(): w.destroy()
        label(self.crm_pay_card, "Payment Reference", size=13, weight="bold").pack(anchor="w", padx=12, pady=(10,4))
        pay_row = ctk.CTkFrame(self.crm_pay_card, fg_color="transparent")
        pay_row.pack(fill="x", padx=12, pady=(0,10))
        pm = c.get('payment_method','e-transfer').title()
        last4 = c.get('payment_last4','')
        label(pay_row, f"💳  {pm}", size=12).pack(side="left")
        if last4: label(pay_row, f"  ···· {last4}", size=12, color=GRAY).pack(side="left")

        # Client invoices
        for w in self.crm_inv_card.winfo_children(): w.destroy()
        label(self.crm_inv_card, "Invoices", size=13, weight="bold").pack(anchor="w", padx=12, pady=(10,4))
        if invs:
            for inv in invs:
                row = ctk.CTkFrame(self.crm_inv_card, fg_color="transparent")
                row.pack(fill="x", padx=12, pady=2)
                label(row, inv['invoice_number'], size=11, weight="bold").pack(side="left")
                label(row, fmt(inv['total']), size=11).pack(side="left", padx=8)
                status_col = GREEN if inv['status']=='paid' else RED
                label(row, inv['status'].upper(), size=10, color=status_col).pack(side="left")
                inv_id = inv['id']; inv_num = inv['invoice_number']
                btn(row, "👁 View", lambda i=inv_id, n=inv_num, c=client_id: self.preview_pdf(i,n,c), color="#374151", width=65).pack(side="right")
        else:
            label(self.crm_inv_card, "No invoices yet", size=12, color=GRAY).pack(padx=12, pady=4)
        ctk.CTkFrame(self.crm_inv_card, fg_color="transparent", height=8).pack()

        self.switch_crm_tab("notes")
        self.refresh_notes()
        self.refresh_followups()
        self.refresh_purchases()

    def _pick_datetime(self, string_var: tk.StringVar):
        """Clickable calendar + 12-hour AM/PM time picker."""
        import calendar as cal_mod

        dlg = ctk.CTkToplevel(self)
        dlg.title("Pick Date & Time")
        dlg.geometry("340x370")
        dlg.resizable(False, False)
        dlg.grab_set()
        dlg.configure(fg_color=WHITE)

        # Parse current value
        now = datetime.now()
        try:
            now = datetime.strptime(string_var.get(), '%Y-%m-%d %H:%M')
        except: pass

        sel = {"year": now.year, "month": now.month, "day": now.day}

        # ── Calendar header ──────────────────────────────────────────────
        cal_frame = ctk.CTkFrame(dlg, fg_color=WHITE)
        cal_frame.pack(fill="x", padx=12, pady=(12,4))

        nav = ctk.CTkFrame(cal_frame, fg_color="transparent")
        nav.pack(fill="x", pady=(0,4))

        MONTH_NAMES = ["January","February","March","April","May","June",
                       "July","August","September","October","November","December"]
        import datetime as _dt; YEAR_RANGE = [str(y) for y in range(2000, _dt.datetime.now().year + 201)]

        month_combo = ctk.CTkComboBox(nav, values=MONTH_NAMES, width=120,
                                      fg_color=WHITE, border_color=BORDER, text_color=DARK,
                                      font=ctk.CTkFont(size=12, weight="bold"))
        month_combo.set(MONTH_NAMES[sel["month"] - 1])
        month_combo.pack(side="left", padx=(0,4))

        year_combo = ctk.CTkComboBox(nav, values=YEAR_RANGE, width=80,
                                     fg_color=WHITE, border_color=BORDER, text_color=DARK,
                                     font=ctk.CTkFont(size=12, weight="bold"))
        year_combo.set(str(sel["year"]))
        year_combo.pack(side="left")

        day_grid_frame = ctk.CTkFrame(cal_frame, fg_color="transparent")
        day_grid_frame.pack(fill="x", pady=4)

        day_btns = {}

        def render_calendar():
            for w in day_grid_frame.winfo_children():
                w.destroy()
            day_btns.clear()
            y, m = sel["year"], sel["month"]
            for col, d in enumerate(["Su","Mo","Tu","We","Th","Fr","Sa"]):
                ctk.CTkLabel(day_grid_frame, text=d, width=36, height=26,
                             font=ctk.CTkFont(size=11, weight="bold"),
                             text_color=GRAY).grid(row=0, column=col, padx=1, pady=1)
            first_dow = cal_mod.monthrange(y, m)[0]
            first_col = (first_dow + 1) % 7
            days_in_month = cal_mod.monthrange(y, m)[1]
            for day in range(1, days_in_month + 1):
                col = (first_col + day - 1) % 7
                row = (first_col + day - 1) // 7 + 1
                is_sel = day == sel["day"]
                b = ctk.CTkButton(
                    day_grid_frame, text=str(day), width=36, height=28,
                    fg_color=RED if is_sel else LIGHT,
                    hover_color="#c4312a" if is_sel else BORDER,
                    text_color=WHITE if is_sel else DARK,
                    font=ctk.CTkFont(size=12),
                    corner_radius=6,
                    command=lambda d=day: pick_day(d)
                )
                b.grid(row=row, column=col, padx=1, pady=1)
                day_btns[day] = b

        def pick_day(d):
            sel["day"] = d
            render_calendar()

        def on_month_change(choice):
            sel["month"] = MONTH_NAMES.index(choice) + 1
            max_day = cal_mod.monthrange(sel["year"], sel["month"])[1]
            sel["day"] = min(sel["day"], max_day)
            render_calendar()

        def on_year_change(choice):
            sel["year"] = int(choice)
            max_day = cal_mod.monthrange(sel["year"], sel["month"])[1]
            sel["day"] = min(sel["day"], max_day)
            render_calendar()

        month_combo.configure(command=on_month_change)
        year_combo.configure(command=on_year_change)
        render_calendar()

        # ── Time picker (12-hour) ────────────────────────────────────────
        sep_line = ctk.CTkFrame(dlg, fg_color=BORDER, height=1)
        sep_line.pack(fill="x", padx=12, pady=6)

        time_frame = ctk.CTkFrame(dlg, fg_color="transparent")
        time_frame.pack(pady=4)

        # Determine initial 12-hr values
        h24 = now.hour
        init_ampm = "AM" if h24 < 12 else "PM"
        init_h12  = h24 % 12 or 12

        label(time_frame, "Time:", size=12, color=GRAY).pack(side="left", padx=(0,8))

        hour_var = tk.StringVar(value=str(init_h12).zfill(2))
        min_var  = tk.StringVar(value=str(now.minute).zfill(2))
        ampm_var = tk.StringVar(value=init_ampm)

        ctk.CTkEntry(time_frame, textvariable=hour_var, width=46,
                     fg_color=WHITE, border_color=BORDER, text_color=DARK,
                     font=ctk.CTkFont(size=13)).pack(side="left")
        label(time_frame, ":", size=14, color=DARK).pack(side="left", padx=2)
        ctk.CTkEntry(time_frame, textvariable=min_var, width=46,
                     fg_color=WHITE, border_color=BORDER, text_color=DARK,
                     font=ctk.CTkFont(size=13)).pack(side="left")

        ampm_btn = ctk.CTkButton(time_frame, textvariable=ampm_var, width=52, height=32,
                                  fg_color=DARK, hover_color="#2d2d44",
                                  text_color=WHITE, font=ctk.CTkFont(size=12),
                                  command=lambda: ampm_var.set("PM" if ampm_var.get()=="AM" else "AM"))
        ampm_btn.pack(side="left", padx=6)

        hint = ctk.CTkLabel(dlg, text="Hour 1–12, Min 0–59",
                            font=ctk.CTkFont(size=10), text_color=GRAY)
        hint.pack()

        # ── OK / Cancel ──────────────────────────────────────────────────
        def confirm():
            try:
                h = int(hour_var.get()); m = int(min_var.get())
                if not (1 <= h <= 12 and 0 <= m <= 59): raise ValueError
            except ValueError:
                messagebox.showerror("Invalid time", "Hour must be 1–12, minute 0–59.", parent=dlg)
                return
            # Convert to 24-hr for storage
            if ampm_var.get() == "AM":
                h24 = 0 if h == 12 else h
            else:
                h24 = 12 if h == 12 else h + 12
            d_str = f"{sel['year']:04d}-{sel['month']:02d}-{sel['day']:02d}"
            string_var.set(f"{d_str} {h24:02d}:{m:02d}")
            dlg.destroy()

        btn_row = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_row.pack(pady=10)
        btn(btn_row, "OK", confirm, color=RED, width=90).pack(side="left", padx=6)
        btn(btn_row, "Cancel", dlg.destroy, color=GRAY, width=90).pack(side="left", padx=6)

    def _update_crm_nav_state(self):
        nav = getattr(self, "_crm_nav_list", [])
        if not nav or not hasattr(self, "_crm_nav_counter"): return
        try:
            idx = nav.index(self.current_client_id)
        except ValueError:
            idx = -1
        total = len(nav)
        if idx >= 0:
            self._crm_nav_counter.configure(text=f"{idx+1} of {total}")
        else:
            self._crm_nav_counter.configure(text="")
        # Dim buttons at boundaries
        prev_state = "normal" if idx > 0 else "disabled"
        next_state = "normal" if 0 <= idx < total - 1 else "disabled"
        self._crm_prev_btn.configure(state=prev_state,
            fg_color=DARK if prev_state=="normal" else GRAY)
        self._crm_next_btn.configure(state=next_state,
            fg_color=DARK if next_state=="normal" else GRAY)

    def _crm_nav_prev(self):
        nav = getattr(self, "_crm_nav_list", [])
        if not nav: return
        try: idx = nav.index(self.current_client_id)
        except ValueError: return
        if idx > 0:
            self.open_crm_detail(nav[idx - 1], nav_list=nav)

    def _crm_nav_next(self):
        nav = getattr(self, "_crm_nav_list", [])
        if not nav: return
        try: idx = nav.index(self.current_client_id)
        except ValueError: return
        if idx < len(nav) - 1:
            self.open_crm_detail(nav[idx + 1], nav_list=nav)

    def show_clients_list(self):
        self.crm_pane.pack_forget()
        if hasattr(self, 'pipeline_pane'): self.pipeline_pane.pack_forget()
        if hasattr(self, 'territory_pane'): self.territory_pane.pack_forget()
        self.clients_pane.pack(fill="both", expand=True)
        self.refresh_clients()

    def _show_territory_view(self):
        self.clients_pane.pack_forget()
        if not hasattr(self, "territory_pane"):
            self.territory_pane = ctk.CTkFrame(self.pages["clients"], fg_color="transparent")
        else:
            for w in self.territory_pane.winfo_children(): w.destroy()
        self.territory_pane.pack(fill="both", expand=True)

        hdr = ctk.CTkFrame(self.territory_pane, fg_color="transparent")
        hdr.pack(fill="x", padx=24, pady=(20,12))
        label(hdr, "Clients by Territory", size=22, weight="bold").pack(side="left")
        btn(hdr, "← All Clients", self._back_from_territory, color="#374151", width=130).pack(side="right")

        conn = get_db()
        clients = [dict(c) for c in conn.execute("SELECT * FROM clients ORDER BY province, company, name").fetchall()]
        conn.close()
        _stage_map = get_all_pipeline_stages()

        # Group by province
        from collections import OrderedDict
        groups = OrderedDict()
        for c in clients:
            prov = (c.get("province") or "").strip() or "Unknown"
            groups.setdefault(prov, []).append(c)

        scroll = scrollframe(self.territory_pane)
        scroll.pack(fill="both", expand=True, padx=24, pady=(0,16))

        for prov, group in sorted(groups.items()):
            # Province header
            prov_hdr = ctk.CTkFrame(scroll, fg_color=DARK, corner_radius=8)
            prov_hdr.pack(fill="x", pady=(8,4))
            prov_inner = ctk.CTkFrame(prov_hdr, fg_color="transparent")
            prov_inner.pack(fill="x", padx=14, pady=8)
            label(prov_inner, f"📍  {prov}", size=14, weight="bold", color=WHITE).pack(side="left")
            label(prov_inner, f"{len(group)} client{"s" if len(group)!=1 else ""}",
                  size=11, color="gray60").pack(side="right")

            for c in group:
                cid = c["id"]
                cname = c.get("company") or c.get("name", "")
                card = ctk.CTkFrame(scroll, fg_color=WHITE,
                                   corner_radius=8, border_width=1, border_color=BORDER)
                card.pack(fill="x", pady=2, padx=8)
                row = ctk.CTkFrame(card, fg_color="transparent")
                row.pack(fill="x", padx=12, pady=6)
                # Name + stage badge
                left = ctk.CTkFrame(row, fg_color="transparent")
                left.pack(side="left")
                label(left, f"{"⭐ " if c["starred"] else ""}{cname}", size=12, weight="bold").pack(anchor="w")
                if c.get("name") and c["name"].lower() != cname.lower():
                    label(left, f"👤 {c["name"]}", size=10, color=GRAY).pack(anchor="w")
                if c.get("city"):
                    label(left, f"🏙 {c["city"]}", size=10, color=GRAY).pack(anchor="w")
                # Stage badge
                stage = _stage_map.get(cid, "cold_lead")
                s_text_col, s_bg = STAGE_COLORS.get(stage, ("#6b7280","#f3f4f6"))
                badge = ctk.CTkFrame(row, fg_color=s_bg, corner_radius=6)
                badge.pack(side="left", padx=(10,0))
                ctk.CTkLabel(badge, text=STAGE_LABELS.get(stage,"?"),
                             font=ctk.CTkFont(size=10, weight="bold"),
                             text_color=s_text_col).pack(padx=6, pady=2)
                # CRM button
                group_ids = [cl["id"] for cl in group]
                btn(row, "CRM →",
                    lambda i=cid, nl=group_ids: self._open_crm_from_territory(i, nl),
                    color=DARK, width=70).pack(side="right")

    def _back_from_territory(self):
        if hasattr(self, "territory_pane"):
            self.territory_pane.pack_forget()
        self.clients_pane.pack(fill="both", expand=True)
        self.refresh_clients()

    def _open_crm_from_territory(self, client_id, nav_list):
        if hasattr(self, "territory_pane"):
            self.territory_pane.pack_forget()
        self.open_crm_detail(client_id, nav_list=nav_list)

    def _prerender_pipeline(self):
        """Silently pre-render the pipeline in the background after app loads.
        So first click feels instant instead of building from scratch."""
        try:
            if not hasattr(self, "pipeline_pane"):
                self.pipeline_pane = ctk.CTkFrame(self.pages["clients"], fg_color="transparent")
            # Build it hidden — don't pack it
            self._pipeline_prerendered = False
            # Just warm the data — actual render happens on first click
            get_all_pipeline_stages()
        except: pass

    def _show_pipeline_view(self):
        self.clients_pane.pack_forget()
        if not hasattr(self, 'pipeline_pane'):
            self.pipeline_pane = ctk.CTkFrame(self.pages["clients"], fg_color="transparent")
        else:
            for w in self.pipeline_pane.winfo_children(): w.destroy()
        self.pipeline_pane.pack(fill="both", expand=True)

        # ── Header ────────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(self.pipeline_pane, fg_color="transparent")
        hdr.pack(fill="x", padx=24, pady=(20,12))
        label(hdr, "Sales Pipeline", size=22, weight="bold").pack(side="left")
        btn(hdr, "← All Clients", self.show_clients_list, color="#374151", width=120).pack(side="right")

        # ── Batch-load all data BEFORE touching the UI ────────────────────
        conn = get_db()
        all_clients = [dict(c) for c in conn.execute('SELECT * FROM clients ORDER BY name').fetchall()]
        conn.close()
        _sm = get_all_pipeline_stages()
        from collections import defaultdict as _dd
        stage_groups = _dd(list)
        for _pc in all_clients:
            stage_groups[_sm.get(_pc['id'], 'cold_lead')].append(_pc)

        # ── Use pack-based columns — no grid, no scrollframe-in-grid ─────
        # Each column is a plain Frame with fixed width packed side by side
        # inside a horizontal scrollable canvas. This renders all at once.
        import tkinter as _tk

        outer = ctk.CTkFrame(self.pipeline_pane, fg_color="transparent")
        outer.pack(fill="both", expand=True, padx=12, pady=(0,16))

        # Horizontal scroll canvas
        h_canvas = _tk.Canvas(outer, bg=LIGHT, highlightthickness=0)
        h_scroll = ctk.CTkScrollbar(outer, orientation="horizontal",
                                    command=h_canvas.xview)
        h_scroll.pack(side="bottom", fill="x")
        h_canvas.pack(side="left", fill="both", expand=True)
        h_canvas.configure(xscrollcommand=h_scroll.set)

        # Inner frame sits inside the canvas
        inner = ctk.CTkFrame(h_canvas, fg_color="transparent")
        h_canvas.create_window((0, 0), window=inner, anchor="nw")

        # Calculate column width reliably — winfo_width can return 1
        # before layout completes so we fall back to window width - sidebar
        MIN_COL_W = 220
        self.update_idletasks()
        raw_w = self.pipeline_pane.winfo_width()
        if raw_w < 100:  # not laid out yet — use main window width
            raw_w = self.winfo_width() - 200  # subtract sidebar width
        avail_w = max(raw_w - 40, MIN_COL_W * len(PIPELINE_STAGES))
        n_cols  = len(PIPELINE_STAGES)
        COL_W   = max(MIN_COL_W, (avail_w // n_cols) - 8)

        for col_idx, (stage_key, stage_label, text_col, bg_col) in enumerate(PIPELINE_STAGES):
            col = ctk.CTkFrame(inner, fg_color="transparent", width=COL_W)
            col.pack(side="left", anchor="n", padx=4, pady=2)
            # Do NOT pack_propagate(False) — let height grow with content

            # Column header
            hdr_f = ctk.CTkFrame(col, fg_color=bg_col, corner_radius=8)
            hdr_f.pack(fill="x", pady=(0,6))
            stage_clients = stage_groups.get(stage_key, [])
            count_txt = f"{stage_label}  ({len(stage_clients)})"
            ctk.CTkLabel(hdr_f, text=count_txt,
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=text_col).pack(pady=7, padx=8)

            # Cards — packed directly, no scrollframe needed
            body = ctk.CTkFrame(col, fg_color="transparent")
            body.pack(fill="x")

            if stage_clients:
                for c in stage_clients:
                    cid   = c['id']
                    cname = c.get('company') or c.get('name', '')
                    card  = ctk.CTkFrame(body, fg_color=WHITE,
                                         corner_radius=8,
                                         border_width=1, border_color=BORDER)
                    card.pack(fill="x", pady=3, padx=2)

                    label(card, cname, size=11, weight="bold",
                          wraplength=COL_W-24, justify="left",
                          anchor="w").pack(anchor="w", padx=8, pady=(6,2))

                    if c.get('name') and c['name'].lower() != cname.lower():
                        label(card, f"👤 {c['name']}", size=10, color=GRAY,
                              wraplength=COL_W-24).pack(anchor="w", padx=8)

                    if c.get('city'):
                        local = is_local_client(c['city'])
                        label(card,
                              f"📍 {c['city']}{' · Local' if local else ''}",
                              size=10,
                              color=GREEN if local else GRAY).pack(anchor="w", padx=8)



                    act = ctk.CTkFrame(card, fg_color="transparent")
                    act.pack(fill="x", padx=6, pady=(2,6))

                    btn(act, "CRM →",
                        lambda i=cid: (self.pipeline_pane.pack_forget(),
                                       self.crm_pane.pack(fill="both", expand=True),
                                       self.open_crm_detail(i)),
                        color=DARK, width=58).pack(side="left", padx=2)

                    cur_idx = STAGE_KEYS.index(stage_key)
                    # Back button — move to previous stage
                    if cur_idx > 0:
                        pk = STAGE_KEYS[cur_idx - 1]
                        def _back(i=cid, ps=pk):
                            if messagebox.askyesno("Move Back",
                                f"Move this client back to '{STAGE_LABELS[ps]}'?"):
                                set_client_pipeline_stage(i, ps)
                                self._show_pipeline_view()
                        btn(act, "← Back", _back,
                            color="#6b7280", width=70).pack(side="left", padx=2)
                    # Forward button — move to next stage
                    next_idx = cur_idx + 1
                    if next_idx < len(STAGE_KEYS):
                        nk = STAGE_KEYS[next_idx]
                        nl = STAGE_LABELS[nk]
                        def _adv(i=cid, ns=nk):
                            set_client_pipeline_stage(i, ns)
                            self._show_pipeline_view()
                        _short = nl[:8] + "…" if len(nl) > 8 else nl
                        btn(act, f"→ {_short}", _adv,
                            color=text_col, width=86).pack(side="left", padx=2)
            else:
                label(body, "None yet", size=11, color=GRAY).pack(pady=16)

        # Update scroll region after all columns are built
        # Update canvas scroll region
        inner.update_idletasks()
        h_canvas.configure(scrollregion=h_canvas.bbox("all") or (0,0,COL_W*n_cols+40,400))
        # Hide scrollbar if everything fits
        total_w = COL_W * n_cols + 40
        if total_w <= avail_w:
            h_scroll.pack_forget()

    def refresh_notes(self):
        for w in self.notes_scroll.winfo_children(): w.destroy()
        conn = get_db()
        notes = conn.execute('SELECT * FROM crm_notes WHERE client_id=? ORDER BY note_date DESC, created_at DESC', (self.current_client_id,)).fetchall()
        conn.close()
        type_colors = {"call":BLUE,"email":RED,"meeting":GREEN,"other":GRAY}
        type_icons = {"call":"📞","email":"📧","meeting":"🤝","other":"📝"}
        if notes:
            for n in notes:
                n = dict(n)
                card = ctk.CTkFrame(self.notes_scroll, fg_color=LIGHT, corner_radius=8)
                card.pack(fill="x", pady=3)
                meta = ctk.CTkFrame(card, fg_color="transparent"); meta.pack(fill="x", padx=10, pady=(6,2))
                nt = n.get('note_type') or 'other'
                icon = type_icons.get(nt,'📝')
                label(meta, f"{icon} {nt.title()}", size=11, weight="bold", color=type_colors.get(nt,GRAY)).pack(side="left")
                # show note_date if set, else fall back to created_at
                display_dt = n.get('note_date') or n.get('created_at','')
                try:
                    dt = datetime.strptime(display_dt, '%Y-%m-%d %H:%M')
                    dt_str = dt.strftime('%b %d, %Y %I:%M %p')
                except:
                    try:
                        dt = datetime.strptime(display_dt, '%Y-%m-%d %H:%M:%S')
                        dt_str = dt.strftime('%b %d, %Y %I:%M %p')
                    except: dt_str = display_dt
                label(meta, dt_str, size=10, color=GRAY).pack(side="left", padx=8)
                nid = n['id']
                btn(meta, "✕", lambda i=nid: self.delete_note(i), color=RED, width=28).pack(side="right")
                btn(meta, "✏", lambda i=nid, c=card: self._edit_note_inline(i, c), color="#374151", width=28).pack(side="right", padx=(0,2))
                note_lbl = label(card, n['note'], size=12, wraplength=380, justify="left", anchor="w")
                note_lbl.pack(anchor="w", padx=10, pady=(2,8))
                note_lbl._note_id = nid
        else:
            label(self.notes_scroll, "No notes yet. Log your first call!", color=GRAY).pack(pady=20)

    def _edit_note_inline(self, note_id, card):
        # Find the text label in this card and replace with editable textbox
        conn = get_db()
        row = conn.execute('SELECT * FROM crm_notes WHERE id=?', (note_id,)).fetchone()
        conn.close()
        if not row: return
        current_text = row['note']
        # Hide existing text label, show textbox
        children = card.winfo_children()
        for w in children:
            if isinstance(w, ctk.CTkLabel) and hasattr(w, '_note_id'):
                w.pack_forget()
                break
        edit_box = ctk.CTkTextbox(card, height=80, fg_color=WHITE, border_color=BORDER, text_color=DARK, border_width=1)
        edit_box.insert("1.0", current_text)
        edit_box.pack(fill="x", padx=10, pady=(0,4))
        save_row = ctk.CTkFrame(card, fg_color="transparent")
        save_row.pack(anchor="e", padx=10, pady=(0,6))
        def save_edit():
            new_text = edit_box.get("1.0","end").strip()
            if not new_text: messagebox.showwarning("Empty","Note cannot be empty."); return
            conn2 = get_db()
            conn2.execute('UPDATE crm_notes SET note=? WHERE id=?', (new_text, note_id))
            conn2.commit(); conn2.close()
            edit_box.destroy(); save_row.destroy()
            self.refresh_notes()
        def cancel_edit():
            edit_box.destroy(); save_row.destroy()
            self.refresh_notes()
        btn(save_row, "💾 Save", save_edit, color=GREEN, width=80).pack(side="left", padx=4)
        btn(save_row, "Cancel", cancel_edit, color=GRAY, width=70).pack(side="left")

    def add_note(self):
        note = self.note_text.get("1.0","end").strip()
        if not note: messagebox.showwarning("Empty Note","Please write a note first."); return
        nt_raw = self.note_type_combo.get()
        nt = "call" if "Call" in nt_raw else ("email" if "Email" in nt_raw else ("meeting" if "Meeting" in nt_raw else "other"))
        note_dt = self.note_dt_var.get() if hasattr(self, 'note_dt_var') else datetime.now().strftime('%Y-%m-%d %H:%M')
        conn = get_db()
        conn.execute('INSERT INTO crm_notes (client_id,note,note_type,note_date) VALUES (?,?,?,?)',
                     (self.current_client_id, note, nt, note_dt))
        conn.commit(); conn.close()
        self.note_text.delete("1.0","end")
        self.note_dt_var.set(datetime.now().strftime('%Y-%m-%d %H:%M'))
        self.refresh_notes()

    def delete_note(self, nid):
        if messagebox.askyesno("Delete Note","Delete this note?"):
            conn = get_db()
            conn.execute('DELETE FROM crm_notes WHERE id=?', (nid,))
            conn.commit(); conn.close()
            self.refresh_notes()

    def refresh_followups(self):
        # Safely clear all children from the scroll frame
        sf = self.fups_scroll
        for w in sf.winfo_children():
            w.destroy()
        conn = get_db()
        fups = conn.execute(
            'SELECT id, client_id, title, due_date, done FROM follow_ups '
            'WHERE client_id=? ORDER BY due_date',
            (self.current_client_id,)
        ).fetchall()
        conn.close()
        if fups:
            for f in fups:
                fid      = f[0]
                title    = f[2] or "(no title)"
                due_date = f[3] or ""
                done     = bool(f[4])
                card = ctk.CTkFrame(sf, fg_color="#f0fdf4" if done else LIGHT, corner_radius=8)
                card.pack(fill="x", pady=3, padx=2)
                # Header row: type badge + timestamp + action buttons
                # Parse type tag from title e.g. "[📅 Task] Call the client"
                import re as _re
                tag_match = _re.match(r'^\[(.+?)\]\s*(.*)', title)
                if tag_match:
                    fup_type_lbl = tag_match.group(1)
                    fup_body     = tag_match.group(2)
                else:
                    fup_type_lbl = "📅 Follow-up"
                    fup_body     = title

                meta = ctk.CTkFrame(card, fg_color="transparent")
                meta.pack(fill="x", padx=10, pady=(6,2))
                is_over = not done and due_date and due_date < today()
                date_col = RED if is_over else GRAY
                label(meta, fup_type_lbl, size=11, weight="bold",
                      color=GRAY if done else "#854d0e").pack(side="left")
                label(meta, fmt_date(due_date), size=10,
                      color=GRAY if done else date_col).pack(side="left", padx=8)
                btn(meta, "✕",
                    lambda i=fid: self.delete_followup(i),
                    color=RED, width=28).pack(side="right")
                btn(meta, "✏",
                    lambda i=fid, t=title, d=due_date: self._edit_followup_dialog(i, t, d),
                    color="#374151", width=28).pack(side="right", padx=(0,2))
                # Checkbox + body text (mirrors call notes card)
                body = ctk.CTkFrame(card, fg_color="transparent")
                body.pack(fill="x", padx=10, pady=(2,8))
                chk_var = ctk.IntVar(value=int(done))
                ctk.CTkCheckBox(
                    body, text="", variable=chk_var, width=24,
                    command=lambda i=fid: self.toggle_followup(i),
                    fg_color=GREEN, hover_color=GREEN
                ).pack(side="left", padx=(0,8))
                label(body, fup_body, size=12, wraplength=340, justify="left",
                      anchor="w", color=GRAY if done else DARK).pack(side="left", anchor="w")
        else:
            label(sf, "No follow-ups yet. Add one above!", color=GRAY).pack(pady=20)

    def _edit_followup_dialog(self, fid, current_title, current_due):
        dlg = ctk.CTkToplevel(self)
        dlg.title("Edit Follow-up")
        dlg.geometry("380x170")
        dlg.resizable(False, False)
        dlg.grab_set()
        dlg.configure(fg_color=WHITE)
        label(dlg, "Task description:", size=12).pack(anchor="w", padx=16, pady=(14,2))
        title_e = ctk.CTkEntry(dlg, fg_color=WHITE, border_color=BORDER, text_color=DARK)
        title_e.insert(0, current_title if current_title != "(no title)" else "")
        title_e.pack(fill="x", padx=16, pady=(0,8))
        dt_var = tk.StringVar(value=f"{current_due} 09:00" if current_due else datetime.now().strftime('%Y-%m-%d %H:%M'))
        dt_row = ctk.CTkFrame(dlg, fg_color="transparent")
        dt_row.pack(fill="x", padx=16, pady=(0,12))
        label(dt_row, "Date:", size=12).pack(side="left")
        dt_display = tk.Label(dt_row, textvariable=dt_var, font=("Segoe UI", 11), fg=DARK, bg=WHITE)
        dt_display.pack(side="left", padx=6)
        btn(dt_row, "📅", lambda: self._pick_datetime(dt_var), color="#374151", width=36).pack(side="left")
        def save():
            new_title = title_e.get().strip()
            if not new_title: messagebox.showwarning("Empty","Please enter a task."); return
            new_due = dt_var.get().split(" ")[0]
            conn = get_db()
            conn.execute('UPDATE follow_ups SET title=?, due_date=? WHERE id=?', (new_title, new_due, fid))
            conn.commit(); conn.close()
            dlg.destroy()
            self.refresh_followups(); self.refresh_dashboard()
        btn_row = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_row.pack(pady=4)
        btn(btn_row, "💾 Save", save, color=GREEN, width=100).pack(side="left", padx=6)
        btn(btn_row, "Cancel", dlg.destroy, color=GRAY, width=80).pack(side="left")

    def add_followup(self):
        if not hasattr(self, 'fup_text') or not hasattr(self, 'fup_dt_var'):
            messagebox.showerror("Error","Follow-up panel not ready."); return
        title = self.fup_text.get("1.0","end").strip()
        if not title:
            messagebox.showwarning("Empty","Please write a follow-up before saving."); return
        # Prepend type tag so it shows in the card header
        fup_type_raw = self.fup_type_combo.get() if hasattr(self,'fup_type_combo') else "📅 Task"
        due_raw  = self.fup_dt_var.get()
        due_date = due_raw.split(" ")[0] if due_raw else datetime.now().strftime('%Y-%m-%d')
        try:
            conn = get_db()
            conn.execute('INSERT INTO follow_ups (client_id,title,due_date) VALUES (?,?,?)',
                         (self.current_client_id, f"[{fup_type_raw}] {title}", due_date))
            conn.commit(); conn.close()
        except Exception as e:
            messagebox.showerror("DB Error", str(e)); return
        self.fup_text.delete("1.0","end")
        self.fup_dt_var.set(datetime.now().strftime('%Y-%m-%d %H:%M'))
        self.refresh_followups()
        self.refresh_dashboard()

    def toggle_followup(self, fid):
        conn = get_db()
        conn.execute('UPDATE follow_ups SET done = 1 - done WHERE id=?', (fid,))
        conn.commit(); conn.close()
        self.refresh_followups(); self.refresh_dashboard()

    def delete_followup(self, fid):
        conn = get_db()
        conn.execute('DELETE FROM follow_ups WHERE id=?', (fid,))
        conn.commit(); conn.close()
        self.refresh_followups(); self.refresh_dashboard()

    # ── CLIENT DIALOG ─────────────────────────────────────────────────────
    def open_client_dialog(self, client_id=None):
        conn = get_db()
        c = dict(conn.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone()) if client_id else {}
        conn.close()

        dlg = ctk.CTkToplevel(self)
        dlg.title("Edit Client" if client_id else "Add Client")
        dlg.geometry("520x660")
        dlg.grab_set()
        dlg.configure(fg_color=WHITE)
        self._set_icon(dlg)

        # ── Fixed footer — always visible, no scrolling needed ────────────
        footer = ctk.CTkFrame(dlg, fg_color=WHITE, border_width=1, border_color=BORDER)
        footer.pack(side="bottom", fill="x", padx=0, pady=0)
        save_status = label(footer, "", size=11, color=GREEN)
        save_status.pack(side="left", padx=16)

        # ── Warning banner (hidden by default, shown on duplicate) ────────
        warn_banner = ctk.CTkFrame(dlg, fg_color="#fffbeb",
                                   border_width=1, border_color=AMBER,
                                   corner_radius=0)
        # Not packed yet — only shown when needed

        # ── Scrollable body ───────────────────────────────────────────────
        sf = scrollframe(dlg)
        sf.pack(fill="both", expand=True, padx=20, pady=(12,0))

        fields = {}
        for lbl_text, key, placeholder in [
            ("Contact Name *", "name",     "Full name"),
            ("Company",        "company",  "Business or organisation name"),
            ("Address",        "address",  "1234 Street Name"),
            ("City",           "city",     "City"),
            ("Province / State","province","Province or state"),
            ("Postal Code / Zip","postal", "Postal or zip code"),
            ("Country",        "country",  "Country"),
            ("Email",          "email",    "Email address"),
            ("Phone",          "phone",    "Phone number"),
        ]:
            label(sf, lbl_text).pack(anchor="w", pady=(6,2))
            e = entry(sf, placeholder)
            e.pack(fill="x", pady=(0,2))
            if c.get(key): e.insert(0, c[key])
            fields[key] = e

        label(sf, "Payment Method").pack(anchor="w", pady=(6,2))
        pay_method = ctk.CTkComboBox(sf, values=["e-transfer","cheque","credit-card","cash","other"],
                                      fg_color=WHITE, border_color=BORDER, text_color=DARK)
        pay_method.set(c.get('payment_method','e-transfer'))
        pay_method.pack(fill="x", pady=(0,2))

        label(sf, "Card Last 4 Digits (reference only)").pack(anchor="w", pady=(6,2))
        last4_e = entry(sf, "Last 4 digits")
        last4_e.pack(fill="x", pady=(0,2))
        if c.get('payment_last4'): last4_e.insert(0, c['payment_last4'])
        # Restrict to digits only, max 4 characters
        def _validate_last4(P):
            return P == "" or (P.isdigit() and len(P) <= 4)
        _vcmd = sf.register(_validate_last4)
        last4_e.configure(validate="key",
                          validatecommand=(_vcmd, "%P"))

        label(sf, "Follow-up Date").pack(anchor="w", pady=(6,2))
        fup_e = entry(sf, "YYYY-MM-DD")
        fup_e.pack(fill="x", pady=(0,2))
        if c.get('follow_up_date'): fup_e.insert(0, c['follow_up_date'])

        separator(sf).pack(fill="x", pady=(10,6))
        label(sf, "Ship-To Address (optional — for invoices with alternate delivery)", size=12, weight="bold").pack(anchor="w", pady=(0,4))
        label(sf, "Street Address").pack(anchor="w", pady=(4,2))
        e_ship_addr = entry(sf, "1234 Street Name")
        e_ship_addr.pack(fill="x", pady=(0,2))
        if c.get('ship_address'): e_ship_addr.insert(0, c['ship_address'])
        fields['ship_address'] = e_ship_addr
        ship_row = ctk.CTkFrame(sf, fg_color="transparent")
        ship_row.pack(fill="x", pady=(4,2))
        for col_lbl, key, ph, w in [
            ("City",            "ship_city",     "City",             160),
            ("Province / State","ship_province", "Province or state", 100),
            ("Postal / Zip",    "ship_postal",   "Postal or zip",    110),
        ]:
            col = ctk.CTkFrame(ship_row, fg_color="transparent")
            col.pack(side="left", padx=(0,8))
            label(col, col_lbl, size=12).pack(anchor="w")
            e = entry(col, ph, width=w)
            e.pack()
            if c.get(key): e.insert(0, c[key])
            fields[key] = e

        star_var = ctk.IntVar(value=c.get('starred',0))
        ctk.CTkCheckBox(sf, text="⭐ Priority / Starred Client", variable=star_var,
                        fg_color=AMBER, hover_color=AMBER, text_color=DARK).pack(anchor="w", pady=(10,8))

        def _do_save(data):
            """Actually write the client to the DB."""
            conn = get_db()
            if client_id:
                conn.execute('''UPDATE clients SET name=?,company=?,address=?,city=?,province=?,postal=?,
                    country=?,email=?,phone=?,payment_method=?,payment_last4=?,follow_up_date=?,starred=?,
                    ship_address=?,ship_city=?,ship_province=?,ship_postal=? WHERE id=?''',
                    (data['name'],data['company'],data['address'],data['city'],data['province'],
                     data['postal'],data['country'] or 'Canada',data['email'],data['phone'],
                     data['payment_method'],data['payment_last4'],data['follow_up_date'],data['starred'],
                     data['ship_address'],data['ship_city'],data['ship_province'],data['ship_postal'],client_id))
            else:
                conn.execute('''INSERT INTO clients (name,company,address,city,province,postal,country,email,phone,
                    payment_method,payment_last4,follow_up_date,starred,ship_address,ship_city,ship_province,ship_postal)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (data['name'],data['company'],data['address'],data['city'],data['province'],
                     data['postal'],data['country'] or 'Canada',data['email'],data['phone'],
                     data['payment_method'],data['payment_last4'],data['follow_up_date'],data['starred'],
                     data['ship_address'],data['ship_city'],data['ship_province'],data['ship_postal']))
            conn.commit(); conn.close()
            dlg.destroy()
            self.refresh_clients(); self.refresh_dashboard()

        def save():
            name = fields['name'].get().strip()
            if not name: messagebox.showwarning("Required","Contact name is required."); return
            data = {k: e.get().strip() or None for k,e in fields.items()}
            data['payment_method'] = pay_method.get()
            data['payment_last4'] = last4_e.get().strip() or None
            data['follow_up_date'] = fup_e.get().strip() or None
            data['starred'] = star_var.get()
            for k in ['ship_address','ship_city','ship_province','ship_postal']:
                data[k] = fields.get(k, type('',(),{'get':lambda self,_=None:'','strip':lambda self:''})()).get().strip() or None

            # ── Duplicate detection (only for new clients, not edits) ──────
            if not client_id:
                conn = get_db()
                dupes = []
                # Check by company name (only if non-empty)
                company_val = (data.get('company') or '').strip()
                if company_val:
                    hit = conn.execute(
                        "SELECT id, name, company FROM clients WHERE LOWER(TRIM(company))=LOWER(TRIM(?))",
                        (company_val,)
                    ).fetchone()
                    if hit:
                        dupes.append(f'Company: "{hit["company"]}"')
                # Check by email (only if non-empty)
                email_val = (data.get('email') or '').strip()
                if email_val:
                    hit = conn.execute(
                        "SELECT id, name, company, email FROM clients WHERE LOWER(TRIM(email))=LOWER(TRIM(?)) AND TRIM(email) != ''",
                        (email_val,)
                    ).fetchone()
                    if hit:
                        dupes.append(f"Email: {hit['email']} — already belongs to {hit['company'] or hit['name']}")
                # Check by phone (only if non-empty)
                phone_val = (data.get('phone') or '').strip()
                if phone_val:
                    clean_new = ''.join(filter(str.isdigit, phone_val))
                    if clean_new:
                        all_clients = conn.execute("SELECT id, name, company, phone FROM clients WHERE phone IS NOT NULL AND TRIM(phone) != ''").fetchall()
                        for row in all_clients:
                            clean_existing = ''.join(filter(str.isdigit, row['phone'] or ''))
                            if clean_existing and clean_new == clean_existing:
                                dupes.append(f"Phone: {row['phone']} — already belongs to {row['company'] or row['name']}")
                                break
                conn.close()

                if dupes:
                    # Show warning banner above the footer
                    for w in warn_banner.winfo_children(): w.destroy()

                    label(warn_banner, "⚠  Duplicate detected:",
                          size=11, weight="bold",
                          color="#b45309").pack(anchor="w", padx=12, pady=(8,2))
                    for d in dupes:
                        label(warn_banner, f"  • {d}",
                              size=10, color="#92400e").pack(anchor="w", padx=16)

                    btn_row = ctk.CTkFrame(warn_banner, fg_color="transparent")
                    btn_row.pack(fill="x", padx=12, pady=(6,8))
                    label(btn_row, "Add anyway?", size=11,
                          color=DARK).pack(side="left", padx=(0,8))

                    def _save_anyway():
                        warn_banner.pack_forget()
                        _do_save(data)

                    def _cancel_dupe():
                        warn_banner.pack_forget()

                    btn(btn_row, "Yes, add anyway", _save_anyway,
                        color=RED, width=140).pack(side="left", padx=(0,6))
                    btn(btn_row, "No, go back", _cancel_dupe,
                        color="#374151", width=110).pack(side="left")

                    # Pack banner above footer
                    warn_banner.pack(side="bottom", fill="x", before=footer)
                    return  # wait for user choice

            _do_save(data)

        # Save button lives in the fixed footer
        btn(footer, "💾  Save Client", save, color=RED, width=160).pack(side="right", padx=12, pady=10)

    def delete_client(self, client_id):
        if messagebox.askyesno("Delete Client","Delete this client and all their notes and follow-ups?"):
            conn = get_db()
            conn.execute('DELETE FROM crm_notes WHERE client_id=?', (client_id,))
            conn.execute('DELETE FROM follow_ups WHERE client_id=?', (client_id,))
            conn.execute('DELETE FROM clients WHERE id=?', (client_id,))
            conn.commit(); conn.close()
            self.refresh_clients(); self.refresh_dashboard()


    # ── FULFILMENT TRACKER ────────────────────────────────────────────────────
    def _build_fulfilment(self):
        p = self.pages["fulfilment"]
        hdr = ctk.CTkFrame(p, fg_color="transparent")
        hdr.pack(fill="x", padx=24, pady=(20,0))
        label(hdr, "Fulfilment Tracker", size=22, weight="bold").pack(side="left")
        btn(hdr, "+ New Fulfilment", self._open_fulfilment_dialog, color=RED, width=150).pack(side="right")
        btn(hdr, "⚙ Carriers", self._open_carriers_dialog, color="#374151", width=110).pack(side="right", padx=(0,8))

        # Filter bar
        fbar = ctk.CTkFrame(p, fg_color="transparent")
        fbar.pack(fill="x", padx=24, pady=(10,0))
        self.ff_filter = ctk.CTkComboBox(fbar,
            values=["All Orders","In Progress","Delivered","Overdue"],
            width=140, fg_color=WHITE, border_color=BORDER, text_color=DARK,
            command=lambda _: self.refresh_fulfilment())
        self.ff_filter.set("All Orders")
        self.ff_filter.pack(side="left")

        # Stats bar
        self.ff_stats = ctk.CTkFrame(p, fg_color="transparent")
        self.ff_stats.pack(fill="x", padx=24, pady=(10,0))

        # List
        self.ff_list = scrollframe(p)
        self.ff_list.pack(fill="both", expand=True, padx=24, pady=(8,16))

    STAGES = [
        ("ordered",   "Order Placed", "#16A34A"),
        ("packed",    "Packing",      "#3b82f6"),
        ("shipped",   "Shipped",      "#7c3aed"),
        ("delivered", "Delivered",    "#16A34A"),
    ]
    STAGE_KEYS_FF  = ["ordered","packed","shipped","delivered"]
    OVERDUE_DAYS   = {"ordered": None, "packed": 3, "shipped": 5, "delivered": None}
    CARRIER_URLS   = {}  # populated from DB

    def _get_carriers(self):
        conn = get_db()
        rows = conn.execute("SELECT name, tracking_url FROM carriers ORDER BY name").fetchall()
        conn.close()
        return {r["name"]: r["tracking_url"] for r in rows}

    def _days_since(self, dt_str):
        if not dt_str: return None
        try:
            from datetime import datetime as _dt
            d = _dt.strptime(dt_str[:10], "%Y-%m-%d")
            return (_dt.now() - d).days
        except: return None

    def _is_overdue(self, ff):
        stage = ff.get("stage","ordered")
        threshold = self.OVERDUE_DAYS.get(stage)
        if threshold is None: return False
        field = {"packed":"ordered_at","shipped":"packed_at"}.get(stage)
        if not field: return False
        days = self._days_since(ff.get(field,""))
        return days is not None and days > threshold

    def refresh_fulfilment(self):
        filt = self.ff_filter.get() if hasattr(self,"ff_filter") else "All Orders"
        conn = get_db()
        rows = [dict(r) for r in conn.execute(
            """SELECT f.*, i.invoice_number, c.company, c.name as cname
               FROM fulfilment f
               LEFT JOIN invoices i ON f.invoice_id=i.id
               LEFT JOIN clients  c ON f.client_id=c.id
               ORDER BY f.id DESC"""
        ).fetchall()]
        conn.close()

        # Apply filter
        if filt == "In Progress":
            rows = [r for r in rows if r["stage"] != "delivered"]
        elif filt == "Delivered":
            rows = [r for r in rows if r["stage"] == "delivered"]
        elif filt == "Overdue":
            rows = [r for r in rows if self._is_overdue(r)]

        # Stats
        for w in self.ff_stats.winfo_children(): w.destroy()
        all_rows_conn = get_db()
        all_ff = [dict(r) for r in all_rows_conn.execute("SELECT * FROM fulfilment").fetchall()]
        all_rows_conn.close()
        total     = len(all_ff)
        delivered = sum(1 for r in all_ff if r["stage"]=="delivered")
        in_transit= sum(1 for r in all_ff if r["stage"]=="shipped")
        overdue   = sum(1 for r in all_ff if self._is_overdue(r))
        # Avg fulfilment days for delivered orders
        times = []
        for r in all_ff:
            if r["stage"]=="delivered" and r.get("ordered_at") and r.get("delivered_at"):
                d = self._days_since(r["ordered_at"])
                if d: times.append(d)
        avg = f"{sum(times)/len(times):.1f} days" if times else "—"
        for lbl_t, val_t, col in [
            ("Total Orders", str(total), DARK),
            ("In Transit",   str(in_transit), BLUE),
            ("Delivered",    str(delivered), GREEN),
            ("Overdue",      str(overdue), RED),
            ("Avg Fulfilment", avg, "#7c3aed"),
        ]:
            card = ctk.CTkFrame(self.ff_stats, fg_color=WHITE, corner_radius=8,
                                border_width=1, border_color=BORDER)
            card.pack(side="left", expand=True, fill="x", padx=4)
            label(card, lbl_t, size=10, color=GRAY).pack(pady=(8,2), padx=10)
            label(card, val_t, size=18, weight="bold", color=col).pack(pady=(0,8), padx=10)

        # Render cards
        for w in self.ff_list.winfo_children(): w.destroy()
        if not rows:
            label(self.ff_list, "No fulfilment records yet — create one with + New Fulfilment",
                  color=GRAY).pack(pady=40)
            return

        carriers = self._get_carriers()
        for ff in rows:
            overdue = self._is_overdue(ff)
            bg  = "#fffbeb" if overdue else WHITE
            bdr = AMBER    if overdue else BORDER
            card = ctk.CTkFrame(self.ff_list, fg_color=bg, corner_radius=10,
                                border_width=1, border_color=bdr)
            card.pack(fill="x", pady=5)
            inner = ctk.CTkFrame(card, fg_color="transparent")
            inner.pack(fill="x", padx=14, pady=(10,4))

            # ── Colour-coded rectangular stage tracker ─────────────────────
            # 25ABCs brand: dark navy / amber / red / green
            # Each entry: (text_colour, background_colour, active_border)
            _FF_COLS = {
                "ordered":   ("#ffffff", "#1a1a2e", "#1a1a2e"),
                "packed":    ("#92400e", "#fef3c7", "#d97706"),
                "shipped":   ("#991b1b", "#fee2e2", "#E63B2E"),
                "delivered": ("#166534", "#dcfce7", "#16A34A"),
            }
            stage_idx = self.STAGE_KEYS_FF.index(ff["stage"]) if ff["stage"] in self.STAGE_KEYS_FF else 0
            bar_frame = ctk.CTkFrame(inner, fg_color="transparent")
            bar_frame.pack(fill="x", pady=(0,8))
            import tkinter as _tk2
            for si, (sk, sl, sc) in enumerate(self.STAGES):
                done   = si <= stage_idx
                active = si == stage_idx
                txt_col, bg_col, bdr_col = _FF_COLS.get(sk, ("#374151","#f3f4f6","#e5e7eb"))
                if not done:
                    bg_col  = "#f3f4f6"
                    txt_col = "#9ca3af"
                    bdr_col = "#e5e7eb"

                # Outer container to hold the segment
                seg_wrap = ctk.CTkFrame(bar_frame, fg_color="transparent")
                seg_wrap.pack(side="left", expand=True, fill="x", padx=2)

                if active:
                    # Active stage — hatched canvas for clear visual progress
                    seg_canvas = _tk2.Canvas(seg_wrap, height=34,
                                            bg=bg_col, highlightthickness=1,
                                            highlightbackground=bdr_col,
                                            relief="flat")
                    seg_canvas.pack(fill="x")
                    # Draw diagonal hatch lines after widget is mapped
                    def _draw_hatch(c=seg_canvas, bc=bg_col, lc=bdr_col, t=txt_col, label_txt=sl):
                        c.update_idletasks()
                        w = c.winfo_width()
                        h = c.winfo_height()
                        if w < 2: w = 100
                        # Fill background
                        c.create_rectangle(0, 0, w, h, fill=bc, outline="")
                        # Diagonal hatch lines (45 degrees, every 6px)
                        spacing = 6
                        for x in range(-h, w + h, spacing):
                            c.create_line(x, 0, x + h, h,
                                         fill=lc, width=1)
                        # Label on top
                        c.create_text(w//2, h//2, text=label_txt,
                                     font=("Segoe UI", 10, "bold"),
                                     fill=t, anchor="center")
                    seg_canvas.bind("<Map>", lambda e, fn=_draw_hatch: fn())
                    seg_canvas.after(50, _draw_hatch)
                else:
                    # Non-active — plain coloured rectangle
                    seg = ctk.CTkFrame(seg_wrap, fg_color=bg_col,
                                       corner_radius=6,
                                       border_width=1,
                                       border_color=bdr_col)
                    seg.pack(fill="x")
                    ctk.CTkLabel(seg, text=sl,
                                 font=ctk.CTkFont(size=10),
                                 text_color=txt_col).pack(pady=6, padx=4)

            # ── Invoice + client ──────────────────────────────────────────
            inv_num = ff.get("invoice_number","—")
            client  = ff.get("company") or ff.get("cname") or "—"
            info_row = ctk.CTkFrame(inner, fg_color="transparent")
            info_row.pack(fill="x", pady=(2,2))
            label(info_row, f"{inv_num}  ·  {client}", size=13, weight="bold").pack(side="left")
            if overdue:
                label(info_row, "⚠ Overdue", size=10, color="#b45309", weight="bold").pack(side="left", padx=(12,0))

            # ── Tracking row ──────────────────────────────────────────────
            trk_row = ctk.CTkFrame(inner, fg_color="transparent")
            trk_row.pack(fill="x", pady=(0,4))
            carrier = ff.get("carrier","")
            tracking = ff.get("tracking_number","")
            days_in_stage = self._days_since(
                ff.get({"ordered":"ordered_at","packed":"ordered_at",
                        "shipped":"shipped_at","delivered":"shipped_at"}.get(ff["stage"],""))
            )
            stage_txt = f"{ff['stage'].title()}"
            if days_in_stage is not None:
                stage_txt += f"  ·  {days_in_stage}d in this stage"
            label(trk_row, f"🚚 {carrier}  {stage_txt}", size=10, color=GRAY).pack(side="left")
            if tracking and carrier in carriers:
                url = carriers[carrier].replace("{tracking}", tracking)
                btn(trk_row, "🔗 Track", lambda u=url: __import__("webbrowser").open(u),
                    color="#374151", width=70).pack(side="left", padx=(10,0))

            # ── Notes ─────────────────────────────────────────────────────
            if ff.get("notes"):
                label(inner, ff["notes"], size=10, color=GRAY).pack(anchor="w")

            # ── Action buttons ────────────────────────────────────────────
            act_row = ctk.CTkFrame(card, fg_color="transparent")
            act_row.pack(fill="x", padx=14, pady=(0,8))
            fid = ff["id"]
            cur_idx = self.STAGE_KEYS_FF.index(ff["stage"]) if ff["stage"] in self.STAGE_KEYS_FF else 0
            if cur_idx < len(self.STAGE_KEYS_FF)-1:
                nk = self.STAGE_KEYS_FF[cur_idx+1]
                nl = self.STAGES[cur_idx+1][1]
                btn(act_row, f"→ Mark as {nl}",
                    lambda i=fid, s=nk: self._advance_fulfilment(i, s),
                    color=DARK, width=140).pack(side="left", padx=(0,6))
            btn(act_row, "✏ Edit",
                lambda i=fid: self._open_fulfilment_dialog(i),
                color="#374151", width=70).pack(side="left", padx=(0,6))
            btn(act_row, "✕",
                lambda i=fid: self._delete_fulfilment(i),
                color=RED, width=36).pack(side="left")

    def _advance_fulfilment(self, fid, new_stage):
        field_map = {
            "packed":    "packed_at",
            "shipped":   "shipped_at",
            "delivered": "delivered_at",
        }
        field = field_map.get(new_stage)
        conn = get_db()
        if field:
            conn.execute(f"UPDATE fulfilment SET stage=?, {field}=? WHERE id=?",
                         (new_stage, today(), fid))
        else:
            conn.execute("UPDATE fulfilment SET stage=? WHERE id=?", (new_stage, fid))
        conn.commit(); conn.close()
        self.refresh_fulfilment()

    def _delete_fulfilment(self, fid):
        if messagebox.askyesno("Delete", "Delete this fulfilment record?"):
            conn = get_db()
            conn.execute("DELETE FROM fulfilment WHERE id=?", (fid,))
            conn.commit(); conn.close()
            self.refresh_fulfilment()

    def _open_fulfilment_dialog(self, fid=None):
        conn = get_db()
        ff = dict(conn.execute("SELECT * FROM fulfilment WHERE id=?", (fid,)).fetchone()) if fid else {}
        invoices = conn.execute(
            "SELECT i.id, i.invoice_number, c.company, c.name as cname FROM invoices i "
            "LEFT JOIN clients c ON i.client_id=c.id ORDER BY i.id DESC"
        ).fetchall()
        carriers = [r["name"] for r in conn.execute("SELECT name FROM carriers ORDER BY name").fetchall()]
        conn.close()

        dlg = ctk.CTkToplevel(self)
        dlg.title("Edit Fulfilment" if fid else "New Fulfilment")
        dlg.geometry("460x520")
        dlg.grab_set()
        dlg.configure(fg_color=WHITE)

        footer = ctk.CTkFrame(dlg, fg_color=WHITE, border_width=1, border_color=BORDER)
        footer.pack(side="bottom", fill="x")
        sf = scrollframe(dlg)
        sf.pack(fill="both", expand=True, padx=20, pady=12)

        # Invoice picker
        label(sf, "Invoice").pack(anchor="w", pady=(4,2))
        inv_opts = ["— No Invoice —"] + [
            f"{r['invoice_number']} · {r['company'] or r['cname'] or ''}" for r in invoices
        ]
        inv_ids = [None] + [r["id"] for r in invoices]
        inv_combo = ctk.CTkComboBox(sf, values=inv_opts, fg_color=WHITE,
                                    border_color=BORDER, text_color=DARK)
        inv_combo.pack(fill="x", pady=(0,6))
        if ff.get("invoice_id"):
            for idx, iid in enumerate(inv_ids):
                if iid == ff["invoice_id"]:
                    inv_combo.set(inv_opts[idx]); break
        else:
            inv_combo.set(inv_opts[0])

        # Carrier + tracking
        label(sf, "Carrier").pack(anchor="w", pady=(4,2))
        carrier_combo = ctk.CTkComboBox(sf, values=carriers, fg_color=WHITE,
                                        border_color=BORDER, text_color=DARK)
        carrier_combo.set(ff.get("carrier", carriers[0] if carriers else "Canada Post"))
        carrier_combo.pack(fill="x", pady=(0,6))

        label(sf, "Tracking Number (optional)").pack(anchor="w", pady=(4,2))
        trk_e = entry(sf, "e.g. 1234567890")
        trk_e.pack(fill="x", pady=(0,6))
        if ff.get("tracking_number"): trk_e.insert(0, ff["tracking_number"])

        # Stage
        label(sf, "Current Stage").pack(anchor="w", pady=(4,2))
        stage_combo = ctk.CTkComboBox(sf,
            values=[s[1] for s in self.STAGES],
            fg_color=WHITE, border_color=BORDER, text_color=DARK)
        cur_stage = ff.get("stage","ordered")
        stage_combo.set(next((s[1] for s in self.STAGES if s[0]==cur_stage), "Order Placed"))
        stage_combo.pack(fill="x", pady=(0,6))

        # Notes
        label(sf, "Notes (optional)").pack(anchor="w", pady=(4,2))
        notes_box = ctk.CTkTextbox(sf, height=70, fg_color=WHITE,
                                   border_color=BORDER, text_color=DARK, border_width=1)
        notes_box.pack(fill="x", pady=(0,6))
        if ff.get("notes"): notes_box.insert("1.0", ff["notes"])

        def save():
            sel_stage = next((s[0] for s in self.STAGES if s[1]==stage_combo.get()), "ordered")
            inv_idx = inv_opts.index(inv_combo.get())
            sel_inv_id = inv_ids[inv_idx]
            # Derive client_id from invoice
            sel_client_id = None
            if sel_inv_id:
                c2 = get_db()
                inv_row = c2.execute("SELECT client_id FROM invoices WHERE id=?", (sel_inv_id,)).fetchone()
                c2.close()
                if inv_row: sel_client_id = inv_row["client_id"]
            # Auto-set timestamps for stages
            now = today()
            conn2 = get_db()
            if fid:
                conn2.execute(
                    "UPDATE fulfilment SET invoice_id=?,client_id=?,carrier=?,tracking_number=?,"
                    "stage=?,notes=? WHERE id=?",
                    (sel_inv_id, sel_client_id, carrier_combo.get(),
                     trk_e.get().strip() or None,
                     sel_stage, notes_box.get("1.0","end").strip() or None, fid)
                )
            else:
                conn2.execute(
                    "INSERT INTO fulfilment (invoice_id,client_id,carrier,tracking_number,"
                    "stage,ordered_at,packed_at,shipped_at,delivered_at,notes) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (sel_inv_id, sel_client_id, carrier_combo.get(),
                     trk_e.get().strip() or None, sel_stage,
                     now,
                     now if sel_stage in ("packed","shipped","delivered") else None,
                     now if sel_stage in ("shipped","delivered") else None,
                     now if sel_stage == "delivered" else None,
                     notes_box.get("1.0","end").strip() or None)
                )
            conn2.commit(); conn2.close()
            dlg.destroy()
            self.refresh_fulfilment()

        btn(footer, "💾 Save", save, color=RED, width=140).pack(side="right", padx=12, pady=10)
        btn(footer, "Cancel", dlg.destroy, color=GRAY, width=90).pack(side="right", pady=10)

    def _open_carriers_dialog(self):
        """Manage carriers — add/remove custom carriers."""
        dlg = ctk.CTkToplevel(self)
        dlg.title("Manage Carriers")
        dlg.geometry("480x480")
        dlg.grab_set()
        dlg.configure(fg_color=WHITE)

        label_hdr = ctk.CTkFrame(dlg, fg_color="transparent")
        label_hdr.pack(fill="x", padx=20, pady=(16,8))
        label(label_hdr, "Carriers", size=16, weight="bold").pack(side="left")

        sf = scrollframe(dlg)
        sf.pack(fill="both", expand=True, padx=20, pady=(0,8))

        def refresh_carrier_list():
            for w in sf.winfo_children(): w.destroy()
            conn = get_db()
            carriers = conn.execute("SELECT * FROM carriers ORDER BY name").fetchall()
            conn.close()
            for car in carriers:
                row = ctk.CTkFrame(sf, fg_color=LIGHT, corner_radius=6)
                row.pack(fill="x", pady=2)
                inner = ctk.CTkFrame(row, fg_color="transparent")
                inner.pack(fill="x", padx=10, pady=6)
                label(inner, car["name"], size=12, weight="bold").pack(side="left")
                label(inner, car["tracking_url"][:40]+"…" if len(car["tracking_url"])>40
                      else car["tracking_url"], size=9, color=GRAY).pack(side="left", padx=8)
                def _del(cid=car["id"]):
                    conn2 = get_db()
                    conn2.execute("DELETE FROM carriers WHERE id=?", (cid,))
                    conn2.commit(); conn2.close()
                    refresh_carrier_list()
                btn(inner, "✕", _del, color=RED, width=28).pack(side="right")

        refresh_carrier_list()

        # Add new carrier
        separator(dlg).pack(fill="x", padx=20, pady=4)
        add_frame = ctk.CTkFrame(dlg, fg_color="transparent")
        add_frame.pack(fill="x", padx=20, pady=(0,12))
        label(add_frame, "Add Carrier", size=13, weight="bold").pack(anchor="w", pady=(0,6))
        name_e = entry(add_frame, "Carrier name (e.g. USPS)")
        name_e.pack(fill="x", pady=(0,4))
        url_e = entry(add_frame, "Tracking URL with {tracking} placeholder")
        url_e.pack(fill="x", pady=(0,6))
        label(add_frame, "e.g. https://tools.usps.com/go/TrackConfirmAction?tLabels={tracking}",
              size=9, color=GRAY).pack(anchor="w")

        def add_carrier():
            name = name_e.get().strip()
            url  = url_e.get().strip()
            if not name or not url:
                messagebox.showwarning("Required", "Name and URL are both required."); return
            if "{tracking}" not in url:
                messagebox.showwarning("Invalid URL", "URL must contain {tracking} placeholder."); return
            conn = get_db()
            try:
                conn.execute("INSERT INTO carriers (name, tracking_url) VALUES (?,?)", (name, url))
                conn.commit()
            except:
                messagebox.showwarning("Duplicate", f"{name} already exists.")
            conn.close()
            name_e.delete(0,"end"); url_e.delete(0,"end")
            refresh_carrier_list()

        btn(add_frame, "+ Add Carrier", add_carrier, color=RED, width=130).pack(anchor="w", pady=(8,0))

    # ── SETTINGS ─────────────────────────────────────────────────────────
    def _build_settings(self):
        p = self.pages["settings"]
        header = ctk.CTkFrame(p, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(20,12))
        label(header, "Business Settings", size=22, weight="bold").pack(side="left")

        sf = scrollframe(p)
        sf.pack(fill="both", expand=True, padx=24, pady=(0,16))

        # Info banner
        banner = ctk.CTkFrame(sf, fg_color="#eff6ff", corner_radius=10, border_width=1, border_color="#bfdbfe")
        banner.pack(fill="x", pady=(0,16))
        label(banner, "ℹ  These details appear on every invoice PDF you generate.", size=12, color=BLUE).pack(padx=16, pady=10)

        self.settings_fields = {}
        field_defs = [
            ("biz_name",     "Business Name *",          "e.g. Your Business Name"),
            ("biz_address",  "Street Address",           "e.g. 1234 Street Name"),
            ("biz_city",     "City, Province, Postal",   "e.g. Your City, Province/State Postal/Zip"),
            ("biz_phone",    "Phone Number",             "e.g. 123-456-7890"),
            ("biz_email",    "Email Address *",          "e.g. hello@yourbusiness.com"),
            ("biz_website",  "Website",                  "e.g. www.yourbusiness.com"),
            ("tagline",      "Tagline (optional)",       "e.g. Where Education Meets Creativity"),
        ]
        # Logo upload
        separator(sf).pack(fill="x", pady=12)
        label(sf, "Business Logo (PNG/JPG — shown on invoice PDF)", size=13, weight="bold").pack(anchor="w", pady=(0,4))
        logo_row = ctk.CTkFrame(sf, fg_color="transparent")
        logo_row.pack(fill="x", pady=(0,4))
        self._logo_path_var = tk.StringVar(value=get_settings().get("logo_path",""))
        logo_name_lbl = ctk.CTkLabel(logo_row, textvariable=self._logo_path_var,
                                     font=ctk.CTkFont(size=11), text_color=GRAY, wraplength=280, anchor="w")
        logo_name_lbl.pack(side="left", padx=(0,8), fill="x", expand=True)
        def pick_logo():
            path = filedialog.askopenfilename(
                title="Select logo image",
                filetypes=[("Image files","*.png *.jpg *.jpeg *.gif *.bmp"),("All files","*.*")]
            )
            if path:
                self._logo_path_var.set(path)
                save_setting("logo_path", path)
        def clear_logo():
            self._logo_path_var.set("")
            save_setting("logo_path", "")
        btn(logo_row, "📂 Browse", pick_logo, color=DARK, width=110).pack(side="left", padx=(0,4))
        btn(logo_row, "✕ Clear", clear_logo, color=RED, width=80).pack(side="left")
        label(sf, "Recommended: PNG with transparent background, max 400×200 px", size=10, color=GRAY).pack(anchor="w")
        separator(sf).pack(fill="x", pady=12)

        for key, lbl_text, placeholder in field_defs:
            label(sf, lbl_text).pack(anchor="w", pady=(8,2))
            e = entry(sf, placeholder)
            e.pack(fill="x", pady=(0,2))
            self.settings_fields[key] = e

        separator(sf).pack(fill="x", pady=16)
        label(sf, "Invoice Settings", size=14, weight="bold").pack(anchor="w", pady=(0,8))

        label(sf, "E-Transfer Email (shown on invoice — overrides business email if set)",
              size=12).pack(anchor="w", pady=(4,2))
        etransfer_entry = entry(sf, "e.g. payments@yourbusiness.com or personal@email.com")
        etransfer_entry.pack(fill="x", pady=(0,8))
        self.settings_fields["etransfer_email"] = etransfer_entry

        label(sf, "Payment Instructions (shown on PDF)").pack(anchor="w", pady=(4,2))
        pay_entry = ctk.CTkTextbox(sf, height=60, fg_color=WHITE, border_color=BORDER, text_color=DARK, border_width=1)
        pay_entry.pack(fill="x", pady=(0,8))
        self.settings_fields["payment_instructions_box"] = pay_entry

        r = ctk.CTkFrame(sf, fg_color="transparent"); r.pack(fill="x", pady=4)
        label(r, "Invoice Number Prefix").pack(side="left", padx=(0,8))
        prefix_entry = entry(r, "INV", width=100)
        prefix_entry.pack(side="left")
        self.settings_fields["invoice_prefix"] = prefix_entry
        label(r, "  Currency Symbol").pack(side="left", padx=(16,8))
        currency_combo = ctk.CTkComboBox(r, values=["CA$","$","£","€","AU$","NZ$"], width=90,
                                          fg_color=WHITE, border_color=BORDER, text_color=DARK)
        currency_combo.set("CA$")
        self.settings_fields["currency_combo"] = currency_combo
        currency_combo.pack(side="left")

        separator(sf).pack(fill="x", pady=16)
        btn(sf, "💾  Save Settings", self.save_settings, color=RED, width=180).pack(pady=(0,8))
        self.settings_status = label(sf, "", size=12, color=GREEN)
        self.settings_status.pack()

    def refresh_settings(self):
        s = get_settings()
        simple_keys = ["biz_name","biz_address","biz_city","biz_phone","biz_email","biz_website","tagline","invoice_prefix","etransfer_email"]
        for key in simple_keys:
            if key in self.settings_fields:
                self.settings_fields[key].delete(0, "end")
                self.settings_fields[key].insert(0, s.get(key, ""))
        pay_box = self.settings_fields.get("payment_instructions_box")
        if pay_box:
            pay_box.delete("1.0", "end")
            pay_box.insert("1.0", s.get("payment_instructions", "E-Transfer"))
        currency_combo = self.settings_fields.get("currency_combo")
        if currency_combo:
            currency_combo.set(s.get("currency", "CA$"))

    def save_settings(self):
        simple_keys = ["biz_name","biz_address","biz_city","biz_phone","biz_email","biz_website","tagline","invoice_prefix","etransfer_email"]
        for key in simple_keys:
            if key in self.settings_fields:
                save_setting(key, self.settings_fields[key].get().strip())
        pay_box = self.settings_fields.get("payment_instructions_box")
        if pay_box:
            save_setting("payment_instructions", pay_box.get("1.0","end").strip())
        currency_combo = self.settings_fields.get("currency_combo")
        if currency_combo:
            save_setting("currency", currency_combo.get())
        self.settings_status.configure(text="✓  Settings saved successfully!")
        self.after(3000, lambda: self.settings_status.configure(text=""))
        # Update window title with business name
        biz = get_settings().get("biz_name","InvoBiz")
        self.title(f"{biz} — InvoBiz")

if __name__ == "__main__":
    app = App()
    app.mainloop()
