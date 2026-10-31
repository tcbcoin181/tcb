#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ALERTA LÍDERES — Detección de SUELOS y TECHOS en monedas clave
Usa la misma lógica de alerta_v6.py (detectar_suelo)
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


def a_alias(real):
    if not real:
        return real
    return REAL_A_ALIAS.get(str(real).strip().upper(), str(real).strip().upper())


def a_real(alias):
    if not alias:
        return alias
    return ALIAS_A_REAL.get(str(alias).strip(), str(alias).strip())


# ============================================================
# GRUPOS DE MONEDAS LÍDERES (SOLO ALIAS)
# ============================================================

GRUPO_RAPIDO  = {"xkr1", "xkq4", "xkr2", "xkr3"}   # BAT, CC, FUN, DOG
GRUPO_LENTO   = {"xkv", "xkr4", "xkr5", "xkr6"}    # W, CAP, BR, SKR
GRUPO_BIMODAL = {"xkr7", "xkr8", "xkr9"}            # BTW, HUMA, STONK
TODAS_LIDERES = GRUPO_RAPIDO | GRUPO_LENTO | GRUPO_BIMODAL

ALIAS_BTC = "xk1"

# ============================================================
# UMBRALES — SUELO (los mismos de alerta_v6.py)
# ============================================================

SUELO_CAIDA_24H_MIN     = -10.0
SUELO_FRENADO_LO        = -1.0
SUELO_FRENADO_HI        = 1.0
SUELO_DIST_MIN_MAX      = 3.0
SUELO_VOL_DECRECIENTE   = 0.75
SUELO_RANGO_COMPRESION  = 0.60

VOL_ABS_MIN             = 500_000

# ============================================================
# UMBRALES — TECHO (inverso al suelo)
# ============================================================

TECHO_SUBIDA_24H_MIN    = 10.0      # subió al menos 10% en 24h
TECHO_FRENADO_LO        = -1.0      # en 4h se estabilizó
TECHO_FRENADO_HI        = 1.0
TECHO_DIST_MAX_MAX      = 3.0       # cerca del máximo de 24h
TECHO_VOL_DECRECIENTE   = 0.75
TECHO_RANGO_COMPRESION  = 0.60

# Cooldowns
COOLDOWN_LIDER          = 4

# Filtros de calidad
MC_MIN                  = 50_000_000
MC_MAX                  = 5_000_000_000
RANK_MAX                = 300

ALERTAS_STATE_FILE      = "alertas_lideres_state.json"


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
# ESTADO PERSISTENTE
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

def es_fresco(ts_max, minutos=30):
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
# DETECCIÓN — SUELO (misma lógica de alerta_v6.py)
# ============================================================

def detectar_suelo(df, alias):
    """Detecta SUELO en una moneda líder (misma lógica de alerta_v6.py)."""
    if alias not in TODAS_LIDERES:
        return None

    g = df[df["symbol"] == alias].sort_values("timestamp")
    if len(g) < 40:
        return None

    ts_max = g["timestamp"].max()
    if not es_fresco(ts_max, minutos=30):
        return None

    mc = g.iloc[-1].get("market_cap", 0) or 0
    rank = g.iloc[-1].get("cmc_rank", 9999)
    if not cumple_calidad(mc, rank):
        return None

    corte_4h  = ts_max - timedelta(hours=4)
    corte_12h = ts_max - timedelta(hours=12)
    corte_24h = ts_max - timedelta(hours=24)
    rec_4h  = g[g["timestamp"] >= corte_4h]
    rec_12h = g[g["timestamp"] >= corte_12h]
    rec_24h = g[g["timestamp"] >= corte_24h]
    if len(rec_4h) < 3 or len(rec_24h) < 5:
        return None

    p_ini_24h = rec_24h.iloc[0]["price"]
    p_actual  = g.iloc[-1]["price"]
    p_ini_4h  = rec_4h.iloc[0]["price"]
    if p_ini_24h <= 0 or p_ini_4h <= 0:
        return None

    cambio_24h = ((p_actual - p_ini_24h) / p_ini_24h) * 100
    cambio_4h  = ((p_actual - p_ini_4h) / p_ini_4h) * 100

    if cambio_24h > SUELO_CAIDA_24H_MIN:
        return None
    if cambio_4h < SUELO_FRENADO_LO or cambio_4h > SUELO_FRENADO_HI:
        return None

    p_min_24h = rec_24h["price"].min()
    if p_min_24h <= 0:
        return None
    dist_min = ((p_actual - p_min_24h) / p_min_24h) * 100
    if dist_min > SUELO_DIST_MIN_MAX:
        return None

    if "volume_24h" not in g.columns:
        return None
    rec_12h_ant = rec_12h[rec_12h["timestamp"] < corte_4h]
    if len(rec_12h_ant) < 3:
        return None

    v_reciente = rec_4h["volume_24h"].iloc[-1]
    v_anterior = rec_12h_ant["volume_24h"].mean()
    if v_anterior <= 0:
        return None
    compresion_vol = v_reciente / v_anterior
    if compresion_vol > SUELO_VOL_DECRECIENTE:
        return None

    rango_reciente = rec_4h["price"].max() - rec_4h["price"].min()
    rango_anterior = (rec_12h_ant["price"].max() - rec_12h_ant["price"].min())
    if rango_anterior <= 0:
        return None
    compresion_rango = rango_reciente / rango_anterior
    if compresion_rango > SUELO_RANGO_COMPRESION:
        return None

    v_ult = g["volume_24h"].iloc[-1]
    if v_ult < VOL_ABS_MIN:
        return None

    # Determinar grupo
    if alias in GRUPO_RAPIDO:
        grupo = "RAPIDA"
    elif alias in GRUPO_LENTO:
        grupo = "LENTA"
    else:
        grupo = "BIMODAL"

    return {
        "tipo": "SUELO",
        "symbol": alias,
        "grupo": grupo,
        "cambio_24h": cambio_24h,
        "cambio_4h": cambio_4h,
        "precio": p_actual,
        "p_min_24h": p_min_24h,
        "dist_min": dist_min,
        "compresion_vol": compresion_vol,
        "compresion_rango": compresion_rango,
        "vol_ratio": compresion_vol,
        "vol_m": v_ult / 1e6,
        "cmc_rank": int(rank),
        "market_cap_m": mc / 1e6,
        "ts": ts_max,
    }


