#!/usr/bin/env python3
"""music-dl — Interactive CLI for downloading music via yt-dlp."""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

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

def c(text, *codes):      return "".join(codes) + str(text) + RESET
def clear():              print("\033[2J\033[H", end="", flush=True)
def info(msg):            print(c("  ● ", CYAN)   + msg)
def success(msg):         print(c("  ✔ ", GREEN)  + msg)
def warn(msg):            print(c("  ⚠ ", YELLOW) + msg)
def error(msg):           print(c("  ✖ ", RED)    + msg)
def sep():                print(c("  " + "─" * 40, DIM, BLUE))

def banner():
    print()
    print(c("  ♪ music-dl ", BOLD, CYAN) + c("— YouTube → MP3 downloader", DIM, WHITE))
    sep()
    print()

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

_INSTALL_HINTS = {
    "yt-dlp": "sudo pacman -S yt-dlp  " + c("o", DIM) + "  pipx install yt-dlp",
    "ffmpeg": "sudo pacman -S ffmpeg",
}

def check_deps():
    missing = [d for d in _INSTALL_HINTS if shutil.which(d) is None]
    if missing:
        error(f"Dependencias faltantes: {', '.join(missing)}")
        print()
        for dep in missing:
            print(c("    Instalar: ", DIM) + _INSTALL_HINTS[dep])
        print()
        sys.exit(1)

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
        if line := line.strip():
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return entries

def _run_ytdlp(args: list[str], timeout: int = 30) -> list[dict]:
    try:
        r = subprocess.run(["yt-dlp"] + args, capture_output=True, text=True, timeout=timeout)
        if r.returncode == 0:
            return _parse_json_lines(r.stdout)
    except (subprocess.TimeoutExpired, Exception):
        pass
    return []

def _confirm(prompt: str) -> bool:
    return input(c(f"  {prompt} [s/N]: ", YELLOW)).strip().lower() in YES_RESPONSES

def _normalize_yt_url(raw: str, is_playlist: bool = False) -> str:
    if raw.startswith("http"):
        return raw
    return f"https://www.youtube.com/playlist?list={raw}" if is_playlist \
           else f"https://www.youtube.com/watch?v={raw}"

def _pick_from_results(results: list[dict]) -> int | None:
    choice = input(c(f"  Elegir número (1-{len(results)}) o Enter para cancelar: ", YELLOW)).strip()
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

def get_info(url: str) -> dict | None:
    entries = _run_ytdlp(["--dump-json", "--no-playlist", url])
    return entries[0] if entries else None

def get_playlist_info(url: str) -> list[dict]:
    return _run_ytdlp(["--dump-json", "--flat-playlist", url], timeout=60)

def search_youtube(query: str, n: int = 5) -> list[dict]:
    return _run_ytdlp(["--dump-json", "--flat-playlist", "--playlist-end", str(n),
                       f"ytsearch{n}:{query}"])[:n]

def search_youtube_playlists(query: str, n: int = 5) -> list[dict]:
    entries = _run_ytdlp(["--dump-json", "--flat-playlist", "--playlist-end", str(n),
                          f"ytsearchdate{n}:{query} playlist"])
    playlists = [e for e in entries if
                 e.get("ie_key") in ("YoutubeTab", "YoutubePlaylist")
                 or "list=" in (e.get("url") or "")
                 or e.get("playlist_id")]
    return (playlists or entries)[:n]

_PROGRESS_RE = re.compile(
    r'\[download\]\s+(\d+\.?\d*)%\s+of\s+~?\s*([\d.]+\w+)\s+at\s+([\d.]+\w+/s)\s+ETA\s+([\d:]+)'
)
_DEST_RE    = re.compile(r'\[download\] Destination: (.+)')
_ALREADY_RE = re.compile(r'\[download\] (.+) has already been downloaded')
_CONVERT_RE = re.compile(r'\[(\w+)\] (?:Destination|Converting|Embedding)')
_CONVERSION_LABELS = {
    "ffmpeg": "Convirtiendo a MP3",
    "EmbedThumbnail": "Incrustando carátula",
    "Metadata": "Incrustando metadatos",
}

