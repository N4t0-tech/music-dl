# music-dl

CLI interactivo para descargar música desde YouTube en MP3, usando [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) como backend.

## Características

- Descarga canciones o playlists completas por URL
- Búsqueda de canciones y playlists directamente desde el menú
- Descarga siempre en **MP3 a máxima calidad** (`--audio-quality 0`)
- Incrusta automáticamente **metadatos y carátula** en cada archivo
- Muestra información del video (título, canal, duración) antes de descargar
- Progreso de descarga en tiempo real con barra animada
- Las playlists se guardan en una subcarpeta con el nombre de la playlist
- Directorio de salida configurable, persiste entre sesiones
- Menú interactivo con colores ANSI — sin dependencias externas de Python

## Dependencias

- Python 3.10+
- [`yt-dlp`](https://github.com/yt-dlp/yt-dlp)
- [`ffmpeg`](https://ffmpeg.org/)

En Arch Linux:

```bash
sudo pacman -S yt-dlp ffmpeg
```

## Instalación

```bash
git clone https://github.com/tu-usuario/music-dl.git
cd music-dl
./install.sh
```

El script crea un symlink en `~/.local/bin/music-dl` apuntando al archivo del repositorio. Si `~/.local/bin` no está en tu `PATH`, el instalador te indica cómo añadirlo.

## Uso

```bash
music-dl
```

```
  ♪ music-dl — YouTube → MP3 downloader
  ────────────────────────────────────────

  Directorio: /home/usuario/Música

  1  Descargar canción (URL)
  2  Descargar playlist (URL)
  3  Buscar canción en YouTube
  4  Buscar playlist en YouTube
  5  Cambiar directorio de salida
  ────────────────────────────────────────
  0  Salir
```

### Opciones

| Opción | Descripción |
|--------|-------------|
| `1` | Pega una URL de YouTube y descarga la canción como MP3 |
| `2` | Pega una URL de playlist y descarga todas las canciones |
| `3` | Busca por nombre, muestra 5 resultados y elige el número |
| `4` | Busca playlists por nombre, muestra 5 resultados y elige el número |
| `5` | Cambia el directorio de salida (se guarda para futuras sesiones) |

### Estructura de archivos generada

```
~/Música/
├── Arctic Monkeys - Do I Wanna Know.mp3
├── Tame Impala - Let It Happen.mp3
└── Random Access Memories/          ← nombre de la playlist
    ├── Daft Punk - Get Lucky.mp3
    └── Daft Punk - Instant Crush.mp3
```

## Configuración

El directorio de salida se guarda en `~/.config/music-dl/config.json`. Por defecto es `~/Música/`.

Para resetear la configuración:

```bash
rm ~/.config/music-dl/config.json
```

## Desinstalar

```bash
rm ~/.local/bin/music-dl
```