# ============================================================
# DETECCIÓN — TECHO (inverso al suelo)
# ============================================================

def detectar_techo(df, alias):
    """Detecta TECHO en una moneda líder (lógica inversa al suelo)."""
    if alias not in TODAS_LIDERES:
        return None

    g = df[df["symbol"] == alias].sort_values("timestamp")
    if len(g) < 40:
        return None

    ts_max = g["timestamp"].max()
    if not es_fresco(ts_max, minutos=30):
        return None

    mc = g.iloc[-1].get("market_cap", 0) or 0
    rank = g.iloc[-1].get("cmc_rank", 9999)
    if not cumple_calidad(mc, rank):
        return None

    corte_4h  = ts_max - timedelta(hours=4)
    corte_12h = ts_max - timedelta(hours=12)
    corte_24h = ts_max - timedelta(hours=24)
    rec_4h  = g[g["timestamp"] >= corte_4h]
    rec_12h = g[g["timestamp"] >= corte_12h]
    rec_24h = g[g["timestamp"] >= corte_24h]
    if len(rec_4h) < 3 or len(rec_24h) < 5:
        return None

    p_ini_24h = rec_24h.iloc[0]["price"]
    p_actual  = g.iloc[-1]["price"]
    p_ini_4h  = rec_4h.iloc[0]["price"]
    if p_ini_24h <= 0 or p_ini_4h <= 0:
        return None

    cambio_24h = ((p_actual - p_ini_24h) / p_ini_24h) * 100
    cambio_4h  = ((p_actual - p_ini_4h) / p_ini_4h) * 100

    # Inverso al suelo: subió al menos 10% en 24h
    if cambio_24h < TECHO_SUBIDA_24H_MIN:
        return None
    # En 4h se estabilizó
    if cambio_4h < TECHO_FRENADO_LO or cambio_4h > TECHO_FRENADO_HI:
        return None

    # Cerca del máximo de 24h
    p_max_24h = rec_24h["price"].max()
    if p_max_24h <= 0:
        return None
    dist_max = ((p_max_24h - p_actual) / p_max_24h) * 100
    if dist_max > TECHO_DIST_MAX_MAX:
        return None

    # Volumen decreciente
    if "volume_24h" not in g.columns:
        return None
    rec_12h_ant = rec_12h[rec_12h["timestamp"] < corte_4h]
    if len(rec_12h_ant) < 3:
        return None

    v_reciente = rec_4h["volume_24h"].iloc[-1]
    v_anterior = rec_12h_ant["volume_24h"].mean()
    if v_anterior <= 0:
        return None
    compresion_vol = v_reciente / v_anterior
    if compresion_vol > TECHO_VOL_DECRECIENTE:
        return None

    rango_reciente = rec_4h["price"].max() - rec_4h["price"].min()
    rango_anterior = (rec_12h_ant["price"].max() - rec_12h_ant["price"].min())
    if rango_anterior <= 0:
        return None
    compresion_rango = rango_reciente / rango_anterior
    if compresion_rango > TECHO_RANGO_COMPRESION:
        return None

    v_ult = g["volume_24h"].iloc[-1]
    if v_ult < VOL_ABS_MIN:
        return None

    if alias in GRUPO_RAPIDO:
        grupo = "RAPIDA"
    elif alias in GRUPO_LENTO:
        grupo = "LENTA"
    else:
        grupo = "BIMODAL"

    return {
        "tipo": "TECHO",
        "symbol": alias,
        "grupo": grupo,
        "cambio_24h": cambio_24h,
        "cambio_4h": cambio_4h,
        "precio": p_actual,
        "p_max_24h": p_max_24h,
        "dist_max": dist_max,
        "compresion_vol": compresion_vol,
        "compresion_rango": compresion_rango,
        "vol_ratio": compresion_vol,
        "vol_m": v_ult / 1e6,
        "cmc_rank": int(rank),
        "market_cap_m": mc / 1e6,
        "ts": ts_max,
    }


