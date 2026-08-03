"""The LocationIQ proxy.

Upstream is stubbed throughout. The point of these tests is the proxy's own
behaviour — that the key never leaves the server, that failures are soft, and
that the cache actually absorbs repetition.
"""

import pytest

from app.services import geocoding


@pytest.fixture(autouse=True)
def clean_cache(app):
    """The cache is process-wide, so it has to be cleared between tests."""
    with app.app_context():
        geocoding.clear_cache()
    yield
    with app.app_context():
        geocoding.clear_cache()


@pytest.fixture()
def locationiq(monkeypatch, app):
    """A stub upstream that records the calls made to it."""
    app.config["LOCATIONIQ_API_KEY"] = "test-key"
    calls = []

    sample = [
        {
            "lat": "41.8180",
            "lon": "-71.4460",
            "display_name": "Dusk, Olneyville, Providence, Rhode Island, USA",
            "name": "Dusk",
            "address": {
                "name": "Dusk",
                "neighbourhood": "Olneyville",
                "city": "Providence",
                "postcode": "02909",
                "country": "United States",
            },
        }
    ]

    class _Response:
        status_code = 200

        @staticmethod
        def json():
            return sample

    def _get(url, params=None, timeout=None):
        calls.append({"url": url, "params": params or {}})
        return _Response()

    monkeypatch.setattr(geocoding.requests, "get", _get)
    return calls


# ── The key stays here ─────────────────────────────────────────────────────


def test_the_api_key_is_never_in_a_response(client, auth, locationiq):
    """The whole reason this proxy exists."""
    response = client.get("/api/v1/geocode/autocomplete?q=Dusk%20Providence", headers=auth())

    assert response.status_code == 200
    assert b"test-key" not in response.data

    place = response.get_json()["data"]["places"][0]
    assert set(place) == {
        "label", "name", "city", "neighborhood", "postcode", "country",
        "latitude", "longitude",
    }


def test_the_key_is_sent_upstream(locationiq, app, client, auth):
    client.get("/api/v1/geocode/autocomplete?q=Dusk%20Providence", headers=auth())
    assert locationiq[0]["params"]["key"] == "test-key"


def test_autocomplete_requires_authentication(client, locationiq):
    """An open proxy is a way for anyone to spend our LocationIQ quota."""
    assert client.get("/api/v1/geocode/autocomplete?q=Dusk").status_code == 401
    assert locationiq == []


def test_reverse_requires_authentication(client, locationiq):
    assert client.get(
        "/api/v1/geocode/reverse?latitude=41.8&longitude=-71.4"
    ).status_code == 401


# ── Shape ──────────────────────────────────────────────────────────────────


def test_a_result_is_flattened_to_what_a_form_needs(client, auth, locationiq):
    place = client.get(
        "/api/v1/geocode/autocomplete?q=Dusk%20Providence", headers=auth()
    ).get_json()["data"]["places"][0]

    assert place["name"] == "Dusk"
    assert place["city"] == "Providence"
    assert place["neighborhood"] == "Olneyville"
    assert place["latitude"] == pytest.approx(41.8180)
    assert place["longitude"] == pytest.approx(-71.4460)


def test_a_result_without_usable_coordinates_is_dropped(client, auth, monkeypatch, app):
    app.config["LOCATIONIQ_API_KEY"] = "test-key"

    class _Response:
        status_code = 200

        @staticmethod
        def json():
            return [{"display_name": "Somewhere", "lat": "not-a-number", "lon": "0"}]

    monkeypatch.setattr(geocoding.requests, "get", lambda *a, **k: _Response())

    places = client.get(
        "/api/v1/geocode/autocomplete?q=somewhere", headers=auth()
    ).get_json()["data"]["places"]
    assert places == []


# ── Quota discipline ───────────────────────────────────────────────────────


def test_a_repeated_lookup_does_not_hit_upstream_twice(client, auth, locationiq):
    """An autocomplete field fires on nearly every keystroke; without a cache
    the free tier is gone in an afternoon."""
    headers = auth()
    for _ in range(5):
        client.get("/api/v1/geocode/autocomplete?q=Dusk%20Providence", headers=headers)

    assert len(locationiq) == 1


def test_a_very_short_query_never_reaches_upstream(client, auth, locationiq):
    headers = auth()
    client.get("/api/v1/geocode/autocomplete?q=Du", headers=headers)
    assert locationiq == []


