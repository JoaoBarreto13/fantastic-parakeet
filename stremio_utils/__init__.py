"""Utils package with small helpers used by tests."""
import re
from pathlib import Path
from urllib.parse import quote_plus


def parse_quality_rank(quality: str | None) -> int:
    quality = (quality or "").lower()
    for index, item in enumerate(["2160p", "4k", "1080p", "720p", "480p", "360p"]):
        if item in quality:
            return index
    return 999


def format_size(value: int | None) -> str:
    if not value:
        return "? GB"
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(value)
    unit_index = 0
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    if unit_index == 0:
        return f"{int(size)} {units[unit_index]}"
    return f"{size:.1f} {units[unit_index]}"


def extract_quality(text: str) -> str:
    lowered = text.lower()
    if "2160p" in lowered or "4k" in lowered:
        return "2160p"
    if "1080p" in lowered:
        return "1080p"
    if "720p" in lowered:
        return "720p"
    if "480p" in lowered:
        return "480p"
    if "360p" in lowered:
        return "360p"
    return "unknown"


def build_magnet(stream: dict) -> str:
    info_hash = stream.get("infoHash")
    if not info_hash:
        return stream.get("url", "")
    dn = quote_plus(stream.get("name", "torrent"))
    magnet = f"magnet:?xt=urn:btih:{info_hash}&dn={dn}"
    for tracker in stream.get("sources", []) or []:
        if isinstance(tracker, str) and tracker.startswith("tracker:"):
            magnet += f"&tr={quote_plus(tracker.removeprefix('tracker:'))}"
    return magnet


def find_subtitles(directory: str | Path) -> list[dict]:
    """Procura arquivos .srt e .ass dentro de `directory` e prioriza PT/BR."""
    from pathlib import Path

    p = Path(directory)
    subs = []
    for path in sorted(p.rglob("*.srt")) + sorted(p.rglob("*.ass")):
        name = path.name
        lowered = name.lower()
        lang = "other"
        if "pt-br" in lowered or "ptbr" in lowered or "portugu" in lowered:
            lang = "pt-br"
        elif "pt" in lowered:
            lang = "pt"
        subs.append({"path": str(path), "name": name, "lang": lang})
    # Priorize pt-br, depois pt, depois outros
    subs.sort(key=lambda s: (0 if s["lang"] == "pt-br" else (1 if s["lang"] == "pt" else 2), s["name"]))
    return subs


def rename_subtitle_to_match(video_path: str | Path, subtitle_path: str | Path) -> Path:
    """Copia a legenda e renomeia para casar com o nome do vídeo.

    Retorna o caminho para o novo arquivo de legenda.
    """
    v = Path(video_path)
    s = Path(subtitle_path)
    target = s.parent / (v.stem + s.suffix)
    # se já existir, gerar sufixo numérico
    if target.exists():
        for i in range(1, 100):
            candidate = s.parent / f"{v.stem}_{i}{s.suffix}"
            if not candidate.exists():
                target = candidate
                break
    from shutil import copy2

    copy2(s, target)
    return target
