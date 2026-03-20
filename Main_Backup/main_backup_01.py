import customtkinter as ctk
import sqlite3, json, io, os, sys
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
    ]
    for m in migrations:
        try: conn.execute(m)
        except: pass
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

def fmt(n): return f"CA${float(n or 0):.2f}"
def today(): return datetime.now().strftime('%Y-%m-%d')
def in_days(n): return (datetime.now() + timedelta(days=n)).strftime('%Y-%m-%d')
def fmt_date(s):
    if not s: return "—"
    try:
        d = datetime.strptime(s, '%Y-%m-%d')
        return d.strftime('%b %d, %Y')
    except: return s

# ── PDF GENERATOR ──────────────────────────────────────────────────────────
def generate_pdf(inv_id, save_path):
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
        rightMargin=0.75*inch, leftMargin=0.75*inch,
        topMargin=0.75*inch, bottomMargin=0.75*inch)
    brand_red = colors.HexColor('#E63B2E')
    brand_dark = colors.HexColor('#1a1a2e')
    brand_light = colors.HexColor('#f9fafb')
    styles = getSampleStyleSheet()
    story = []

    ht = Table([[
        Paragraph('<font size="20" color="#E63B2E"><b>25ABCs</b></font>', styles['Normal']),
        Paragraph('<font size="28" color="#1a1a2e"><b>INVOICE</b></font>', ParagraphStyle('r', alignment=TA_RIGHT))
    ]], colWidths=[3.5*inch, 3.5*inch])
    ht.setStyle(TableStyle([('ALIGN',(0,0),(0,0),'LEFT'),('ALIGN',(1,0),(1,0),'RIGHT'),('VALIGN',(0,0),(-1,-1),'MIDDLE')]))
    story.append(ht)
    story.append(HRFlowable(width="100%", thickness=2, color=brand_red, spaceAfter=12))

    biz = '<font size="9"><b>25ABCs</b></font><br/><font size="8" color="#6b7280">1405 Planetree Court, Coquitlam BC V3E2T2<br/>annaelusini@gmail.com | www.25abcs.com</font>'
    meta = f'<font size="8" color="#6b7280">INVOICE NO</font><br/><font size="9"><b>{inv["invoice_number"]}</b></font><br/><br/><font size="8" color="#6b7280">ISSUE DATE</font><br/><font size="9">{inv["issue_date"]}</font><br/><br/><font size="8" color="#6b7280">DUE DATE</font><br/><font size="9"><b>{inv["due_date"]}</b></font>'
    mt = Table([[Paragraph(biz, styles['Normal']), Paragraph(meta, ParagraphStyle('mr', alignment=TA_RIGHT))]], colWidths=[3.5*inch,3.5*inch])
    mt.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP')]))
    story.append(mt)
    story.append(Spacer(1, 0.25*inch))

    cl = '<font size="10" color="#E63B2E"><b>BILL TO</b></font><br/>'
    if inv.get('client_company'): cl += f'<font size="9"><b>{inv["client_company"]}</b></font><br/>'
    if inv.get('client_name'): cl += f'<font size="9">{inv["client_name"]}</font><br/>'
    for f in ['client_address','client_city','client_email']:
        if inv.get(f): cl += f'<font size="8" color="#6b7280">{inv[f]}</font><br/>'
    pi = '<font size="10" color="#E63B2E"><b>PAYMENT INFO</b></font><br/><font size="9">E-Transfer</font><br/><font size="8" color="#6b7280">annaelusini@gmail.com</font>'
    bt = Table([[Paragraph(cl,styles['Normal']), Paragraph(pi,styles['Normal'])]], colWidths=[3.5*inch,3.5*inch])
    bt.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('BACKGROUND',(0,0),(-1,-1),brand_light),('PADDING',(0,0),(-1,-1),12)]))
    story.append(bt)
    story.append(Spacer(1, 0.25*inch))

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
    it = Table(irows, colWidths=[3.5*inch,0.8*inch,1*inch,1.2*inch])
    it.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),brand_dark),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,brand_light]),('GRID',(0,0),(-1,-1),0.5,colors.HexColor('#e5e7eb')),('PADDING',(0,0),(-1,-1),8)]))
    story.append(it)
    story.append(Spacer(1,0.15*inch))

    td = [['', 'Subtotal', f'CA${inv["subtotal"]:.2f}']]
    if inv.get('discount_amount') and float(inv['discount_amount']) > 0:
        td.append(['', f'Discount', f'-CA${float(inv["discount_amount"]):.2f}'])
    if inv.get('shipping_type') == 'free':
        td.append(['', 'Shipping', 'FREE'])
    elif inv.get('shipping') and float(inv['shipping']) > 0:
        td.append(['', 'Shipping', f'CA${float(inv["shipping"]):.2f}'])
    if inv.get('tax') and float(inv['tax']) > 0:
        td.append(['', 'Tax', f'CA${float(inv["tax"]):.2f}'])
    td.append(['', Paragraph('<font size="11" color="#ffffff"><b>TOTAL DUE</b></font>',styles['Normal']),
               Paragraph(f'<font size="11" color="#ffffff"><b>CA${inv["total"]:.2f}</b></font>', ParagraphStyle('r',alignment=TA_RIGHT))])
    tt = Table(td, colWidths=[3.5*inch,1.8*inch,1.2*inch])
    tt.setStyle(TableStyle([('ALIGN',(1,0),(2,-1),'RIGHT'),('FONTSIZE',(0,0),(-1,-1),9),('PADDING',(0,0),(-1,-1),6),('LINEABOVE',(1,-1),(2,-1),1,brand_red),('BACKGROUND',(1,-1),(2,-1),brand_dark)]))
    story.append(tt)

    if inv.get('notes'):
        story.append(Spacer(1,0.15*inch))
        story.append(Paragraph(f'<font size="8" color="#6b7280"><i>Notes: {inv["notes"]}</i></font>', styles['Normal']))

    story.append(Spacer(1,0.3*inch))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#e5e7eb')))
    story.append(Spacer(1,0.1*inch))
    story.append(Paragraph('<font size="8" color="#6b7280">Thank you for your business! — 25ABCs | www.25abcs.com | Where Education Meets Creativity</font>', ParagraphStyle('footer',alignment=TA_CENTER)))
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

