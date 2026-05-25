import sys
from pathlib import Path
from pathlib import Path

# Ensure project root available for imports
sys.path.append(str(Path(__file__).resolve().parent.parent))

from stremio_utils import find_subtitles
from stremio_utils import rename_subtitle_to_match


def test_find_subtitles_prioritizes_ptbr(tmp_path: Path):
    d = tmp_path
    # create files
    (d / "movie.en.srt").write_text("en content")
    (d / "movie.pt.srt").write_text("pt content")
    (d / "movie.pt-br.ass").write_text("pt-br content")
    subs = find_subtitles(d)
    assert len(subs) == 3
    # first should be pt-br
    assert subs[0]["lang"] == "pt-br"
    # second pt
    assert subs[1]["lang"] == "pt"
    # third other
    assert subs[2]["lang"] == "other"


def test_rename_subtitle_to_match(tmp_path: Path):
    video = tmp_path / "Movie.Name.mkv"
    video.write_text("x")
    sub = tmp_path / "movie.pt.srt"
    sub.write_text("leg")
    new = rename_subtitle_to_match(video, sub)
    assert new.exists()
    assert new.name.startswith("Movie.Name")
