from pathlib import Path
from types import SimpleNamespace

from botocore.exceptions import ClientError

from scripts import seed_real_nyc
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


def test_render_predeploy_does_not_gate_api_health_on_r2_backfill():
    render_config = (Path(__file__).parents[3] / "render.yaml").read_text()

    assert "preDeployCommand: flask --app app db upgrade" in render_config
    assert "preDeployCommand: flask --app app db upgrade &&" not in render_config


def test_poster_backfill_reports_r2_access_denied_without_a_traceback(
    app, monkeypatch, tmp_path, capsys
):
    photo = tmp_path / "show.jpg"
    photo.write_bytes(b"\xff\xd8\xfftest")

    class DeniedClient:
        def put_object(self, **_kwargs):
            raise ClientError(
                {"Error": {"Code": "AccessDenied", "Message": "Access Denied"}},
                "PutObject",
            )

    monkeypatch.setattr(seed_real_nyc, "build_client", lambda: DeniedClient())
    monkeypatch.setattr(
        seed_real_nyc.R2Storage,
        "build_key",
        staticmethod(lambda *_args, **_kwargs: "events/poster/test.jpg"),
    )

    with app.app_context():
        app.config["R2_BUCKET"] = "live-msc-media"
        event = SimpleNamespace(id="event-id", poster_key=None, poster_credit=None)
        assert seed_real_nyc._upload_poster(event, str(tmp_path), photo.name) is False

    assert "AccessDenied" in capsys.readouterr().err
    assert event.poster_key is None
