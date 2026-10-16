"""
SURYA SENTINEL dan TENUN WALLET: Command Center KDMP
Purwarupa simulasi untuk Case Study MATRIX UI 2026
Desa Percontohan, Sumba Timur

Jalankan: python -m streamlit run app.py

CATATAN KEJUJURAN DATA
- Input sensor (cuaca, SOC, level tandon, debit) diganti slider di sidebar.
- Model Scikit learn dilatih dari data sintetis (hubungan awan ke radiasi diasumsikan).
- Grafik riwayat 7 hari adalah data ilustrasi, bukan hasil pengukuran.
- Harga komoditas adalah contoh. Ganti dengan harga pasar desa.
"""

import html
import os
import random
import sqlite3
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from sklearn.linear_model import LinearRegression

# ============================================================
# 1. KONSTANTA DESAIN (sumber: Excel Perhitungan PLTS Pompa)
# ============================================================
TARIF_ACUAN = 99_617                      # Rp per KK per bulan
BATAS_BARTER_PERSEN = 0.30
BATAS_BARTER = round(TARIF_ACUAN * BATAS_BARTER_PERSEN)   # Rp 29.885 per KK per bulan

BEBAN_PENUH = 91.3                        # kWh per hari, lapis 1 sampai 5
RADIASI_REF = 5.0                         # kWh per m2 per hari (acuan R)
PV_REF_KWH = 91.3                         # ASUMSI: PV harian pada radiasi acuan. Cocokkan dengan Excel.
BATAS_NORMAL = 0.856
BATAS_DARURAT = 0.48
PV_KRITIS_KWH = 40.0

SOC_MIN = 20                              # persen, genset menyala
KAP_TANDON = 80.0                         # m3
BATAS_P3 = 0.30                           # di bawah 30%: irigasi ditutup
BATAS_P2 = 0.15                           # di bawah 15%: ternak ikut ditutup
TURUN_MUKA_AIR_AMAN = 16.5                # m, batas aman kenaikan TDH
BATAS_SELISIH_BOCOR = 5.0                 # persen, ASUMSI ambang peringatan

# Harga komoditas CONTOH (satuan, Rp per satuan)
KOMODITAS = {
    "Jagung pipil": ("kg", 5_000),
    "Kacang tanah": ("kg", 15_000),
    "Hasil kebun (sayur)": ("kg", 8_000),
    "Kain tenun ikat": ("lembar", 250_000),
}

WIB = timezone(timedelta(hours=7))
BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
         "Agustus", "September", "Oktober", "November", "Desember"]


# ============================================================
# 2. FUNGSI BANTU (format Indonesia)
# ============================================================
def fmt(x: float, d: int = 1) -> str:
    """Angka format Indonesia: titik ribuan, koma desimal."""
    s = f"{x:,.{d}f}"
    return s.replace(",", "#").replace(".", ",").replace("#", ".")


def rp(x: float) -> str:
    return "Rp " + fmt(x, 0)


def waktu_wib() -> str:
    t = datetime.now(WIB)
    return f"{t.day} {BULAN[t.month - 1]} {t.year} {t:%H:%M} WIB"


def tampil(fig_or_df, kind="chart"):
    """Kompatibel dengan versi Streamlit lama dan baru."""
    fn = st.plotly_chart if kind == "chart" else st.dataframe
    kw = {} if kind == "chart" else {"hide_index": True}
    try:
        fn(fig_or_df, width="stretch", **kw)
    except TypeError:
        fn(fig_or_df, use_container_width=True, **kw)


