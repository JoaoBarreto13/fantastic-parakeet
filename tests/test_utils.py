import os
import sys
from pathlib import Path
import pytest

# Garantir que o root do projeto esteja no sys.path para imports durante pytest
sys.path.append(str(Path(__file__).resolve().parent.parent))

from stremio_utils import format_size, extract_quality, build_magnet, parse_quality_rank


def test_format_size_bytes():
    assert format_size(512) == "512 B"


def test_format_size_gb():
    assert format_size(3 * 1024**3) == "3.0 GB" or format_size(3 * 1024**3).startswith("3.0")


def test_extract_quality():
    assert extract_quality("Inception.2010.1080p.BluRay") == "1080p"
    assert extract_quality("some 4K content") == "2160p"
    assert extract_quality("lowres 360p") == "360p"


def test_build_magnet_with_infohash():
    stream = {"infoHash": "abcdef123456", "name": "Test Torrent", "sources": ["tracker:https://t.example/announce"]}
    magnet = build_magnet(stream)
    assert "magnet:?xt=urn:btih:abcdef123456" in magnet
    assert "tr=" in magnet


def test_parse_quality_rank():
    assert parse_quality_rank("1080p") < parse_quality_rank("720p")
 