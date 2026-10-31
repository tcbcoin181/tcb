#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ALERTA LÍDERES — Detección de techos/suelos en monedas clave

Las monedas están definidas SOLO por alias. Los nombres reales
están en el SECRETOS_JSON (nunca en el código).
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

# Rápidas: BAT, CC, FUN, DOG
GRUPO_RAPIDO  = {"xkr1", "xkq4", "xkr2", "xkr3"}

# Lentas: W, CAP, BR, SKR
GRUPO_LENTO   = {"xkv", "xkr4", "xkr5", "xkr6"}

# Bimodales: BTW, HUMA, STONK
GRUPO_BIMODAL = {"xkr7", "xkr8", "xkr9"}

TODAS_LIDERES = GRUPO_RAPIDO | GRUPO_LENTO | GRUPO_BIMODAL

# Alias de BTC (para contexto)
ALIAS_BTC = "xk1"

# Umbrales
LIDER_CAMBIO_4H_MIN   = 1.0
LIDER_CAMBIO_1H_MAX   = 0.3
LIDER_VOL_MIN         = 1.2
LIDER_DIST_MAX_MIN    = 0.5
VOL_ABS_MIN           = 500_000
COOLDOWN_LIDER        = 4
MC_MIN                = 50_000_000
MC_MAX                = 5_000_000_000
RANK_MAX              = 300
ALERTAS_STATE_FILE    = "alertas_lideres_state.json"


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
# DETECCIÓN DE LÍDER (techo/suelo en 5m)
# ============================================================

def detectar_lider(df, alias):
    """
    Detecta si una moneda líder tocó techo o suelo recientemente.
    Usa velas de 5m para detectar el giro.
    """
    if alias not in TODAS_LIDERES:
        return None

    g = df[df["symbol"] == alias].sort_values("timestamp")
    if len(g) < 30:
        return None

    ts_max = g["timestamp"].max()
    if not es_fresco(ts_max, minutos=30):
        return None

    mc = g.iloc[-1].get("market_cap", 0) or 0
    rank = g.iloc[-1].get("cmc_rank", 9999)
    if not cumple_calidad(mc, rank):
        return None

    corte_30m = ts_max - timedelta(minutes=30)
    rec_5m = (g[g["timestamp"] >= corte_30m]
              .set_index("timestamp")["price"]
              .resample("5min").last().dropna())
    if len(rec_5m) < 4:
        return None

    corte_1h = ts_max - timedelta(hours=1)
    rec_1h = g[g["timestamp"] >= corte_1h]
    if len(rec_1h) < 3:
        return None
    p_ini_1h = rec_1h.iloc[0]["price"]
    p_fin = rec_1h.iloc[-1]["price"]
    cambio_1h = ((p_fin - p_ini_1h) / p_ini_1h) * 100 if p_ini_1h > 0 else 0

    corte_4h = ts_max - timedelta(hours=4)
    rec_4h = g[g["timestamp"] >= corte_4h]
    if len(rec_4h) < 3:
        return None
    p_ini_4h = rec_4h.iloc[0]["price"]
    cambio_4h = ((p_fin - p_ini_4h) / p_ini_4h) * 100 if p_ini_4h > 0 else 0

    p_max_30m = rec_5m.max()
    p_min_30m = rec_5m.min()
    p_actual = rec_5m.iloc[-1]
    dist_max = ((p_actual - p_max_30m) / p_max_30m) * 100 if p_max_30m > 0 else 0
    dist_min = ((p_actual - p_min_30m) / p_min_30m) * 100 if p_min_30m > 0 else 0

    v_base = g["volume_24h"].tail(20).mean()
    v_ult = g["volume_24h"].iloc[-1]
    vol_ratio = v_ult / v_base if v_base > 0 else 0
    if v_ult < VOL_ABS_MIN:
        return None

    if alias in GRUPO_RAPIDO:
        grupo = "RAPIDA"
    elif alias in GRUPO_LENTO:
        grupo = "LENTA"
    else:
        grupo = "BIMODAL"

    techo = False
    if (cambio_4h > LIDER_CAMBIO_4H_MIN and
        dist_max > -LIDER_DIST_MAX_MIN and
        cambio_1h < LIDER_CAMBIO_1H_MAX and
        vol_ratio > LIDER_VOL_MIN):
        techo = True

    suelo = False
    if (cambio_4h < -LIDER_CAMBIO_4H_MIN and
        dist_min < LIDER_DIST_MAX_MIN and
        cambio_1h > -LIDER_CAMBIO_1H_MAX and
        vol_ratio > LIDER_VOL_MIN):
        suelo = True

    if not (techo or suelo):
        return None

    return {
        "tipo": "TECHO" if techo else "SUELO",
        "symbol": alias,
        "grupo": grupo,
        "precio": p_actual,
        "cambio_1h": cambio_1h,
        "cambio_4h": cambio_4h,
        "dist_max_30m": dist_max,
        "dist_min_30m": dist_min,
        "vol_ratio": vol_ratio,
        "vol_m": v_ult / 1e6,
        "cmc_rank": int(rank),
        "market_cap_m": mc / 1e6,
        "ts": ts_max,
    }


