# Estado de las fases (PLAN_FINAL §11)

> **Última actualización: 2026-06-17 (cierre de sprint S7).**
> Leyenda: ✅ hecho · 🟡 hecho con cambios respecto al plan · ⏳ pendiente · ❌ descartado a propósito · 🔜 continuo

## Resumen ejecutivo

| Fase | Qué | Estado |
|------|-----|:------:|
| 0 · Base | Host, particiones, AEC, `.env` | ✅ |
| 1 · Oídos y voz | Wake word, STT, TTS, sin auto-interrupción | ✅ |
| 2 · Cerebro | LLM natural + personalidad | 🟡 (Groq → **GLM-5** vía OpenCode Go) |
| 2-3 · STT Parakeet | Sustituir Whisper | ❌ (Parakeet solo inglés → revertido) |
| 3 · Memoria | Recuerdo entre sesiones, reflexión | 🟡 (sin mem0: **FTS5 + Curator + almacén con recall/decay**) |
| 4 · Acciones e internet | Recordatorios, confirmación, web, SSRF | ✅ |
| 5 · Presencia y visión | YOLO, caras, saludo al llegar | ⏳ (construido y apagado; falta la cámara) |
| 6 · Centro de control | Panel, métricas, DND | ✅ (vía Cloudflare, no tailscale) |
| 7 · Refinamiento | Speaker-ID, voz móvil, MCP… | 🔜 (varias piezas ya adelantadas, ver abajo) |

## Construido DESPUÉS del plan (sprint S6-S7, no estaba en las fases originales)

- ✅ **Delegación a Claude Code**: `investigar` (solo lectura) y `encargar` (acciones reales en el homelab, con sudo acotado + guardia de comandos + doble confirmación inteligente).
- ✅ **Proactividad**: heartbeat + gate único (DND, horario, presupuesto, dedup) + brain-review.
- ✅ **Telegram bidireccional**: chatear con Jarvis por texto (mismo cerebro/tools/memoria). Si escribes por Telegram, no te responde por voz (estás fuera).
- ✅ **Routing por presencia** (Fase B de la cámara): presente→voz, ausente→Telegram, con fail-safe.
- ✅ **Cron en lenguaje natural + monitores** (`[SILENT]`): "cada mañana dame el tiempo", "cada hora avísame si tengo algo urgente".
- ✅ **Memoria que aprende y olvide**: almacén estructurado con recall (lo que usas se queda) y decay (lo que no, se archiva sin borrar).
- ✅ **Auto-mejora con aprobación**: el Curator propone, José aprueba en el panel.
- ✅ **Suite de tests (68)** + verificación completa del sistema.

## Pendiente real
- ⏳ **Fase C (cámara)**: enchufar webcam USB + enrolar la cara → encender la visión. Todo lo demás está hecho. Ver `docs/CAMERA_FASE_C.md`.
- 🔜 **Mejoras futuras** (Fase 7): voz desde otra habitación (satélite ESP32 / móvil WebRTC), speaker-ID, wake word propia.
- ❌ **Observabilidad Prometheus/Grafana**: descartado por sobre-ingeniería para un homelab personal (el HUD ya da métricas básicas).

---

## Detalle del plan original (checklist histórico)

<details><summary>Fases 0-7 del PLAN_FINAL — checklist de origen</summary>

### Fase 0 — Base · ✅
Host Ubuntu, particionado NVMe/SATA, docker/ufw/fail2ban, audio detectado. La "puerta AEC"
se resolvió con el **Anker PowerConf (AEC por hardware)** en vez del test formal.

### Fase 1 — Oídos y voz · ✅
Wake word **"hey Mycroft"** (openWakeWord) + STT faster-whisper small + Piper TTS davefx +
sin auto-interrupción (mute strategy). Verificado E2E por voz.

### Fase 2 — Cerebro · 🟡
Conversación natural y personalidad de mayordomo ✅. **Cambio**: de Groq a **GLM-5 vía OpenCode Go**
(litellm), fallbacks deepseek/groq. Latencia variable (pasarela remota).

### Fase 2-3 — STT Parakeet · ❌
Probado y **revertido**: Parakeet era solo inglés. Se mantiene Whisper small.

### Fase 3 — Memoria · 🟡
Sin mem0. **FTS5** sobre events.db (`recordar`) + **Curator** (aprende hechos durables) +
**almacén `facts`** con recall/decay real + perfil de usuario con aprobación.

### Fase 4 — Acciones e internet · ✅
`crear_recordatorio` con confirmación verbal, `confirmar_accion`, web_search/web_read, guard SSRF,
defensa anti prompt-injection.

### Fase 5 — Presencia y visión · ⏳
YOLO11n (OpenVINO/iGPU) + InsightFace + pipeline de presencia: **todo construido**, apagado
(`DISABLE_PRESENCE=true`), sin cara enrolada. Falta la cámara física.

### Fase 6 — Centro de control · ✅
Panel en producción vía **Cloudflare Tunnel + Access**, HUD kiosko con actividad, agenda, Spotify,
uso de tokens; editor de personas, toggles de tools y DND.

### Fase 7 — Refinamiento · 🔜
Continuo. Ya adelantadas piezas nuevas (delegación, proactividad, Telegram, cron, memoria).

</details>