def test_an_empty_query_returns_empty_without_an_upstream_call(client, auth, locationiq):
    response = client.get("/api/v1/geocode/autocomplete?q=", headers=auth())
    assert response.get_json()["data"]["places"] == []
    assert locationiq == []


def test_a_transport_failure_is_cached_only_briefly(client, auth, monkeypatch, app):
    """Two competing hazards, both real.

    Caching a failure for the full hour would suppress lookups long after the
    outage ended. Not caching it at all means every keystroke pays the full
    upstream timeout on a form's critical path while the outage lasts. The
    answer is a short failure TTL — held here, but far below the success one.
    """
    app.config["LOCATIONIQ_API_KEY"] = "test-key"
    attempts = []

    def _boom(*args, **kwargs):
        attempts.append(1)
        raise geocoding.requests.RequestException("upstream down")

    monkeypatch.setattr(geocoding.requests, "get", _boom)
    headers = auth()

    for _ in range(4):
        client.get("/api/v1/geocode/autocomplete?q=Dusk%20Providence", headers=headers)
    assert len(attempts) == 1, "an outage must not be re-hammered on every keystroke"

    assert geocoding._FAILURE_CACHE_SECONDS < app.config["GEOCODE_CACHE_SECONDS"]


# ── Failing soft ───────────────────────────────────────────────────────────


def test_an_upstream_outage_returns_empty_rather_than_an_error(
    client, auth, monkeypatch, app
):
    """Address lookup is an assist, never a gate."""
    app.config["LOCATIONIQ_API_KEY"] = "test-key"
    monkeypatch.setattr(
        geocoding.requests,
        "get",
        lambda *a, **k: (_ for _ in ()).throw(geocoding.requests.Timeout()),
    )

    response = client.get("/api/v1/geocode/autocomplete?q=Dusk%20Providence", headers=auth())
    assert response.status_code == 200
    assert response.get_json()["data"]["places"] == []


def test_an_unconfigured_key_is_reported_not_fatal(client, auth, app):
    app.config["LOCATIONIQ_API_KEY"] = ""
    response = client.get("/api/v1/geocode/autocomplete?q=Dusk%20Providence", headers=auth())

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["places"] == []
    # The client uses this to fall back to a plain text field rather than
    # showing a typeahead that will never suggest anything.
    assert data["configured"] is False


def test_a_rate_limited_upstream_returns_empty(client, auth, monkeypatch, app):
    app.config["LOCATIONIQ_API_KEY"] = "test-key"

    class _Limited:
        status_code = 429

        @staticmethod
        def json():
            return {}

    monkeypatch.setattr(geocoding.requests, "get", lambda *a, **k: _Limited())
    response = client.get("/api/v1/geocode/autocomplete?q=Dusk%20Providence", headers=auth())
    assert response.status_code == 200
    assert response.get_json()["data"]["places"] == []


# ── Validation ─────────────────────────────────────────────────────────────


def test_reverse_rejects_impossible_coordinates(client, auth, locationiq):
    headers = auth()
    assert client.get(
        "/api/v1/geocode/reverse?latitude=95&longitude=0", headers=headers
    ).status_code == 400
    assert client.get(
        "/api/v1/geocode/reverse?latitude=41&longitude=999", headers=headers
    ).status_code == 400


def test_a_country_filter_must_be_iso_codes(client, auth, locationiq):
    response = client.get(
        "/api/v1/geocode/autocomplete?q=Dusk%20Providence&countries=us;DROP", headers=auth()
    )
    assert response.status_code == 400


def test_a_country_filter_is_passed_upstream(client, auth, locationiq):
    client.get(
        "/api/v1/geocode/autocomplete?q=Dusk%20Providence&countries=us,ca", headers=auth()
    )
    # Canonicalised: sorted and de-duplicated, so casing and ordering cannot be
    # varied to produce a different cache key for the same query.
    assert locationiq[0]["params"]["countrycodes"] == "ca,us"


def test_an_over_long_query_is_refused(client, auth, locationiq):
    response = client.get(
        f"/api/v1/geocode/autocomplete?q={'x' * 500}", headers=auth()
    )
    assert response.status_code == 400


# ── Venue creation uses it ─────────────────────────────────────────────────


