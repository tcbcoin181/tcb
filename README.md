# TCB Coin — Bot V3

Bot de alertas basado en TCB (Time Conversion Bar) + Acumulación + BTC-céntrico.

## Señales

1. 🎯 TCB + BTC soporte (máxima prioridad)
2. 🚀 Acumulación QNT-style
3. 🎯 Suelo + BTC soporte
4. 📐 Reentrada Fibo
5. 🟡 Arranque

## Deploy

1. Configurar secrets:
   - TELEGRAM_BOT_TOKEN
   - TELEGRAM_CHAT_ID
   - SECRETOS_JSON

2. Configurar cron-job.org:
   - URL: https://api.github.com/repos/tcbcoin181/tcb/actions/workflows/alerta_v3.yml/dispatches
   - Method: POST
   - Headers: Authorization: Bearer <TOKEN>, Accept: application/vnd.github+json
   - Body: {"ref":"main"}
   - Cada 15 min

3. Probar manualmente en Actions.

## Estado

- btc_state.json → estado actual de BTC
- alertas_state.json → cooldowns de alertas
