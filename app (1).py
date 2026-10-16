"""
============================================================
 SURYA SENTINEL & TENUN WALLET — Command Center
 Purwarupa MVP untuk Case Study MATRIX UI 2026
 Desa Percontohan, Sumba Timur
============================================================
 Stack: Python · Streamlit · FastAPI-ready · Scikit-learn
        Eclipse Mosquitto (MQTT) · SQLite
 Jalankan: streamlit run app.py
============================================================
"""

import streamlit as st
import sqlite3
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
import plotly.graph_objects as go
from datetime import datetime, timezone, timedelta
import random
import os

# Zona waktu WIB (UTC+7), tanpa library tambahan.
# Server cloud memakai UTC, jadi waktu harus diatur manual.
WIB = timezone(timedelta(hours=7))
BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
         "Agustus", "September", "Oktober", "November", "Desember"]


def waktu_wib() -> str:
    t = datetime.now(WIB)
    return f"{t.day} {BULAN[t.month - 1]} {t.year} {t:%H:%M} WIB"

# ============================================================
# 1. KONFIGURASI HALAMAN
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
    /* ---------- header ---------- */
    .main-title {
        font-size: 2.1rem; font-weight: 800; color: #1B3A4B;
        text-align: center; margin-bottom: 0;
    }
    .sub-title {
        font-size: 1rem; color: #5A7184;
        text-align: center; margin-bottom: 1.2rem;
    }

    /* ---------- status banner ---------- */
    .st-normal  { background:#D5F5E3; color:#1B6B3A; padding:1rem;
                   border-radius:0.6rem; text-align:center;
                   font-weight:800; font-size:1.25rem; }
    .st-siaga   { background:#FEF9E7; color:#7D6608; padding:1rem;
                   border-radius:0.6rem; text-align:center;
                   font-weight:800; font-size:1.25rem; }
    .st-darurat { background:#FDEDEC; color:#922B21; padding:1rem;
                   border-radius:0.6rem; text-align:center;
                   font-weight:800; font-size:1.25rem; }

    /* ---------- chat bubbles ---------- */
    .bubble-warga {
        background:#DCF8C6; padding:0.75rem 1rem;
        border-radius:0.8rem 0.8rem 0.8rem 0;
        margin:0.4rem 0; max-width:82%; font-size:0.95rem;
    }
    .bubble-bot {
        background:#FFFFFF; padding:0.75rem 1rem;
        border-radius:0.8rem 0.8rem 0 0.8rem;
        margin:0.4rem 0; max-width:82%;
        border:1px solid #E0E0E0; font-size:0.95rem;
    }

    /* ---------- misc ---------- */
    .footer-text {
        text-align:center; color:#AAA; font-size:0.8rem;
        margin-top:2rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# 2. DATABASE SQLite
# ============================================================
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "koperasi_desa.db")

TARIF_ACUAN   = 99_617       # Rp per KK per bulan
BATAS_BARTER  = 0.30         # 30% dari tarif acuan
BARTER_MAKS   = TARIF_ACUAN * BATAS_BARTER   # Rp 29.885


