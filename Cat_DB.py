import sys, os, csv, sqlite3, tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
from pathlib import Path
import re
from math import ceil
from PIL import Image, ImageTk

APP_TITLE = "Cat_DB-Manager – Lern-GUI"

# -------- Pfade (EXE-ready) ----------
def is_frozen() -> bool:
    return getattr(sys, "frozen", False)

def resource_base() -> Path:
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).parent

def app_dir() -> Path:
    return Path(sys.executable).parent if is_frozen() else Path(__file__).parent

def resource_path(rel: str) -> Path:
    return resource_base() / rel

APP_DIR = app_dir()
DATA_DIR = APP_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

SAFE_DB_RE = re.compile(r"^[a-zA-Z0-9_\-]+\.db$")
CURRENT_DB = DATA_DIR / "database.db"

def set_current_db(name: str):
    global CURRENT_DB
    if not SAFE_DB_RE.match(name):
        raise ValueError("Ungültiger DB-Name (a-z, 0-9, _, -, .db)")
    CURRENT_DB = DATA_DIR / name

def list_databases():
    return sorted([p.name for p in DATA_DIR.glob("*.db")])

def get_db_conn():
    conn = sqlite3.connect(CURRENT_DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def ensure_default_db():
    base = DATA_DIR / "database.db"
    if not base.exists():
        with sqlite3.connect(base) as conn:
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT,
                    created TEXT DEFAULT (datetime('now','localtime'))
                )
            """)
            conn.commit()
    set_current_db("database.db")

# ------------- App --------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1100x780")
        self.minsize(980, 660)

        self._build_header()
        self._build_menu()
        self._build_tabs()
        self._bind_keys()

        self._status("Bereit. Öffne oder erstelle eine Datenbank.")
        self.refresh_schema()
        self.build_er_diagram()

    # Header (cat.png optional)
    def _build_header(self):
        hdr = ttk.Frame(self)
        hdr.pack(fill="x", padx=8, pady=(8, 0))
        inner = ttk.Frame(hdr)
        inner.pack()

        self.cat_img = None
        for p in (resource_path("cat.png"), APP_DIR / "cat.png", APP_DIR / "assets" / "cat.png"):
            if p.exists():
                try:
                    img = Image.open(p)
                    if img.width > 220:
                        ratio = 220 / img.width
                        new_size = (220, int(img.height * ratio))
                        img = img.resize(new_size, Image.LANCZOS)
                    self.cat_img = ImageTk.PhotoImage(img)
                except Exception:
                    self.cat_img = None
                break

        if self.cat_img:
            ttk.Label(inner, image=self.cat_img).pack()
        else:
            ttk.Label(inner, text="(cat.png optional)", foreground="#999").pack()

        ttk.Label(inner, text="Cat_DB Manager – LernGUI", font=("Segoe UI", 20, "bold")).pack(pady=(6, 2))
        ttk.Label(inner, text="Lernen · Ausprobieren · Verstehen — SQLite, GUI & Beispiele",
                  font=("Segoe UI", 10)).pack(pady=(0, 8))
        ttk.Separator(self).pack(fill="x", padx=8, pady=8)

    def _build_menu(self):
        menubar = tk.Menu(self)
        m_file = tk.Menu(menubar, tearoff=False)
        m_file.add_command(label="DB öffnen …", command=self.on_open_db)
        m_file.add_command(label="Neue DB …", command=self.on_new_db)
        m_file.add_separator()
        m_file.add_command(label="Datenordner öffnen", command=self.open_data_dir)
        m_file.add_separator()
        m_file.add_command(label="Beenden", command=self.destroy)
        menubar.add_cascade(label="Datei", menu=m_file)

        m_tools = tk.Menu(menubar, tearoff=False)
        m_tools.add_command(label="CSV-Export (Browse-Tab)", command=self.export_csv_current)
        menubar.add_cascade(label="Tools", menu=m_tools)

        m_help = tk.Menu(menubar, tearoff=False)
        m_help.add_command(label="Kurz-Anleitung", command=self.show_quick_help)
        menubar.add_cascade(label="Hilfe", menu=m_help)

        self.config(menu=menubar)

    def _build_tabs(self):
        top = ttk.Frame(self, padding=(10, 0))
        top.pack(side=tk.TOP, fill=tk.X)
        self.lbl_db = ttk.Label(top, text=f"Aktuelle DB: {Path(CURRENT_DB).resolve()}", width=120, anchor="w")
        self.lbl_db.pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(top, text="DB öffnen …", command=self.on_open_db).pack(side=tk.LEFT)
        ttk.Button(top, text="Neue DB …", command=self.on_new_db).pack(side=tk.LEFT, padx=6)
        ttk.Button(top, text="Schema neu laden", command=self.refresh_schema).pack(side=tk.LEFT, padx=12)

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # Schema
        self.tab_schema = ttk.Frame(self.nb, padding=8)
        self.nb.add(self.tab_schema, text="Schema")
        ttk.Label(self.tab_schema, text="Tabellen & Keys", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.tree = ttk.Treeview(self.tab_schema, columns=("info",), show="tree")
        self.tree.pack(fill=tk.BOTH, expand=True, pady=(6, 0))

        # SQL
        self.tab_sql = ttk.Frame(self.nb, padding=8)
        self.nb.add(self.tab_sql, text="SQL")
        ttk.Label(self.tab_sql, text="SQL-Editor (mehrere Statements mit Semikolon trennen)",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w")
        edf = ttk.Frame(self.tab_sql)
        edf.pack(fill=tk.BOTH, expand=False)
        self.txt_sql = tk.Text(edf, height=10, wrap="none", undo=True, font=("Consolas", 10))
        self.txt_sql.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb_y = ttk.Scrollbar(edf, command=self.txt_sql.yview)
        self.txt_sql.configure(yscrollcommand=sb_y.set)
        sb_y.pack(side=tk.RIGHT, fill=tk.Y)

        ex_row = ttk.Frame(self.tab_sql)
        ex_row.pack(fill=tk.X, pady=(6, 2))
        ttk.Label(ex_row, text="Beispiele:").pack(side=tk.LEFT)
        for title, sql in self._example_queries()[:3]:
            ttk.Button(ex_row, text=title, command=lambda s=sql: self.insert_example(s)).pack(side=tk.LEFT, padx=4)

        ttk.Button(self.tab_sql, text="▶ Ausführen (Strg+Enter)", command=self.run_sql).pack(anchor="w", pady=(2, 6))
        ttk.Label(self.tab_sql, text="Ergebnis", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        rf = ttk.Frame(self.tab_sql)
        rf.pack(fill=tk.BOTH, expand=True)
        self.result = ttk.Treeview(rf, show="headings")
        self.result.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb_res = ttk.Scrollbar(rf, command=self.result.yview)
        self.result.configure(yscrollcommand=sb_res.set)
        sb_res.pack(side=tk.RIGHT, fill=tk.Y)

        # Browse
        self.tab_browse = ttk.Frame(self.nb, padding=8)
        self.nb.add(self.tab_browse, text="Browse")
        topb = ttk.Frame(self.tab_browse)
        topb.pack(fill=tk.X)
        ttk.Label(topb, text="Tabelle:").pack(side=tk.LEFT)
        self.cmb_tables = ttk.Combobox(topb, width=30, state="readonly")
        self.cmb_tables.pack(side=tk.LEFT, padx=6)
        self.cmb_tables.bind("<<ComboboxSelected>>", lambda _e: self.load_table_rows())
        self.ent_filter = ttk.Entry(topb, width=32)
        self.ent_filter.pack(side=tk.LEFT, padx=6)
        ttk.Button(topb, text="Neu laden", command=self.load_table_rows).pack(side=tk.LEFT, padx=6)
        ttk.Button(topb, text="CSV exportieren", command=self.export_csv_current).pack(side=tk.LEFT, padx=6)
        ttk.Button(topb, text="Ausgewählte Zeile löschen", command=self.delete_selected_row).pack(side=tk.LEFT, padx=6)

        bf = ttk.Frame(self.tab_browse)
        bf.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        self.grid_browse = ttk.Treeview(bf, show="headings")
        self.grid_browse.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb_b = ttk.Scrollbar(bf, command=self.grid_browse.yview)
        self.grid_browse.configure(yscrollcommand=sb_b.set)
        sb_b.pack(side=tk.RIGHT, fill=tk.Y)

        # Items
        self.tab_items = ttk.Frame(self.nb, padding=8)
        self.nb.add(self.tab_items, text="Items")
        ttk.Label(self.tab_items, text="Item hinzufügen (Tabelle: items)", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        form = ttk.Frame(self.tab_items)
        form.pack(fill=tk.X, pady=(6, 4))
        ttk.Label(form, text="Name").grid(row=0, column=0, sticky="w")
        ttk.Label(form, text="Beschreibung").grid(row=0, column=1, sticky="w")
        self.ent_name = ttk.Entry(form, width=28)
        self.ent_desc = ttk.Entry(form, width=50)
        self.ent_name.grid(row=1, column=0, padx=(0, 8), pady=4, sticky="we")
        self.ent_desc.grid(row=1, column=1, padx=(0, 8), pady=4, sticky="we")
        ttk.Button(form, text="➕ Hinzufügen", command=self.add_item).grid(row=1, column=2, padx=(0, 8), pady=4)

        ttk.Label(self.tab_items, text="items-Vorschau", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(8, 2))
        itf = ttk.Frame(self.tab_items)
        itf.pack(fill=tk.BOTH, expand=True)
        self.grid_items = ttk.Treeview(itf, show="headings")
        self.grid_items.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb_it = ttk.Scrollbar(itf, command=self.grid_items.yview)
        self.grid_items.configure(yscrollcommand=sb_it.set)
        sb_it.pack(side=tk.RIGHT, fill=tk.Y)
        ttk.Button(self.tab_items, text="Items neu laden", command=self.reload_items).pack(anchor="w", pady=(6, 0))

        # ER-Modell (Canvas, pure Tk)
        self.tab_er = ttk.Frame(self.nb, padding=8)
        self.nb.add(self.tab_er, text="ER-Modell")
        top_er = ttk.Frame(self.tab_er)
        top_er.pack(fill="x")
        ttk.Label(top_er, text="Diagramm des aktuellen Schemas (ohne Graphviz)").pack(side=tk.LEFT)
        ttk.Button(top_er, text="🔄 Aktualisieren", command=self.build_er_diagram).pack(side=tk.LEFT, padx=8)
        self.er_info = ttk.Label(top_er, text="", foreground="#666")
        self.er_info.pack(side=tk.LEFT, padx=8)
        self.er_canvas = tk.Canvas(self.tab_er, bg="#fafafa", height=520)
        self.er_canvas.pack(fill="both", expand=True, pady=8)

        # Hilfe
        self.tab_help = ttk.Frame(self.nb, padding=10)
        self.nb.add(self.tab_help, text="Hilfe")
        ttk.Label(self.tab_help, text="Lernhilfe & Cheatsheet", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        helptext = scrolledtext.ScrolledText(self.tab_help, wrap=tk.WORD, height=26, font=("Segoe UI", 10))
        helptext.pack(fill=tk.BOTH, expand=True, pady=(6, 6))
        helptext.insert("1.0", self._help_text())
        helptext.config(state="disabled")
        ex2 = ttk.Frame(self.tab_help)
        ex2.pack(anchor="w", pady=(2, 0))
        ttk.Label(ex2, text="Beispiel-Queries in Editor einfügen:").pack(side=tk.LEFT)
        for title, sql in self._example_queries()[3:]:
            ttk.Button(ex2, text=title, command=lambda s=sql: self.insert_example(s)).pack(side=tk.LEFT, padx=4)

        # Statusleiste
        self.status = ttk.Label(self, text="—", anchor="w", padding=(10, 6))
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

    def _bind_keys(self):
        self.bind_all("<Control-Return>", lambda _e: self.run_sql())

    def _status(self, text: str):
        self.status.config(text=text)
        self.title(f"{APP_TITLE} — {text}")

    # Menü
    def on_open_db(self):
        file = filedialog.askopenfilename(
            title="Datenbank öffnen",
            initialdir=DATA_DIR,
            filetypes=[("SQLite DB", "*.db"), ("Alle Dateien", "*.*")]
        )
        if not file: return
        set_current_db(Path(file).name)
        self.lbl_db.config(text=f"Aktuelle DB: {Path(CURRENT_DB).resolve()}")
        self.refresh_schema()
        self.build_er_diagram()
        self._status("DB geöffnet.")

    def on_new_db(self):
        file = filedialog.asksaveasfilename(
            title="Neue Datenbank anlegen",
            initialdir=DATA_DIR,
            defaultextension=".db",
            filetypes=[("SQLite DB", "*.db")]
        )
        if not file: return
        p = Path(file)
        with sqlite3.connect(p) as conn:
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT,
                    created TEXT DEFAULT (datetime('now','localtime'))
                )
            """)
            conn.commit()
        set_current_db(p.name)
        self.lbl_db.config(text=f"Aktuelle DB: {Path(CURRENT_DB).resolve()}")
        self.refresh_schema()
        self.build_er_diagram()
        self._status("Neue DB erstellt.")

    def open_data_dir(self):
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(DATA_DIR))
            elif sys.platform == "darwin":
                os.system(f"open '{DATA_DIR}'")
            else:
                os.system(f"xdg-open '{DATA_DIR}'")
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"Konnte Datenordner nicht öffnen:\n{e}")

    # Schema/Browse
    def refresh_schema(self):
        self.tree.delete(*self.tree.get_children())
        self.cmb_tables.set("")
        self.cmb_tables["values"] = []
        if not CURRENT_DB.exists(): return
        with get_db_conn() as conn:
            tables = conn.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name
            """).fetchall()
            names = []
            for t in tables:
                tname = t["name"]
                names.append(tname)
                node = self.tree.insert("", "end", text=tname, open=True)
                cols = conn.execute(f"PRAGMA table_info('{tname}')").fetchall()
                for c in cols:
                    label = f"• {c['name']} ({c['type']})"
                    if c['pk'] == 1: label += " [PK]"
                    if c['notnull'] == 1: label += " [NOT NULL]"
                    if c['dflt_value'] is not None: label += f" [DEFAULT {c['dflt_value']}]"
                    self.tree.insert(node, "end", text=label)
                fks = conn.execute(f"PRAGMA foreign_key_list('{tname}')").fetchall()
                if fks:
                    fk_parent = self.tree.insert(node, "end", text="Foreign Keys", open=True)
                    for fk in fks:
                        fk_label = f"{fk['from']} → {fk['table']}.{fk['to']} (ON DELETE {fk['on_delete']}, ON UPDATE {fk['on_update']})"
                        self.tree.insert(fk_parent, "end", text=fk_label)
            self.cmb_tables["values"] = names
            if names:
                self.cmb_tables.set(names[0])
                self.load_table_rows()
        self.reload_items()

    def load_table_rows(self):
        t = self.cmb_tables.get().strip()
        if not t: return
        where = self.ent_filter.get().strip()
        sql = f"SELECT * FROM {t}" + (f" WHERE {where}" if where else "")
        try:
            with get_db_conn() as conn:
                cur = conn.execute(sql)
                rows = cur.fetchall()
                cols = [d[0] for d in cur.description] if cur.description else []
            self._render_grid(self.grid_browse, cols, rows)
            self._status(f"{len(rows)} Zeilen aus '{t}' geladen.")
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"Fehler beim Laden:\n{e}")

    def _render_grid(self, grid: ttk.Treeview, columns, rows):
        grid.delete(*grid.get_children())
        grid["columns"] = columns
        for c in columns:
            grid.heading(c, text=c)
            grid.column(c, width=max(60, 10 * len(c)))
        for r in rows:
            grid.insert("", "end", values=[r[c] for c in columns])

    def delete_selected_row(self):
        t = self.cmb_tables.get().strip()
        if not t: return
        sel = self.grid_browse.selection()
        if not sel:
            messagebox.showinfo(APP_TITLE, "Bitte eine Zeile im Browse-Tab auswählen.")
            return
        cols = list(self.grid_browse["columns"])
        vals = self.grid_browse.item(sel[0], "values")
        pk_col = None
        if "id" in cols:
            pk_col = "id"
        else:
            with get_db_conn() as conn:
                pkinfo = conn.execute(f"PRAGMA table_info('{t}')").fetchall()
            for c in pkinfo:
                if c["pk"] == 1:
                    pk_col = c["name"]; break
        if not pk_col:
            messagebox.showwarning(APP_TITLE, "Keine PK-Spalte gefunden (z. B. 'id').")
            return
        try:
            pk_idx = cols.index(pk_col)
            pk_val = vals[pk_idx]
            with get_db_conn() as conn:
                conn.execute(f"DELETE FROM {t} WHERE {pk_col} = ?", (pk_val,))
                conn.commit()
            self.load_table_rows()
            self._status(f"Zeile mit {pk_col}={pk_val} aus '{t}' gelöscht.")
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"Löschfehler:\n{e}")

    def export_csv_current(self):
        t = self.cmb_tables.get().strip()
        if not t:
            messagebox.showinfo(APP_TITLE, "Bitte im Browse-Tab zuerst eine Tabelle wählen.")
            return
        file = filedialog.asksaveasfilename(
            title="CSV exportieren",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")]
        )
        if not file: return
        try:
            with get_db_conn() as conn:
                cur = conn.execute(f"SELECT * FROM {t}")
                cols = [d[0] for d in cur.description]
                rows = cur.fetchall()
            with open(file, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow(cols)
                for r in rows:
                    w.writerow([r[c] for c in cols])
            self._status(f"{len(rows)} Zeilen aus '{t}' nach CSV exportiert.")
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"Exportfehler:\n{e}")

    # Items
    def add_item(self):
        name = self.ent_name.get().strip()
        desc = self.ent_desc.get().strip()
        if not name:
            messagebox.showwarning(APP_TITLE, "Name erforderlich.")
            return
        try:
            with get_db_conn() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS items (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        description TEXT,
                        created TEXT DEFAULT (datetime('now','localtime'))
                    )
                """)
                conn.execute("INSERT INTO items (name, description) VALUES (?, ?)", (name, desc))
                conn.commit()
            self.ent_name.delete(0, tk.END)
            self.ent_desc.delete(0, tk.END)
            self.reload_items()
            messagebox.showinfo(APP_TITLE, "Item hinzugefügt.")
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"Fehler beim Hinzufügen:\n{e}")

    def reload_items(self):
        try:
            with get_db_conn() as conn:
                cur = conn.execute("SELECT * FROM items ORDER BY created DESC")
                rows = cur.fetchall()
                cols = [d[0] for d in cur.description]
            self._render_grid(self.grid_items, cols, rows)
        except Exception:
            self._render_grid(self.grid_items, [], [])

    # SQL
    def insert_example(self, sql: str):
        self.nb.select(self.tab_sql)
        self.txt_sql.delete("1.0", "end")
        self.txt_sql.insert("1.0", sql)

    def run_sql(self):
        sql_text = self.txt_sql.get("1.0", "end").strip()
        if not sql_text: return
        try:
            with get_db_conn() as conn:
                cur = conn.cursor()
                ddl_markers = ("create trigger", "create view", "begin", "end",
                               "create table", "drop table", "drop view", "alter table")
                text_low = sql_text.lower()
                use_script = any(m in text_low for m in ddl_markers)
                out_cols, out_rows = [], []
                if use_script and ("select" not in text_low and "pragma" not in text_low):
                    cur.executescript(sql_text)
                    conn.commit()
                else:
                    statements = [s.strip() for s in sql_text.split(";") if s.strip()]
                    affected_total = 0
                    for stmt in statements:
                        low = stmt.lower()
                        if low.startswith(("select", "pragma")):
                            cur.execute(stmt)
                            rows = cur.fetchall()
                            cols = [d[0] for d in cur.description] if cur.description else []
                            out_cols, out_rows = cols, rows
                        else:
                            before = conn.total_changes
                            cur.execute(stmt)
                            after = conn.total_changes
                            affected_total += max(0, after - before)
                    conn.commit()
                    if not out_cols:
                        out_cols = ["Info"]
                        out_rows = [{"Info": f"OK. Geänderte Zeilen: {affected_total}"}]
                # Ergebnis anzeigen
                self.result.delete(*self.result.get_children())
                if out_cols:
                    self.result["columns"] = out_cols
                    for c in out_cols:
                        self.result.heading(c, text=c)
                        self.result.column(c, width=max(60, 10 * len(c)))
                    for r in out_rows:
                        if isinstance(r, dict):
                            self.result.insert("", "end", values=[r.get(c) for c in out_cols])
                        else:
                            self.result.insert("", "end", values=[r[c] for c in out_cols])
            self.refresh_schema()
            self.build_er_diagram()
            self._status("SQL ausgeführt.")
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"SQL-Fehler:\n{e}")

    # Hilfe
    def show_quick_help(self):
        messagebox.showinfo(
            "Kurz-Anleitung",
            "• Schema-Tab: Tabellen + Spalten + Foreign Keys\n"
            "• SQL-Tab: Mehrere Befehle mit Semikolon trennen; DDL wird als Block ausgeführt\n"
            "• Browse-Tab: Tabelle wählen, optional WHERE-Filter, CSV-Export, Zeilen löschen\n"
            "• Items-Tab: Schnelles Hinzufügen zur items-Tabelle\n"
            "• ER-Modell: Einfaches Diagramm (ohne Graphviz)"
        )

    def _help_text(self) -> str:
        return """==============================
 SQL Cheatsheet & Lernhilfe
==============================
📌 Grundlegende SQL-Befehle
---------------------------
-- Tabelle erstellen
CREATE TABLE tabelle (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    wert INTEGER
);

-- Tabelle löschen
DROP TABLE tabelle;

-- Datensatz einfügen
INSERT INTO tabelle (name, wert) VALUES ('Beispiel', 42);

-- Daten abfragen
SELECT * FROM tabelle;
SELECT name, wert FROM tabelle WHERE wert > 10;
SELECT * FROM tabelle WHERE name LIKE '%abc%';

-- Daten ändern
UPDATE tabelle SET wert = 100 WHERE id = 1;

-- Datensatz löschen
DELETE FROM tabelle WHERE id = 1;


🔑 Wichtige Schlüsselbegriffe
-----------------------------
PRIMARY KEY (PK): Eindeutige ID pro Datensatz (z. B. id INTEGER PRIMARY KEY).
FOREIGN KEY (FK): Verweis auf PK einer anderen Tabelle.
NOT NULL: Spalte darf nicht leer sein.
UNIQUE: Werte dürfen sich nicht wiederholen.
DEFAULT: Standardwert, wenn nichts angegeben wird.
AUTOINCREMENT: Erhöht Integer-PK automatisch.

Beispiel (PK/FK):
CREATE TABLE kunden (
    kunden_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL
);

CREATE TABLE bestellungen (
    bestellung_id INTEGER PRIMARY KEY AUTOINCREMENT,
    kunden_id INTEGER NOT NULL,
    datum TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (kunden_id) REFERENCES kunden(kunden_id)
);


🤝 Relationen & ER-Modelle
--------------------------
1:1  Ein Kunde ↔ genau eine Adresse (selten)
1:n  Ein Kunde ↔ viele Bestellungen (häufig)
n:m  Viele Produkte ↔ viele Bestellungen → Zwischentabelle nötig

Zwischentabelle (n:m):
CREATE TABLE bestellungen_produkte (
    bestellung_id INTEGER NOT NULL,
    produkt_id INTEGER NOT NULL,
    PRIMARY KEY (bestellung_id, produkt_id),
    FOREIGN KEY (bestellung_id) REFERENCES bestellungen(bestellung_id),
    FOREIGN KEY (produkt_id)   REFERENCES produkte(produkt_id)
);


🔍 Joins erklärt
----------------
-- Nur übereinstimmende Paare
SELECT b.bestellung_id, k.name
FROM bestellungen b
JOIN kunden k ON b.kunden_id = k.kunden_id;

-- Alle Kunden, auch ohne Bestellungen (LEFT JOIN)
SELECT k.name, b.bestellung_id
FROM kunden k
LEFT JOIN bestellungen b ON k.kunden_id = b.kunden_id;

Hinweis: RIGHT/FULL JOIN sind im SQLite-Standard nicht direkt vorhanden.


🛠️ Nützliche PRAGMA/Meta-Abfragen
---------------------------------
-- Alle Tabellen:
SELECT name FROM sqlite_master WHERE type='table';

-- Struktur einer Tabelle:
SELECT * FROM pragma_table_info('tabelle');

-- Foreign Keys einer Tabelle:
SELECT * FROM pragma_foreign_key_list('tabelle');

-- Indizes:
SELECT * FROM pragma_index_list('tabelle');


📦 Transaktionen (mehrere Aktionen sicher ausführen)
---------------------------------------------------
BEGIN TRANSACTION;
  INSERT INTO tabelle (name) VALUES ('A');
  INSERT INTO tabelle (name) VALUES ('B');
COMMIT;
-- Bei Fehler stattdessen ROLLBACK;


⚡ Performance-Tipps
--------------------
- Indizes auf Spalten, die oft in WHERE/JOIN vorkommen
- SELECT nur benötigte Spalten
- Lange Transaktionen vermeiden (sperren DB)

🧪 Übungsideen
--------------
1) Erstelle Kunden/Produkte/Bestellungen + FK, fülle Daten und baue Joins.
2) Füge einen Index auf kunden(name) hinzu und teste die Suche.
3) Schreibe eine n:m-Beziehung (Produkte ↔ Bestellungen) mit Zwischentabelle.
"""

    def _example_queries(self):
        return [
            ("Tabellen anlegen (PK/FK)", """CREATE TABLE kunden (
  kunden_id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  email TEXT UNIQUE
);
CREATE TABLE produkte (
  produkt_id INTEGER PRIMARY KEY AUTOINCREMENT,
  titel TEXT NOT NULL,
  preis REAL
);
CREATE TABLE bestellungen (
  bestellung_id INTEGER PRIMARY KEY AUTOINCREMENT,
  kunden_id INTEGER NOT NULL,
  produkt_id INTEGER NOT NULL,
  datum TEXT DEFAULT (datetime('now','localtime')),
  FOREIGN KEY (kunden_id) REFERENCES kunden(kunden_id),
  FOREIGN KEY (produkt_id) REFERENCES produkte(produkt_id)
);"""),
            ("Testdaten", """INSERT INTO kunden (name, email) VALUES
('Alice','alice@example.com'),
('Bob','bob@example.com');
INSERT INTO produkte (titel, preis) VALUES
('Kaffeemaschine',79.99),
('Toaster',29.95);
INSERT INTO bestellungen (kunden_id, produkt_id) VALUES
(1,1),(2,2),(1,2);"""),
            ("Alle Tabellen", "SELECT name FROM sqlite_master WHERE type='table';"),
            ("Struktur: bestellungen", "SELECT * FROM pragma_table_info('bestellungen');"),
            ("FKs: bestellungen", "SELECT * FROM pragma_foreign_key_list('bestellungen');"),
            ("Join-Beispiel", """SELECT b.bestellung_id, k.name AS kunde, p.titel AS produkt, b.datum
FROM bestellungen b
JOIN kunden k ON b.kunden_id = k.kunden_id
JOIN produkte p ON b.produkt_id = p.produkt_id;"""),
        ]

    # -------- ER-Diagramm (Canvas) ----------
    def build_er_diagram(self):
        self.er_canvas.delete("all")
        if not CURRENT_DB.exists():
            self.er_info.config(text="Keine DB.")
            return

        with get_db_conn() as conn:
            tables = [r["name"] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()]

            # Daten sammeln
            cols_by_table = {}
            fks = []  # (from_table, from_col, to_table, to_col)
            for t in tables:
                cols = conn.execute(f"PRAGMA table_info('{t}')").fetchall()
                cols_by_table[t] = cols
                for fk in conn.execute(f"PRAGMA foreign_key_list('{t}')").fetchall():
                    fks.append((t, fk["from"], fk["table"], fk["to"]))

        # Auto-Layout: Kacheln in Spalten/Zeilen
        W = self.er_canvas.winfo_width() or 1000
        PADDING = 24
        BOX_W = 260
        LINE_H = 18
        TITLE_H = 26
        GAP_X = 40
        GAP_Y = 40
        per_row = max(1, (W - PADDING) // (BOX_W + GAP_X))

        boxes = {}  # t -> (x1,y1,x2,y2)
        for idx, t in enumerate(tables):
            row = idx // per_row
            col = idx % per_row
            x1 = PADDING + col * (BOX_W + GAP_X)
            # Höhe je nach Spaltenanzahl:
            nlines = max(1, len(cols_by_table[t]))
            box_h = TITLE_H + 8 + nlines * LINE_H + 12
            y1 = PADDING + row * (box_h + GAP_Y)
            x2 = x1 + BOX_W
            y2 = y1 + box_h
            # Zeichnen
            self._draw_table_box(t, cols_by_table[t], x1, y1, x2, y2, LINE_H)
            boxes[t] = (x1, y1, x2, y2)

        # Kanten (einfache Gerade + Pfeil)
        for (ft, fc, tt, tc) in fks:
            if ft not in boxes or tt not in boxes: continue
            fx1, fy1, fx2, fy2 = boxes[ft]
            tx1, ty1, tx2, ty2 = boxes[tt]
            # Start: Mitte rechts von Quelle, Ziel: Mitte links vom Ziel
            sx, sy = fx2, (fy1 + fy2) // 2
            ex, ey = tx1, (ty1 + ty2) // 2
            self._draw_arrow(sx, sy, ex, ey, text=f"{fc} → {tc}")

        self.er_info.config(text=f"Generiert aus: {CURRENT_DB.name}")

    def _draw_table_box(self, name, cols, x1, y1, x2, y2, line_h):
        # Rahmen + Titel
        self.er_canvas.create_rectangle(x1, y1, x2, y2, outline="#888", width=1, fill="#ffffff")
        self.er_canvas.create_rectangle(x1, y1, x2, y1+24, outline="#666", fill="#f0f0f0")
        self.er_canvas.create_text((x1+8, y1+12), text=name, anchor="w", font=("Segoe UI", 10, "bold"))
        # Spalten
        y = y1 + 32
        for c in cols:
            label = c['name']
            if c['type']: label += f": {c['type']}"
            if c['pk'] == 1: label += " [PK]"
            self.er_canvas.create_text((x1+10, y), text=label, anchor="w", font=("Consolas", 9))
            y += line_h

    def _draw_arrow(self, x1, y1, x2, y2, text=""):
        line = self.er_canvas.create_line(x1, y1, x2, y2, arrow=tk.LAST, smooth=False)
        if text:
            mx, my = (x1 + x2) // 2, (y1 + y2) // 2
            self.er_canvas.create_text(mx, my - 8, text=text, font=("Segoe UI", 8), fill="#444")

# -------- Start --------
if __name__ == "__main__":
    ensure_default_db()
    app = App()
    app.mainloop()