def test_posting_a_show_geocodes_a_typed_venue(client, auth, locationiq):
    """A band that types a room name still gets a pin on the map."""
    from datetime import timedelta

    from app.models import utcnow

    response = client.post(
        "/api/v1/events",
        json={
            "headline": "Bloodroot Choir",
            "starts_at": (utcnow() + timedelta(days=1)).isoformat(),
            "venue": {"name": "Dusk", "city": "Providence"},
            "publish": True,
        },
        headers=auth(),
    )
    assert response.status_code == 201

    venue = response.get_json()["data"]["event"]["venue"]
    assert venue["latitude"] == pytest.approx(41.8180)
    assert venue["longitude"] == pytest.approx(-71.4460)
    assert venue["neighborhood"] == "Olneyville"


def test_supplied_coordinates_are_not_overwritten(client, auth, locationiq):
    """A client that used the autocomplete already has the exact place."""
    from datetime import timedelta

    from app.models import utcnow

    response = client.post(
        "/api/v1/events",
        json={
            "headline": "Bloodroot Choir",
            "starts_at": (utcnow() + timedelta(days=1)).isoformat(),
            "venue": {
                "name": "Dusk",
                "city": "Providence",
                "latitude": 12.5,
                "longitude": 34.5,
            },
            "publish": True,
        },
        headers=auth(),
    )
    venue = response.get_json()["data"]["event"]["venue"]
    assert venue["latitude"] == pytest.approx(12.5)
    assert venue["longitude"] == pytest.approx(34.5)
    assert locationiq == [], "no lookup is needed when the client already knows"


def test_posting_a_show_still_works_when_geocoding_is_down(client, auth, monkeypatch, app):
    """The listing matters more than the pin."""
    from datetime import timedelta

    from app.models import utcnow

    app.config["LOCATIONIQ_API_KEY"] = "test-key"
    monkeypatch.setattr(
        geocoding.requests,
        "get",
        lambda *a, **k: (_ for _ in ()).throw(geocoding.requests.Timeout()),
    )

    response = client.post(
        "/api/v1/events",
        json={
            "headline": "Bloodroot Choir",
            "starts_at": (utcnow() + timedelta(days=1)).isoformat(),
            "venue": {"name": "Dusk", "city": "Providence"},
            "publish": True,
        },
        headers=auth(),
    )
    assert response.status_code == 201
    assert response.get_json()["data"]["event"]["venue"]["latitude"] is None


# ── Hardening (2026-08-03 review) ──────────────────────────────────────────


