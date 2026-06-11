# BOOTSTRAP — del Ubuntu virgen a trabajar con Claude

Pasos para el M70q recién instalado. El objetivo: dejar a **Claude Code** dentro
del repo, con todo el contexto cargado, y seguir desde la Fase 0.

> Todo lo posterior a "abrir Claude" lo puedes hacer conversando con él: conoce
> el proyecto por `CLAUDE.md`, trae el agente `jarvis-builder` y las skills.

## 0. Requisitos previos (ya hechos al llegar aquí)
- Ubuntu Server 24.04 LTS instalado, con OpenSSH y tu llave SSH.
- Acceso a internet y a tu cuenta de GitHub (`josete734`).

## 1. Instalar Claude Code
```bash
# Node 22 (si no está)
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt-get install -y nodejs git

# Claude Code
sudo npm install -g @anthropic-ai/claude-code
claude --version
```
> Si el método de instalación cambió, consulta `docs.anthropic.com/claude-code`.
> Alternativa sin npm: el instalador nativo de Anthropic (verifica el comando vigente).

## 2. Autenticar
```bash
claude            # sigue el login (abrirá una URL; en headless, ábrela desde tu PC)
```

## 3. Traer el repositorio (privado)
```bash
# autentica gh con tu cuenta y clona en /opt/jarvis
sudo mkdir -p /opt/jarvis && sudo chown "$USER" /opt/jarvis
gh auth login                       # GitHub.com → HTTPS → navegador
gh repo clone josete734/jarvis /opt/jarvis
```
> Si prefieres no usar `gh`: añade una deploy key o clona por HTTPS con un PAT.

## 4. Abrir Claude en el proyecto
```bash
cd /opt/jarvis
claude
```
Primer mensaje sugerido (cópialo tal cual):

> Lee `CLAUDE.md` y `docs/FASES.md`. Estamos en un server virgen: guíame en la
> **Fase 0** paso a paso (preparación del host y prueba de AEC). Usa el agente
> `jarvis-builder` y la skill `advance-phase`.

A partir de ahí Claude tiene todo el contexto. La Fase 0, resumida, es:

```bash
# (Claude te irá guiando; estos son los hitos)
sudo bash scripts/install_host.sh          # zram, governor, docker, ufw, grupos, dirs
sudo tailscale up                          # unir al tailnet
# montar el SSD SATA en /srv/jarvis y el USB en /mnt/backup (fstab por UUID, nofail)
cp .env.example .env && nano .env          # claves y RENDER_GID (getent group render)
bash scripts/test_aec.sh plughw:1,0        # PUERTA: prueba de eco del micro/altavoz
```

## 5. Seguir
- `docs/FASES.md` es el checklist maestro. Tras la Fase 0 viene construir e
  instalar modelos (`make build && make models`) y la Fase 1 (oídos y voz).
- Operación diaria: skill `deploy-operate` y `docs/RUNBOOK.md`.

## Notas
- El repo NO contiene secretos: `.env` se crea desde `.env.example` en el server
  y está en `.gitignore`.
- Si reinstalas el SO, basta repetir este BOOTSTRAP: el estado vive en
  `/srv/jarvis` y los backups en `/mnt/backup` (restic).