# ============================================================
# ALERTA DE LÍDERES (combinada)
# ============================================================

def enviar_alerta_lideres(lideres, btc):
    """Envía una alerta combinada de todos los líderes detectados."""
    if not lideres:
        return False

    conteo = {
        "RAPIDA_TECHO": 0, "RAPIDA_SUELO": 0,
        "LENTA_TECHO": 0, "LENTA_SUELO": 0,
        "BIMODAL_TECHO": 0, "BIMODAL_SUELO": 0,
    }
    for a in lideres:
        clave = f"{a['grupo']}_{a['tipo']}"
        if clave in conteo:
            conteo[clave] += 1

    total_techo = conteo["RAPIDA_TECHO"] + conteo["LENTA_TECHO"] + conteo["BIMODAL_TECHO"]
    total_suelo = conteo["RAPIDA_SUELO"] + conteo["LENTA_SUELO"] + conteo["BIMODAL_SUELO"]

    msg = "📡 *MONEDAS LÍDERES*\n━━━━━━━━━━━━━━━━━━━\n"

    if total_techo >= 3:
        msg += f"🚨 *SEÑAL EXTREMA*: {total_techo} líderes tocaron TECHO\n"
    elif conteo["RAPIDA_TECHO"] >= 2:
        msg += f"⚠️ *SEÑAL FUERTE*: {conteo['RAPIDA_TECHO']} rápidas tocaron TECHO → BTC cae en 1-3h\n"
    elif conteo["LENTA_TECHO"] >= 2:
        msg += f"⚠️ *SEÑAL FUERTE*: {conteo['LENTA_TECHO']} lentas tocaron TECHO → BTC cae en 4-6h\n"

    if total_suelo >= 3:
        msg += f"🚨 *SEÑAL EXTREMA*: {total_suelo} líderes tocaron SUELO\n"
    elif conteo["RAPIDA_SUELO"] >= 2:
        msg += f"⚠️ *SEÑAL FUERTE*: {conteo['RAPIDA_SUELO']} rápidas tocaron SUELO → BTC sube en 1-3h\n"
    elif conteo["LENTA_SUELO"] >= 2:
        msg += f"⚠️ *SEÑAL FUERTE*: {conteo['LENTA_SUELO']} lentas tocaron SUELO → BTC sube en 4-6h\n"

    msg += "\n"
    for a in lideres[:10]:
        emoji = "🔺" if a["tipo"] == "TECHO" else "🔻"
        msg += f"{emoji} {a_real(a['symbol'])} ({a['grupo']}) — {a['tipo']}\n"
        msg += f"   Cambio 1h: {a['cambio_1h']:+.2f}% | 4h: {a['cambio_4h']:+.2f}%\n"
        msg += f"   Precio: ${a['precio']:.6f} | Vol: {a['vol_ratio']:.2f}x\n\n"

    if btc:
        msg += f"⚪ {a_real(ALIAS_BTC)}: {btc.get('estado', 'UNKNOWN')} ({btc.get('cambio_1h', 0):+.2f}% 1h)\n"

    return enviar_telegram(msg)


# ============================================================
# ANÁLISIS BTC (simplificado, solo alias)
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

    # === VERIFICACIÓN TEMPORAL ===
    print(f"\n🔍 VERIFICACIÓN DE SÍMBOLOS:")
    for alias in sorted(TODAS_LIDERES):
        nombre = a_real(alias)
        existe_alias = alias in df["symbol"].values
        existe_nombre = nombre in df["symbol"].values
        print(f"   {nombre} ({alias}): alias={existe_alias} | nombre={existe_nombre}")
    # === FIN VERIFICACIÓN ===

    btc = analizar_btc(df)
    print(f"\n🔍 {a_real(ALIAS_BTC)}: {btc['estado']} ({btc['cambio_1h']:+.2f}% 1h)")

    alertas_state = cargar_alertas_state()

    print(f"\n📡 Escaneando {len(TODAS_LIDERES)} monedas líderes...")
    lideres = []
    for alias in TODAS_LIDERES:
        r = detectar_lider(df, alias)
        if r:
            if not paso_cooldown(alertas_state, r["symbol"], "LIDER", COOLDOWN_LIDER):
                print(f"   ⏳ {a_real(r['symbol'])} en cooldown")
                continue
            lideres.append(r)

    if lideres:
        print(f"   🔺🔻 {len(lideres)} líderes detectados:")
        for a in lideres:
            print(f"      {a_real(a['symbol'])} ({a['grupo']}) — {a['tipo']}")

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