def init_db():
    """Buat tabel dan isi data contoh bila belum ada."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS kas_koperasi (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            nama_kk         TEXT    NOT NULL,
            saldo_barter    REAL    DEFAULT 0,
            saldo_tunai     REAL    DEFAULT 0,
            terakhir_bayar  TEXT,
            status_token    TEXT    DEFAULT 'Aktif'
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS riwayat_bayar (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            id_kk           INTEGER,
            tanggal         TEXT,
            jumlah_tunai    REAL,
            jumlah_barter   REAL,
            keterangan      TEXT,
            FOREIGN KEY (id_kk) REFERENCES kas_koperasi(id)
        )
    """)

    # Seed 10 KK contoh (sekali saja)
    c.execute("SELECT COUNT(*) FROM kas_koperasi")
    if c.fetchone()[0] == 0:
        seed = [
            ("Keluarga Mbili Praing",  25_000,  75_000, "2026-10-10", "Aktif"),
            ("Keluarga Umbu Ratu",     18_000,  82_000, "2026-10-12", "Aktif"),
            ("Keluarga Rambu Ana",     29_000,  71_000, "2026-10-08", "Aktif"),
            ("Keluarga Umbu Ndilu",     5_000,  45_000, "2026-09-28", "Nonaktif"),
            ("Keluarga Rambu Kaha",    22_000,  78_000, "2026-10-11", "Aktif"),
            ("Keluarga Mbili Hamu",    15_000,  60_000, "2026-10-05", "Aktif"),
            ("Keluarga Umbu Landu",    28_500,  70_500, "2026-10-13", "Aktif"),
            ("Keluarga Rambu Ami",     12_000,  88_000, "2026-10-09", "Aktif"),
            ("Keluarga Umbu Sapu",     20_000,  65_000, "2026-10-07", "Aktif"),
            ("Keluarga Rambu Hiri",     8_000,  55_000, "2026-10-01", "Aktif"),
        ]
        c.executemany(
            "INSERT INTO kas_koperasi "
            "(nama_kk, saldo_barter, saldo_tunai, terakhir_bayar, status_token) "
            "VALUES (?,?,?,?,?)",
            seed,
        )

    conn.commit()
    conn.close()


def get_all_kk() -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM kas_koperasi", conn)
    conn.close()
    return df


