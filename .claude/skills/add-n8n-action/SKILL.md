---
name: add-n8n-action
description: >-
  Úsala para dar a Jarvis una capacidad/acción nueva vía n8n (crear recordatorios,
  enviar mensajes, domótica, etc.). Cubre el workflow n8n con HMAC, la declaración
  en config/tools.yaml y la confirmación verbal obligatoria para acciones con efecto.
---

# Añadir una acción n8n

Patrón: el LLM llama a una tool → el orchestrator hace `POST` firmado al webhook
de n8n → n8n ejecuta el workflow → la respuesta vuelve al contexto.

## 1. Crear el workflow en n8n
- Parte de `n8n/workflows/recordatorio.example.json` (impórtalo en la UI de n8n :5678).
- **Primer nodo siempre**: Webhook (rawBody) → Code que **verifica el HMAC**
  (`crypto.timingSafeEqual`, ventana 5 min) → IF válido → acción → Respond.
- Define en n8n la variable `JARVIS_WEBHOOK_SECRET` con el MISMO valor que
  `N8N_WEBHOOK_SECRET` del `.env`.
- El path del webhook (p. ej. `recordatorio`) es el que referenciará la tool.

## 2. Declarar la tool en `config/tools.yaml`
```yaml
  mi_accion:
    n8n_webhook: mi-path-webhook
    type: side_effect          # read_only si NO tiene efecto real
    enabled: true
    timeout_secs: 15
    description: >-
      Descripción clara para el LLM: qué hace y cuándo usarla.
    parameters:
      campo: { type: string, required: true, description: "..." }
```
- `type: side_effect` → pasa SIEMPRE por confirmación verbal (no se ejecuta a la
  primera; el usuario debe decir "sí"). Es la regla de seguridad §9.1.1 y la
  aplica `security.py` + `tools/__init__.py` automáticamente. No la saltes.
- Descripción concisa y precisa: con varias tools, los modelos fallan más si las
  descripciones son vagas (sobre todo gpt-oss; ver el A/B en PLAN_FINAL §4).

## 3. Aplicar
```bash
make restart s=orchestrator
```

## 4. Probar (Fase 4 checklist)
- Pídele la acción por voz → debe **repetirla y pedir confirmación** → solo tras
  tu "sí" se ejecuta.
- Manda una petición con firma inválida al webhook → n8n debe responder 401.
- Verifica que `confirmar_accion` sin confirmación real del usuario es DENEGADO.

## Código relevante
- `services/orchestrator/tools/n8n.py` — firma HMAC del POST.
- `services/orchestrator/tools/__init__.py` — registro y enrutado a confirmación.
- `services/orchestrator/security.py` — lógica de confirmación y taint mode.
