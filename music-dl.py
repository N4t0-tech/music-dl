#!/usr/bin/env python3
"""music-dl — Interactive CLI for downloading music via yt-dlp."""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# ─── ANSI Colors ────────────────────────────────────────────────────────────

RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"

BLACK   = "\033[30m"
RED     = "\033[31m"
GREEN   = "\033[32m"
YELLOW  = "\033[33m"
BLUE    = "\033[34m"
MAGENTA = "\033[35m"
CYAN    = "\033[36m"
WHITE   = "\033[37m"

BG_BLACK = "\033[40m"

def c(text, *codes):
    return "".join(codes) + str(text) + RESET

def clear():
    print("\033[2J\033[H", end="", flush=True)

def banner():
    print()
    print(c("  ♪ music-dl ", BOLD, CYAN) + c("— YouTube → MP3 downloader", DIM, WHITE))
    print(c("  " + "─" * 40, DIM, BLUE))
    print()

def info(msg):    print(c("  ● ", CYAN)  + msg)
def success(msg): print(c("  ✔ ", GREEN) + msg)
def warn(msg):    print(c("  ⚠ ", YELLOW) + msg)
def error(msg):   print(c("  ✖ ", RED)   + msg)
def sep():        print(c("  " + "─" * 40, DIM, BLUE))

# ─── Config ──────────────────────────────────────────────────────────────────

CONFIG_DIR  = Path.home() / ".config" / "music-dl"
CONFIG_FILE = CONFIG_DIR / "config.json"
DEFAULT_DIR = Path.home() / "Música"

def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except json.JSONDecodeError:
            pass
    return {"output_dir": str(DEFAULT_DIR)}

def save_config(cfg: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))

# ─── Dependency check ────────────────────────────────────────────────────────

def check_deps():
    missing = []
    for dep in ("yt-dlp", "ffmpeg"):
        if shutil.which(dep) is None:
            missing.append(dep)
    if missing:
        error(f"Dependencias faltantes: {', '.join(missing)}")
        print()
        for dep in missing:
            if dep == "yt-dlp":
                print(c("    Instalar: ", DIM) + "sudo pacman -S yt-dlp  " + c("o", DIM) + "  pipx install yt-dlp")
            elif dep == "ffmpeg":
                print(c("    Instalar: ", DIM) + "sudo pacman -S ffmpeg")
        print()
        sys.exit(1)

# ─── yt-dlp helpers ──────────────────────────────────────────────────────────