# ============================================================
# 3. HALAMAN
# ============================================================
st.set_page_config(
    page_title="Surya Sentinel & Tenun Wallet",
    page_icon="☀️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .main-title { font-size:2.1rem; font-weight:800; color:#1B3A4B;
                  text-align:center; margin-bottom:0; }
    .sub-title  { font-size:1rem; color:#5A7184; text-align:center;
                  margin-bottom:0.6rem; }
    .st-normal  { background:#D5F5E3; color:#1B6B3A; padding:1rem;
                  border-radius:0.6rem; text-align:center;
                  font-weight:800; font-size:1.25rem; }
    .st-siaga   { background:#FEF9E7; color:#7D6608; padding:1rem;
                  border-radius:0.6rem; text-align:center;
                  font-weight:800; font-size:1.25rem; }
    .st-darurat { background:#FDEDEC; color:#922B21; padding:1rem;
                  border-radius:0.6rem; text-align:center;
                  font-weight:800; font-size:1.25rem; }
    .bubble-warga { background:#DCF8C6; padding:0.7rem 1rem;
                    border-radius:0.8rem 0.8rem 0.8rem 0; margin:0.4rem 0;
                    max-width:82%; font-size:0.95rem; color:#1B1B1B; }
    .bubble-bot { background:#FFFFFF; padding:0.7rem 1rem;
                  border-radius:0.8rem 0.8rem 0 0.8rem; margin:0.4rem 0;
                  max-width:82%; border:1px solid #E0E0E0;
                  font-size:0.95rem; color:#1B1B1B; }
    .footer-text { text-align:center; color:#999; font-size:0.8rem;
                   margin-top:2rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# 4. DATABASE SQLite
# ============================================================
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "koperasi_desa_v2.db")


def koneksi():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = koneksi()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS kas_koperasi (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            nama_kk         TEXT NOT NULL,
            saldo_barter    REAL DEFAULT 0,
            saldo_tunai     REAL DEFAULT 0,
            barter_terpakai REAL DEFAULT 0,
            terakhir_bayar  TEXT,
            status_token    TEXT DEFAULT 'Aktif'
        )""")
    c.execute("""
        CREATE TABLE IF NOT EXISTS riwayat_token (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            id_kk   INTEGER,
            waktu   TEXT,
            nominal REAL,
            barter  REAL,
            tunai   REAL,
            kode    TEXT
        )""")
    c.execute("""
        CREATE TABLE IF NOT EXISTS stok_komoditas (
            komoditas TEXT PRIMARY KEY,
            jumlah    REAL DEFAULT 0,
            satuan    TEXT
        )""")

    c.execute("SELECT COUNT(*) FROM kas_koperasi")
    if c.fetchone()[0] == 0:
        seed = [
            ("Keluarga Mbili Praing", 25_000, 75_000, 0, "2026-10-10", "Aktif"),
            ("Keluarga Umbu Ratu",    18_000, 82_000, 0, "2026-10-12", "Aktif"),
            ("Keluarga Rambu Ana",    29_000, 71_000, 0, "2026-10-08", "Aktif"),
            ("Keluarga Umbu Ndilu",    5_000, 45_000, 0, "2026-09-28", "Nonaktif"),
            ("Keluarga Rambu Kaha",   22_000, 78_000, 0, "2026-10-11", "Aktif"),
            ("Keluarga Mbili Hamu",   15_000, 60_000, 0, "2026-10-05", "Aktif"),
            ("Keluarga Umbu Landu",   28_500, 70_500, 0, "2026-10-13", "Aktif"),
            ("Keluarga Rambu Ami",    12_000, 88_000, 0, "2026-10-09", "Aktif"),
            ("Keluarga Umbu Sapu",    20_000, 65_000, 0, "2026-10-07", "Aktif"),
            ("Keluarga Rambu Hiri",    8_000, 55_000, 0, "2026-10-01", "Aktif"),
        ]
        c.executemany(
            "INSERT INTO kas_koperasi (nama_kk, saldo_barter, saldo_tunai, "
            "barter_terpakai, terakhir_bayar, status_token) VALUES (?,?,?,?,?,?)",
            seed,
        )
    for nama, (satuan, _) in KOMODITAS.items():
        c.execute("INSERT OR IGNORE INTO stok_komoditas VALUES (?,?,?)", (nama, 0, satuan))
    conn.commit()
    conn.close()


def semua_kk() -> pd.DataFrame:
    conn = koneksi()
    df = pd.read_sql_query("SELECT * FROM kas_koperasi", conn)
    conn.close()
    return df


def ambil_kk(id_kk: int):
    conn = koneksi()
    row = conn.execute("SELECT * FROM kas_koperasi WHERE id = ?", (id_kk,)).fetchone()
    conn.close()
    return row


def beli_token(id_kk: int, nominal: int):
    """
    Aturan Wallet (desain):
    - Barter dipakai maksimal 30% dari tarif acuan per KK per bulan (Rp 29.885).
    - Batas dicek saat saldo dipakai membeli token.
    - Kekurangan harus tunai. Tunai kurang berarti token tidak terbit.
    Mengembalikan (berhasil, pesan_html).
    """
    kk = ambil_kk(id_kk)
    if kk is None:
        return False, "Data KK tidak ditemukan. Hubungi operator KDMP."
    if kk["status_token"] != "Aktif":
        return False, "Status token Anda nonaktif. Hubungi operator KDMP."
    if nominal < 10_000:
        return False, "Nominal minimal Rp 10.000. Contoh: BELI 50000"

    sisa_batas = max(0.0, BATAS_BARTER - kk["barter_terpakai"])
    barter_pakai = round(min(kk["saldo_barter"], sisa_batas, nominal))
    tunai_butuh = nominal - barter_pakai

    if kk["saldo_tunai"] < tunai_butuh:
        kurang = tunai_butuh - kk["saldo_tunai"]
        return False, (
            "❌ Token tidak terbit. Saldo tunai kurang.<br>"
            f"Barter dipakai: {rp(barter_pakai)} (sisa batas barter bulan ini {rp(sisa_batas)})<br>"
            f"Tunai dibutuhkan: {rp(tunai_butuh)}<br>"
            f"Saldo tunai Anda: {rp(kk['saldo_tunai'])}<br>"
            f"Kekurangan: {rp(kurang)}<br>Setor tunai di KDMP, lalu coba lagi."
        )

    kode = " ".join(str(random.randint(1000, 9999)) for _ in range(3))
    conn = koneksi()
    conn.execute(
        "UPDATE kas_koperasi SET saldo_barter = saldo_barter - ?, "
        "saldo_tunai = saldo_tunai - ?, barter_terpakai = barter_terpakai + ?, "
        "terakhir_bayar = ? WHERE id = ?",
        (barter_pakai, tunai_butuh, barter_pakai,
         datetime.now(WIB).strftime("%Y-%m-%d"), id_kk),
    )
    conn.execute(
        "INSERT INTO riwayat_token (id_kk, waktu, nominal, barter, tunai, kode) "
        "VALUES (?,?,?,?,?,?)",
        (id_kk, datetime.now(WIB).strftime("%Y-%m-%d %H:%M"), nominal,
         barter_pakai, tunai_butuh, kode),
    )
    conn.commit()
    conn.close()
    return True, (
        f"✅ Token {rp(nominal)} terbit.<br>"
        f"Barter dipakai: {rp(barter_pakai)}<br>Tunai dipotong: {rp(tunai_butuh)}<br>"
        f"Kode token: <b>{kode}</b><br>Masukkan kode ke meter prabayar Anda."
    )


def catat_hasil_bumi(id_kk: int, komoditas: str, jumlah: float) -> float:
    satuan, harga = KOMODITAS[komoditas]
    nilai = round(jumlah * harga)
    conn = koneksi()
    conn.execute("UPDATE kas_koperasi SET saldo_barter = saldo_barter + ? WHERE id = ?",
                 (nilai, id_kk))
    conn.execute("UPDATE stok_komoditas SET jumlah = jumlah + ? WHERE komoditas = ?",
                 (jumlah, komoditas))
    conn.commit()
    conn.close()
    return nilai


def tabel_stok() -> pd.DataFrame:
    conn = koneksi()
    df = pd.read_sql_query("SELECT * FROM stok_komoditas", conn)
    conn.close()
    return df


def kas_om() -> float:
    conn = koneksi()
    total = conn.execute("SELECT COALESCE(SUM(tunai),0) FROM riwayat_token").fetchone()[0]
    conn.close()
    return total


def reset_db():
    """Kembalikan seluruh data demo ke kondisi awal."""
    conn = koneksi()
    for tabel in ("kas_koperasi", "riwayat_token", "stok_komoditas"):
        conn.execute(f"DROP TABLE IF EXISTS {tabel}")
    conn.commit()
    conn.close()
    init_db()


init_db()


# ============================================================
# 5. MODEL MACHINE LEARNING (data sintetis)
# ============================================================
@st.cache_resource
def latih_model():
    """
    Linear Regression sederhana: tutupan awan (%) menjadi radiasi harian (kWh per m2).
    Data latih SINTETIS dengan asumsi: langit cerah sekitar 5,5 dan awan penuh sekitar 1,0.
    Pada sistem nyata, model dilatih dari radiasi terukur dan prakiraan BMKG.
    """
    rng = np.random.default_rng(42)
    awan = rng.uniform(0, 100, 300)
    radiasi = np.clip(5.5 - 0.045 * awan + rng.normal(0, 0.15, 300), 0.5, 6.0)
    model = LinearRegression()
    model.fit(awan.reshape(-1, 1), radiasi)
    return model


model_radiasi = latih_model()


# ============================================================
# 6. SIDEBAR: PENGGANTI INPUT SENSOR
# ============================================================
df_kk = semua_kk()

with st.sidebar:
    st.markdown("## ☀️ Panel Kontrol")
    st.caption("Operator KDMP Desa Percontohan. Slider menggantikan data sensor.")
    st.divider()

    st.markdown("#### 🌤️ Prakiraan Cuaca Besok")
    tutupan_awan = st.slider("Tutupan Awan (%)", 0, 100, 35,
                             help="Sumber nyata: prakiraan BMKG")
    st.divider()

    st.markdown("#### ⚙️ Kondisi Lapangan")
    soc_baterai = st.slider("SOC Baterai LFP (%)", 0, 100, 72)
    level_tandon = st.slider("Level Tandon Air (m³)", 0.0, KAP_TANDON, 58.0, step=0.5)
    turun_muka_air = st.slider("Penurunan muka air sumur (m)", 0.0, 20.0, 14.0, step=0.5,
                               help=f"Batas aman {TURUN_MUKA_AIR_AMAN} m")
    st.divider()

    st.markdown("#### 💧 Meter Debit (m³ per hari)")
    debit_pompa = st.number_input("Keluar pompa", 0.0, 150.0, 78.9, step=0.5)
    debit_tandon = st.number_input("Keluar tandon", 0.0, 150.0, 78.0, step=0.5)
    debit_p1 = st.number_input("Cabang P1 (air minum)", 0.0, 150.0, 52.0, step=0.5)
    debit_p2 = st.number_input("Cabang P2 (ternak)", 0.0, 150.0, 25.5, step=0.5)
    st.divider()

    st.markdown("#### 👤 Simulasi Warga")
    kk_terpilih = st.selectbox(
        "Pilih KK",
        options=df_kk["id"].tolist(),
        format_func=lambda x: df_kk.loc[df_kk["id"] == x, "nama_kk"].values[0],
    )
    st.divider()
    if st.button("Reset data demo"):
        reset_db()
        st.session_state.chat = []
        st.session_state.laporan = []
        st.session_state.pesan_valuasi = ""
        st.rerun()
    st.caption("Data demo dipakai bersama oleh semua pengunjung dan kembali ke awal bila aplikasi dimulai ulang.")


# ============================================================
# 7. LOGIKA SURYA SENTINEL
# ============================================================
radiasi = float(np.clip(model_radiasi.predict([[tutupan_awan]])[0], 0.5, 6.0))
r_ratio = radiasi / RADIASI_REF
prediksi_pv = r_ratio * PV_REF_KWH

if r_ratio >= BATAS_NORMAL:
    mode, css, ikon = "NORMAL", "st-normal", "🟢"
    lapis = "Lapis 1 sampai 5 (semua aktif)"
    vfd_mode = 100
    ket = "Seluruh beban terlayani. Pompa beroperasi penuh."
elif r_ratio >= BATAS_DARURAT:
    mode, css, ikon = "SIAGA", "st-siaga", "🟡"
    lapis = "Lapis 1 sampai 4 (lapis 5 pompa tidak memakai baterai)"
    vfd_mode = 60
    ket = ("Lapis 5 diputus dari baterai. Pompa hanya jalan dari surplus PV "
           "siang hari dengan kecepatan 60%.")
else:
    mode, css, ikon = "DARURAT (KRITIS)", "st-darurat", "🔴"
    lapis = "Lapis 1 sampai 3 saja (lapis 4 UMKM dan lapis 5 pompa diputus dari baterai)"
    vfd_mode = 30
    ket = ("Pemutusan beban aktif. Hanya beban esensial yang dilayani. "
           "Pompa diturunkan ke 30% dan hanya memakai surplus PV.")

if prediksi_pv < PV_KRITIS_KWH and not mode.startswith("DARURAT"):
    mode, css, ikon = "DARURAT (KRITIS)", "st-darurat", "🔴"
    lapis = "Lapis 1 sampai 3 saja (lapis 4 UMKM dan lapis 5 pompa diputus dari baterai)"
    vfd_mode = 30
    ket = (f"Prediksi PV di bawah {PV_KRITIS_KWH:.0f} kWh. Pemutusan beban aktif. "
           "Pompa diturunkan ke 30% dan hanya memakai surplus PV.")

# ---- HydroBank
persen_tandon = level_tandon / KAP_TANDON
sumur_kritis = turun_muka_air > TURUN_MUKA_AIR_AMAN
tandon_penuh = level_tandon >= KAP_TANDON - 0.1

if sumur_kritis:
    status_pompa, vfd_pct = "BERHENTI: muka air sumur terlalu rendah", 0
elif tandon_penuh:
    status_pompa, vfd_pct = "BERHENTI: tandon penuh", 0
else:
    status_pompa, vfd_pct = f"Menyala {vfd_mode}%", vfd_mode

if persen_tandon < BATAS_P2:
    zona_teks, zona_ikon = "Prioritas 1 saja (air minum)", "🔴"
    status_zona = {"P1": "Aktif", "P2": "Tutup", "P3": "Tutup"}
elif persen_tandon < BATAS_P3:
    zona_teks, zona_ikon = "Prioritas 1 dan 2 (air minum dan ternak)", "🟡"
    status_zona = {"P1": "Aktif", "P2": "Aktif", "P3": "Tutup"}
else:
    zona_teks, zona_ikon = "Semua zona aktif (air minum, ternak, irigasi)", "🟢"
    status_zona = {"P1": "Aktif", "P2": "Aktif", "P3": "Aktif"}

selisih_bocor = debit_tandon - (debit_p1 + debit_p2)
persen_bocor = (selisih_bocor / debit_tandon * 100) if debit_tandon > 0 else 0.0
bocor_tinggi = persen_bocor > BATAS_SELISIH_BOCOR


# ============================================================
# 8. TAMPILAN UTAMA
# ============================================================
if "chat" not in st.session_state:
    st.session_state.chat = []
if "laporan" not in st.session_state:
    st.session_state.laporan = []
if "pesan_valuasi" not in st.session_state:
    st.session_state.pesan_valuasi = ""

st.markdown('<p class="main-title">☀️ Surya Sentinel & Tenun Wallet</p>',
            unsafe_allow_html=True)
st.markdown(
    f'<p class="sub-title">Command Center KDMP · Desa Percontohan, Sumba Timur · {waktu_wib()}</p>',
    unsafe_allow_html=True,
)
st.info("Purwarupa simulasi. Input sensor memakai slider, model dilatih dari data sintetis, "
        "dan grafik riwayat adalah data ilustrasi.")

# ---- Metrik utama
m1, m2, m3, m4 = st.columns(4)
selisih_beban = prediksi_pv - BEBAN_PENUH
with m1:
    st.metric("Prediksi PV Besok", f"{fmt(prediksi_pv)} kWh",
              delta=f"{fmt(selisih_beban)} kWh dari beban penuh")
    st.caption(f"Radiasi diprediksi {fmt(radiasi, 2)} kWh per m² per hari")
with m2:
    st.metric("SOC Baterai", f"{soc_baterai}%")
    st.caption("🟢 Aman (di atas batas 20%)" if soc_baterai > SOC_MIN
               else "🔴 Kritis (genset siap menyala)")
with m3:
    st.metric("Level Tandon", f"{fmt(level_tandon)} m³")
    st.caption(f"{fmt(persen_tandon * 100, 0)}% dari kapasitas 80 m³")
with m4:
    st.metric("Pompa VFD", f"{vfd_pct}%")
    st.caption(("🔴 " if vfd_pct == 0 else "🟢 " if vfd_pct == 100 else "🟡 ") + status_pompa)

st.divider()
st.markdown(f'<div class="{css}">{ikon} MODE SURYA SENTINEL: {mode}</div>',
            unsafe_allow_html=True)
c1, c2 = st.columns(2)
with c1:
    st.markdown(f"**Lapis aktif:** {lapis}")
    st.markdown(f"**Keterangan:** {ket}")
with c2:
    st.markdown(f"**Zonasi air:** {zona_ikon} {zona_teks}")
    st.markdown(f"**R (prakiraan radiasi / {RADIASI_REF:.0f} kWh per m²):** {fmt(r_ratio * 100)}%")
    st.caption(f"Ambang: Normal ≥ {fmt(BATAS_NORMAL * 100)}%, Siaga {fmt(BATAS_DARURAT * 100, 0)}% sampai "
               f"{fmt(BATAS_NORMAL * 100)}%, Darurat di bawah {fmt(BATAS_DARURAT * 100, 0)}%")

# ---- Notifikasi operator
st.divider()
st.markdown("### 🔔 Notifikasi Operator")
notif = []
if mode.startswith("DARURAT"):
    notif.append(("error", "Load shedding aktif (lapis 4 dan 5). Notifikasi WhatsApp dikirim ke operator desa."))
elif mode == "SIAGA":
    notif.append(("warning", "Mode Siaga. Lapis 5 diputus dari baterai. Notifikasi WhatsApp dikirim ke operator desa."))
if soc_baterai <= SOC_MIN:
    notif.append(("error", "SOC mencapai batas 20%. Genset cadangan siap dinyalakan."))
if sumur_kritis:
    notif.append(("error", f"Muka air sumur turun {fmt(turun_muka_air)} m, melewati batas aman "
                           f"{fmt(TURUN_MUKA_AIR_AMAN)} m. Pompa berhenti, periksa sumur."))
if tandon_penuh:
    notif.append(("info", "Tandon penuh. Pompa berhenti otomatis."))
if bocor_tinggi:
    notif.append(("warning", f"Selisih debit tandon dan cabang {fmt(selisih_bocor)} m³ per hari "
                             f"({fmt(persen_bocor)}%). Dugaan kebocoran jaringan."))
if persen_tandon < BATAS_P3:
    notif.append(("warning", f"Level tandon {fmt(persen_tandon * 100, 0)}%. Zona dikurangi: {zona_teks}."))
for w, nama, isi in st.session_state.laporan[-3:]:
    notif.append(("info", f"Laporan warga ({w}) dari {nama}: {isi}"))
if not notif:
    st.success("Tidak ada peringatan. Sistem berjalan normal.")
for jenis, teks in notif:
    getattr(st, jenis)(teks)

# ---- Gauge
st.divider()
st.markdown("### 📊 Indikator Utama")
g1, g2 = st.columns(2)
with g1:
    fig_bat = go.Figure(go.Indicator(
        mode="gauge+number", value=soc_baterai,
        number={"suffix": "%", "font": {"size": 36}},
        title={"text": "Baterai LFP 70 kWh", "font": {"size": 16}},
        gauge={"axis": {"range": [0, 100]}, "bar": {"color": "#2980B9"},
               "steps": [{"range": [0, 20], "color": "#FADBD8"},
                         {"range": [20, 50], "color": "#FCF3CF"},
                         {"range": [50, 100], "color": "#D5F5E3"}],
               "threshold": {"line": {"color": "#E74C3C", "width": 4},
                             "thickness": 0.75, "value": SOC_MIN}}))
    fig_bat.update_layout(height=290, margin=dict(t=50, b=10, l=25, r=25))
    tampil(fig_bat)
with g2:
    fig_air = go.Figure(go.Indicator(
        mode="gauge+number", value=level_tandon,
        number={"suffix": " m³", "font": {"size": 36}},
        title={"text": "HydroBank Tandon 80 m³", "font": {"size": 16}},
        gauge={"axis": {"range": [0, KAP_TANDON]}, "bar": {"color": "#2471A3"},
               "steps": [{"range": [0, KAP_TANDON * BATAS_P2], "color": "#FADBD8"},
                         {"range": [KAP_TANDON * BATAS_P2, KAP_TANDON * BATAS_P3], "color": "#FCF3CF"},
                         {"range": [KAP_TANDON * BATAS_P3, KAP_TANDON], "color": "#D6EAF8"}],
               "threshold": {"line": {"color": "#E74C3C", "width": 4},
                             "thickness": 0.75, "value": KAP_TANDON * BATAS_P2}}))
    fig_air.update_layout(height=290, margin=dict(t=50, b=10, l=25, r=25))
    tampil(fig_air)

# ---- HydroBank detail
st.divider()
st.markdown("### 💧 HydroBank Kemarau")
h1, h2 = st.columns(2)
with h1:
    st.markdown("**Status zona prioritas**")
    zona_df = pd.DataFrame({
        "Zona": ["P1 Air minum", "P2 Ternak", "P3 Irigasi tetes (Fase 2)"],
        "Status": [status_zona["P1"], status_zona["P2"], status_zona["P3"]],
    })
    tampil(zona_df, kind="df")
    st.caption(f"Pompa: {status_pompa}. Muka air sumur turun {fmt(turun_muka_air)} m "
               f"(batas aman {fmt(TURUN_MUKA_AIR_AMAN)} m).")
with h2:
    st.markdown("**Neraca empat meter debit (m³ per hari)**")
    debit_df = pd.DataFrame({
        "Titik ukur": ["Keluar pompa", "Keluar tandon", "Cabang P1", "Cabang P2"],
        "Debit": [fmt(debit_pompa), fmt(debit_tandon), fmt(debit_p1), fmt(debit_p2)],
    })
    tampil(debit_df, kind="df")
    st.caption(f"Selisih tandon dan cabang: {fmt(selisih_bocor)} m³ ({fmt(persen_bocor)}%). "
               + ("🔴 Dugaan kebocoran." if bocor_tinggi else "🟢 Normal."))

# ---- Wallet
st.divider()
st.markdown("### 💰 Tenun dan Panen Wallet")

w1, w2, w3, w4 = st.columns(4)
df_kk = semua_kk()
with w1:
    st.metric("Total Saldo Barter", rp(df_kk["saldo_barter"].sum()))
with w2:
    st.metric("Total Saldo Tunai", rp(df_kk["saldo_tunai"].sum()))
with w3:
    st.metric("Kas O&M (tunai token)", rp(kas_om()))
with w4:
    st.metric("KK Aktif", f"{int((df_kk['status_token'] == 'Aktif').sum())} dari {len(df_kk)}")

df_view = pd.DataFrame({
    "ID": df_kk["id"],
    "Nama KK": df_kk["nama_kk"],
    "Saldo Barter": df_kk["saldo_barter"].map(rp),
    "Saldo Tunai": df_kk["saldo_tunai"].map(rp),
    "Sisa Batas Barter Bulan Ini": (BATAS_BARTER - df_kk["barter_terpakai"]).clip(lower=0).map(rp),
    "Terakhir Bayar": df_kk["terakhir_bayar"],
    "Status Token": df_kk["status_token"],
})
tampil(df_view, kind="df")
st.caption(f"Batas barter {fmt(BATAS_BARTER_PERSEN * 100, 0)}% dari tarif acuan {rp(TARIF_ACUAN)} "
           f"= {rp(BATAS_BARTER)} per KK per bulan. Batas dicek saat saldo dipakai membeli token.")

st.markdown("**Valuasi hasil bumi dan tenun (dicatat operator di KDMP)**")
with st.form("form_valuasi", clear_on_submit=True):
    f1, f2, f3 = st.columns(3)
    with f1:
        kk_val = st.selectbox(
            "KK penyetor", options=df_kk["id"].tolist(),
            format_func=lambda x: df_kk.loc[df_kk["id"] == x, "nama_kk"].values[0],
            key="kk_val")
    with f2:
        komoditas = st.selectbox("Komoditas", list(KOMODITAS.keys()))
    with f3:
        jumlah = st.number_input("Jumlah (kg atau lembar)", 0.0, 10_000.0, 10.0, step=1.0)
    simpan = st.form_submit_button("Catat dan tambahkan ke saldo barter")
if simpan and jumlah > 0:
    nilai = catat_hasil_bumi(kk_val, komoditas, jumlah)
    satuan, harga = KOMODITAS[komoditas]
    nama_kk = df_kk.loc[df_kk["id"] == kk_val, "nama_kk"].values[0]
    st.session_state.pesan_valuasi = (
        f"Tercatat: {nama_kk} menyetor {fmt(jumlah, 0)} {satuan} {komoditas.lower()} "
        f"senilai {rp(nilai)} (harga contoh {rp(harga)} per {satuan}).")
    st.rerun()
if st.session_state.pesan_valuasi:
    st.success(st.session_state.pesan_valuasi)
st.caption("Harga komoditas adalah contoh. Gunakan harga pasar desa pada penerapan nyata.")

stok = tabel_stok()
stok_view = pd.DataFrame({
    "Komoditas": stok["komoditas"],
    "Stok di KDMP": [f"{fmt(j, 0)} {s}" for j, s in zip(stok["jumlah"], stok["satuan"])],
})
tampil(stok_view, kind="df")
st.caption("Desain membatasi stok maksimal satu bulan agar margin jual kembali terjaga.")

# ---- Riwayat (ilustrasi)
st.divider()
st.markdown("### 📈 Riwayat Produksi PV dan Beban (7 Hari, Data Ilustrasi)")
rng_h = np.random.default_rng(99)
hari = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"]
pv_h = [float(np.clip(PV_REF_KWH * rng_h.uniform(0.45, 0.95), 15, 95)) for _ in range(7)]
beban_h = [float(rng_h.uniform(70, 91)) for _ in range(7)]
fig_h = go.Figure()
fig_h.add_trace(go.Bar(x=hari, y=pv_h, name="Produksi PV (kWh)", marker_color="#F39C12"))
fig_h.add_trace(go.Scatter(x=hari, y=beban_h, name="Beban harian (kWh)", mode="lines+markers",
                           line=dict(color="#2C3E50", width=2.5), marker=dict(size=7)))
fig_h.add_hline(y=PV_KRITIS_KWH, line_dash="dot", line_color="#E74C3C",
                annotation_text=f"Batas kritis {PV_KRITIS_KWH:.0f} kWh",
                annotation_position="bottom right")
fig_h.update_layout(height=320, margin=dict(t=30, b=30), yaxis_title="kWh",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5))
tampil(fig_h)
st.caption("Data ilustrasi untuk menunjukkan tampilan, bukan hasil pengukuran.")

# ---- Simulasi WhatsApp bot
st.divider()
st.markdown("### 💬 Simulasi Chat Warga (WhatsApp Bot)")
kk_row = ambil_kk(kk_terpilih)
nama_kk = kk_row["nama_kk"]
st.caption(f"Mengirim sebagai: **{nama_kk}**. Perintah: SALDO, CEK AIR, STATUS, BELI 50000, LAPOR")


def proses_perintah(cmd: str, id_kk: int) -> str:
    c = " ".join(cmd.strip().upper().split())
    kk = ambil_kk(id_kk)
    if c in ("CEK SALDO", "SALDO"):
        sisa = max(0.0, BATAS_BARTER - kk["barter_terpakai"])
        return (f"Halo, {html.escape(kk['nama_kk'])}.<br>"
                f"Saldo barter: {rp(kk['saldo_barter'])}<br>"
                f"Saldo tunai: {rp(kk['saldo_tunai'])}<br>"
                f"Sisa batas barter bulan ini: {rp(sisa)} dari {rp(BATAS_BARTER)}<br>"
                f"Status token: {kk['status_token']}<br>Terakhir bayar: {kk['terakhir_bayar']}")
    if c in ("CEK AIR", "AIR"):
        return (f"Volume tandon: {fmt(level_tandon)} m³ dari 80 m³ ({fmt(persen_tandon * 100, 0)}%)<br>"
                f"Zonasi aktif: {zona_teks}<br>Pompa: {status_pompa}")
    if c == "STATUS":
        return (f"<b>Status sistem hari ini</b><br>Listrik: mode {mode}<br>"
                f"Prediksi PV: {fmt(prediksi_pv)} kWh<br>Baterai: {soc_baterai}%<br>"
                f"Tandon: {fmt(level_tandon)} m³ ({fmt(persen_tandon * 100, 0)}%)<br>"
                f"Pompa: {status_pompa}<br>Lapis aktif: {lapis}")
    if c.startswith("BELI"):
        bagian = c.split()
        angka = bagian[1].replace(".", "") if len(bagian) == 2 else ""
        if angka.isdigit():
            return beli_token(id_kk, int(angka))[1]
        return "Format: BELI [nominal]<br>Contoh: BELI 50000"
    if c.startswith("LAPOR"):
        isi = html.escape(cmd.strip()[5:].strip() or "tanpa keterangan")
        st.session_state.laporan.append((datetime.now(WIB).strftime("%H:%M"),
                                         html.escape(kk["nama_kk"]), isi))
        return ("✅ Terima kasih. Laporan Anda diteruskan ke operator KDMP.<br>"
                "Untuk keadaan darurat, hubungi langsung nomor KDMP.")
    return ("Perintah tidak dikenali. Yang tersedia:<br>"
            "<b>SALDO</b>: cek saldo barter dan tunai<br>"
            "<b>CEK AIR</b>: volume tandon dan status pompa<br>"
            "<b>STATUS</b>: kondisi listrik dan air hari ini<br>"
            "<b>BELI [nominal]</b>: beli token, contoh BELI 50000<br>"
            "<b>LAPOR [pesan]</b>: laporkan gangguan ke operator")


with st.form("form_chat", clear_on_submit=True):
    perintah = st.text_input("Ketik perintah", placeholder="Contoh: SALDO, CEK AIR, STATUS, BELI 50000, LAPOR")
    kirim = st.form_submit_button("Kirim")
if kirim and perintah.strip():
    st.session_state.chat.append(("warga", nama_kk, perintah.strip()))
    st.session_state.chat.append(("bot", "Bot KDMP", proses_perintah(perintah, kk_terpilih)))
    st.rerun()

for peran, nama, isi in st.session_state.chat[-10:]:
    if peran == "warga":
        st.markdown(f'<div class="bubble-warga">📱 <b>{html.escape(nama)}:</b> {html.escape(isi)}</div>',
                    unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="bubble-bot">🤖 <b>{nama}:</b><br>{isi}</div>',
                    unsafe_allow_html=True)
if st.session_state.chat and st.button("Bersihkan percakapan"):
    st.session_state.chat = []
    st.rerun()

# ---- Arsitektur
st.divider()
with st.expander("🔧 Arsitektur IoT dan Alur Data"):
    st.markdown("""
**Alur data dari sensor ke dashboard:**

1. **Sensor lapangan** (level sumur, level tandon, empat meter debit, SOC baterai, produksi PV)
   terhubung ke mikrokontroler atau gateway lokal.
2. **Gateway** menerbitkan data ke broker **Eclipse Mosquitto** lewat protokol MQTT
   (publish dan subscribe). Contoh topik: `desa/tandon/level`, `desa/baterai/soc`.
3. **Backend FastAPI** berlangganan topik itu, memvalidasi data, dan menyimpannya ke **SQLite**.
4. **Model Scikit learn** mengoreksi prakiraan radiasi BMKG dan memperkirakan beban harian.
5. **Dashboard Streamlit** menampilkan hasilnya, dan notifikasi dikirim ke operator desa lewat WhatsApp.

**Pada purwarupa ini** langkah 1 sampai 3 digantikan slider dan input angka di sidebar,
sedangkan aturan keselamatan (batas SOC 20%, proteksi pompa kering) pada sistem nyata
dijalankan oleh pengendali lokal dan inverter, bukan oleh dashboard.
""")

st.markdown(
    '<p class="footer-text">Purwarupa simulasi · Case Study MATRIX UI 2026 · '
    "Surya Sentinel · HydroBank Kemarau · Tenun dan Panen Wallet</p>",
    unsafe_allow_html=True,
)
