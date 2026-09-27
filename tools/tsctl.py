#!/usr/bin/env python3
"""
tsctl — CLI admin para Tailscale SaaS
=====================================

Herramienta de línea de comandos para administrar un tailnet de Tailscale SaaS
sin abrir el admin console. Pensado para DevOps/SRE que necesita generar
authkeys, listar devices, aplicar policies, etc., desde un script o
automatización.

Uso:
    python3 tsctl.py <comando> [opciones]

Subcomandos principales:
    login-info                testea conexión con la API
    authkey create --tag ...  genera una auth key para un tag
    authkey list              lista auth keys activas (vía devices)
    device list [--tag ...]   lista devices (con filtro por tag)
    device delete <id>        elimina un device
    device expire <id>        expira un device inmediatamente
    device set-tags <id> ...  asigna tags a un device
    policy get                muestra la policy actual
    policy set <file>         aplica una policy desde un archivo .hujson
    user list                 lista usuarios del tailnet
    dns list                  lista nameservers DNS configurados
    webhooks list             lista webhooks configurados

Config:
    Las credenciales se leen de .env (en el cwd o directorios padre) o del entorno:
      TAILSCALE_API_KEY=tskey-api-...
      TAILSCALE_TAILNET=githubusercontent-com/foo  (o '-' para default)

Generá tu API key en:
    https://login.tailscale.com/admin/settings/keys
    (usar el toggle "API access", no "Auth keys")

Ejemplos:
    # Crear auth key reusable para un servicio
    python3 tsctl.py authkey create --tag tag:admin-portal --reusable --days 30

    # Crear auth key efímera para un job
    python3 tsctl.py authkey create --tag tag:warehouse-job --ephemeral --days 7

    # Crear auth key sin tag (user-owned, para empleados)
    python3 tsctl.py authkey create --days 90

    # Listar devices activos con un tag específico
    python3 tsctl.py device list --tag tag:identity-bridge

    # Aplicar una policy nueva
    python3 tsctl.py policy set ../tailscale/acl/policy.hujson

Más info:
    API ref: https://tailscale.com/kb/1101/api
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from tsctl import main

if __name__ == "__main__":
    main()
