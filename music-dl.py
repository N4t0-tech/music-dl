#!/usr/bin/env python3
"""music-dl — Interactive CLI for downloading music via yt-dlp."""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

# ─── ANSI Colors ────────────────────────────────────────────────────────────

RESET   = "\033[0m"
BOLD    = "\033[1m"
DIM     = "\033[2m"
RED     = "\033[31m"
GREEN   = "\033[32m"
YELLOW  = "\033[33m"
BLUE    = "\033[34m"
MAGENTA = "\033[35m"
CYAN    = "\033[36m"
WHITE   = "\033[37m"

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

YES_RESPONSES = ("s", "si", "sí", "y", "yes")

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

# ─── Shared helpers ──────────────────────────────────────────────────────────

def fmt_duration(secs) -> str:
    if secs is None:
        return "?"
    secs = int(secs)
    m, s = divmod(secs, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

def _parse_json_lines(text: str) -> list[dict]:
    entries = []
    for line in text.strip().splitlines():
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return entries

def _confirm(prompt: str) -> bool:
    resp = input(c(f"  {prompt} [s/N]: ", YELLOW)).strip().lower()
    return resp in YES_RESPONSES

def _normalize_yt_url(raw: str, is_playlist: bool = False) -> str:
    if raw.startswith("http"):
        return raw
    if is_playlist:
        return f"https://www.youtube.com/playlist?list={raw}"
    return f"https://www.youtube.com/watch?v={raw}"

def _pick_from_results(results: list[dict], max_option: int) -> int | None:
    choice = input(c(f"  Elegir número (1-{max_option}) o Enter para cancelar: ", YELLOW)).strip()
    if not choice:
        return None
    try:
        idx = int(choice) - 1
        if not (0 <= idx < len(results)):
            raise ValueError
        return idx
    except ValueError:
        error("Opción inválida.")
        return None

# ─── yt-dlp helpers ──────────────────────────────────────────────────────────

def get_info(url: str) -> dict | None:
    """Fetch single-video metadata without downloading."""
    try:
        result = subprocess.run(
            ["yt-dlp", "--dump-json", "--no-playlist", url],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and result.stdout.strip():
            return _parse_json_lines(result.stdout)[0]
    except (subprocess.TimeoutExpired, Exception):
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
            return _parse_json_lines(result.stdout)
    except (subprocess.TimeoutExpired, Exception):
        pass
    return []

def search_youtube(query: str, max_results: int = 5) -> list[dict]:
    """Search YouTube and return up to max_results video entries."""
    try:
        result = subprocess.run(
            ["yt-dlp", "--dump-json", "--flat-playlist",
             "--playlist-end", str(max_results),
             f"ytsearch{max_results}:{query}"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            return _parse_json_lines(result.stdout)[:max_results]
    except (subprocess.TimeoutExpired, Exception):
        pass
    return []

def search_youtube_playlists(query: str, max_results: int = 5) -> list[dict]:
    """Search YouTube for playlists and return up to max_results entries."""
    try:
        result = subprocess.run(
            ["yt-dlp", "--dump-json", "--flat-playlist",
             "--playlist-end", str(max_results),
             f"ytsearchdate{max_results}:{query} playlist"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            entries = _parse_json_lines(result.stdout)
            playlists = [e for e in entries if
                         e.get("ie_key") in ("YoutubeTab", "YoutubePlaylist")
                         or "list=" in (e.get("url") or "")
                         or e.get("playlist_id")]
            return (playlists or entries)[:max_results]
    except (subprocess.TimeoutExpired, Exception):
        pass
    return []

# ─── Download with live progress ─────────────────────────────────────────────

_PROGRESS_RE = re.compile(
    r'\[download\]\s+(\d+\.?\d*)%\s+of\s+~?\s*([\d.]+\w+)\s+at\s+([\d.]+\w+/s)\s+ETA\s+([\d:]+)'
)
_DEST_RE    = re.compile(r'\[download\] Destination: (.+)')
_ALREADY_RE = re.compile(r'\[download\] (.+) has already been downloaded')
_CONVERT_RE = re.compile(r'\[(\w+)\] (?:Destination|Converting|Embedding)')

_CONVERSION_LABELS = {
    "ffmpeg":         "Convirtiendo a MP3",
    "EmbedThumbnail": "Incrustando carátula",
    "Metadata":       "Incrustando metadatos",
}

def _progress_bar(pct: float, width: int = 30) -> str:
    filled = int(width * pct / 100)
    bar = "█" * filled + "░" * (width - filled)
    return c(bar, GREEN if pct >= 100 else CYAN)

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
        "--newline",
        "--progress",
    ]
    if not is_playlist:
        cmd += ["--no-playlist"]
    cmd.append(url)

    print()
    info(f"Directorio de salida: {c(output_dir, YELLOW)}")
    print()

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

            m = _DEST_RE.search(line)
            if m:
                print(f"\r  {c('↓', CYAN)} {c(Path(m.group(1)).name[:60], WHITE)}")
                last_pct = -1.0
                continue

            m = _ALREADY_RE.search(line)
            if m:
                warn(f"Ya descargado: {Path(m.group(1)).name}")
                continue

            m = _CONVERT_RE.search(line)
            if m:
                label = _CONVERSION_LABELS.get(m.group(1), m.group(1))
                print(f"\r  {c('⚙', YELLOW)} {label}…" + " " * 20)
                continue

            m = _PROGRESS_RE.search(line)
            if m:
                pct = float(m.group(1))
                if abs(pct - last_pct) >= 0.5 or pct >= 100:
                    last_pct = pct
                    print(
                        f"\r  {_progress_bar(pct)} {c(f'{pct:5.1f}%', BOLD)} "
                        f"{c(m.group(2), DIM)} {c('@', DIM)} {c(m.group(3), GREEN)} "
                        f"ETA {c(m.group(4), YELLOW)}    ",
                        end="", flush=True
                    )
                continue

            if line.startswith("[error]") or "ERROR" in line:
                print()
                error(line)
            elif line.startswith("[warning]") or "WARNING" in line:
                print()
                warn(line)

        proc.wait()
        print()

        if proc.returncode == 0:
            success("Descarga completada.")
        else:
            error(f"yt-dlp terminó con código {proc.returncode}")

    except KeyboardInterrupt:
        print()
        warn("Descarga cancelada por el usuario.")
        proc.terminate()

# ─── Shared playlist display + confirm ───────────────────────────────────────

def _show_playlist_and_confirm(entries: list[dict], fallback_msg: str) -> bool:
    if entries:
        total = len(entries)
        print()
        print(c(f"  {total} canciones encontradas:", DIM, WHITE))
        print()
        for i, e in enumerate(entries[:10], 1):
            title = (e.get("title") or e.get("id") or "?")[:55]
            print(f"  {c(f'{i:>2}.', DIM)} {title}  {c(fmt_duration(e.get('duration')), DIM)}")
        if total > 10:
            print(c(f"  … y {total - 10} más", DIM))
        print()
        if not _confirm(f"¿Descargar las {total} canciones?"):
            warn("Cancelado.")
            return False
        return True
    else:
        warn(fallback_msg)
        return _confirm("¿Continuar de todas formas?")

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
        pl_title = entries[0].get("playlist_title") or entries[0].get("playlist") or "Playlist"
        print()
        print(c("  Playlist: ", DIM) + c(pl_title, BOLD, WHITE))

    if not _show_playlist_and_confirm(entries, "No se pudo obtener información de la playlist (se intentará descargar igual)."):
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
        title = (r.get("title") or r.get("id") or "?")[:55]
        ch    = (r.get("uploader") or r.get("channel") or "")[:30]
        print(
            f"  {c(f'{i}.', BOLD, CYAN)} {c(title, WHITE)}\n"
            f"      {c(ch, DIM)}  {c(fmt_duration(r.get('duration')), DIM)}"
        )
        print()

    idx = _pick_from_results(results, len(results))
    if idx is None:
        return

    chosen = results[idx]
    video_url = _normalize_yt_url(
        chosen.get("url") or chosen.get("webpage_url") or chosen.get("id") or ""
    )
    if not video_url:
        error("No se pudo obtener la URL del resultado.")
        return

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
        title = (r.get("title") or r.get("id") or "?")[:55]
        ch    = (r.get("uploader") or r.get("channel") or r.get("playlist_uploader") or "")[:30]
        count = r.get("playlist_count") or r.get("n_entries")
        count_str = f"{count} canciones" if count else "? canciones"
        print(
            f"  {c(f'{i}.', BOLD, MAGENTA)} {c(title, WHITE)}\n"
            f"      {c(ch, DIM)}  {c(count_str, DIM)}"
        )
        print()

    idx = _pick_from_results(results, len(results))
    if idx is None:
        return

    chosen = results[idx]
    pl_url = _normalize_yt_url(
        chosen.get("url") or chosen.get("webpage_url") or chosen.get("id") or "",
        is_playlist=True
    )
    if not pl_url:
        error("No se pudo obtener la URL del resultado.")
        return

    info(f"Seleccionada: {c(chosen.get('title', pl_url), BOLD, WHITE)}")
    print()

    info("Obteniendo contenido de la playlist…")
    entries = get_playlist_info(pl_url)

    if not _show_playlist_and_confirm(entries, "No se pudo obtener el contenido de la playlist (se intentará descargar igual)."):
        return

    download(pl_url, cfg["output_dir"], is_playlist=True)

def action_change_dir(cfg: dict):
    print()
    print(c(f"  Directorio actual: {cfg['output_dir']}", DIM))
    new_dir = input(c("  Nuevo directorio (Enter para cancelar): ", CYAN)).strip()
    if not new_dir:
        return
    cfg["output_dir"] = str(Path(new_dir).expanduser().resolve())
    save_config(cfg)
    success(f"Directorio actualizado: {c(cfg['output_dir'], YELLOW)}")

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

            action = next((fn for key, _, fn in MENU_ITEMS if key == choice), ...)

            if choice == "0":
                clear()
                print(c("  Hasta luego ♪", DIM, CYAN))
                print()
                sys.exit(0)

            if action is ...:
                if choice:
                    print()
                    warn(f"Opción «{choice}» no válida.")
                    input(c("  Pulsa Enter para continuar…", DIM))
                continue

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
