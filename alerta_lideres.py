#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ALERTA LÍDERES — FIBONACCI + 5 VELAS VERDES

1. Fibonacci confirmación LONG (monedas líderes)
2. 5 velas verdes después de suelo (señal grupal, mínimo 3 monedas)
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from io import StringIO

import pandas as pd
import requests


# ============================================================
# CARGAR SECRETOS
# ============================================================

def _cargar_secretos():
    data = {}
    if os.path.exists("secretos.json"):
        try:
            with open("secretos.json", "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
    if not data:
        raw = os.getenv("SECRETOS_JSON")
        if raw:
            try:
                data = json.loads(raw)
            except Exception:
                data = {}
    real_a_alias = dict(data)
    alias_a_real = {v: k for k, v in data.items()}
    return alias_a_real, real_a_alias


ALIAS_A_REAL, REAL_A_ALIAS = _cargar_secretos()


def _cargar_recolectores_urls():
    raw = os.getenv("RECOLECTORES_URLS")
    if raw:
        try:
            return json.loads(raw)
        except Exception:
            pass
    return {}


RECOLECTORES_URLS = _cargar_recolectores_urls()


def _cargar_fibo_niveles():
    raw = os.getenv("FIBO_NIVELES")
    if raw:
        try:
            return json.loads(raw)
        except Exception as e:
            print(f"⚠️ Error al leer FIBO_NIVELES: {e}")
    print("⚠️ FIBO_NIVELES no encontrado. Fibonacci desactivado.")
    return {}


FIBO_NIVELES = _cargar_fibo_niveles()


def a_alias(real):
    if not real:
        return real
    return REAL_A_ALIAS.get(str(real).strip().upper(), str(real).strip().upper())


def a_real(alias):
    if not alias:
        return alias
    return ALIAS_A_REAL.get(str(alias).strip(), str(alias).strip())


# ============================================================
# GRUPOS DE MONEDAS
# ============================================================

# Líderes (Fibonacci)
GRUPO_RAPIDO  = {"xkr1", "xkq4", "xkr2", "xkr3"}   # BAT, CC, FUN, DOG
GRUPO_LENTO   = {"xkv", "xkr4", "xkr5", "xkr6"}    # W, CAP, BR, SKR
GRUPO_BIMODAL = {"xkr7", "xkr8", "xkr9"}            # BTW, HUMA, STONK
TODAS_LIDERES = GRUPO_RAPIDO | GRUPO_LENTO | GRUPO_BIMODAL

# Monedas que funcionan con 5 velas verdes (134 monedas)
MONEDAS_5_VELAS = {
    # Originales del JSON
    "xky",    # AGT
    "xkq1",   # Q
    "xkq9",   # SUPER
    "xkq6",   # FTT
    "xkt",    # EIGEN
    "xku",    # ETHFI
    "xka",    # PEPE
    "xkb",    # BONK
    "xkZ",    # WIF
    "xkD",    # SHIB
    "xkF",    # BCH
    "xkA",    # LINK
    "xk5",    # XRP
    "xk4",    # BNB
    "xk9",    # DOT
    "xkj",    # AAVE
    "xkn",    # COMP
    "xkE",    # LTC
    "xkG",    # TRX
    "xk6",    # ADA
    "xk8",    # AVAX
    "xkR",    # SUI
    "xkL",    # NEAR
    "xkM",    # APT
    "xkN",    # FIL
    "xkQ",    # INJ
    "xkT",    # TIA
    "xkV",    # STRK
    "xkW",    # ONDO
    "xkX",    # JUP
    "xkY",    # ENA
    "xke",    # FET
    "xkf",    # IMX
    "xki",    # GRT
    "xkl",    # CRV
    "xkm",    # SNX
    "xkp",    # 1INCH
    "xkr",    # LDO
    "xkv",    # W
    "xk0",    # LIT
    "xkq3",   # SOON
    "xkq4",   # CC
    "xkqe",   # SYRUP
    "xkqf",   # RAY
    "xkqg",   # MET
    # Nuevas (del JSON ampliado)
    "xkr1",   # BAT
    "xkr5",   # BR
    "xkr9",   # STONK
    "xkr10",  # RAIN
    "xkr11",  # TIBBIR
    "xkr12",  # TAG
    "xkr14",  # SOXLB
    "xkr15",  # VVV
    "xkr16",  # GENIUS
    "xkr17",  # ZEC
    "xkr18",  # MAGMA
    "xkr19",  # KNTQ
    "xkr20",  # M
    "xkr21",  # COW
    "xkr22",  # PREDICT
    "xkr23",  # RSR
    "xkr24",  # TEL
    "xkr25",  # NPC
    "xkr26",  # PENDLE
    "xkr27",  # JASMY
    "xkr28",  # ORDI
    "xkr29",  # ALT
    "xkr30",  # SKY
    "xkr31",  # UB
    "xkr32",  # ZRO
    "xkr33",  # FLOKI
    "xkr34",  # POL
    "xkr35",  # DIEM
    "xkr36",  # ZAMA
    "xkr37",  # LUNC
    "xkr38",  # EDGE
    "xkr39",  # RUNE
    "xkr40",  # SN51
    "xkr41",  # 币安人生
    "xkr42",  # FLUID
    "xkr43",  # NIGHT
    "xkr44",  # TRUMP
    "xkr45",  # MNT
    "xkr46",  # STX
    "xkr47",  # PLUME
    "xkr48",  # DEEP
    "xkr49",  # ZETA
    "xkr50",  # AXS
    "xkr51",  # NMR
    "xkr52",  # PEARL
    "xkr53",  # PROM
    "xkr54",  # BABY
    "xkr55",  # BDX
    "xkr56",  # BOME
    "xkr57",  # GALA
    "xkr58",  # MANA
    "xkr59",  # TWT
    "xkr60",  # AXL
    "xkr61",  # WEMIX
    "xkr62",  # KMNO
    "xkr63",  # KAIA
    "xkr64",  # CARDS
    "xkr65",  # HBAR
    "xkr66",  # WIN
    "xkr67",  # MSTRB
    "xkr68",  # EGLD
    "xkr69",  # MSTRX
    "xkr70",  # VIRTUAL
    "xkr71",  # NFT
    "xkr72",  # BEAM
    "xkr73",  # ASTER
    "xkr74",  # CHZ
    "xkr75",  # ZK
    "xkr76",  # KITE
    "xkr77",  # CVX
    "xkr78",  # RED
    "xkr79",  # IOTA
    "xkr80",  # ICP
    "xkr81",  # APE
    "xkr82",  # GRASS
    "xkr83",  # FLR
    "xkr84",  # CATE
    "xkr85",  # MX
    "xkr86",  # A
    "xkr87",  # CT
    "xkr88",  # GMX
    "xkr89",  # SUN
    "xkr90",  # CFX
    "xkr91",  # JST
    "xkr92",  # GAS
    "xkr93",  # JSM
    "xkr94",  # AWE
    "xkr95",  # SLX
    "xkr96",  # APEPE
}

ALIAS_BTC = "xk1"

# ============================================================
# UMBRALES — FIBONACCI
# ============================================================

FIBO_TOL_TOQUE   = 1.5
FIBO_VENTANA_H   = 4
FIBO_REBOTE_MIN  = 1.5
FIBO_CIERRE_TOL  = 0.5
FIBO_MAX_CIERRES = 0.30
FIBO_N_CONSEC    = 2

COOLDOWN_FIBO    = 4

# ============================================================
# UMBRALES — 5 VELAS VERDES
# ============================================================

VELAS_VERDES_N          = 5
VELAS_VERDES_VENTANA    = 15
VELAS_VERDES_RESULTADO  = 30
COOLDOWN_5_VELAS        = 2
MIN_MONEDAS_GRUPAL      = 3

MC_MIN           = 50_000_000
MC_MAX           = 5_000_000_000
RANK_MAX         = 300

ALERTAS_STATE_FILE = "alertas_lideres_state.json"


# ============================================================
# TELEGRAM
# ============================================================

def enviar_telegram(msg):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("⚠️ Telegram no configurado")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    for intento in range(2):
        try:
            r = requests.post(url, data={"chat_id": chat_id, "text": msg}, timeout=20)
            if r.status_code == 200 and r.json().get("ok", False):
                return True
        except Exception as e:
            print(f"Error Telegram (intento {intento+1}): {e}")
    return False


# ============================================================
# CARGA DE DATOS
# ============================================================

def normalizar_symbol(df, nombre_recolector):
    if "symbol" not in df.columns:
        return df
    muestra = df["symbol"].astype(str).str.strip().str.upper().head(100)
    es_alias = muestra.str.startswith("XK").mean() > 0.5
    if es_alias:
        print(f"   {nombre_recolector}: usa ALIAS")
    else:
        print(f"   {nombre_recolector}: usa NOMBRES REALES → traducidos a alias")
        df["symbol"] = df["symbol"].astype(str).str.strip().str.upper().map(lambda s: a_alias(s))
    return df


def cargar_datos():
    dfs = []
    for nombre, url in RECOLECTORES_URLS.items():
        try:
            r = requests.get(url, timeout=30, headers={
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
            })
            r.raise_for_status()
            df = pd.read_csv(StringIO(r.text), low_memory=False)
            df["_fuente"] = nombre
            df = normalizar_symbol(df, nombre)
            dfs.append(df)
            print(f"✅ {nombre}: {len(df):,} filas")
        except Exception as e:
            print(f"⚠️ {nombre}: {str(e)[:80]}")

    if not dfs:
        sys.exit("❌ No se pudo cargar ningún CSV")

    df = pd.concat(dfs, ignore_index=True)
    df["timestamp"] = pd.to_datetime(
        df["timestamp"], utc=True, errors="coerce", format="mixed"
    )

    for c in ["price", "volume_24h", "percent_change_24h", "cmc_rank", "market_cap"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    df = df.dropna(subset=["timestamp", "price", "symbol"])
    df = df[df["price"] > 0]
    df = df.drop_duplicates(subset=["timestamp", "symbol"], keep="last")
    df = df.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
    return df


# ============================================================
# ESTADO
# ============================================================

def cargar_alertas_state():
    if not os.path.exists(ALERTAS_STATE_FILE):
        return {}
    try:
        with open(ALERTAS_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def guardar_alertas_state(state):
    try:
        with open(ALERTAS_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def paso_cooldown(state, symbol, tipo, horas):
    sym_state = state.get(symbol, {})
    ultimo = sym_state.get(tipo)
    if not ultimo:
        return True
    try:
        t = datetime.fromisoformat(ultimo)
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - t).total_seconds() / 3600 >= horas
    except Exception:
        return True


def registrar_alerta(state, symbol, tipo):
    if symbol not in state:
        state[symbol] = {}
    state[symbol][tipo] = datetime.now(timezone.utc).isoformat()


# ============================================================
# HELPERS
# ============================================================

def es_fresco(ts_max, minutos=60):
    ahora = datetime.now(timezone.utc)
    if ts_max.tzinfo is None:
        ts_max = ts_max.replace(tzinfo=timezone.utc)
    return (ahora - ts_max).total_seconds() / 60 <= minutos


def cumple_calidad(mc, rank):
    if mc < MC_MIN or mc > MC_MAX:
        return False
    if rank > RANK_MAX:
        return False
    return True


# ============================================================
# FIBONACCI — confirmación LONG
# ============================================================

def _velas_5m_fibo(df, symbol, ts_desde, ts_hasta):
    g = df[(df["symbol"] == symbol) &
           (df["timestamp"] >= ts_desde) &
           (df["timestamp"] <= ts_hasta)].sort_values("timestamp")
    if len(g) == 0:
        return None
    v = (g.set_index("timestamp")["price"]
         .resample("5min")
         .agg(["first", "max", "min", "last"])
         .dropna())
    v.columns = ["open", "high", "low", "close"]
    return v


def confirmar_long_en_nivel_fibo(df, symbol, nivel_valor):
    TOL_TOQUE   = FIBO_TOL_TOQUE
    VENTANA_H   = FIBO_VENTANA_H
    REBOTE_MIN  = FIBO_REBOTE_MIN
    CIERRE_TOL  = FIBO_CIERRE_TOL
    MAX_CIERRES = FIBO_MAX_CIERRES
    N_CONSEC    = FIBO_N_CONSEC

    g = df[df["symbol"] == symbol].sort_values("timestamp")
    if len(g) < 40:
        return None
    ts_max = g["timestamp"].max()
    if not es_fresco(ts_max):
        return None
    p_actual = float(g.iloc[-1]["price"])
    if nivel_valor <= 0 or p_actual <= 0:
        return None

    corte = ts_max - timedelta(hours=VENTANA_H)
    rec = g[g["timestamp"] >= corte]
    if len(rec) < 6:
        return None
    p_min_ventana = float(rec["price"].min())
    dist_toque = abs(p_min_ventana - nivel_valor) / nivel_valor * 100
    if dist_toque > TOL_TOQUE:
        return None
    ts_toque = rec.loc[rec["price"].idxmin(), "timestamp"]

    rebote_pct = (p_actual - nivel_valor) / nivel_valor * 100
    if rebote_pct < REBOTE_MIN:
        return None

    velas = _velas_5m_fibo(df, symbol, ts_toque - timedelta(minutes=10), ts_max)
    if velas is None or len(velas) < N_CONSEC + 2:
        return None

    umbral_bajo = nivel_valor * (1 - CIERRE_TOL / 100)
    if int((velas["close"] < umbral_bajo).sum()) > 0:
        return None

    velas_bajo_nivel = int((velas["close"] < nivel_valor).sum())
    if velas_bajo_nivel / len(velas) > MAX_CIERRES:
        return None

    cierres_sobre = (velas["close"] > nivel_valor).astype(int)
    max_consec, actual = 0, 0
    for v in cierres_sobre:
        if v == 1:
            actual += 1
            max_consec = max(max_consec, actual)
        else:
            actual = 0
    if max_consec < N_CONSEC:
        return None

    p_max_post = float(velas["high"].max())
    rebote_max = (p_max_post - nivel_valor) / nivel_valor * 100

    return {
        "symbol": symbol, "estado": "LONG_CONFIRMADO",
        "nivel_valor": nivel_valor, "precio": p_actual,
        "rebote_pct": rebote_pct, "rebote_max_pct": rebote_max,
        "p_min_ventana": p_min_ventana, "dist_toque_pct": dist_toque,
        "distancia": dist_toque,
        "velas_5m_total": len(velas),
        "velas_bajo_nivel": velas_bajo_nivel,
        "velas_consecutivas_ok": max_consec,
        "ts_toque": ts_toque,
    }


def detectar_lider_fibo(df, alias):
    """Detecta confirmación LONG en niveles Fibonacci para una líder."""
    if alias not in TODAS_LIDERES:
        return None

    nombre_real = a_real(alias)
    niveles = FIBO_NIVELES.get(nombre_real)
    if not niveles:
        return None

    for nombre_nivel, valor in [("0.618", niveles.get("fibo_618")),
                                 ("0.786", niveles.get("fibo_786"))]:
        if not valor or valor <= 0:
            continue

        conf = confirmar_long_en_nivel_fibo(df, alias, valor)
        if conf:
            conf["nivel"] = nombre_nivel
            if alias in GRUPO_RAPIDO:
                conf["grupo"] = "RAPIDA"
            elif alias in GRUPO_LENTO:
                conf["grupo"] = "LENTA"
            else:
                conf["grupo"] = "BIMODAL"
            return conf

    return None


# ============================================================
# 5 VELAS VERDES — DETECCIÓN
# ============================================================

def detectar_5_velas_verdes(df, alias):
    if alias not in MONEDAS_5_VELAS:
        return None

    g = df[df["symbol"] == alias].sort_values("timestamp")
    if len(g) < 50:
        return None

    ts_max = g["timestamp"].max()
    if not es_fresco(ts_max, minutos=30):
        return None

    mc = g.iloc[-1].get("market_cap", 0) or 0
    rank = g.iloc[-1].get("cmc_rank", 9999)
    if not cumple_calidad(mc, rank):
        return None

    velas_5m = (g.set_index("timestamp")["price"]
                .resample("5min").last().dropna())

    if len(velas_5m) < 20:
        return None

    # === VERIFICAR QUE LAS ÚLTIMAS 5 VELAS SEAN VERDES ===
    ultimas_5 = velas_5m.iloc[-5:]
    if len(ultimas_5) < 5:
        return None

    subidas = 0
    for j in range(1, len(ultimas_5)):
        if ultimas_5.iloc[j] > ultimas_5.iloc[j-1]:
            subidas += 1

    if subidas < 4:
        return None

    # === VERIFICAR SUELO RECIENTE ===
    ventana_suelo = velas_5m.iloc[-30:]
    p_min = ventana_suelo.min()
    idx_min = ventana_suelo.idxmin()
    idx_min_pos = velas_5m.index.get_loc(idx_min)

    if idx_min_pos >= len(velas_5m) - 5:
        return None

    # === CALCULAR RESULTADO ===
    precio_rebote = ultimas_5.iloc[-1]
    fecha_rebote = ultimas_5.index[-1]

    idx_rebote = velas_5m.index.get_loc(fecha_rebote)
    idx_fin = min(idx_rebote + VELAS_VERDES_RESULTADO, len(velas_5m) - 1)

    if idx_fin <= idx_rebote:
        return None

    serie_ventana = velas_5m.iloc[idx_rebote:idx_fin + 1]
    precio_max = serie_ventana.max()
    precio_min = serie_ventana.min()

    subida_desde_rebote = (precio_max - precio_rebote) / precio_rebote * 100
    drawdown = (precio_min - precio_rebote) / precio_rebote * 100

    # === FILTROS ===
    if subida_desde_rebote < 1.0:
        return None
    if drawdown < -1.0:
        return None
    # === FIN FILTROS ===

    return {
        "symbol": alias,
        "tipo": "5_VELAS_VERDES",
        "precio_suelo": p_min,
        "fecha_suelo": idx_min,
        "precio_rebote": precio_rebote,
        "fecha_rebote": fecha_rebote,
        "subida_desde_rebote": subida_desde_rebote,
        "drawdown": drawdown,
        "precio_actual": float(g.iloc[-1]["price"]),
        "mc_m": mc / 1e6,
        "rank": int(rank),
    }


# ============================================================
# ALERTAS
# ============================================================

def enviar_alerta_fibo(confirmaciones, btc):
    if not confirmaciones:
        return False

    n = len(confirmaciones)
    if n >= 3:
        titulo = f"🔥 FIBO GRUPAL: {n} LÍDERES"
    else:
        titulo = f"✅ FIBO: {n} LÍDER(ES)"

    msg = f"{titulo}\n"
    msg += "━━━━━━━━━━━━━━━━━━━\n"

    for a in confirmaciones:
        emoji = "🟢" if a["nivel"] == "0.786" else "🟡"
        msg += f"{emoji} {a_real(a['symbol'])} — {a['nivel']} (+{a['rebote_pct']:.2f}%)\n"

    msg += f"\n🚀 Entrada LONG confirmada"
    if btc:
        msg += f"\n⚪ BTC: {btc.get('estado', 'UNKNOWN')}"

    return enviar_telegram(msg)


def enviar_alerta_5_velas(alertas, btc):
    if not alertas:
        return False

    n = len(alertas)
    if n >= 5:
        titulo = f"🔥 SEÑAL FUERTE: {n} MONEDAS"
    else:
        titulo = f"🟢 SEÑAL GRUPAL: {n} MONEDAS"

    msg = f"{titulo}\n"
    msg += "━━━━━━━━━━━━━━━━━━━\n"

    for a in alertas:
        msg += f"🟢 {a_real(a['symbol'])}\n"

    msg += f"\n📊 {n} monedas con 5 velas verdes"
    msg += f"\n🚀 Posible tendencia general"
    if btc:
        msg += f"\n⚪ BTC: {btc.get('estado', 'UNKNOWN')}"

    return enviar_telegram(msg)


# ============================================================
# ANÁLISIS BTC
# ============================================================

def analizar_btc(df):
    g = df[df["symbol"] == ALIAS_BTC].sort_values("timestamp")
    if len(g) < 40:
        return {"estado": "UNKNOWN", "cambio_1h": 0}

    ts_max = g["timestamp"].max()
    corte_1h = ts_max - timedelta(hours=1)
    rec_1h = g[g["timestamp"] >= corte_1h]
    if len(rec_1h) < 3:
        return {"estado": "UNKNOWN", "cambio_1h": 0}

    p_ini_1h = rec_1h.iloc[0]["price"]
    p_fin = g.iloc[-1]["price"]
    cambio_1h = ((p_fin - p_ini_1h) / p_ini_1h) * 100 if p_ini_1h > 0 else 0

    if cambio_1h > 0.5:
        estado = "UP"
    elif cambio_1h < -1.5:
        estado = "DOWN"
    elif cambio_1h < -0.5:
        estado = "DOWN_SOFT"
    else:
        estado = "FLAT"

    return {"estado": estado, "cambio_1h": cambio_1h}


# ============================================================
# MAIN
# ============================================================

def main():
    ahora = datetime.now(timezone.utc)
    ahora_lima = ahora - timedelta(hours=5)

    print(f"\n{'='*60}")
    print(f"📡 ALERTA LÍDERES — {ahora_lima.strftime('%Y-%m-%d %H:%M:%S')} Lima")
    print(f"{'='*60}")

    if not FIBO_NIVELES:
        print("⚠️ FIBO_NIVELES no configurado. Solo se analizarán 5 velas verdes.")

    df = cargar_datos()
    print(f"📊 Total: {len(df):,} filas | {df['symbol'].nunique()} monedas")

    btc = analizar_btc(df)
    print(f"\n🔍 {a_real(ALIAS_BTC)}: {btc['estado']} ({btc['cambio_1h']:+.2f}% 1h)")

    alertas_state = cargar_alertas_state()

    # ============================================================
    # FIBONACCI
    # ============================================================
    if FIBO_NIVELES:
        print(f"\n📡 Escaneando {len(TODAS_LIDERES)} monedas líderes (Fibonacci)...")
        confirmaciones = []
        for alias in TODAS_LIDERES:
            r = detectar_lider_fibo(df, alias)
            if r:
                if not paso_cooldown(alertas_state, r["symbol"], "FIBO", COOLDOWN_FIBO):
                    continue
                confirmaciones.append(r)

        if confirmaciones:
            print(f"   ✅ {len(confirmaciones)} confirmaciones Fibonacci")
            for a in confirmaciones:
                print(f"      {a_real(a['symbol'])} — {a['nivel']} rebote +{a['rebote_pct']:.2f}%")

            if enviar_alerta_fibo(confirmaciones, btc):
                print(f"   📱 Alerta FIBO enviada")
                for a in confirmaciones:
                    registrar_alerta(alertas_state, a["symbol"], "FIBO")
                guardar_alertas_state(alertas_state)
        else:
            print("   ⚪ Sin confirmaciones Fibonacci.")

    # ============================================================
    # 5 VELAS VERDES (GRUPAL - MÍNIMO 3 MONEDAS)
    # ============================================================
    print(f"\n📡 Escaneando {len(MONEDAS_5_VELAS)} monedas (5 velas verdes)...")
    alertas_5v = []
    for alias in MONEDAS_5_VELAS:
        r = detectar_5_velas_verdes(df, alias)
        if r:
            if not paso_cooldown(alertas_state, r["symbol"], "5_VELAS", COOLDOWN_5_VELAS):
                continue
            alertas_5v.append(r)

    # === ALERTA GRUPAL: mínimo 3 monedas ===
    if len(alertas_5v) >= MIN_MONEDAS_GRUPAL:
        print(f"   🟢 SEÑAL GRUPAL: {len(alertas_5v)} monedas con 5 velas verdes")
        for a in alertas_5v:
            print(f"      {a_real(a['symbol'])}")

        if enviar_alerta_5_velas(alertas_5v, btc):
            print(f"   📱 Alerta grupal enviada")
            for a in alertas_5v:
                registrar_alerta(alertas_state, a["symbol"], "5_VELAS")
            guardar_alertas_state(alertas_state)
    elif len(alertas_5v) > 0:
        print(f"   ⚪ Solo {len(alertas_5v)} moneda(s) con 5 velas verdes (sin señal grupal, mínimo {MIN_MONEDAS_GRUPAL})")
    else:
        print("   ⚪ Sin alertas de 5 velas verdes.")

    print(f"\n✅ Análisis completado.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