def download(url: str, output_dir: str, is_playlist: bool = False,
             playlist_name: str = "", total_tracks: int = 0):
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    subdir   = "%(playlist)s/" if is_playlist else ""
    template = str(out_path / f"{subdir}%(artist)s - %(title)s.%(ext)s")

    cmd = ["yt-dlp", "--extract-audio", "--audio-format", "mp3", "--audio-quality", "0",
           "--embed-metadata", "--embed-thumbnail", "--add-metadata",
           "--output", template, "--newline", "--progress"]
    if not is_playlist:
        cmd += ["--no-playlist"]
    cmd.append(url)

    print()
    display_dir = str(out_path / playlist_name) if playlist_name else output_dir
    info(f"Directorio de salida: {c(display_dir, YELLOW)}")
    print()

    last_pct    = -1.0
    mid_line    = False
    current_trk = 0

    def end_line():
        nonlocal mid_line
        if mid_line:
            print()
            mid_line = False

    def track_prefix() -> str:
        if total_tracks:
            return c(f"[{current_trk}/{total_tracks}] ", DIM)
        return ""

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, bufsize=1)
        for raw_line in proc.stdout:
            line = raw_line.rstrip()
            if m := _DEST_RE.search(line):
                end_line()
                current_trk += 1
                print(f"  {track_prefix()}{c('↓', CYAN)} {c(Path(m.group(1)).name[:55], WHITE)}")
                last_pct = -1.0
            elif m := _ALREADY_RE.search(line):
                end_line()
                current_trk += 1
                warn(f"{track_prefix()}Ya descargado: {Path(m.group(1)).name}")
            elif m := _CONVERT_RE.search(line):
                label = _CONVERSION_LABELS.get(m.group(1), m.group(1))
                print(f"\r  {c('⚙', YELLOW)} {label}…" + " " * 20)
                mid_line = False
            elif m := _PROGRESS_RE.search(line):
                pct = float(m.group(1))
                if abs(pct - last_pct) >= 0.5 or pct >= 100:
                    last_pct = pct
                    filled = int(30 * pct / 100)
                    bar = c("█" * filled + "░" * (30 - filled), GREEN if pct >= 100 else CYAN)
                    print(f"\r  {bar} {c(f'{pct:5.1f}%', BOLD)} "
                          f"{c(m.group(2), DIM)} {c('@', DIM)} {c(m.group(3), GREEN)} "
                          f"ETA {c(m.group(4), YELLOW)}    ", end="", flush=True)
                    mid_line = True
            elif "ERROR" in line or line.startswith("[error]"):
                end_line(); error(line)
            elif "WARNING" in line or line.startswith("[warning]"):
                end_line(); warn(line)

        proc.wait()
        end_line()
        if proc.returncode == 0:
            success("Descarga completada.")
        else:
            error(f"yt-dlp terminó con código {proc.returncode}")

    except KeyboardInterrupt:
        end_line()
        warn("Descarga cancelada por el usuario.")
        proc.terminate()

def _show_playlist_and_confirm(entries: list[dict], fallback_msg: str) -> bool:
    if not entries:
        warn(fallback_msg)
        return _confirm("¿Continuar de todas formas?")
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

def action_download_song(cfg: dict):
    print()
    url = input(c("  URL de la canción: ", CYAN)).strip()
    if not url:
        return warn("URL vacía, cancelando.")
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
        return warn("URL vacía, cancelando.")
    info("Obteniendo información de la playlist…")
    entries  = get_playlist_info(url)
    pl_title = ""
    if entries:
        pl_title = entries[0].get("playlist_title") or entries[0].get("playlist") or ""
        print()
        print(c("  Playlist: ", DIM) + c(pl_title or "Playlist", BOLD, WHITE))
    if _show_playlist_and_confirm(entries, "No se pudo obtener información de la playlist (se intentará descargar igual)."):
        download(url, cfg["output_dir"], is_playlist=True,
                 playlist_name=pl_title, total_tracks=len(entries))

def _search_and_download(cfg: dict, prompt: str, search_fn, is_playlist: bool):
    print()
    query = input(c(f"  {prompt}: ", CYAN)).strip()
    if not query:
        return warn("Búsqueda vacía, cancelando.")
    info(f"Buscando «{query}» en YouTube…")
    results = search_fn(query)
    if not results:
        return error("No se encontraron resultados.")
    print()
    for i, r in enumerate(results, 1):
        title = (r.get("title") or r.get("id") or "?")[:55]
        ch    = (r.get("uploader") or r.get("channel") or r.get("playlist_uploader") or "")[:30]
        num_color = MAGENTA if is_playlist else CYAN
        extra = fmt_duration(r.get("duration"))
        if is_playlist:
            count = r.get("playlist_count") or r.get("n_entries")
            extra = f"{count} canciones" if count else "? canciones"
        print(f"  {c(f'{i}.', BOLD, num_color)} {c(title, WHITE)}\n      {c(ch, DIM)}  {c(extra, DIM)}")
        print()
    idx = _pick_from_results(results)
    if idx is None:
        return
    chosen  = results[idx]
    raw_url = chosen.get("url") or chosen.get("webpage_url") or chosen.get("id") or ""
    url     = _normalize_yt_url(raw_url, is_playlist=is_playlist)
    if not url:
        return error("No se pudo obtener la URL del resultado.")
    label = "Seleccionada" if is_playlist else "Seleccionado"
    info(f"{label}: {c(chosen.get('title', url), BOLD, WHITE)}")
    pl_name, pl_total = "", 0
    if is_playlist:
        print()
        info("Obteniendo contenido de la playlist…")
        entries = get_playlist_info(url)
        if not _show_playlist_and_confirm(entries, "No se pudo obtener el contenido de la playlist (se intentará descargar igual)."):
            return
        pl_name  = chosen.get("title", "")
        pl_total = len(entries)
    download(url, cfg["output_dir"], is_playlist=is_playlist,
             playlist_name=pl_name, total_tracks=pl_total)

def action_search(cfg: dict):
    _search_and_download(cfg, "Nombre de la canción", search_youtube, is_playlist=False)

def action_search_playlist(cfg: dict):
    _search_and_download(cfg, "Nombre de la playlist", search_youtube_playlists, is_playlist=True)

def action_change_dir(cfg: dict):
    print()
    print(c(f"  Directorio actual: {cfg['output_dir']}", DIM))
    new_dir = input(c("  Nuevo directorio (Enter para cancelar): ", CYAN)).strip()
    if not new_dir:
        return
    cfg["output_dir"] = str(Path(new_dir).expanduser().resolve())
    save_config(cfg)
    success(f"Directorio actualizado: {c(cfg['output_dir'], YELLOW)}")

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
