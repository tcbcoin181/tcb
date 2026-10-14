#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ALERTA V3 — TCB + ACUMULACIÓN + GRUPOS + BTC-CÉNTRICO

Señales (por prioridad):
  1. 🎯 TCB + BTC soporte  → rebote desde Fibo 0.618-0.786
  2. 🚀 ACUMULACIÓN        → QNT-style (rango comprimido + ruptura)
  3. 🎯 SUELO + BTC soporte → caída fuerte + frenado
  4. 📐 REENTRADA FIBO     → retroceso tras pump
  5. 🟡 ARRANQUE           → momentum con volumen

Filtro BTC (4h):
  - BTC en Fibo 0.618-0.786 + rebotando → señales máximas
  - BTC fuera de soporte → solo ACUMULACIÓN
  - BTC rompió 0.786 → bloqueo total

Sistema de alias: lee secretos.json o SECRETOS_JSON
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from io import StringIO

import numpy as np
import pandas as pd
import requests


# ============================================================
# SISTEMA DE ALIAS
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


def a_alias(real):
    if not real:
        return real
    return REAL_A_ALIAS.get(str(real).strip().upper(), str(real).strip().upper())


def a_real(alias):
    if not alias:
        return alias
    return ALIAS_A_REAL.get(str(alias).strip(), str(alias).strip())


# ============================================================
# URLs
# ============================================================

CSV_URLS = {
    "top100": (
        "https://raw.githubusercontent.com/mattluna3/inspector/"
        "main/data/cmc/market_history_top100.csv"
    ),
    "emerging": (
        "https://raw.githubusercontent.com/mattluna3/inspector/"
        "main/data/cmc/market_history_emerging.csv"
    ),
    "201_300": (
        "https://raw.githubusercontent.com/emerging2/inspector2/"
        "main/data/cmc/market_history_201_300.csv"
    ),
}

EXCLUIR = {
    "xkqy1", "xkqy2", "xkqy3", "xkqy4", "xkqy5", "xkqy6", "xkqy7", "xkqy8",
    "xkqy9", "xkqya", "xkqyb", "xkqyc", "xkqyd", "xkqye", "xkqyf",
    "xkqyg", "xkqyh", "xkqyi", "xkqyj", "xkqyk", "xkqyl", "xkqym", "xkqyn",
    "xkqyo", "xkqyp", "xkqyq", "xkqyr", "xkqys", "xkqyt", "xkqyu", "xkqyv",
    "xkqyw", "xkqyx", "xkqyy", "xkqyz", "xkqy0", "xkqz1", "xkqz2",
}


# ============================================================
# UMBRALES — ARRANQUE
# ============================================================

TEMPRANA_CAMBIO_1H  = 2.5
TEMPRANA_VOL_MIN    = 1.4
TEMPRANA_VOL_MAX    = 1.6

FUERTE_CAMBIO_1H    = 4.0
FUERTE_VOL_MIN      = 1.6

VOL_ABS_MIN         = 500_000

MAX_CAMBIO_4H       = 8.0
MAX_CAMBIO_24H      = 20.0


# ============================================================
# UMBRALES — SUELO
# ============================================================

SUELO_CAIDA_24H_MIN = -10.0
SUELO_FRENADO_LO    = -1.0
SUELO_FRENADO_HI    = 1.0
SUELO_DIST_MIN_MAX  = 3.0
SUELO_VOL_CRECIENTE = 1.2
SUELO_VELOCIDAD_MIN = 15.0
SUELO_RANGO_COMPR   = 0.60


# ============================================================
# UMBRALES — REENTRADA
# ============================================================

PUMP_MIN_PCT        = 30.0
PUMP_VENTANA_H      = 48
FIBO_MIN_REENT      = 38.0
FIBO_MAX_REENT      = 70.0
REBOTE_MIN_PCT      = 5.0
REENTRADA_VOL_MIN   = 1.2


# ============================================================
# UMBRALES — TCB
# ============================================================

TCB_RANGO_MIN       = 15.0
TCB_DUR_RALLY_MIN   = 10
TCB_RATIO_MIN       = 0.5
TCB_RATIO_MAX       = 1.3
TCB_FIBO_MIN        = 0.5
TCB_FIBO_MAX        = 0.786
TCB_VOL_CRECIENTE   = 1.2
TCB_REBOTE_MIN      = 3.0


# ============================================================
# UMBRALES — ACUMULACIÓN
# ============================================================

