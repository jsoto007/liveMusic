from pathlib import Path

from scripts.seed_real_nyc import EVENTS


def test_every_seed_event_has_a_unique_matching_photo_asset():
    photos_dir = Path(__file__).parents[1] / "seed_photos" / "nyc"
    filenames = [event[-1] for event in EVENTS]

    assert len(filenames) == len(set(filenames))

    for filename in filenames:
        path = photos_dir / filename
        assert path.is_file(), f"Missing stock photo for seed event: {filename}"
        assert path.read_bytes()[:3] == b"\xff\xd8\xff", f"Not a JPEG: {filename}"
        assert path.stat().st_size < 8 * 1024 * 1024
