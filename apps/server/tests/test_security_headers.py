"""Response headers, asserted because two of them are easy to lose silently."""


def test_api_responses_are_not_cacheable(client):
    response = client.get("/api/v1/events")
    # Several API responses carry presigned URLs and user-scoped data; a shared
    # proxy must not keep them.
    assert response.headers["Cache-Control"] == "no-store"


def test_hardening_headers_are_present(client):
    response = client.get("/api/v1/events")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_permissions_policy_survives_talismans_default(client):
    """Regression: a `setdefault` here lost to Talisman's own default, so the
    camera/microphone restrictions never shipped."""
    policy = client.get("/api/v1/events").headers["Permissions-Policy"]
    assert "camera=()" in policy
    assert "microphone=()" in policy


def test_csp_forbids_inline_script(client):
    csp = client.get("/api/v1/events").headers["Content-Security-Policy"]
    assert "script-src 'self'" in csp
    assert "unsafe-eval" not in csp
    # 'unsafe-inline' is permitted for styles only, never for scripts.
    script_directive = [part for part in csp.split(";") if part.strip().startswith("script-src")]
    assert script_directive and "unsafe-inline" not in script_directive[0]


def test_csp_allows_the_browser_to_upload_directly_to_r2(client, app):
    """Without R2 in connect-src the direct upload is blocked by the policy."""
    csp = client.get("/api/v1/events").headers["Content-Security-Policy"]
    connect = [part for part in csp.split(";") if part.strip().startswith("connect-src")][0]
    assert "r2.cloudflarestorage.com" in connect, csp
    assert app.config["R2_ENDPOINT_URL"]


def test_a_bare_hostname_is_normalised_to_an_origin(app):
    """Render's `fromService: property: host` yields a bare hostname. Left as
    is, every origin comparison and every emailed link would be wrong."""
    from app.security import normalize_origin

    assert normalize_origin("live-msc-web.onrender.com") == "https://live-msc-web.onrender.com"
    assert normalize_origin("https://livemsc.org/") == "https://livemsc.org"
    # Loopback is the one case that is plain http — a dev server has no TLS.
    assert normalize_origin("localhost:5173") == "http://localhost:5173"
    assert normalize_origin("") == ""


def test_email_links_use_configured_origins_not_the_request_host(app):
    """Trusting the inbound Host is how a reset link ends up pointing at an
    attacker's domain."""
    from app.services.email_links import api_url, site_url

    app.config["FRONTEND_URL"] = "live-msc-web.onrender.com"
    app.config["PUBLIC_API_URL"] = "live-msc-api.onrender.com"

    with app.test_request_context("/", headers={"Host": "evil.example"}):
        assert site_url() == "https://live-msc-web.onrender.com"
        assert api_url() == "https://live-msc-api.onrender.com"


def test_the_api_url_falls_back_to_the_site_when_unset(app):
    """Same-origin deploys need only one variable."""
    from app.services.email_links import api_url

    app.config["FRONTEND_URL"] = "https://livemsc.org"
    app.config["PUBLIC_API_URL"] = ""
    with app.test_request_context("/"):
        assert api_url() == "https://livemsc.org"
