#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from io import StringIO

import pandas as pd
import requests


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


GRUPO_RAPIDO  = {"xkr1", "xkq4", "xkr2", "xkr3"}
GRUPO_LENTO   = {"xkv", "xkr4", "xkr5", "xkr6"}
GRUPO_BIMODAL = {"xkr7", "xkr8", "xkr9"}
TODAS_LIDERES = GRUPO_RAPIDO | GRUPO_LENTO | GRUPO_BIMODAL

MONEDAS_5_VELAS = {
    "xky", "xkq1", "xkq9", "xkq6", "xkt", "xku", "xka", "xkb", "xkZ",
    "xkD", "xkF", "xkA", "xk5", "xk4", "xk9", "xkj", "xkn", "xkE",
    "xkG", "xk6", "xk8", "xkR", "xkL", "xkM", "xkN", "xkQ", "xkT",
    "xkV", "xkW", "xkX", "xkY", "xke", "xkf", "xki", "xkl", "xkm",
    "xkp", "xkr", "xkv", "xk0", "xkq3", "xkq4", "xkqe", "xkqf",
    "xkqg", "xkr1", "xkr5", "xkr9", "xkr10", "xkr11", "xkr12",
    "xkr14", "xkr15", "xkr16", "xkr17", "xkr18", "xkr19", "xkr20",
    "xkr21", "xkr22", "xkr23", "xkr24", "xkr25", "xkr26", "xkr27",
    "xkr28", "xkr29", "xkr30", "xkr31", "xkr32", "xkr33", "xkr34",
    "xkr35", "xkr36", "xkr37", "xkr38", "xkr39", "xkr40", "xkr41",
    "xkr42", "xkr43", "xkr44", "xkr45", "xkr46", "xkr47", "xkr48",
    "xkr49", "xkr50", "xkr51", "xkr52", "xkr53", "xkr54", "xkr55",
    "xkr56", "xkr57", "xkr58", "xkr59", "xkr60", "xkr61", "xkr62",
    "xkr63", "xkr64", "xkr65", "xkr66", "xkr67", "xkr68", "xkr69",
    "xkr70", "xkr71", "xkr72", "xkr73", "xkr74", "xkr75", "xkr76",
    "xkr77", "xkr78", "xkr79", "xkr80", "xkr81", "xkr82", "xkr83",
    "xkr84", "xkr85", "xkr86", "xkr87", "xkr88", "xkr89", "xkr90",
    "xkr91", "xkr92", "xkr93", "xkr94", "xkr95", "xkr96",
}

ALIAS_BTC = "xk1"

FIBO_TOL_TOQUE   = 1.5
FIBO_VENTANA_H   = 4
FIBO_REBOTE_MIN  = 1.5
FIBO_CIERRE_TOL  = 0.5
FIBO_MAX_CIERRES = 0.30
FIBO_N_CONSEC    = 2

COOLDOWN_FIBO    = 4

VENTANA_GRUPAL_MIN = 15
SUBIDA_GRUPAL_MIN  = 1.0
MIN_MONEDAS_GRUPAL = 3

ROJAS_MIN           = 2
ROJAS_MAX           = 5
CAIDA_MIN           = 4.0
COOLDOWN_INDIVIDUAL = 2

MC_MIN           = 50_000_000
MC_MAX           = 5_000_000_000
RANK_MAX         = 300

ALERTAS_STATE_FILE = "alertas_lideres_state.json"


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


def detectar_tendencia_grupal(df, alias):
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

    ultima_vela = velas_5m.index[-1]
    inicio_ventana = ultima_vela - timedelta(minutes=VENTANA_GRUPAL_MIN)

    serie_ventana = velas_5m[(velas_5m.index >= inicio_ventana) & (velas_5m.index <= ultima_vela)]
    if len(serie_ventana) < 2:
        return None

    precio_inicio = serie_ventana.iloc[0]
    precio_fin = serie_ventana.iloc[-1]
    if precio_inicio <= 0:
        return None

    subida = (precio_fin - precio_inicio) / precio_inicio * 100
    if subida < SUBIDA_GRUPAL_MIN:
        return None

    return {
        "symbol": alias,
        "tipo": "GRUPAL",
        "precio_inicio": precio_inicio,
        "precio_fin": precio_fin,
        "subida": subida,
        "precio_actual": float(g.iloc[-1]["price"]),
        "mc_m": mc / 1e6,
        "rank": int(rank),
    }


