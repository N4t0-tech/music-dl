#!/usr/bin/env zsh
# install.sh — Instala music-dl como comando global en ~/.local/bin

set -e

RESET="\033[0m"
BOLD="\033[1m"
GREEN="\033[32m"
CYAN="\033[36m"
YELLOW="\033[33m"
RED="\033[31m"
DIM="\033[2m"

info()    { print -P "%F{cyan}  ●%f $1" }
success() { print -P "%F{green}  ✔%f $1" }
warn()    { print -P "%F{yellow}  ⚠%f $1" }
err()     { print -P "%F{red}  ✖%f $1" }

# Ruta del script (absoluta, resolviendo symlinks)
SCRIPT_DIR="${0:A:h}"
SCRIPT="$SCRIPT_DIR/music-dl.py"
BIN_DIR="$HOME/.local/bin"
LINK="$BIN_DIR/music-dl"

print ""
print "${BOLD}${CYAN}  ♪ music-dl installer${RESET}"
print "${DIM}  ─────────────────────────────────────${RESET}"
print ""

# Verificar que el script existe
if [[ ! -f "$SCRIPT" ]]; then
    err "No se encontró music-dl.py en: $SCRIPT_DIR"
    exit 1
fi

# Verificar python3
if ! command -v python3 &>/dev/null; then
    err "python3 no está instalado. Instalar: sudo pacman -S python"
    exit 1
fi

# Verificar yt-dlp
if ! command -v yt-dlp &>/dev/null; then
    warn "yt-dlp no está instalado."
    print "    Instalar con: ${BOLD}sudo pacman -S yt-dlp${RESET}  o  ${BOLD}pipx install yt-dlp${RESET}"
fi

# Verificar ffmpeg
if ! command -v ffmpeg &>/dev/null; then
    warn "ffmpeg no está instalado."
    print "    Instalar con: ${BOLD}sudo pacman -S ffmpeg${RESET}"
fi

# Crear ~/.local/bin si no existe
if [[ ! -d "$BIN_DIR" ]]; then
    info "Creando $BIN_DIR…"
    mkdir -p "$BIN_DIR"
fi

# Hacer ejecutable el script
chmod +x "$SCRIPT"

# Eliminar symlink anterior si existe
if [[ -L "$LINK" ]]; then
    warn "Eliminando symlink anterior: $LINK"
    rm "$LINK"
elif [[ -e "$LINK" ]]; then
    err "$LINK ya existe y no es un symlink. Elimínalo manualmente."
    exit 1
fi

# Crear symlink
info "Creando symlink: $LINK → $SCRIPT"
ln -s "$SCRIPT" "$LINK"
success "Symlink creado."

# Verificar que ~/.local/bin está en PATH
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    warn "$BIN_DIR no está en tu PATH."
    print ""
    print "  Añade esto a tu ~/.zshrc:"
    print "  ${BOLD}export PATH=\"\$HOME/.local/bin:\$PATH\"${RESET}"
    print ""
    print "  Luego recarga con:  ${BOLD}source ~/.zshrc${RESET}"
    print ""
else
    print ""
    success "Instalación completada."
    print ""
    print "  Ejecuta ${BOLD}${CYAN}music-dl${RESET} para empezar."
fi

print ""