def fmt_duration(secs) -> str:
    if secs is None:
        return "?"
    secs = int(secs)
    m, s = divmod(secs, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

def fmt_bytes(b) -> str:
    if b is None:
        return "?"
    for unit in ("B", "KB", "MB", "GB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} TB"

def get_info(url: str) -> dict | None:
    """Fetch video/playlist metadata as JSON without downloading."""
    try:
        result = subprocess.run(
            ["yt-dlp", "--dump-json", "--no-playlist", url],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout.strip().splitlines()[0])
    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception):
        pass
    return None

def get_playlist_info(url: str) -> list[dict]:
    """Fetch all entries in a playlist."""
    try:
        result = subprocess.run(
            ["yt-dlp", "--dump-json", "--flat-playlist", url],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            entries = []
            for line in result.stdout.strip().splitlines():
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
            return entries
    except (subprocess.TimeoutExpired, Exception):
        pass
    return []

def search_youtube(query: str, max_results: int = 5) -> list[dict]:
    """Search YouTube and return up to max_results video entries."""
    try:
        result = subprocess.run(
            ["yt-dlp",
             "--dump-json",
             "--flat-playlist",
             "--playlist-end", str(max_results),
             f"ytsearch{max_results}:{query}"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            entries = []
            for line in result.stdout.strip().splitlines():
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
            return entries[:max_results]
    except (subprocess.TimeoutExpired, Exception):
        pass
    return []

def search_youtube_playlists(query: str, max_results: int = 5) -> list[dict]:
    """Search YouTube for playlists and return up to max_results entries."""
    try:
        result = subprocess.run(
            ["yt-dlp",
             "--dump-json",
             "--flat-playlist",
             "--playlist-end", str(max_results),
             f"ytsearchdate{max_results}:{query} playlist"],
            capture_output=True, text=True, timeout=30
        )
        entries = []
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        # Filter to keep only playlist results (ie_key == YoutubeTab or has playlist_id)
        playlists = [e for e in entries if
                     e.get("ie_key") in ("YoutubeTab", "YoutubePlaylist")
                     or "list=" in (e.get("url") or "")
                     or e.get("playlist_id")]
        # If no playlists detected, return all results and let the user decide
        return (playlists or entries)[:max_results]
    except (subprocess.TimeoutExpired, Exception):
        pass
    return []

# ─── Download with live progress ─────────────────────────────────────────────

# yt-dlp progress line patterns
_PROGRESS_RE = re.compile(
    r'\[download\]\s+(\d+\.?\d*)%\s+of\s+~?\s*([\d.]+\w+)\s+at\s+([\d.]+\w+/s)\s+ETA\s+([\d:]+)'
)
_DEST_RE = re.compile(r'\[download\] Destination: (.+)')
_ALREADY_RE = re.compile(r'\[download\] (.+) has already been downloaded')
_CONVERT_RE = re.compile(r'\[(\w+)\] (?:Destination|Converting|Embedding)')

def _progress_bar(pct: float, width: int = 30) -> str:
    filled = int(width * pct / 100)
    bar = "█" * filled + "░" * (width - filled)
    color = GREEN if pct >= 100 else CYAN
    return c(bar, color)

def download(url: str, output_dir: str, is_playlist: bool = False):
    """Run yt-dlp and display live progress."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    if is_playlist:
        template = str(out_path / "%(playlist)s" / "%(artist)s - %(title)s.%(ext)s")
    else:
        template = str(out_path / "%(artist)s - %(title)s.%(ext)s")

    cmd = [
        "yt-dlp",
        "--extract-audio",
        "--audio-format", "mp3",
        "--audio-quality", "0",
        "--embed-metadata",
        "--embed-thumbnail",
        "--add-metadata",
        "--output", template,
        "--newline",          # one progress line per line (easier to parse)
        "--progress",
    ]
    if not is_playlist:
        cmd += ["--no-playlist"]
    cmd.append(url)

    print()
    info(f"Directorio de salida: {c(output_dir, YELLOW)}")
    print()

    current_file = ""
    last_pct = -1.0

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        for raw_line in proc.stdout:
            line = raw_line.rstrip()

            # Destination file
            m = _DEST_RE.search(line)
            if m:
                current_file = Path(m.group(1)).name
                print(f"\r  {c('↓', CYAN)} {c(current_file[:60], WHITE)}")
                last_pct = -1.0
                continue

            # Already downloaded
            m = _ALREADY_RE.search(line)
            if m:
                warn(f"Ya descargado: {Path(m.group(1)).name}")
                continue

            # Conversion / embedding step
            m = _CONVERT_RE.search(line)
            if m:
                step = m.group(1)
                label = {"ffmpeg": "Convirtiendo a MP3", "EmbedThumbnail": "Incrustando carátula",
                         "Metadata": "Incrustando metadatos"}.get(step, step)
                print(f"\r  {c('⚙', YELLOW)} {label}…" + " " * 20)
                continue

            # Progress
            m = _PROGRESS_RE.search(line)
            if m:
                pct  = float(m.group(1))
                size = m.group(2)
                spd  = m.group(3)
                eta  = m.group(4)
                if abs(pct - last_pct) >= 0.5 or pct >= 100:
                    last_pct = pct
                    bar = _progress_bar(pct)
                    print(
                        f"\r  {bar} {c(f'{pct:5.1f}%', BOLD)} "
                        f"{c(size, DIM)} {c('@', DIM)} {c(spd, GREEN)} "
                        f"ETA {c(eta, YELLOW)}    ",
                        end="", flush=True
                    )
                continue

            # Other yt-dlp output (errors, warnings)
            if line.startswith("[error]") or "ERROR" in line:
                print()
                error(line)
            elif line.startswith("[warning]") or "WARNING" in line:
                print()
                warn(line)

        proc.wait()
        print()  # newline after progress bar

        if proc.returncode == 0:
            success("Descarga completada.")
        else:
            error(f"yt-dlp terminó con código {proc.returncode}")

    except KeyboardInterrupt:
        print()
        warn("Descarga cancelada por el usuario.")
        proc.terminate()

# ─── Menu actions ────────────────────────────────────────────────────────────

def action_download_song(cfg: dict):
    print()
    url = input(c("  URL de la canción: ", CYAN)).strip()
    if not url:
        warn("URL vacía, cancelando.")
        return

    info("Obteniendo información…")
    meta = get_info(url)
    if meta:
        print()
        print(c("  Título:   ", DIM) + c(meta.get("title", "?"), BOLD, WHITE))
        print(c("  Canal:    ", DIM) + c(meta.get("uploader") or meta.get("channel") or "?", WHITE))
        print(c("  Duración: ", DIM) + c(fmt_duration(meta.get("duration")), WHITE))
        print()
    else:
        warn("No se pudo obtener información previa (se intentará descargar igual).")

    download(url, cfg["output_dir"])

def action_download_playlist(cfg: dict):
    print()
    url = input(c("  URL de la playlist: ", CYAN)).strip()
    if not url:
        warn("URL vacía, cancelando.")
        return

    info("Obteniendo información de la playlist…")
    entries = get_playlist_info(url)

    if entries:
        total = len(entries)
        pl_title = entries[0].get("playlist_title") or entries[0].get("playlist") or "Playlist"
        print()
        print(c("  Playlist: ", DIM) + c(pl_title, BOLD, WHITE))
        print(c(f"  {total} canciones encontradas:", DIM, WHITE))
        print()
        for i, e in enumerate(entries[:10], 1):
            dur = fmt_duration(e.get("duration"))
            title = (e.get("title") or e.get("id") or "?")[:55]
            print(f"  {c(f'{i:>2}.', DIM)} {title}  {c(dur, DIM)}")
        if total > 10:
            print(c(f"  … y {total - 10} más", DIM))
        print()
        resp = input(c(f"  ¿Descargar las {total} canciones? [s/N]: ", YELLOW)).strip().lower()
        if resp not in ("s", "si", "sí", "y", "yes"):
            warn("Cancelado.")
            return
    else:
        warn("No se pudo obtener información de la playlist (se intentará descargar igual).")
        resp = input(c("  ¿Continuar de todas formas? [s/N]: ", YELLOW)).strip().lower()
        if resp not in ("s", "si", "sí", "y", "yes"):
            return

    download(url, cfg["output_dir"], is_playlist=True)

def action_search(cfg: dict):
    print()
    query = input(c("  Nombre de la canción: ", CYAN)).strip()
    if not query:
        warn("Búsqueda vacía, cancelando.")
        return

    info(f"Buscando «{query}» en YouTube…")
    results = search_youtube(query)

    if not results:
        error("No se encontraron resultados.")
        return

    print()
    for i, r in enumerate(results, 1):
        dur   = fmt_duration(r.get("duration"))
        title = (r.get("title") or r.get("id") or "?")[:55]
        ch    = (r.get("uploader") or r.get("channel") or "")[:30]
        print(
            f"  {c(f'{i}.', BOLD, CYAN)} {c(title, WHITE)}\n"
            f"      {c(ch, DIM)}  {c(dur, DIM)}"
        )
        print()

    choice = input(c("  Elegir número (1-5) o Enter para cancelar: ", YELLOW)).strip()
    if not choice:
        return
    try:
        idx = int(choice) - 1
        if not (0 <= idx < len(results)):
            raise ValueError
    except ValueError:
        error("Opción inválida.")
        return

    chosen = results[idx]
    video_url = chosen.get("url") or chosen.get("webpage_url") or chosen.get("id")
    if not video_url:
        error("No se pudo obtener la URL del resultado.")
        return

    # Make sure it's a full URL
    if not video_url.startswith("http"):
        video_url = f"https://www.youtube.com/watch?v={video_url}"

    info(f"Seleccionado: {c(chosen.get('title', video_url), BOLD, WHITE)}")
    download(video_url, cfg["output_dir"])

def action_search_playlist(cfg: dict):
    print()
    query = input(c("  Nombre de la playlist: ", CYAN)).strip()
    if not query:
        warn("Búsqueda vacía, cancelando.")
        return

    info(f"Buscando playlists «{query}» en YouTube…")
    results = search_youtube_playlists(query)

    if not results:
        error("No se encontraron resultados.")
        return

    print()
    for i, r in enumerate(results, 1):
        title  = (r.get("title") or r.get("id") or "?")[:55]
        ch     = (r.get("uploader") or r.get("channel") or r.get("playlist_uploader") or "")[:30]
        count  = r.get("playlist_count") or r.get("n_entries")
        count_str = f"{count} canciones" if count else "? canciones"
        print(
            f"  {c(f'{i}.', BOLD, MAGENTA)} {c(title, WHITE)}\n"
            f"      {c(ch, DIM)}  {c(count_str, DIM)}"
        )
        print()

    choice = input(c(f"  Elegir número (1-{len(results)}) o Enter para cancelar: ", YELLOW)).strip()
    if not choice:
        return
    try:
        idx = int(choice) - 1
        if not (0 <= idx < len(results)):
            raise ValueError
    except ValueError:
        error("Opción inválida.")
        return

    chosen = results[idx]
    pl_url = chosen.get("url") or chosen.get("webpage_url") or chosen.get("id")
    if not pl_url:
        error("No se pudo obtener la URL del resultado.")
        return

    if not pl_url.startswith("http"):
        # Could be a playlist id or video id — try as playlist
        if "list=" not in pl_url:
            pl_url = f"https://www.youtube.com/playlist?list={pl_url}"
        else:
            pl_url = f"https://www.youtube.com/{pl_url}"

    info(f"Seleccionada: {c(chosen.get('title', pl_url), BOLD, WHITE)}")
    print()

    # Fetch full playlist info for confirmation
    info("Obteniendo contenido de la playlist…")
    entries = get_playlist_info(pl_url)

    if entries:
        total = len(entries)
        print()
        print(c(f"  {total} canciones encontradas:", DIM, WHITE))
        print()
        for i, e in enumerate(entries[:10], 1):
            dur   = fmt_duration(e.get("duration"))
            title = (e.get("title") or e.get("id") or "?")[:55]
            print(f"  {c(f'{i:>2}.', DIM)} {title}  {c(dur, DIM)}")
        if total > 10:
            print(c(f"  … y {total - 10} más", DIM))
        print()
        resp = input(c(f"  ¿Descargar las {total} canciones? [s/N]: ", YELLOW)).strip().lower()
        if resp not in ("s", "si", "sí", "y", "yes"):
            warn("Cancelado.")
            return
    else:
        warn("No se pudo obtener el contenido de la playlist (se intentará descargar igual).")
        resp = input(c("  ¿Continuar de todas formas? [s/N]: ", YELLOW)).strip().lower()
        if resp not in ("s", "si", "sí", "y", "yes"):
            return

    download(pl_url, cfg["output_dir"], is_playlist=True)

def action_change_dir(cfg: dict):
    print()
    current = cfg["output_dir"]
    print(c(f"  Directorio actual: {current}", DIM))
    new_dir = input(c("  Nuevo directorio (Enter para cancelar): ", CYAN)).strip()
    if not new_dir:
        return
    new_dir = str(Path(new_dir).expanduser().resolve())
    cfg["output_dir"] = new_dir
    save_config(cfg)
    success(f"Directorio actualizado: {c(new_dir, YELLOW)}")

# ─── Main menu ───────────────────────────────────────────────────────────────

MENU_ITEMS = [
    ("1", "Descargar canción (URL)",      action_download_song),
    ("2", "Descargar playlist (URL)",     action_download_playlist),
    ("3", "Buscar canción en YouTube",    action_search),
    ("4", "Buscar playlist en YouTube",   action_search_playlist),
    ("5", "Cambiar directorio de salida", action_change_dir),
    ("0", "Salir",                        None),
]

def print_menu(cfg: dict):
    banner()
    print(c(f"  Directorio: {cfg['output_dir']}", DIM))
    print()
    for key, label, _ in MENU_ITEMS:
        if key == "0":
            sep()
            print(f"  {c(key, DIM, RED)}  {c(label, DIM)}")
        else:
            print(f"  {c(key, BOLD, CYAN)}  {label}")
    print()

def main():
    check_deps()
    cfg = load_config()

    while True:
        try:
            clear()
            print_menu(cfg)
            choice = input(c("  » ", BOLD, CYAN)).strip()

            action = None
            for key, _, fn in MENU_ITEMS:
                if choice == key:
                    action = fn
                    break

            if choice == "0" or action is None and choice != "":
                if choice == "0":
                    clear()
                    print(c("  Hasta luego ♪", DIM, CYAN))
                    print()
                    sys.exit(0)
                else:
                    # Opción inválida: mostrar aviso brevemente sin limpiar aún
                    print()
                    warn(f"Opción «{choice}» no válida.")
                    input(c("  Pulsa Enter para continuar…", DIM))
                    continue

            if action:
                clear()
                try:
                    action(cfg)
                except KeyboardInterrupt:
                    print()
                    warn("Operación cancelada.")

            sep()
            input(c("  Pulsa Enter para continuar…", DIM))

        except KeyboardInterrupt:
            clear()
            print(c("  Hasta luego ♪", DIM, CYAN))
            print()
            sys.exit(0)

if __name__ == "__main__":
    main()