def detectar_oportunidad_individual(df, alias):
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

    ultimas_5 = velas_5m.iloc[-5:]
    if len(ultimas_5) < 5:
        return None

    subidas = 0
    for j in range(1, len(ultimas_5)):
        if ultimas_5.iloc[j] > ultimas_5.iloc[j-1]:
            subidas += 1

    if subidas < 4:
        return None

    subida_5_velas = (ultimas_5.iloc[-1] - ultimas_5.iloc[0]) / ultimas_5.iloc[0] * 100
    if subida_5_velas < 1.0:
        return None

    ventana_suelo = velas_5m.iloc[-30:]
    p_min = ventana_suelo.min()
    idx_min = ventana_suelo.idxmin()
    idx_min_pos = velas_5m.index.get_loc(idx_min)

    if idx_min_pos >= len(velas_5m) - 5:
        return None

    rojas_consecutivas = 0
    for j in range(idx_min_pos - 1, max(idx_min_pos - 15, 0), -1):
        if velas_5m.iloc[j] < velas_5m.iloc[j-1]:
            rojas_consecutivas += 1
        else:
            break

    idx_inicio_rojas = idx_min_pos - rojas_consecutivas
    if idx_inicio_rojas < 0:
        return None

    precio_inicio = velas_5m.iloc[idx_inicio_rojas]
    caida_previa = (precio_inicio - p_min) / precio_inicio * 100

    if rojas_consecutivas < ROJAS_MIN:
        return None
    if rojas_consecutivas > ROJAS_MAX:
        return None
    if caida_previa < CAIDA_MIN:
        return None

    precio_rebote = ultimas_5.iloc[-1]
    fecha_rebote = ultimas_5.index[-1]

    idx_rebote = velas_5m.index.get_loc(fecha_rebote)
    idx_fin = min(idx_rebote + 30, len(velas_5m) - 1)

    if idx_fin <= idx_rebote:
        return None

    serie_ventana = velas_5m.iloc[idx_rebote:idx_fin + 1]
    precio_max = serie_ventana.max()
    precio_min = serie_ventana.min()

    subida_desde_rebote = (precio_max - precio_rebote) / precio_rebote * 100
    drawdown = (precio_min - precio_rebote) / precio_rebote * 100

    if subida_desde_rebote < 1.0:
        return None
    if drawdown < -1.0:
        return None

    return {
        "symbol": alias,
        "tipo": "INDIVIDUAL",
        "precio_suelo": p_min,
        "fecha_suelo": idx_min,
        "precio_rebote": precio_rebote,
        "fecha_rebote": fecha_rebote,
        "rojas_consecutivas": rojas_consecutivas,
        "caida_previa": caida_previa,
        "subida_5_velas": subida_5_velas,
        "subida_desde_rebote": subida_desde_rebote,
        "drawdown": drawdown,
        "precio_actual": float(g.iloc[-1]["price"]),
        "mc_m": mc / 1e6,
        "rank": int(rank),
    }


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


def enviar_alerta_grupal(alertas, btc):
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
        msg += f"🟢 {a_real(a['symbol'])} — +{a['subida']:.2f}%\n"

    msg += f"\n📊 {n} monedas con subida > {SUBIDA_GRUPAL_MIN}% en {VENTANA_GRUPAL_MIN} min"
    msg += f"\n🚀 Posible tendencia general"
    if btc:
        msg += f"\n⚪ BTC: {btc.get('estado', 'UNKNOWN')}"

    return enviar_telegram(msg)


def enviar_alerta_individual(alertas, btc):
    if not alertas:
        return False

    msg = "🎯 OPORTUNIDAD INDIVIDUAL\n"
    msg += "━━━━━━━━━━━━━━━━━━━\n"

    for a in alertas:
        msg += f"🟢 {a_real(a['symbol'])}\n"
        msg += f"   Rojas: {a['rojas_consecutivas']} | Caída: {a['caida_previa']:.1f}%\n"
        msg += f"   Subida esperada: +{a['subida_desde_rebote']:.2f}%\n\n"

    msg += "🚀 Posible rebote individual"
    if btc:
        msg += f"\n⚪ BTC: {btc.get('estado', 'UNKNOWN')}"

    return enviar_telegram(msg)


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


def main():
    ahora = datetime.now(timezone.utc)
    ahora_lima = ahora - timedelta(hours=5)

    print(f"\n{'='*60}")
    print(f"📡 ALERTA LÍDERES — {ahora_lima.strftime('%Y-%m-%d %H:%M:%S')} Lima")
    print(f"{'='*60}")

    if not FIBO_NIVELES:
        print("⚠️ FIBO_NIVELES no configurado. Solo se analizarán señales grupales e individuales.")

    df = cargar_datos()
    print(f"📊 Total: {len(df):,} filas | {df['symbol'].nunique()} monedas")

    btc = analizar_btc(df)
    print(f"\n🔍 {a_real(ALIAS_BTC)}: {btc['estado']} ({btc['cambio_1h']:+.2f}% 1h)")

    alertas_state = cargar_alertas_state()

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

    print(f"\n📡 Buscando tendencia grupal (subida > {SUBIDA_GRUPAL_MIN}% en {VENTANA_GRUPAL_MIN} min)...")
    grupales = []
    for alias in MONEDAS_5_VELAS:
        r = detectar_tendencia_grupal(df, alias)
        if r:
            grupales.append(r)

    if len(grupales) >= MIN_MONEDAS_GRUPAL:
        print(f"   🟢 SEÑAL GRUPAL: {len(grupales)} monedas")
        for a in grupales:
            print(f"      {a_real(a['symbol'])} — +{a['subida']:.2f}%")

        if enviar_alerta_grupal(grupales, btc):
            print(f"   📱 Alerta grupal enviada")
    elif len(grupales) > 0:
        print(f"   ⚪ Solo {len(grupales)} moneda(s) (mínimo {MIN_MONEDAS_GRUPAL})")
    else:
        print("   ⚪ Sin tendencia grupal.")

    print(f"\n📡 Buscando oportunidades individuales...")
    individuales = []
    for alias in MONEDAS_5_VELAS:
        r = detectar_oportunidad_individual(df, alias)
        if r:
            if not paso_cooldown(alertas_state, r["symbol"], "INDIVIDUAL", COOLDOWN_INDIVIDUAL):
                continue
            individuales.append(r)
            print(f"   🎯 {a_real(alias)} — caída {r['caida_previa']:.1f}%, {r['rojas_consecutivas']} rojas")

    if individuales:
        if enviar_alerta_individual(individuales, btc):
            print(f"   📱 Alerta individual enviada")
            for a in individuales:
                registrar_alerta(alertas_state, a["symbol"], "INDIVIDUAL")
            guardar_alertas_state(alertas_state)
    else:
        print("   ⚪ Sin oportunidades individuales.")

    print(f"\n✅ Análisis completado.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