def get_kk_by_id(id_kk: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM kas_koperasi WHERE id = ?", (id_kk,))
    row = c.fetchone()
    conn.close()
    return row


# Jalankan sekali saat aplikasi dimuat
init_db()


# ============================================================
# 3. MODEL MACHINE LEARNING (Prediksi Produksi PV)
# ============================================================
@st.cache_resource
def train_pv_model():
    """
    Linear Regression sederhana.
      Input  : tutupan awan (%)
      Output : prediksi produksi PV harian (kWh)

    Data latih sintetis berdasarkan desain PLTS desa:
      PV maks ~ 91 kWh/hari pada langit cerah,
      turun sampai ~ 15 kWh saat tutupan awan 100%.
    """
    rng = np.random.default_rng(42)
    n = 200
    awan = rng.uniform(0, 100, n)
    pv = 91 - 0.76 * awan + rng.normal(0, 4.5, n)
    pv = np.clip(pv, 5, 95)

    model = LinearRegression()
    model.fit(awan.reshape(-1, 1), pv)
    return model


model_pv = train_pv_model()


# ============================================================
# 4. SIDEBAR — INPUT KONTROL OPERATOR
# ============================================================
with st.sidebar:
    st.markdown("## ☀️ Panel Kontrol")
    st.caption("Operator KDMP Desa Percontohan")
    st.divider()

    # --- Prakiraan cuaca ---
    st.markdown("#### 🌤️ Prakiraan Cuaca Besok")
    tutupan_awan = st.slider(
        "Tutupan Awan (%)",
        min_value=0, max_value=100, value=35,
        help="Sumber: prakiraan BMKG atau pengamatan lokal",
    )

    st.divider()

    # --- Kontrol manual ---
    st.markdown("#### ⚙️ Kontrol Manual")
    soc_baterai = st.slider("SOC Baterai LFP (%)", 0, 100, 72)
    level_tandon = st.slider("Level Tandon Air (m³)", 0.0, 80.0, 58.0, step=0.5)

    st.divider()

    # --- Pilih KK untuk simulasi ---
    st.markdown("#### 👤 Simulasi Warga")
    df_kk = get_all_kk()
    kk_terpilih = st.selectbox(
        "Pilih KK",
        options=df_kk["id"].tolist(),
        format_func=lambda x: df_kk.loc[df_kk["id"] == x, "nama_kk"].values[0],
    )


# ============================================================
# 5. LOGIKA SURYA SENTINEL
# ============================================================
prediksi_pv = float(model_pv.predict([[tutupan_awan]])[0])
prediksi_pv = max(5.0, min(95.0, prediksi_pv))

BEBAN_PENUH = 91.3          # kWh total harian (5 lapis)
r_ratio     = prediksi_pv / BEBAN_PENUH

BATAS_NORMAL  = 0.856       # 85,6%
BATAS_DARURAT = 0.48        # 48%

# Tentukan mode berdasarkan R
if r_ratio >= BATAS_NORMAL:
    mode, css, ikon = "NORMAL",  "st-normal",  "🟢"
    lapis   = "Lapis 1 sampai 5 (semua aktif)"
    vfd_pct = 100
    ket     = "Seluruh beban terlayani. Pompa beroperasi penuh."
elif r_ratio >= BATAS_DARURAT:
    mode, css, ikon = "SIAGA",   "st-siaga",   "🟡"
    lapis   = "Lapis 1 sampai 4 (lapis 5 pompa tidak memakai baterai)"
    vfd_pct = 60
    ket     = ("Lapis 5 diputus dari baterai. Pompa hanya jalan dari surplus "
               "PV siang hari dengan kecepatan 60%.")
else:
    mode, css, ikon = "DARURAT", "st-darurat", "🔴"
    lapis   = "Lapis 1 sampai 3 saja (lapis 4 UMKM dan lapis 5 pompa diputus dari baterai)"
    vfd_pct = 30
    ket     = ("Pemutusan beban aktif! Hanya beban esensial yang dilayani. "
               "Pompa diturunkan ke 30% dan hanya memakai surplus PV.")

# Override: jika prediksi < 40 kWh selalu masuk DARURAT
if prediksi_pv < 40:
    mode, css, ikon = "DARURAT", "st-darurat", "🔴"
    lapis   = "Lapis 1 sampai 3 saja (lapis 4 UMKM dan lapis 5 pompa diputus dari baterai)"
    vfd_pct = 30
    ket     = ("Produksi PV di bawah 40 kWh! Pemutusan beban aktif. "
               "Pompa diturunkan ke 30% dan hanya memakai surplus PV.")

# Zonasi HydroBank
persen_tandon = level_tandon / 80.0
if persen_tandon < 0.15:
    zona_teks = "Prioritas 1 saja (air minum)"
    zona_ikon = "🔴"
elif persen_tandon < 0.30:
    zona_teks = "Prioritas 1 dan 2 (air minum dan ternak)"
    zona_ikon = "🟡"
else:
    zona_teks = "Semua zona aktif (air minum, ternak, irigasi)"
    zona_ikon = "🟢"


# ============================================================
# 6. TAMPILAN UTAMA
# ============================================================
st.markdown(
    '<p class="main-title">☀️ Surya Sentinel & Tenun Wallet</p>',
    unsafe_allow_html=True,
)
st.markdown(
    '<p class="sub-title">'
    "Command Center KDMP · Desa Percontohan, Sumba Timur · "
    f"{waktu_wib()}"
    "</p>",
    unsafe_allow_html=True,
)

# ---------- Baris metrik utama ----------
m1, m2, m3, m4 = st.columns(4)
with m1:
    st.metric(
        "Prediksi PV Besok",
        f"{prediksi_pv:.1f} kWh",
        delta=f"{prediksi_pv - BEBAN_PENUH:.1f} dari beban penuh",
    )
with m2:
    st.metric("SOC Baterai", f"{soc_baterai}%")
    if soc_baterai > 20:
        st.caption("🟢 Aman (di atas batas 20%)")
    else:
        st.caption("🔴 Kritis (genset siap menyala)")
with m3:
    st.metric("Level Tandon", f"{level_tandon:.1f} m³")
    st.caption(f"{persen_tandon*100:.0f}% dari kapasitas 80 m³")
with m4:
    st.metric("Pompa VFD", f"{vfd_pct}%")
    if vfd_pct == 100:
        st.caption("🟢 Kecepatan penuh")
    else:
        st.caption(f"🟡 Kecepatan diturunkan ke {vfd_pct}%")

# ---------- Banner status Surya Sentinel ----------
st.divider()
st.markdown(
    f'<div class="{css}">{ikon} MODE SURYA SENTINEL: {mode}</div>',
    unsafe_allow_html=True,
)

col_info1, col_info2 = st.columns(2)
with col_info1:
    st.markdown(f"**Lapis aktif:** {lapis}")
    st.markdown(f"**Keterangan:** {ket}")
with col_info2:
    st.markdown(f"**Zonasi air:** {zona_ikon} {zona_teks}")
    st.markdown(f"**R (rasio produksi):** {r_ratio*100:.1f}%")

if mode == "DARURAT":
    st.error(
        "⚠️ PERINGATAN LOAD SHEDDING — "
        "Beban lapis 4 (UMKM tenun) dan lapis 5 (pompa) diputus. "
        "Notifikasi otomatis dikirim ke operator dan warga via WhatsApp."
    )
if soc_baterai <= 20:
    st.error(
        "⚠️ SOC mendekati batas 20%. Genset cadangan siap dinyalakan."
    )


# ============================================================
# 7. GAUGE CHARTS (Plotly)
# ============================================================
st.divider()
st.markdown("### 📊 Indikator Utama")
g1, g2 = st.columns(2)

with g1:
    fig_bat = go.Figure(
        go.Indicator(
            mode="gauge+number+delta",
            value=soc_baterai,
            number={"suffix": "%", "font": {"size": 36}},
            delta={
                "reference": 50,
                "increasing": {"color": "#27AE60"},
                "decreasing": {"color": "#E74C3C"},
            },
            title={"text": "Baterai LFP 70 kWh", "font": {"size": 16}},
            gauge={
                "axis": {"range": [0, 100], "tickwidth": 1},
                "bar": {"color": "#2980B9"},
                "steps": [
                    {"range": [0, 20],  "color": "#FADBD8"},
                    {"range": [20, 50], "color": "#FCF3CF"},
                    {"range": [50, 100],"color": "#D5F5E3"},
                ],
                "threshold": {
                    "line": {"color": "#E74C3C", "width": 4},
                    "thickness": 0.75,
                    "value": 20,
                },
            },
        )
    )
    fig_bat.update_layout(height=290, margin=dict(t=50, b=10, l=25, r=25))
    st.plotly_chart(fig_bat, use_container_width=True)

with g2:
    fig_air = go.Figure(
        go.Indicator(
            mode="gauge+number+delta",
            value=level_tandon,
            number={"suffix": " m³", "font": {"size": 36}},
            delta={
                "reference": 40,
                "increasing": {"color": "#27AE60"},
                "decreasing": {"color": "#E74C3C"},
            },
            title={"text": "HydroBank Tandon 80 m³", "font": {"size": 16}},
            gauge={
                "axis": {"range": [0, 80], "tickwidth": 1},
                "bar": {"color": "#2471A3"},
                "steps": [
                    {"range": [0, 12],  "color": "#FADBD8"},
                    {"range": [12, 24], "color": "#FCF3CF"},
                    {"range": [24, 80], "color": "#D6EAF8"},
                ],
                "threshold": {
                    "line": {"color": "#E74C3C", "width": 4},
                    "thickness": 0.75,
                    "value": 12,
                },
            },
        )
    )
    fig_air.update_layout(height=290, margin=dict(t=50, b=10, l=25, r=25))
    st.plotly_chart(fig_air, use_container_width=True)


# ============================================================
# 8. TABEL KAS KOPERASI
# ============================================================
st.divider()
st.markdown("### 💰 Data Kas Koperasi (Saldo Warga)")

df_view = df_kk.rename(columns={
    "id":             "ID",
    "nama_kk":        "Nama KK",
    "saldo_barter":   "Saldo Barter (Rp)",
    "saldo_tunai":    "Saldo Tunai (Rp)",
    "terakhir_bayar": "Terakhir Bayar",
    "status_token":   "Status Token",
})
st.dataframe(df_view, use_container_width=True, hide_index=True)

# Ringkasan
s1, s2, s3 = st.columns(3)
with s1:
    st.metric("Total Saldo Barter", f"Rp {df_kk['saldo_barter'].sum():,.0f}")
with s2:
    st.metric("Total Saldo Tunai",  f"Rp {df_kk['saldo_tunai'].sum():,.0f}")
with s3:
    aktif = int((df_kk["status_token"] == "Aktif").sum())
    st.metric("KK Aktif", f"{aktif} dari {len(df_kk)}")


# ============================================================
# 9. GRAFIK RIWAYAT PV (7 HARI TERAKHIR — DATA SIMULASI)
# ============================================================
st.divider()
st.markdown("### 📈 Riwayat Produksi PV dan Beban (7 Hari Terakhir)")

rng_hist = np.random.default_rng(99)
hari_label = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"]
pv_hist    = [91 - 0.76 * rng_hist.uniform(10, 70) + rng_hist.normal(0, 3) for _ in range(7)]
pv_hist    = [max(15, min(95, v)) for v in pv_hist]
beban_hist = [rng_hist.uniform(70, 91) for _ in range(7)]

fig_hist = go.Figure()
fig_hist.add_trace(go.Bar(
    x=hari_label, y=pv_hist,
    name="Produksi PV (kWh)",
    marker_color="#F39C12",
))
fig_hist.add_trace(go.Scatter(
    x=hari_label, y=beban_hist,
    name="Beban harian (kWh)",
    mode="lines+markers",
    line=dict(color="#2C3E50", width=2.5),
    marker=dict(size=7),
))
fig_hist.add_hline(
    y=40, line_dash="dot", line_color="#E74C3C",
    annotation_text="Batas Darurat 40 kWh",
    annotation_position="top left",
)
fig_hist.update_layout(
    height=320,
    margin=dict(t=30, b=30),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
    yaxis_title="kWh",
)
st.plotly_chart(fig_hist, use_container_width=True)


# ============================================================
# 10. SIMULASI WHATSAPP BOT
# ============================================================
st.divider()
st.markdown("### 💬 Simulasi Chat Warga (WhatsApp Bot)")

kk_row  = get_kk_by_id(kk_terpilih)
kk_nama = kk_row[1] if kk_row else "Warga"
st.caption(f"Mengirim sebagai: **{kk_nama}**")

perintah = st.text_input(
    "Ketik perintah",
    placeholder="Contoh: CEK SALDO, CEK AIR, STATUS, BELI 50000, LAPOR",
    key="wa_input",
)

if perintah:
    cmd = perintah.strip().upper()

    # Bubble warga
    st.markdown(
        f'<div class="bubble-warga">📱 <b>{kk_nama}:</b> {perintah}</div>',
        unsafe_allow_html=True,
    )

    # ---------- CEK SALDO ----------
    if cmd in ("CEK SALDO", "SALDO"):
        if kk_row:
            balasan = (
                f"Halo, {kk_row[1]}.<br><br>"
                f"Saldo barter : Rp {kk_row[2]:,.0f}<br>"
                f"Saldo tunai  : Rp {kk_row[3]:,.0f}<br>"
                f"Batas barter : Rp {BARTER_MAKS:,.0f} (30% tarif acuan)<br>"
                f"Status token : {kk_row[5]}<br>"
                f"Terakhir bayar: {kk_row[4]}"
            )
        else:
            balasan = "Data tidak ditemukan. Hubungi operator KDMP."

    # ---------- CEK AIR ----------
    elif cmd in ("CEK AIR", "AIR"):
        balasan = (
            f"Volume tandon: {level_tandon:.1f} m³ dari 80 m³ "
            f"({persen_tandon*100:.0f}%)<br>"
            f"Zonasi aktif: {zona_teks}<br>"
            f"Kecepatan pompa: {vfd_pct}%"
        )

    # ---------- STATUS ----------
    elif cmd == "STATUS":
        balasan = (
            f"<b>Status sistem hari ini</b><br><br>"
            f"Listrik : Mode {mode}<br>"
            f"PV prediksi : {prediksi_pv:.1f} kWh<br>"
            f"Baterai : {soc_baterai}%<br>"
            f"Tandon  : {level_tandon:.1f} m³ ({persen_tandon*100:.0f}%)<br>"
            f"Pompa   : {vfd_pct}%<br>"
            f"Lapis aktif: {lapis}"
        )

    # ---------- BELI [nominal] ----------
    elif cmd.startswith("BELI"):
        bagian = cmd.split()
        if len(bagian) == 2 and bagian[1].isdigit():
            nominal = int(bagian[1])
            if kk_row:
                barter_pakai = min(kk_row[2], nominal * BATAS_BARTER)
                tunai_butuh  = nominal - barter_pakai
                if barter_pakai > BARTER_MAKS:
                    barter_pakai = BARTER_MAKS
                    tunai_butuh  = nominal - barter_pakai

                if kk_row[3] >= tunai_butuh:
                    kode = (f"{random.randint(1000,9999)} "
                            f"{random.randint(1000,9999)} "
                            f"{random.randint(1000,9999)}")
                    balasan = (
                        f"✅ Token Rp {nominal:,} terbit!<br><br>"
                        f"Barter digunakan : Rp {barter_pakai:,.0f}<br>"
                        f"Tunai dipotong   : Rp {tunai_butuh:,.0f}<br>"
                        f"Kode token: <b>{kode}</b><br><br>"
                        f"Masukkan kode ke meter prabayar Anda."
                    )
                else:
                    kurang = tunai_butuh - kk_row[3]
                    balasan = (
                        f"❌ Saldo tidak cukup.<br>"
                        f"Tunai dibutuhkan : Rp {tunai_butuh:,.0f}<br>"
                        f"Saldo tunai Anda : Rp {kk_row[3]:,.0f}<br>"
                        f"Kekurangan : Rp {kurang:,.0f}<br><br>"
                        f"Tambah setoran tunai atau barter di KDMP."
                    )
            else:
                balasan = "Data KK tidak ditemukan."
        else:
            balasan = "Format: BELI [nominal]<br>Contoh: BELI 50000"

    # ---------- LAPOR ----------
    elif cmd.startswith("LAPOR"):
        balasan = (
            "✅ Terima kasih. Laporan Anda diteruskan ke operator KDMP.<br>"
            "Operator akan merespons dalam 1×24 jam.<br>"
            "Untuk darurat, hubungi langsung nomor KDMP."
        )

    # ---------- TIDAK DIKENALI ----------
    else:
        balasan = (
            "Perintah tidak dikenali. Yang tersedia:<br><br>"
            "<b>SALDO</b> — Cek saldo barter dan tunai<br>"
            "<b>CEK AIR</b> — Volume tandon dan status pompa<br>"
            "<b>STATUS</b> — Kondisi listrik dan air hari ini<br>"
            "<b>BELI [nominal]</b> — Beli token (contoh: BELI 50000)<br>"
            "<b>LAPOR</b> — Laporkan gangguan ke operator"
        )

    # Bubble bot
    st.markdown(
        f'<div class="bubble-bot">🤖 <b>Bot KDMP:</b><br>{balasan}</div>',
        unsafe_allow_html=True,
    )


# ============================================================
# 11. ARSITEKTUR IoT (INFORMASI)
# ============================================================
st.divider()
with st.expander("🔧 Arsitektur IoT dan Alur Data (klik untuk membuka)"):
    st.markdown("""
    **Alur komunikasi data sensor ke dashboard:**

    1. **Sensor lapangan** (level sumur, level tandon, 4 meter debit,
       SOC baterai, produksi PV) terhubung ke mikrokontroler atau
       gateway lokal.
    2. **Gateway** menerbitkan data ke broker **Eclipse Mosquitto**
       melalui protokol MQTT (publish/subscribe).
       Contoh topik: `desa/tandon/level`, `desa/baterai/soc`.
    3. **Backend FastAPI** berlangganan topik tersebut, memvalidasi
       data, dan menyimpannya ke **SQLite**.
    4. **Model Scikit-learn** di backend mengoreksi prakiraan radiasi
       BMKG dan memperkirakan beban harian dari riwayat pemakaian.
    5. **Streamlit dashboard** menampilkan hasilnya secara waktu nyata,
       dan notifikasi dikirim ke operator serta warga via WhatsApp.

    **Mengapa MQTT?**
    Header paket minimal 2 byte, sangat hemat bandwidth, cocok untuk
    jaringan seluler terbatas di Sumba Timur. Mosquitto cukup ringan
    untuk berjalan pada satu komputer mini di kantor KDMP.
    """)


# ============================================================
# FOOTER
# ============================================================
st.markdown(
    '<p class="footer-text">'
    "Purwarupa MVP · Case Study MATRIX UI 2026 · "
    "Surya Sentinel · HydroBank Kemarau · Tenun dan Panen Wallet"
    "</p>",
    unsafe_allow_html=True,
)