# ============================================================
# ALERTA DE LÍDERES
# ============================================================

def enviar_alerta_lideres(lideres, btc):
    if not lideres:
        return False

    # Separar suelos y techos
    suelos = [a for a in lideres if a["tipo"] == "SUELO"]
    techos = [a for a in lideres if a["tipo"] == "TECHO"]

    msg = "📡 *MONEDAS LÍDERES — SUELOS/TECHOS*\n━━━━━━━━━━━━━━━━━━━\n"

    if suelos:
        msg += f"\n🟢 *SUELOS DETECTADOS: {len(suelos)}*\n"
        for a in suelos[:5]:
            msg += f"   {a_real(a['symbol'])} ({a['grupo']})\n"
            msg += f"   Caída 24h: {a['cambio_24h']:+.2f}% | Frenado 4h: {a['cambio_4h']:+.2f}%\n"
            msg += f"   Vol: {a['compresion_vol']:.2f}x | Rango: {a['compresion_rango']:.2f}x\n\n"

    if techos:
        msg += f"\n🔴 *TECHOS DETECTADOS: {len(techos)}*\n"
        for a in techos[:5]:
            msg += f"   {a_real(a['symbol'])} ({a['grupo']})\n"
            msg += f"   Subida 24h: {a['cambio_24h']:+.2f}% | Frenado 4h: {a['cambio_4h']:+.2f}%\n"
            msg += f"   Vol: {a['compresion_vol']:.2f}x | Rango: {a['compresion_rango']:.2f}x\n\n"

    if btc:
        msg += f"⚪ BTC: {btc.get('estado', 'UNKNOWN')} ({btc.get('cambio_1h', 0):+.2f}% 1h)\n"

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

    df = cargar_datos()
    print(f"📊 Total: {len(df):,} filas | {df['symbol'].nunique()} monedas")

    btc = analizar_btc(df)
    print(f"\n🔍 {a_real(ALIAS_BTC)}: {btc['estado']} ({btc['cambio_1h']:+.2f}% 1h)")

    # === DIAGNÓSTICO DE LÍDERES ===
    print(f"\n🔍 DIAGNÓSTICO DE LÍDERES:")
    print(f"   {'MONEDA':<8} | {'24h%':<8} | {'4h%':<8} | {'dist_min%':<10} | {'dist_max%':<10} | {'vol_ratio':<10} | {'rango_ratio':<11} | {'¿SUELO?':<8} | {'¿TECHO?':<8}")
    print(f"   {'-'*100}")
    
    for alias in sorted(TODAS_LIDERES):
        nombre = a_real(alias)
        g = df[df["symbol"] == alias].sort_values("timestamp")
        if len(g) < 40:
            print(f"   {nombre:<8} | ❌ pocos datos")
            continue
        
        ts_max = g["timestamp"].max()
        edad = (datetime.now(timezone.utc) - ts_max).total_seconds() / 60
        if edad > 30:
            print(f"   {nombre:<8} | ❌ datos viejos ({edad:.0f} min)")
            continue
        
        mc = g.iloc[-1].get("market_cap", 0) or 0
        rank = g.iloc[-1].get("cmc_rank", 9999)
        if not cumple_calidad(mc, rank):
            print(f"   {nombre:<8} | ❌ calidad (MC={mc/1e6:.1f}M, rank={rank})")
            continue
        
        corte_4h = ts_max - timedelta(hours=4)
        corte_12h = ts_max - timedelta(hours=12)
        corte_24h = ts_max - timedelta(hours=24)
        rec_4h = g[g["timestamp"] >= corte_4h]
        rec_12h = g[g["timestamp"] >= corte_12h]
        rec_24h = g[g["timestamp"] >= corte_24h]
        
        if len(rec_4h) < 3 or len(rec_24h) < 5:
            print(f"   {nombre:<8} | ❌ pocas velas (4h={len(rec_4h)}, 24h={len(rec_24h)})")
            continue
        
        p_ini_24h = rec_24h.iloc[0]["price"]
        p_actual = g.iloc[-1]["price"]
        p_ini_4h = rec_4h.iloc[0]["price"]
        if p_ini_24h <= 0 or p_ini_4h <= 0:
            continue
        
        cambio_24h = ((p_actual - p_ini_24h) / p_ini_24h) * 100
        cambio_4h = ((p_actual - p_ini_4h) / p_ini_4h) * 100
        
        p_min_24h = rec_24h["price"].min()
        p_max_24h = rec_24h["price"].max()
        dist_min = ((p_actual - p_min_24h) / p_min_24h) * 100 if p_min_24h > 0 else 999
        dist_max = ((p_max_24h - p_actual) / p_max_24h) * 100 if p_max_24h > 0 else 999
        
        rec_12h_ant = rec_12h[rec_12h["timestamp"] < corte_4h]
        if len(rec_12h_ant) < 3:
            print(f"   {nombre:<8} | ❌ pocas velas 12h_ant")
            continue
        
        v_reciente = rec_4h["volume_24h"].iloc[-1]
        v_anterior = rec_12h_ant["volume_24h"].mean()
        if v_anterior <= 0:
            continue
        compresion_vol = v_reciente / v_anterior
        
        rango_reciente = rec_4h["price"].max() - rec_4h["price"].min()
        rango_anterior = (rec_12h_ant["price"].max() - rec_12h_ant["price"].min())
        if rango_anterior <= 0:
            continue
        compresion_rango = rango_reciente / rango_anterior
        
        cumple_suelo_24h = cambio_24h <= SUELO_CAIDA_24H_MIN
        cumple_suelo_4h = SUELO_FRENADO_LO <= cambio_4h <= SUELO_FRENADO_HI
        cumple_suelo_dist = dist_min <= SUELO_DIST_MIN_MAX
        cumple_suelo_vol = compresion_vol <= SUELO_VOL_DECRECIENTE
        cumple_suelo_rango = compresion_rango <= SUELO_RANGO_COMPRESION
        
        cumple_techo_24h = cambio_24h >= TECHO_SUBIDA_24H_MIN
        cumple_techo_4h = TECHO_FRENADO_LO <= cambio_4h <= TECHO_FRENADO_HI
        cumple_techo_dist = dist_max <= TECHO_DIST_MAX_MAX
        cumple_techo_vol = compresion_vol <= TECHO_VOL_DECRECIENTE
        cumple_techo_rango = compresion_rango <= TECHO_RANGO_COMPRESION
        
        es_suelo = all([cumple_suelo_24h, cumple_suelo_4h, cumple_suelo_dist, cumple_suelo_vol, cumple_suelo_rango])
        es_techo = all([cumple_techo_24h, cumple_techo_4h, cumple_techo_dist, cumple_techo_vol, cumple_techo_rango])
        
        print(f"   {nombre:<8} | {cambio_24h:>+7.2f}% | {cambio_4h:>+7.2f}% | {dist_min:>9.2f}% | {dist_max:>9.2f}% | {compresion_vol:>9.2f}x | {compresion_rango:>10.2f}x | {'✅ SÍ' if es_suelo else '❌ NO':<8} | {'✅ SÍ' if es_techo else '❌ NO':<8}")
    # === FIN DIAGNÓSTICO ===

    alertas_state = cargar_alertas_state()

    print(f"\n📡 Escaneando {len(TODAS_LIDERES)} monedas líderes (suelos y techos)...")
    lideres = []
    for alias in TODAS_LIDERES:
        # Detectar suelo
        r = detectar_suelo(df, alias)
        if r:
            if paso_cooldown(alertas_state, r["symbol"], "SUELO", COOLDOWN_LIDER):
                lideres.append(r)
                print(f"   🟢 SUELO: {a_real(alias)} ({r['grupo']}) — caída {r['cambio_24h']:.2f}%")
            else:
                print(f"   ⏳ {a_real(alias)} SUELO en cooldown")
            continue

        # Detectar techo
        r = detectar_techo(df, alias)
        if r:
            if paso_cooldown(alertas_state, r["symbol"], "TECHO", COOLDOWN_LIDER):
                lideres.append(r)
                print(f"   🔴 TECHO: {a_real(alias)} ({r['grupo']}) — subida {r['cambio_24h']:.2f}%")
            else:
                print(f"   ⏳ {a_real(alias)} TECHO en cooldown")

    if lideres:
        if enviar_alerta_lideres(lideres, btc):
            print(f"   📱 Alerta enviada")
            for a in lideres:
                tipo = "SUELO" if a["tipo"] == "SUELO" else "TECHO"
                registrar_alerta(alertas_state, a["symbol"], tipo)
            guardar_alertas_state(alertas_state)
        else:
            print(f"   ⚠️ No se pudo enviar la alerta")
    else:
        print("   ⚪ Sin suelos ni techos detectados.")

    print(f"\n✅ Análisis completado.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