ACUM_RANGO_MAX      = 15.0
ACUM_POS_RANGO_MIN  = 70.0
ACUM_VOL_CV_MAX     = 0.8
ACUM_DUR_MIN        = 20
ACUM_RUPTURA_MIN    = 5.0


# ============================================================
# UMBRALES — BTC-CÉNTRICO
# ============================================================

BTC_RALLY_DUR_MIN   = 5
BTC_RALLY_RANGO_MIN = 3.0
BTC_FIBO_MIN        = 0.618
BTC_FIBO_MAX        = 0.786
BTC_FIBO_TOLERANCIA = 2.0
BTC_REBOTE_MIN      = 2.0


# ============================================================
# FILTROS COMUNES
# ============================================================

MC_MIN              = 50_000_000
MC_MAX              = 10_000_000_000
RANK_MAX            = 300

BTC_STATE_FILE      = "btc_state.json"
ALERTAS_STATE_FILE  = "alertas_state.json"

COOLDOWN_TCB        = 12
COOLDOWN_ACUM       = 24
COOLDOWN_SUELO      = 12
COOLDOWN_REENTRADA  = 8
COOLDOWN_ARRANQUE   = 6

MAX_TCB             = 2
MAX_ACUM            = 3
MAX_SUELO           = 3
MAX_REENTRADA       = 3
MAX_ARRANQUE        = 3


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
# CARGA
# ============================================================

