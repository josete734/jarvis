# Checklist por fases (PLAN_FINAL §11)

## Fase 0 — Base (sem. 1)
- [ ] Ubuntu Server 24.04 instalado; particionado §5.0 (NVMe: /, docker, modelos, swapfile · SATA: /srv/jarvis)
- [ ] `sudo bash scripts/install_host.sh` (zram, governor, grupos, docker, ufw, fail2ban, tailscale)
- [ ] SSH solo llaves verificado → `PasswordAuthentication no`
- [ ] USB de backup montado en /mnt/backup (fstab `nofail`) + repo restic init
- [ ] `arecord -l` / `aplay -l` / `v4l2-ctl --list-devices` detectan los dispositivos
- [ ] **PUERTA: `scripts/test_aec.sh` pasa (delta ≤ ~6 dB)** — si no, decidir plan B/C antes de seguir
- [ ] `.env` completo (claves, RENDER_GID, allowlist panel)

## Fase 1 — Oídos y voz (sem. 2)
- [ ] `make build && make models`
- [ ] `make list-audio` → fijar índices si hace falta
- [ ] Arranque del orquestador sin errores de imports (ajustar TODO(Fase 1) si Pipecat movió algo)
- [ ] "Hey Jarvis" despierta el gate (log score) y vuelve a dormir a los 45 s
- [ ] Eco hablado: lo que dices se transcribe y Piper lo lee
- [ ] CPU en reposo < 10 %; el bot NO se auto-interrumpe

## Fase 2 — Cerebro (sem. 3)
- [ ] Developer tier activado en Groq (método de pago)
- [ ] Conversación natural < 2 s percibidos, barge-in funciona
- [ ] **A/B/C**: 20 turnos guionizados a ciegas (llama-3.3-70b vs gpt-oss-120b [vs qwen3-32b])
      con tasa de fallos de tools y coste/turno → decidir `jarvis-main`
- [ ] Personalidad v1 validada (humor seco, sin listas por voz)

## Fase 2-3 — STT parakeet
- [ ] Perfil `stt-parakeet` arriba, `STT_BACKEND=openai`
- [ ] Sin regresión en español coloquial; latencia STT ~0,25-0,8 s
- [ ] RAM total < 8 GB (si aprieta: canary-180m-flash o rollback)

## Fase 3 — Memoria (sem. 4)
- [ ] `MEM0_ENABLED=true`; self-test del prefijo e5 OK en logs
- [ ] Recuerda hechos entre sesiones (test: dile algo hoy, pregúntalo mañana)
- [ ] Metadata `origin` en memorias; extracción omitida en turnos con web (probar)
- [ ] Timer de reflexión activo; `perfil_usuario.md` se actualiza y se commitea
- [ ] Cuarentena: la reflexión marca memorias sospechosas (probar con una trampa)

## Fase 4 — Acciones e internet (sem. 5)
- [ ] Workflow `recordatorio` importado con verificación HMAC (probar firma inválida → 401)
- [ ] `crear_recordatorio` habilitado: pide confirmación verbal y solo ejecuta tras tu "sí"
- [ ] `confirmar_accion` sin confirmación real del usuario → DENEGADO (probar)
- [ ] web_search + web_read funcionan; "¿qué ha pasado hoy con X?" busca y cita fuente
- [ ] Guard SSRF: `web_read http://192.168.1.1` y `http://169.254.169.254` → bloqueados
- [ ] **Página trampa propia** (con instrucciones inyectadas) NO consigue disparar un webhook ni guardar memoria

## Fase 5 — Presencia y visión (sem. 6)
- [ ] `clinfo` dentro del contenedor vision lista la UHD 630
- [ ] YOLO compila en GPU (log); post-proceso NMS implementado (TODO del esqueleto)
- [ ] Caras enroladas en /faces; reconoce a 1-3 personas
- [ ] `DISABLE_PRESENCE=false`; saluda al llegar con histéresis (no saluda dos veces)
- [ ] `ver_camara` habilitada; revalidar modelo de visión vigente en Groq
- [ ] CPU de visión en reposo < 10 %

## Fase 6 — Centro de control (sem. 7)
- [ ] `tailscale serve` para panel (443) y n8n (8443); login por identidad del tailnet
- [ ] Estado de servicios, eventos, editor de persona, toggles de tools y DND operativos
- [ ] Métricas de latencia por etapa persistidas y visibles (TODO del esqueleto)

## Fase 7 — Refinamiento (continuo)
- [ ] Speaker-ID (sherpa-onnx CAM++) como gate de acciones sensibles + PIN verbal
- [ ] STT propio con onnx-asr (quitar hop HTTP) o canary-180m plan B
- [ ] Supertonic 3 A/B vs Piper · EmbeddingGemma (re-indexar) · mem0 2.x
- [ ] Egress-deny de red para web_read · suite de páginas trampa
- [ ] Voz móvil (SmallWebRTC) · MCP · YOLO26 · wake word propia
- [ ] Upgrade Ubuntu 26.04.1 (≥ ago-2026) · revisar deprecations Groq cada fase