# ── MAIN APPLICATION ───────────────────────────────────────────────────────
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("25ABCs Invoicer")
        self.geometry("1200x750")
        self.minsize(900, 600)
        self.configure(fg_color=LIGHT)
        init_db()
        self._build_ui()
        self.show_page("dashboard")

    def _build_ui(self):
        # Sidebar
        self.sidebar = ctk.CTkFrame(self, width=200, fg_color=DARK, corner_radius=0)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        # Logo
        logo_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        logo_frame.pack(pady=(20,8), padx=16, fill="x")
        ctk.CTkLabel(logo_frame, text="25", font=ctk.CTkFont(size=24, weight="bold"), text_color=WHITE).pack(side="left")
        ctk.CTkLabel(logo_frame, text="A", font=ctk.CTkFont(size=24, weight="bold"), text_color=RED).pack(side="left")
        ctk.CTkLabel(logo_frame, text="B", font=ctk.CTkFont(size=24, weight="bold"), text_color="#60a5fa").pack(side="left")
        ctk.CTkLabel(logo_frame, text="C", font=ctk.CTkFont(size=24, weight="bold"), text_color="#4ade80").pack(side="left")
        ctk.CTkLabel(logo_frame, text="s", font=ctk.CTkFont(size=24, weight="bold"), text_color=AMBER).pack(side="left")

        ctk.CTkLabel(self.sidebar, text="Where Education\nMeets Creativity",
                     font=ctk.CTkFont(size=10), text_color="gray60").pack(pady=(0,20))
        separator(self.sidebar).pack(fill="x", padx=16, pady=(0,16))

        self.nav_btns = {}
        nav_items = [("🏠  Dashboard","dashboard"),("📄  Invoices","invoices"),("👥  Clients & CRM","clients")]
        for label_text, page in nav_items:
            b = ctk.CTkButton(self.sidebar, text=label_text, command=lambda p=page: self.show_page(p),
                              fg_color="transparent", hover_color="#2d2d44",
                              text_color="gray70", anchor="w", height=40,
                              font=ctk.CTkFont(size=13), corner_radius=8)
            b.pack(fill="x", padx=12, pady=2)
            self.nav_btns[page] = b

        # Version at bottom
        ctk.CTkLabel(self.sidebar, text="v2.0 — 25ABCs", font=ctk.CTkFont(size=10),
                     text_color="gray50").pack(side="bottom", pady=16)

        # Main content area
        self.content = ctk.CTkFrame(self, fg_color=LIGHT, corner_radius=0)
        self.content.pack(side="left", fill="both", expand=True)

        self.pages = {}
        for page in ["dashboard","invoices","clients"]:
            frame = ctk.CTkFrame(self.content, fg_color=LIGHT, corner_radius=0)
            self.pages[page] = frame

        self._build_dashboard()
        self._build_invoices()
        self._build_clients()

    def show_page(self, page):
        for p, f in self.pages.items():
            f.pack_forget()
            self.nav_btns[p].configure(fg_color="transparent", text_color="gray70")
        self.pages[page].pack(fill="both", expand=True)
        self.nav_btns[page].configure(fg_color="#2d2d44", text_color=WHITE)
        if page == "dashboard": self.refresh_dashboard()
        elif page == "invoices": self.refresh_invoices()
        elif page == "clients": self.refresh_clients()

    # ── DASHBOARD ────────────────────────────────────────────────────────
    def _build_dashboard(self):
        p = self.pages["dashboard"]
        header = ctk.CTkFrame(p, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(20,0))
        label(header, "Dashboard", size=22, weight="bold").pack(side="left")
        btn(header, "+ New Invoice", lambda: self.open_invoice_dialog(), color=RED, width=130).pack(side="right")

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
        lh.pack(fill="x", padx=16, pady=12)
        label(lh, "Recent Invoices", size=14, weight="bold").pack(side="left")
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

    def refresh_dashboard(self):
        conn = get_db()
        total_inv = conn.execute('SELECT COUNT(*) FROM invoices').fetchone()[0]
        unpaid = conn.execute('SELECT COUNT(*), SUM(total) FROM invoices WHERE status="unpaid"').fetchone()
        paid = conn.execute('SELECT COUNT(*), SUM(total) FROM invoices WHERE status="paid"').fetchone()
        clients_count = conn.execute('SELECT COUNT(*) FROM clients').fetchone()[0]
        fup_count = conn.execute('SELECT COUNT(*) FROM follow_ups WHERE done=0').fetchone()[0]
        recent_invs = conn.execute('''SELECT i.*, c.name as cn, c.company as cc
            FROM invoices i LEFT JOIN clients c ON i.client_id=c.id
            ORDER BY i.id DESC LIMIT 8''').fetchall()
        fups = conn.execute('''SELECT f.*, c.name as cn, c.company as cc
            FROM follow_ups f JOIN clients c ON f.client_id=c.id
            WHERE f.done=0 ORDER BY f.due_date LIMIT 10''').fetchall()
        conn.close()

        # Stat cards
        for w in self.dash_stats.winfo_children(): w.destroy()
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

        # Recent invoices
        for w in self.dash_inv_frame.winfo_children(): w.destroy()
        if recent_invs:
            for inv in recent_invs:
                row = ctk.CTkFrame(self.dash_inv_frame, fg_color="transparent")
                row.pack(fill="x", pady=2)
                client_name = inv['cc'] or inv['cn'] or "—"
                label(row, inv['invoice_number'], size=12, weight="bold").pack(side="left")
                label(row, client_name, size=11, color=GRAY).pack(side="left", padx=8)
                status_col = GREEN if inv['status']=='paid' else RED
                label(row, inv['status'].upper(), size=10, color=status_col).pack(side="right")
                label(row, fmt(inv['total']), size=12, weight="bold").pack(side="right", padx=8)
        else:
            label(self.dash_inv_frame, "No invoices yet", color=GRAY).pack(pady=20)

        # Follow-ups
        for w in self.dash_fup_frame.winfo_children(): w.destroy()
        if fups:
            for f in fups:
                row = ctk.CTkFrame(self.dash_fup_frame, fg_color="transparent")
                row.pack(fill="x", pady=3)
                client_name = f['cc'] or f['cn'] or "—"
                is_overdue = f['due_date'] < today()
                label(row, f['title'], size=12).pack(side="left")
                date_col = RED if is_overdue else GRAY
                label(row, fmt_date(f['due_date']), size=11, color=date_col).pack(side="right")
                label(row, client_name, size=11, color=GRAY).pack(side="left", padx=8)
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
        self.inv_search = entry(bar, "Search invoices...", width=300)
        self.inv_search.pack(side="left")
        self.inv_search.bind("<KeyRelease>", lambda e: self.refresh_invoices())
        self.inv_status_filter = ctk.CTkComboBox(bar, values=["All","unpaid","paid","overdue"], width=120,
                                                  fg_color=WHITE, border_color=BORDER, text_color=DARK,
                                                  command=lambda _: self.refresh_invoices())
        self.inv_status_filter.set("All")
        self.inv_status_filter.pack(side="left", padx=8)

        # Table header
        th = ctk.CTkFrame(p, fg_color=DARK, corner_radius=8)
        th.pack(fill="x", padx=24, pady=(0,2))
        for col, w in [("Invoice #",120),("Client",200),("Issue Date",100),("Due Date",100),("Total",100),("Status",80),("",180)]:
            label(th, col, size=11, color=WHITE, weight="bold", width=w, anchor="w").pack(side="left", padx=8, pady=8)

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
        for w in self.inv_list.winfo_children(): w.destroy()
        shown = 0
        for inv in invoices:
            client_name = inv['cc'] or inv['cn'] or "—"
            if q and q not in inv['invoice_number'].lower() and q not in client_name.lower(): continue
            if s != "All" and inv['status'] != s: continue
            shown += 1
            row = ctk.CTkFrame(self.inv_list, fg_color=WHITE if shown%2==0 else "#fafafa",
                               corner_radius=6, border_width=1, border_color=BORDER)
            row.pack(fill="x", pady=2)
            label(row, inv['invoice_number'], size=12, weight="bold", width=120, anchor="w").pack(side="left", padx=8, pady=8)
            label(row, client_name, size=12, color=DARK, width=200, anchor="w").pack(side="left", padx=4)
            label(row, inv['issue_date'] or "—", size=11, color=GRAY, width=100, anchor="w").pack(side="left", padx=4)
            label(row, inv['due_date'] or "—", size=11, color=GRAY, width=100, anchor="w").pack(side="left", padx=4)
            label(row, fmt(inv['total']), size=12, weight="bold", width=100, anchor="w").pack(side="left", padx=4)
            status_col = GREEN if inv['status']=='paid' else RED
            label(row, inv['status'].upper(), size=10, color=status_col, width=80, anchor="w").pack(side="left", padx=4)
            # Action buttons
            acts = ctk.CTkFrame(row, fg_color="transparent")
            acts.pack(side="right", padx=8)
            inv_id = inv['id']; inv_num = inv['invoice_number']
            btn(acts, "PDF", lambda i=inv_id, n=inv_num: self.save_pdf(i,n), color="#374151", width=45).pack(side="left", padx=2)
            btn(acts, "Edit", lambda i=inv_id: self.open_invoice_dialog(i), color="#374151", width=45).pack(side="left", padx=2)
            if inv['status'] != 'paid':
                btn(acts, "✓ Paid", lambda i=inv_id: self.mark_paid(i), color=GREEN, width=65).pack(side="left", padx=2)
            btn(acts, "✕", lambda i=inv_id: self.delete_invoice(i), color=RED, width=35).pack(side="left", padx=2)
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

    def save_pdf(self, inv_id, inv_num):
        path = filedialog.asksaveasfilename(defaultextension=".pdf",
            filetypes=[("PDF files","*.pdf")], initialfile=f"{inv_num}.pdf")
        if path:
            generate_pdf(inv_id, path)
            messagebox.showinfo("PDF Saved", f"Saved to:\n{path}")

    # ── INVOICE DIALOG ────────────────────────────────────────────────────
    def open_invoice_dialog(self, inv_id=None):
        dlg = ctk.CTkToplevel(self)
        dlg.title("Edit Invoice" if inv_id else "New Invoice")
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
            q.bind("<KeyRelease>", update_amt); r.bind("<KeyRelease>", update_amt)
            update_amt()
            def remove():
                item_rows.remove(ir); row.destroy()
            ir = (d,q,r,amt_lbl)
            rem_btn = btn(row, "✕", remove, color=RED, width=30)
            rem_btn.pack(side="left")
            item_rows.append(ir)

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

        label(adj, "Tax ($)").grid(row=0,column=4,sticky="w",padx=4,pady=2)
        tax_val = ctk.CTkEntry(adj, placeholder_text="0", width=80, fg_color=WHITE, border_color=BORDER, text_color=DARK)
        tax_val.insert(0, str(inv.get('tax',0))); tax_val.grid(row=1,column=4,padx=4,pady=2)

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
            tax = float(tax_val.get() or 0)
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

        btn(sf, "💾  Save Invoice", save, color=RED, width=180).pack(pady=8)

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
        self.client_search = entry(bar, "Search clients...", width=300)
        self.client_search.pack(side="left")
        self.client_search.bind("<KeyRelease>", lambda e: self.refresh_clients())
        self.client_filter = ctk.CTkComboBox(bar, values=["All","Starred","Has Follow-up"], width=140,
                                              fg_color=WHITE, border_color=BORDER, text_color=DARK,
                                              command=lambda _: self.refresh_clients())
        self.client_filter.set("All")
        self.client_filter.pack(side="left", padx=8)

        self.clients_list = scrollframe(pane)
        self.clients_list.pack(fill="both", expand=True, padx=24, pady=(0,16))

    def refresh_clients(self):
        q = self.client_search.get().lower() if hasattr(self,'client_search') else ""
        f = self.client_filter.get() if hasattr(self,'client_filter') else "All"
        conn = get_db()
        clients = conn.execute('SELECT * FROM clients ORDER BY starred DESC, name').fetchall()
        conn.close()
        for w in self.clients_list.winfo_children(): w.destroy()
        shown = 0
        for c in clients:
            name = c['company'] or c['name']
            if q and q not in name.lower() and q not in (c['email'] or '').lower(): continue
            if f == "Starred" and not c['starred']: continue
            if f == "Has Follow-up" and not c['follow_up_date']: continue
            shown += 1
            card = ctk.CTkFrame(self.clients_list, fg_color=WHITE, corner_radius=10,
                               border_width=2 if c['starred'] else 1,
                               border_color=AMBER if c['starred'] else BORDER)
            card.pack(fill="x", pady=4)

            top = ctk.CTkFrame(card, fg_color="transparent"); top.pack(fill="x", padx=12, pady=(10,4))
            star = "⭐" if c['starred'] else "☆"
            label(top, f"{star}  {name}", size=14, weight="bold").pack(side="left")

            acts = ctk.CTkFrame(top, fg_color="transparent"); acts.pack(side="right")
            cid = c['id']
            btn(acts, "CRM →", lambda i=cid: self.open_crm_detail(i), color=DARK, width=70).pack(side="left", padx=2)
            btn(acts, "Edit", lambda i=cid: self.open_client_dialog(i), color="#374151", width=55).pack(side="left", padx=2)
            btn(acts, "✕", lambda i=cid: self.delete_client(i), color=RED, width=35).pack(side="left", padx=2)

            info = ctk.CTkFrame(card, fg_color="transparent"); info.pack(fill="x", padx=12, pady=(0,10))
            if c['email']: label(info, f"✉  {c['email']}", size=12, color=RED).pack(side="left", padx=(0,16))
            if c['phone']: label(info, f"📞  {c['phone']}", size=12, color=GRAY).pack(side="left", padx=(0,16))
            if c['follow_up_date']:
                is_over = c['follow_up_date'] < today()
                label(info, f"📅  {fmt_date(c['follow_up_date'])}", size=11, color=RED if is_over else GRAY).pack(side="left")

        if shown == 0:
            label(self.clients_list, "No clients found", color=GRAY).pack(pady=40)

    def _build_crm_detail(self):
        pane = self.crm_pane
        back_bar = ctk.CTkFrame(pane, fg_color="transparent")
        back_bar.pack(fill="x", padx=24, pady=(20,8))
        btn(back_bar, "← Back to Clients", self.show_clients_list, color="#374151", width=160).pack(side="left")
        self.crm_client_title = label(back_bar, "", size=18, weight="bold")
        self.crm_client_title.pack(side="left", padx=16)

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
        right = ctk.CTkFrame(cols, fg_color=WHITE, corner_radius=12, border_width=1, border_color=BORDER)
        right.grid(row=0, column=1, sticky="nsew", padx=(8,0))

        tab_bar = ctk.CTkFrame(right, fg_color=LIGHT, corner_radius=0, height=40)
        tab_bar.pack(fill="x", padx=0, pady=0)
        self.crm_tab_btns = {}
        for tab_name in ["notes","followups"]:
            tab_lbl = "📞 Call Notes" if tab_name=="notes" else "📅 Follow-ups"
            b = ctk.CTkButton(tab_bar, text=tab_lbl, command=lambda t=tab_name: self.switch_crm_tab(t),
                              fg_color=RED if tab_name=="notes" else LIGHT,
                              hover_color=RED, text_color=WHITE if tab_name=="notes" else DARK,
                              corner_radius=0, height=40, font=ctk.CTkFont(size=13))
            b.pack(side="left", expand=True, fill="x")
            self.crm_tab_btns[tab_name] = b

        self.crm_panels = {}
        # Notes panel
        np = ctk.CTkFrame(right, fg_color="transparent")
        np.pack(fill="both", expand=True, padx=12, pady=12)
        self.crm_panels["notes"] = np
        note_input_row = ctk.CTkFrame(np, fg_color="transparent")
        note_input_row.pack(fill="x", pady=(0,8))
        self.note_type_combo = ctk.CTkComboBox(note_input_row, values=["📞 Call","📧 Email","🤝 Meeting","📝 Other"],
                                                width=120, fg_color=WHITE, border_color=BORDER, text_color=DARK)
        self.note_type_combo.set("📞 Call")
        self.note_type_combo.pack(side="left", padx=(0,8))
        btn(note_input_row, "Add Note", self.add_note, color=RED, width=100).pack(side="right")
        self.note_text = ctk.CTkTextbox(np, height=80, fg_color=WHITE, border_color=BORDER, text_color=DARK, border_width=1)
        self.note_text.pack(fill="x", pady=(0,8))
        separator(np).pack(fill="x", pady=(0,8))
        self.notes_scroll = scrollframe(np)
        self.notes_scroll.pack(fill="both", expand=True)

        # Follow-ups panel
        fp = ctk.CTkFrame(right, fg_color="transparent")
        self.crm_panels["followups"] = fp
        fup_input = ctk.CTkFrame(fp, fg_color="transparent")
        fup_input.pack(fill="x", padx=12, pady=12)
        self.fup_title_entry = entry(fup_input, "Follow-up task...", width=250)
        self.fup_title_entry.pack(side="left", padx=(0,8))
        self.fup_date_entry = entry(fup_input, "YYYY-MM-DD", width=130)
        self.fup_date_entry.pack(side="left", padx=(0,8))
        btn(fup_input, "Add", self.add_followup, color=RED, width=70).pack(side="left")
        separator(fp).pack(fill="x", padx=12)
        self.fups_scroll = scrollframe(fp)
        self.fups_scroll.pack(fill="both", expand=True, padx=12, pady=8)

    def switch_crm_tab(self, tab):
        for t, b in self.crm_tab_btns.items():
            if t == tab:
                b.configure(fg_color=RED, text_color=WHITE)
                self.crm_panels[t].pack(fill="both", expand=True, padx=12 if t!="notes" else 0, pady=12 if t!="notes" else 0)
            else:
                b.configure(fg_color=LIGHT, text_color=DARK)
                self.crm_panels[t].pack_forget()

    def open_crm_detail(self, client_id):
        self.current_client_id = client_id
        self.clients_pane.pack_forget()
        self.crm_pane.pack(fill="both", expand=True)
        conn = get_db()
        c = dict(conn.execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone())
        invs = conn.execute('''SELECT i.* FROM invoices i WHERE i.client_id=? ORDER BY i.id DESC''', (client_id,)).fetchall()
        conn.close()

        self.crm_client_title.configure(text=f"{'⭐ ' if c['starred'] else ''}{c['company'] or c['name']}")

        # Client info
        for w in self.crm_info_card.winfo_children(): w.destroy()
        label(self.crm_info_card, "Client Info", size=13, weight="bold").pack(anchor="w", padx=12, pady=(10,4))
        for lbl_text, val in [("Name", c['name']),("Company", c.get('company','')),("Email", c.get('email','')),("Phone", c.get('phone','')),("City", f"{c.get('city','')} {c.get('province','')}")]:
            if val:
                row = ctk.CTkFrame(self.crm_info_card, fg_color="transparent")
                row.pack(fill="x", padx=12, pady=1)
                label(row, f"{lbl_text}:", size=11, color=GRAY, width=65, anchor="w").pack(side="left")
                label(row, val, size=12).pack(side="left")
        if c.get('follow_up_date'):
            is_over = c['follow_up_date'] < today()
            row = ctk.CTkFrame(self.crm_info_card, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=(4,2))
            label(row, "Follow-up:", size=11, color=GRAY, width=65, anchor="w").pack(side="left")
            label(row, fmt_date(c['follow_up_date']), size=12, color=RED if is_over else DARK).pack(side="left")
        ctk.CTkFrame(self.crm_info_card, fg_color="transparent", height=8).pack()

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
                btn(row, "PDF", lambda i=inv_id, n=inv_num: self.save_pdf(i,n), color="#374151", width=40).pack(side="right")
        else:
            label(self.crm_inv_card, "No invoices yet", size=12, color=GRAY).pack(padx=12, pady=4)
        ctk.CTkFrame(self.crm_inv_card, fg_color="transparent", height=8).pack()

        self.switch_crm_tab("notes")
        self.refresh_notes()
        self.refresh_followups()

    def show_clients_list(self):
        self.crm_pane.pack_forget()
        self.clients_pane.pack(fill="both", expand=True)
        self.refresh_clients()

    def refresh_notes(self):
        for w in self.notes_scroll.winfo_children(): w.destroy()
        conn = get_db()
        notes = conn.execute('SELECT * FROM crm_notes WHERE client_id=? ORDER BY created_at DESC', (self.current_client_id,)).fetchall()
        conn.close()
        type_colors = {"call":BLUE,"email":RED,"meeting":GREEN,"other":GRAY}
        type_icons = {"call":"📞","email":"📧","meeting":"🤝","other":"📝"}
        if notes:
            for n in notes:
                card = ctk.CTkFrame(self.notes_scroll, fg_color=LIGHT, corner_radius=8)
                card.pack(fill="x", pady=3)
                meta = ctk.CTkFrame(card, fg_color="transparent"); meta.pack(fill="x", padx=10, pady=(6,2))
                nt = n['note_type'] or 'other'
                icon = type_icons.get(nt,'📝')
                label(meta, f"{icon} {nt.title()}", size=11, weight="bold", color=type_colors.get(nt,GRAY)).pack(side="left")
                try:
                    dt = datetime.strptime(n['created_at'], '%Y-%m-%d %H:%M:%S')
                    dt_str = dt.strftime('%b %d, %Y %I:%M %p')
                except: dt_str = n['created_at']
                label(meta, dt_str, size=10, color=GRAY).pack(side="left", padx=8)
                nid = n['id']
                btn(meta, "✕", lambda i=nid: self.delete_note(i), color=RED, width=28).pack(side="right")
                label(card, n['note'], size=12, wraplength=380, justify="left", anchor="w").pack(anchor="w", padx=10, pady=(2,8))
        else:
            label(self.notes_scroll, "No notes yet. Log your first call!", color=GRAY).pack(pady=20)

    def add_note(self):
        note = self.note_text.get("1.0","end").strip()
        if not note: messagebox.showwarning("Empty Note","Please write a note first."); return
        nt_raw = self.note_type_combo.get()
        nt = "call" if "Call" in nt_raw else ("email" if "Email" in nt_raw else ("meeting" if "Meeting" in nt_raw else "other"))
        conn = get_db()
        conn.execute('INSERT INTO crm_notes (client_id,note,note_type) VALUES (?,?,?)', (self.current_client_id, note, nt))
        conn.commit(); conn.close()
        self.note_text.delete("1.0","end")
        self.refresh_notes()

    def delete_note(self, nid):
        if messagebox.askyesno("Delete Note","Delete this note?"):
            conn = get_db()
            conn.execute('DELETE FROM crm_notes WHERE id=?', (nid,))
            conn.commit(); conn.close()
            self.refresh_notes()

    def refresh_followups(self):
        for w in self.fups_scroll.winfo_children(): w.destroy()
        conn = get_db()
        fups = conn.execute('SELECT * FROM follow_ups WHERE client_id=? ORDER BY due_date', (self.current_client_id,)).fetchall()
        conn.close()
        if fups:
            for f in fups:
                row = ctk.CTkFrame(self.fups_scroll, fg_color=LIGHT if not f['done'] else "#f0fdf4", corner_radius=8)
                row.pack(fill="x", pady=3)
                inner = ctk.CTkFrame(row, fg_color="transparent"); inner.pack(fill="x", padx=10, pady=8)
                fid = f['id']
                chk_var = ctk.IntVar(value=f['done'])
                chk = ctk.CTkCheckBox(inner, text="", variable=chk_var, width=20,
                                       command=lambda i=fid: self.toggle_followup(i),
                                       fg_color=GREEN, hover_color=GREEN)
                chk.pack(side="left")
                is_over = not f['done'] and f['due_date'] < today()
                title_style = {"text_color": GRAY if f['done'] else DARK}
                label(inner, f['title'], size=12, **title_style).pack(side="left", padx=8)
                label(inner, fmt_date(f['due_date']), size=11, color=RED if is_over else GRAY).pack(side="left")
                btn(inner, "✕", lambda i=fid: self.delete_followup(i), color=RED, width=30).pack(side="right")
        else:
            label(self.fups_scroll, "No follow-ups yet", color=GRAY).pack(pady=20)

    def add_followup(self):
        title = self.fup_title_entry.get().strip()
        due = self.fup_date_entry.get().strip()
        if not title or not due: messagebox.showwarning("Missing Info","Please enter a title and date (YYYY-MM-DD)."); return
        conn = get_db()
        conn.execute('INSERT INTO follow_ups (client_id,title,due_date) VALUES (?,?,?)', (self.current_client_id, title, due))
        conn.commit(); conn.close()
        self.fup_title_entry.delete(0,"end")
        self.fup_date_entry.delete(0,"end")
        self.refresh_followups(); self.refresh_dashboard()

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
        dlg.geometry("520x620")
        dlg.grab_set()
        dlg.configure(fg_color=WHITE)

        sf = scrollframe(dlg)
        sf.pack(fill="both", expand=True, padx=20, pady=16)

        fields = {}
        for lbl_text, key, placeholder in [
            ("Contact Name *","name","Mindy Smith"),("Company","company","Green & Green"),
            ("Address","address","1122 SW Marine Drive"),("City","city","Vancouver"),
            ("Province","province","BC"),("Postal Code","postal","V6P5Z3"),
            ("Country","country","Canada"),("Email","email","info@example.com"),
            ("Phone","phone","604-000-0000"),
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
        last4_e = entry(sf, "e.g. 9479")
        last4_e.pack(fill="x", pady=(0,2))
        if c.get('payment_last4'): last4_e.insert(0, c['payment_last4'])

        label(sf, "Follow-up Date (YYYY-MM-DD)").pack(anchor="w", pady=(6,2))
        fup_e = entry(sf, "2026-04-01")
        fup_e.pack(fill="x", pady=(0,2))
        if c.get('follow_up_date'): fup_e.insert(0, c['follow_up_date'])

        star_var = ctk.IntVar(value=c.get('starred',0))
        ctk.CTkCheckBox(sf, text="⭐ Priority / Starred Client", variable=star_var,
                        fg_color=AMBER, hover_color=AMBER, text_color=DARK).pack(anchor="w", pady=(10,0))

        def save():
            name = fields['name'].get().strip()
            if not name: messagebox.showwarning("Required","Contact name is required."); return
            data = {k: e.get().strip() or None for k,e in fields.items()}
            data['payment_method'] = pay_method.get()
            data['payment_last4'] = last4_e.get().strip() or None
            data['follow_up_date'] = fup_e.get().strip() or None
            data['starred'] = star_var.get()
            conn = get_db()
            if client_id:
                conn.execute('''UPDATE clients SET name=?,company=?,address=?,city=?,province=?,postal=?,
                    country=?,email=?,phone=?,payment_method=?,payment_last4=?,follow_up_date=?,starred=? WHERE id=?''',
                    (data['name'],data['company'],data['address'],data['city'],data['province'],
                     data['postal'],data['country'] or 'Canada',data['email'],data['phone'],
                     data['payment_method'],data['payment_last4'],data['follow_up_date'],data['starred'],client_id))
            else:
                conn.execute('''INSERT INTO clients (name,company,address,city,province,postal,country,email,phone,
                    payment_method,payment_last4,follow_up_date,starred) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (data['name'],data['company'],data['address'],data['city'],data['province'],
                     data['postal'],data['country'] or 'Canada',data['email'],data['phone'],
                     data['payment_method'],data['payment_last4'],data['follow_up_date'],data['starred']))
            conn.commit(); conn.close()
            dlg.destroy()
            self.refresh_clients(); self.refresh_dashboard()

        btn(sf, "💾  Save Client", save, color=RED, width=160).pack(pady=12)

    def delete_client(self, client_id):
        if messagebox.askyesno("Delete Client","Delete this client and all their notes and follow-ups?"):
            conn = get_db()
            conn.execute('DELETE FROM crm_notes WHERE client_id=?', (client_id,))
            conn.execute('DELETE FROM follow_ups WHERE client_id=?', (client_id,))
            conn.execute('DELETE FROM clients WHERE id=?', (client_id,))
            conn.commit(); conn.close()
            self.refresh_clients(); self.refresh_dashboard()

if __name__ == "__main__":
    app = App()
    app.mainloop()