def cargar_datos():
    dfs = []
    for nombre, url in CSV_URLS.items():
        try:
            r = requests.get(url, timeout=60)
            r.raise_for_status()
            df = pd.read_csv(StringIO(r.text), low_memory=False)
            df["_fuente"] = nombre
            # Alias: nombre real → alias interno
            if REAL_A_ALIAS and "symbol" in df.columns:
                df["symbol"] = (
                    df["symbol"].astype(str).str.strip().str.upper()
                    .map(lambda s: a_alias(s))
                )
            dfs.append(df)
            print(f"✅ {nombre}: {len(df):,} filas")
        except Exception as e:
            print(f"⚠️ {nombre}: {str(e)[:80]}")

    if not dfs:
        sys.exit("❌ No se pudo cargar ningún CSV")

    df = pd.concat(dfs, ignore_index=True)
    df["timestamp"] = pd.to_datetime(
        df["timestamp"], utc=True, errors="coerce", format="ISO8601"
    )

    for c in ["price", "volume_24h", "percent_change_24h", "cmc_rank", "market_cap"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    df = df.dropna(subset=["timestamp", "price", "symbol"])
    df = df[df["price"] > 0]
    df = df.drop_duplicates(subset=["timestamp", "symbol"], keep="last")
    df = df.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
    return df


def hacer_velas(df, vela_min=60):
    """Convierte snapshots en velas OHLC."""
    df = df.copy()
    df["vela"] = df["timestamp"].dt.floor(f"{vela_min}min")
    velas = df.groupby(["symbol", "vela"]).agg(
        open=("price", "first"),
        high=("price", "max"),
        low=("price", "min"),
        close=("price", "last"),
        volume=("volume_24h", "last"),
        rank=("cmc_rank", "last"),
        mc=("market_cap", "last"),
    ).reset_index().sort_values(["symbol", "vela"]).reset_index(drop=True)
    return velas


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


def detectar_pivotes(velas, ventana=5):
    velas = velas.copy()
    velas["es_max"] = False
    velas["es_min"] = False

    for sym, g in velas.groupby("symbol"):
        g = g.sort_values("vela").reset_index(drop=False)
        highs = g["high"].values
        lows = g["low"].values
        n = len(g)

        for i in range(ventana, n - ventana):
            if highs[i] == max(highs[i-ventana:i+ventana+1]):
                velas.loc[g.iloc[i]["index"], "es_max"] = True
            if lows[i] == min(lows[i-ventana:i+ventana+1]):
                velas.loc[g.iloc[i]["index"], "es_min"] = True
    return velas


# ============================================================
# ANÁLISIS BTC
# ============================================================

def analizar_btc(velas_4h):
    """Analiza BTC en 4h: rally, fibos, estado."""
    btc = velas_4h[velas_4h["symbol"] == "xk1"].sort_values("vela").reset_index(drop=True)
    if len(btc) < 20:
        return {"estado": "UNKNOWN", "precio": 0, "fibos": {}}

    ts_max = btc["vela"].max()
    p_actual = btc.iloc[-1]["close"]

    # Rally: últimos 14 días
    inicio = ts_max - timedelta(days=14)
    rango = btc[btc["vela"] >= inicio]

    if len(rango) < 5:
        return {"estado": "UNKNOWN", "precio": p_actual, "fibos": {}}

    p_min = rango["low"].min()
    idx_min = rango["low"].idxmin()
    p_max = rango.loc[idx_min:]["high"].max()
    idx_max = rango.loc[idx_min:]["high"].idxmax()

    if p_min <= 0 or p_max <= p_min:
        return {"estado": "UNKNOWN", "precio": p_actual, "fibos": {}}

    rango_p = p_max - p_min
    rango_pct = (rango_p / p_min) * 100

    # Fibos
    fibos = {
        0.236: p_max - rango_p * 0.236,
        0.382: p_max - rango_p * 0.382,
        0.5: p_max - rango_p * 0.5,
        0.618: p_max - rango_p * 0.618,
        0.786: p_max - rango_p * 0.786,
    }

    # Cambio 1h, 4h
    cambio_1h = 0
    cambio_4h = 0
    if len(btc) >= 2:
        cambio_4h = ((p_actual - btc.iloc[-2]["close"]) / btc.iloc[-2]["close"]) * 100
    if len(btc) >= 2:
        cambio_1h = ((p_actual - btc.iloc[-1]["open"]) / btc.iloc[-1]["open"]) * 100

    # Estado
    fibo_786 = fibos[0.786]
    fibo_618 = fibos[0.618]

    dist_786 = abs(p_actual - fibo_786) / p_max * 100
    dist_618 = abs(p_actual - fibo_618) / p_max * 100

    if p_actual < fibo_786 * 0.98:
        estado = "ROMPIO_786"
    elif dist_786 <= BTC_FIBO_TOLERANCIA:
        if cambio_1h > 0:
            estado = "SOPORTE_786_REBOTANDO"
        else:
            estado = "SOPORTE_786"
    elif dist_618 <= BTC_FIBO_TOLERANCIA:
        estado = "SOPORTE_618"
    else:
        estado = "SIN_SOPORTE"

    return {
        "estado": estado,
        "precio": p_actual,
        "rango_pct": rango_pct,
        "cambio_1h": cambio_1h,
        "cambio_4h": cambio_4h,
        "fibos": fibos,
        "p_min": p_min,
        "p_max": p_max,
    }


def _contexto_btc(btc):
    mapa = {
        "SOPORTE_786_REBOTANDO": ("🟢 xk1: rebote desde 0.786", "🔥 MOMENTO ÓPTIMO"),
        "SOPORTE_786": ("🟡 xk1: en 0.786 — esperando rebote", "⏳ Vigilar"),
        "SOPORTE_618": ("🟡 xk1: en 0.618", "⚠️ Posible corrección mayor"),
        "ROMPIO_786": ("🔴 xk1: rompió 0.786", "🚨 NO ENTRAR"),
        "SIN_SOPORTE": ("⚪ xk1: fuera de soporte", "⚠️ Sin contexto claro"),
        "UNKNOWN": ("❓ xk1: sin datos", ""),
    }
    return mapa.get(btc["estado"], ("⚪ xk1: neutral", ""))


# ============================================================
# ESTADO PERSISTENTE
# ============================================================

def cargar_btc_estado_previo():
    if not os.path.exists(BTC_STATE_FILE):
        return None
    try:
        with open(BTC_STATE_FILE, "r") as f:
            data = json.load(f)
        return data.get("estado")
    except Exception:
        return None


def guardar_btc_estado(estado):
    try:
        with open(BTC_STATE_FILE, "w") as f:
            json.dump({
                "estado": estado,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }, f)
    except Exception:
        pass


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
# DETECCIÓN — TCB
# ============================================================

def detectar_tcb(velas, btc_estado):
    """Detecta patrón TCB: rally + corrección Fibo + rebote."""
    resultados = []

    if btc_estado not in ("SOPORTE_786_REBOTANDO", "SOPORTE_786", "SOPORTE_618"):
        return resultados

    for sym, g in velas.groupby("symbol"):
        if sym == "xk1" or sym in EXCLUIR:
            continue

        g = g.sort_values("vela").reset_index(drop=True)
        if len(g) < 30:
            continue

        # Verificar frescura y calidad
        ts_max = g["vela"].max()
        rank = g.iloc[-1].get("rank", 9999)
        mc = g.iloc[-1].get("mc", 0) or 0
        if not cumple_calidad(mc, rank):
            continue

        # Buscar rally (mín → máx)
        min_idxs = g.index[g["es_min"]].tolist()
        max_idxs = g.index[g["es_max"]].tolist()

        for i_min in min_idxs:
            proximos_max = [j for j in max_idxs if j > i_min]
            if not proximos_max:
                continue
            i_max = proximos_max[0]

            p_min = g.iloc[i_min]["low"]
            p_max = g.iloc[i_max]["high"]

            if p_min <= 0 or p_max <= p_min:
                continue

            rango = p_max - p_min
            rango_pct = (rango / p_min) * 100
            dur_rally = i_max - i_min

            if dur_rally < TCB_DUR_RALLY_MIN or rango_pct < TCB_RANGO_MIN:
                continue

            # Post-máximo
            post = g.iloc[i_max+1:]
            if len(post) < 3:
                continue

            p_actual = g.iloc[-1]["close"]
            min_post = post["low"].min()
            idx_min_post = post["low"].idxmin()
            dur_corr = idx_min_post - i_max

            if dur_rally <= 0:
                continue
            ratio_tiempo = dur_corr / dur_rally

            if ratio_tiempo < TCB_RATIO_MIN or ratio_tiempo > TCB_RATIO_MAX:
                continue

            # Profundidad
            profundidad = (p_max - p_actual) / rango
            if profundidad < TCB_FIBO_MIN or profundidad > TCB_FIBO_MAX:
                continue

            # Volumen
            vol_rally = g.iloc[i_min:i_max+1]["volume"].mean()
            vol_corr = post["volume"].mean()
            vol_ratio = vol_corr / vol_rally if vol_rally > 0 else 1

            if vol_ratio < TCB_VOL_CRECIENTE:
                continue

            # Rebote
            rebote_pct = ((p_actual - min_post) / min_post) * 100 if min_post > 0 else 0

            resultados.append({
                "tipo": "TCB",
                "symbol": sym,
                "rango_pct": rango_pct,
                "dur_rally": dur_rally,
                "dur_corr": dur_corr,
                "ratio_tiempo": ratio_tiempo,
                "profundidad": profundidad,
                "vol_ratio": vol_ratio,
                "p_actual": p_actual,
                "p_max": p_max,
                "min_post": min_post,
                "rebote_pct": rebote_pct,
                "objetivo_50": p_max - rango * 0.5,
                "objetivo_618": p_max - rango * 0.618,
                "rank": int(rank),
                "mc": mc,
            })

    return resultados


# ============================================================
# DETECCIÓN — ACUMULACIÓN
# ============================================================

def detectar_acumulacion(velas):
    """Detecta acumulación QNT-style."""
    resultados = []

    for sym, g in velas.groupby("symbol"):
        if sym == "xk1" or sym in EXCLUIR:
            continue

        g = g.sort_values("vela").reset_index(drop=True)
        if len(g) < ACUM_DUR_MIN + 5:
            continue

        rank = g.iloc[-1].get("rank", 9999)
        mc = g.iloc[-1].get("mc", 0) or 0
        if not cumple_calidad(mc, rank):
            continue

        # Últimas N velas
        ultimas = g.tail(ACUM_DUR_MIN)

        p_min = ultimas["low"].min()
        p_max = ultimas["high"].max()
        if p_min <= 0:
            continue

        rango_pct = ((p_max - p_min) / p_min) * 100
        if rango_pct > ACUM_RANGO_MAX:
            continue

        p_actual = ultimas.iloc[-1]["close"]
        pos_rango = ((p_actual - p_min) / (p_max - p_min)) * 100 if p_max > p_min else 50

        if pos_rango < ACUM_POS_RANGO_MIN:
            continue

        # Volumen
        vol_medio = ultimas["volume"].mean()
        vol_std = ultimas["volume"].std()
        vol_cv = vol_std / vol_medio if vol_medio > 0 else 1

        if vol_cv > ACUM_VOL_CV_MAX:
            continue

        # Cambio reciente (últimas 5 velas)
        cambio_reciente = 0
        if len(g) >= 5:
            cambio_reciente = ((g.iloc[-1]["close"] - g.iloc[-5]["close"])
                               / g.iloc[-5]["close"]) * 100

        # Solo alertar si ruptura o muy cerca
        if cambio_reciente < ACUM_RUPTURA_MIN and pos_rango < 90:
            continue

        resultados.append({
            "tipo": "ACUMULACION",
            "symbol": sym,
            "rango_pct": rango_pct,
            "pos_rango": pos_rango,
            "vol_medio_m": vol_medio / 1e6,
            "vol_cv": vol_cv,
            "cambio_reciente": cambio_reciente,
            "p_actual": p_actual,
            "p_max": p_max,
            "p_min": p_min,
            "rank": int(rank),
            "mc": mc,
        })

    return resultados


# ============================================================
# DETECCIÓN — SUELO
# ============================================================

def detectar_suelo(velas, btc_estado):
    """Detecta suelos: caída fuerte + frenado."""
    resultados = []

    if btc_estado == "ROMPIO_786":
        return resultados

    for sym, g in velas.groupby("symbol"):
        if sym == "xk1" or sym in EXCLUIR:
            continue

        g = g.sort_values("vela").reset_index(drop=True)
        if len(g) < 30:
            continue

        rank = g.iloc[-1].get("rank", 9999)
        mc = g.iloc[-1].get("mc", 0) or 0
        if not cumple_calidad(mc, rank):
            continue

        # Cambio 24h
        if len(g) < 24:
            continue

        p_ini_24h = g.iloc[-24]["close"]
        p_actual = g.iloc[-1]["close"]
        cambio_24h = ((p_actual - p_ini_24h) / p_ini_24h) * 100

        if cambio_24h > SUELO_CAIDA_24H_MIN:
            continue

        # Frenado 4h
        if len(g) < 4:
            continue
        p_ini_4h = g.iloc[-4]["close"]
        cambio_4h = ((p_actual - p_ini_4h) / p_ini_4h) * 100

        if cambio_4h < SUELO_FRENADO_LO or cambio_4h > SUELO_FRENADO_HI:
            continue

        # Cerca del mínimo
        ultimas = g.tail(24)
        p_min = ultimas["low"].min()
        dist_min = ((p_actual - p_min) / p_min) * 100 if p_min > 0 else 0

        if dist_min > SUELO_DIST_MIN_MAX:
            continue

        # Volumen
        vol_reciente = ultimas.tail(4)["volume"].mean()
        vol_anterior = ultimas.head(12)["volume"].mean()
        vol_ratio = vol_reciente / vol_anterior if vol_anterior > 0 else 1

        if vol_ratio < SUELO_VOL_CRECIENTE:
            continue

        resultados.append({
            "tipo": "SUELO",
            "symbol": sym,
            "cambio_24h": cambio_24h,
            "cambio_4h": cambio_4h,
            "dist_min": dist_min,
            "vol_ratio": vol_ratio,
            "p_actual": p_actual,
            "p_min": p_min,
            "rank": int(rank),
            "mc": mc,
        })

    return resultados


# ============================================================
# DETECCIÓN — REENTRADA FIBO
# ============================================================

def detectar_reentrada(velas, btc_estado):
    """Detecta retroceso Fibo tras pump."""
    resultados = []

    if btc_estado == "ROMPIO_786":
        return resultados

    for sym, g in velas.groupby("symbol"):
        if sym == "xk1" or sym in EXCLUIR:
            continue

        g = g.sort_values("vela").reset_index(drop=True)
        if len(g) < 48:
            continue

        rank = g.iloc[-1].get("rank", 9999)
        mc = g.iloc[-1].get("mc", 0) or 0
        if not cumple_calidad(mc, rank):
            continue

        # Pump 48h
        ultimas = g.tail(48)
        p_min = ultimas["low"].min()
        p_max = ultimas["high"].max()
        p_actual = ultimas.iloc[-1]["close"]

        if p_min <= 0 or p_max <= p_min:
            continue

        pump = ((p_max - p_min) / p_min) * 100
        if pump < PUMP_MIN_PCT:
            continue

        rango = p_max - p_min
        pos_actual = ((p_max - p_actual) / rango) * 100

        if pos_actual < FIBO_MIN_REENT or pos_actual > FIBO_MAX_REENT:
            continue

        # Rebote
        if len(g) < 12:
            continue
        p_min_pull = g.tail(12)["low"].min()
        if p_min_pull <= 0:
            continue

        rebote = ((p_actual - p_min_pull) / p_min_pull) * 100
        if rebote < REBOTE_MIN_PCT:
            continue

        # Volumen
        vol_ratio = g.tail(4)["volume"].mean() / g.tail(20)["volume"].mean() if g.tail(20)["volume"].mean() > 0 else 1
        if vol_ratio < REENTRADA_VOL_MIN:
            continue

        resultados.append({
            "tipo": "REENTRADA",
            "symbol": sym,
            "pump_pct": pump,
            "pos_actual": pos_actual,
            "rebote": rebote,
            "vol_ratio": vol_ratio,
            "p_actual": p_actual,
            "p_max": p_max,
            "p_min": p_min,
            "fib_382": p_max - rango * 0.382,
            "fib_500": p_max - rango * 0.5,
            "fib_618": p_max - rango * 0.618,
            "rank": int(rank),
            "mc": mc,
        })

    return resultados


# ============================================================
# DETECCIÓN — ARRANQUE
# ============================================================

def detectar_arranque(velas_1h, btc_estado):
    """Detecta arranques con volumen."""
    resultados = []

    if btc_estado in ("ROMPIO_786", "SIN_SOPORTE"):
        return resultados

    for sym, g in velas_1h.groupby("symbol"):
        if sym == "xk1" or sym in EXCLUIR:
            continue

        g = g.sort_values("vela").reset_index(drop=True)
        if len(g) < 40:
            continue

        ts_max = g["vela"].max()
        if not es_fresco(ts_max):
            continue

        rank = g.iloc[-1].get("rank", 9999)
        mc = g.iloc[-1].get("mc", 0) or 0
        if not cumple_calidad(mc, rank):
            continue

        # Cambio 1h
        if len(g) < 2:
            continue
        p_ini = g.iloc[-2]["close"]
        p_fin = g.iloc[-1]["close"]
        cambio_1h = ((p_fin - p_ini) / p_ini) * 100

        # Cambio 4h y 24h
        cambio_4h = 0
        if len(g) >= 4:
            cambio_4h = ((p_fin - g.iloc[-4]["close"]) / g.iloc[-4]["close"]) * 100

        cambio_24h = 0
        if len(g) >= 24:
            cambio_24h = ((p_fin - g.iloc[-24]["close"]) / g.iloc[-24]["close"]) * 100

        if cambio_4h > MAX_CAMBIO_4H or cambio_24h > MAX_CAMBIO_24H:
            continue

        # Volumen
        v_base = g.tail(20)["volume"].mean()
        v_ult = g.iloc[-1]["volume"]
        vol_ratio = v_ult / v_base if v_base > 0 else 0

        if v_ult < VOL_ABS_MIN:
            continue

        # Clasificar
        señal = None
        if cambio_1h >= FUERTE_CAMBIO_1H and vol_ratio >= FUERTE_VOL_MIN:
            señal = "FUERTE"
        elif (cambio_1h >= TEMPRANA_CAMBIO_1H and
              TEMPRANA_VOL_MIN <= vol_ratio < TEMPRANA_VOL_MAX):
            señal = "TEMPRANA"

        if not señal:
            continue

        resultados.append({
            "tipo": "ARRANQUE",
            "señal": señal,
            "symbol": sym,
            "cambio_1h": cambio_1h,
            "cambio_4h": cambio_4h,
            "cambio_24h": cambio_24h,
            "vol_ratio": vol_ratio,
            "vol_m": v_ult / 1e6,
            "p_actual": p_fin,
            "rank": int(rank),
            "mc": mc,
            "ts": ts_max,
        })

    return resultados


# ============================================================
# ENVÍO DE MENSAJES
# ============================================================

def enviar_tcb(a, btc):
    hora = (datetime.now(timezone.utc) - timedelta(hours=5)).strftime("%H:%M")
    linea, aviso = _contexto_btc(btc)

    msg = (
        f"🎯 TCB DETECTADO\n"
        f"🪙 {a_real(a['symbol'])} (rank {a['rank']})\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📈 Rally: +{a['rango_pct']:.1f}% en {a['dur_rally']} velas\n"
        f"📉 Corrección: {a['profundidad']*100:.0f}% del rango\n"
        f"⏱️ Ratio tiempo: {a['ratio_tiempo']:.2f}x\n"
        f"📊 Volumen: {a['vol_ratio']:.2f}x\n"
        f"💰 Precio: ${a['p
