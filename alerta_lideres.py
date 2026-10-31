#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ALERTA LÍDERES — Detección de techos/suelos en monedas clave
Usa la misma lógica del ARRANQUE de alerta_v6.py
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

# Umbrales del ARRANQUE (los mismos de alerta_v6.py)
TEMPRANA_CAMBIO_1H  = 2.0
TEMPRANA_VOL_MIN    = 1.2
TEMPRANA_VOL_MAX    = 1.3

FUERTE_CAMBIO_1H    = 3.0
FUERTE_VOL_MIN      = 1.3

VOL_ABS_MIN         = 500_000
MAX_CAMBIO_4H       = 5.0
MAX_CAMBIO_24H      = 15.0

# Cooldowns
COOLDOWN_LIDER      = 4

# Filtros de calidad
MC_MIN              = 50_000_000
MC_MAX              = 5_000_000_000
RANK_MAX            = 300

ALERTAS_STATE_FILE  = "alertas_lideres_state.json"


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
# DETECCIÓN — ARRANQUE (misma lógica de alerta_v6.py)
# ============================================================

def detectar_arranque(df, alias):
    """
    Detecta arranque (subida fuerte) en una moneda líder.
    Usa la misma lógica de alerta_v6.py.
    Devuelve dict con señal (FUERTE/TEMPRANA) o None.
    """
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

    # Cambio 1h
    corte_1h = ts_max - timedelta(hours=1)
    rec_1h = g[g["timestamp"] >= corte_1h]
    if len(rec_1h) < 3:
        return None
    p_ini_1h = rec_1h.iloc[0]["price"]
    p_fin = rec_1h.iloc[-1]["price"]
    if p_ini_1h <= 0:
        return None
    cambio_1h = ((p_fin - p_ini_1h) / p_ini_1h) * 100

    # Cambio 4h
    corte_4h = ts_max - timedelta(hours=4)
    rec_4h = g[g["timestamp"] >= corte_4h]
    if len(rec_4h) < 3:
        return None
    p_ini_4h = rec_4h.iloc[0]["price"]
    cambio_4h = ((p_fin - p_ini_4h) / p_ini_4h) * 100 if p_ini_4h > 0 else 0

    # Cambio 24h
    corte_24h = ts_max - timedelta(hours=24)
    rec_24h = g[g["timestamp"] >= corte_24h]
    p_ini_24h = rec_24h.iloc[0]["price"] if len(rec_24h) > 0 else p_ini_4h
    cambio_24h = ((p_fin - p_ini_24h) / p_ini_24h) * 100 if p_ini_24h > 0 else 0

    # Filtros de seguridad (evitar pumps ya pasados)
    if cambio_4h > MAX_CAMBIO_4H:
        return None
    if cambio_24h > MAX_CAMBIO_24H:
        return None

    # Volumen
    v_base = g["volume_24h"].tail(20).mean()
    v_ult = g["volume_24h"].iloc[-1]
    vol_ratio = v_ult / v_base if v_base > 0 else 0
    if v_ult < VOL_ABS_MIN:
        return None

    # Determinar señal (misma lógica de alerta_v6.py)
    señal = None
    if cambio_1h >= FUERTE_CAMBIO_1H and vol_ratio >= FUERTE_VOL_MIN:
        señal = "FUERTE"
    elif (cambio_1h >= TEMPRANA_CAMBIO_1H and
          TEMPRANA_VOL_MIN <= vol_ratio < TEMPRANA_VOL_MAX):
        señal = "TEMPRANA"

    if señal is None:
        return None

    # Determinar grupo
    if alias in GRUPO_RAPIDO:
        grupo = "RAPIDA"
    elif alias in GRUPO_LENTO:
        grupo = "LENTA"
    else:
        grupo = "BIMODAL"

    return {
        "tipo": "ARRANQUE",
        "señal": señal,
        "symbol": alias,
        "grupo": grupo,
        "precio": p_fin,
        "cambio_1h": cambio_1h,
        "cambio_4h": cambio_4h,
        "cambio_24h": cambio_24h,
        "vol_ratio": vol_ratio,
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

    # Contar por grupo
    conteo = {
        "RAPIDA": 0, "LENTA": 0, "BIMODAL": 0,
    }
    fuertes = 0
    tempranas = 0
    for a in lideres:
        conteo[a["grupo"]] += 1
        if a["señal"] == "FUERTE":
            fuertes += 1
        else:
            tempranas += 1

    total = len(lideres)

    msg = "📡 *MONEDAS LÍDERES — ARRANQUE*\n━━━━━━━━━━━━━━━━━━━\n"

    if fuertes >= 2:
        msg += f"🚨 *SEÑAL FUERTE*: {fuertes} líderes con ARRANQUE FUERTE\n"
    elif fuertes == 1:
        msg += f"⚠️ *SEÑAL MEDIA*: 1 líder con ARRANQUE FUERTE\n"

    if tempranas >= 2:
        msg += f"🟡 *SEÑAL TEMPRANA*: {tempranas} líderes con ARRANQUE TEMPRANO\n"

    msg += f"\n📊 Total: {total} líderes detectados\n"
    msg += f"   Rápidas: {conteo['RAPIDA']} | Lentas: {conteo['LENTA']} | Bimodales: {conteo['BIMODAL']}\n\n"

    for a in lideres[:10]:
        emoji = "🚨" if a["señal"] == "FUERTE" else "🟡"
        msg += f"{emoji} {a_real(a['symbol'])} ({a['grupo']}) — {a['señal']}\n"
        msg += f"   +{a['cambio_1h']:.2f}% en 1h | 4h: {a['cambio_4h']:+.2f}%\n"
        msg += f"   Precio: ${a['precio']:.6f} | Vol: {a['vol_ratio']:.2f}x\n\n"

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

    # === VERIFICACIÓN DE FRESCURA ===
    print(f"\n🕐 Antigüedad de los datos (últimas velas):")
    for alias in sorted(TODAS_LIDERES):
        nombre = a_real(alias)
        g = df[df["symbol"] == alias]
        if len(g) > 0:
            ts = g["timestamp"].max()
            edad = (datetime.now(timezone.utc) - ts).total_seconds() / 60
            print(f"   {nombre}: última vela hace {edad:.0f} min")
        else:
            print(f"   {nombre}: ❌ NO ENCONTRADO")
    # === FIN VERIFICACIÓN ===

    btc = analizar_btc(df)
    print(f"\n🔍 {a_real(ALIAS_BTC)}: {btc['estado']} ({btc['cambio_1h']:+.2f}% 1h)")

    alertas_state = cargar_alertas_state()

    print(f"\n📡 Escaneando {len(TODAS_LIDERES)} monedas líderes...")
    lideres = []
    for alias in TODAS_LIDERES:
        r = detectar_arranque(df, alias)
        if r:
            if not paso_cooldown(alertas_state, r["symbol"], "LIDER", COOLDOWN_LIDER):
                print(f"   ⏳ {a_real(r['symbol'])} en cooldown")
                continue
            lideres.append(r)

    if lideres:
        print(f"   🔺 {len(lideres)} líderes con arranque detectado:")
        for a in lideres:
            print(f"      {a_real(a['symbol'])} ({a['grupo']}) — {a['señal']} (+{a['cambio_1h']:.2f}%)")

        if enviar_alerta_lideres(lideres, btc):
            print(f"   📱 Alerta enviada")
            for a in lideres:
                registrar_alerta(alertas_state, a["symbol"], "LIDER")
            guardar_alertas_state(alertas_state)
        else:
            print(f"   ⚠️ No se pudo enviar la alerta")
    else:
        print("   ⚪ Sin líderes detectados.")

    print(f"\n✅ Análisis completado.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