def test_the_api_key_is_never_written_to_a_log(client, auth, monkeypatch, app):
    """`requests` embeds the full URL — key included — in every connection-level
    error, and this fires on exactly the outage the module exists to survive.

    Captured off the app's own logger: it sets `propagate = False`, so pytest's
    `caplog` (which listens on the root) sees nothing.
    """
    import logging

    app.config["LOCATIONIQ_API_KEY"] = "SUPER-SECRET-KEY"
    records = []

    class _Capture(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    handler = _Capture(level=logging.WARNING)
    app.logger.addHandler(handler)

    def _boom(*args, **kwargs):
        raise geocoding.requests.ConnectionError(
            "HTTPSConnectionPool(host='us1.locationiq.com', port=443): Max retries "
            "exceeded with url: /v1/autocomplete?q=x&key=SUPER-SECRET-KEY&format=json"
        )

    monkeypatch.setattr(geocoding.requests, "get", _boom)
    try:
        client.get("/api/v1/geocode/autocomplete?q=Dusk%20Providence", headers=auth())
    finally:
        app.logger.removeHandler(handler)

    logged = "\n".join(records)
    assert "SUPER-SECRET-KEY" not in logged
    assert "ConnectionError" in logged


def test_cosmetic_variants_of_one_query_share_a_cache_entry(client, auth, locationiq):
    """`strip().lower()` alone was defeated by a double space or a stray comma —
    seven spellings of one address were seven upstream calls."""
    headers = auth()
    for variant in [
        "Dusk Providence",
        "dusk providence",
        "  Dusk   Providence  ",
        "Dusk Providence,",
        "DUSK PROVIDENCE.",
        "Dusk\u00a0Providence",
        "\uff24usk Providence",
    ]:
        client.get(
            f"/api/v1/geocode/autocomplete?q={variant}", headers=headers
        )

    assert len(locationiq) == 1


def test_country_filters_are_canonicalised_before_they_key_the_cache(
    client, auth, locationiq
):
    """`us`, `US`, `us,us`, `ca,us` all mean the same thing and must not each
    buy their own upstream call."""
    headers = auth()
    for variant in ["us,ca", "ca,us", "US,CA", "us,ca,us", " us , ca "]:
        client.get(
            f"/api/v1/geocode/autocomplete?q=Dusk%20Providence&countries={variant}",
            headers=headers,
        )

    assert len(locationiq) == 1


def test_a_country_filter_is_bounded(client, auth, locationiq):
    response = client.get(
        "/api/v1/geocode/autocomplete?q=Dusk%20Providence&countries=usa,france",
        headers=auth(),
    )
    assert response.status_code == 400


def test_the_daily_budget_caps_upstream_spend(client, auth, locationiq, app):
    """The per-user limit bounds one caller; this bounds the bill."""
    app.config["LOCATIONIQ_DAILY_BUDGET"] = 3
    headers = auth()

    for index in range(10):
        client.get(f"/api/v1/geocode/autocomplete?q=Query%20number%20{index}", headers=headers)

    assert len(locationiq) == 3
    assert geocoding.budget_remaining() == 0


def test_nan_and_out_of_range_coordinates_are_dropped(client, auth, monkeypatch, app):
    """Unvalidated, these reach the response as literal NaN/Infinity — which is
    not valid JSON, so every client's parse throws — and are copied onto the
    venue row, poisoning every listing that serializes it."""
    app.config["LOCATIONIQ_API_KEY"] = "test-key"

    class _Response:
        status_code = 200

        @staticmethod
        def json():
            return [
                {"display_name": "NaN", "lat": "nan", "lon": "0"},
                {"display_name": "Infinite", "lat": "1e400", "lon": "-1e400"},
                {"display_name": "Off the globe", "lat": "9999", "lon": "0"},
                {"display_name": "Fine", "lat": "41.8", "lon": "-71.4"},
            ]

    monkeypatch.setattr(geocoding.requests, "get", lambda *a, **k: _Response())

    response = client.get("/api/v1/geocode/autocomplete?q=anything", headers=auth())
    body = response.get_data(as_text=True)

    assert "NaN" not in body
    assert "Infinity" not in body
    places = response.get_json()["data"]["places"]
    assert [place["label"] for place in places] == ["Fine"]


def test_an_over_long_upstream_string_is_clamped(client, auth, monkeypatch, app):
    """SQLite accepts an over-long String(120) silently; Postgres raises a
    DataError, which is not a requests exception and so escapes the module's
    'nothing raises' contract and 500s the show post."""
    app.config["LOCATIONIQ_API_KEY"] = "test-key"

    class _Response:
        status_code = 200

        @staticmethod
        def json():
            return [
                {
                    "display_name": "x" * 5000,
                    "lat": "41.8",
                    "lon": "-71.4",
                    "address": {"neighbourhood": "y" * 5000, "city": "z" * 5000},
                }
            ]

    monkeypatch.setattr(geocoding.requests, "get", lambda *a, **k: _Response())

    place = client.get(
        "/api/v1/geocode/autocomplete?q=anything", headers=auth()
    ).get_json()["data"]["places"][0]

    assert len(place["label"]) <= 300
    assert len(place["neighborhood"]) <= 120
    assert len(place["city"]) <= 120


def test_a_non_string_upstream_field_is_dropped_not_stored(client, auth, monkeypatch, app):
    app.config["LOCATIONIQ_API_KEY"] = "test-key"

    class _Response:
        status_code = 200

        @staticmethod
        def json():
            return [
                {
                    "display_name": "Somewhere",
                    "lat": "41.8",
                    "lon": "-71.4",
                    "address": {"city": {"nested": "object"}, "postcode": 12345},
                }
            ]

    monkeypatch.setattr(geocoding.requests, "get", lambda *a, **k: _Response())

    place = client.get(
        "/api/v1/geocode/autocomplete?q=anything", headers=auth()
    ).get_json()["data"]["places"][0]
    assert place["city"] is None
    assert place["postcode"] is None


def test_a_cached_result_cannot_be_mutated_by_a_caller(client, auth, locationiq, app):
    """The stored list used to be handed out by reference."""
    with app.test_request_context():
        first = geocoding.autocomplete("Dusk Providence")
        first[0]["name"] = "MUTATED"
        second = geocoding.autocomplete("Dusk Providence")
    assert second[0]["name"] == "Dusk"
