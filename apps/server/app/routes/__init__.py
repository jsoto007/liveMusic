"""Blueprint registration.

Every blueprint is mounted under ``/api/v1``. Adding a route module means
adding it to ``_BLUEPRINTS`` here — there is no autodiscovery, so the full API
surface is readable in one place.
"""

API_PREFIX = "/api/v1"


def register_api_blueprints(app) -> None:
    from .artists import artists_bp
    from .auth import auth_bp
    from .comments import comments_bp
    from .email import email_bp
    from .events import events_bp
    from .feed import feed_bp
    from .geocode import geocode_bp
    from .gigs import gigs_bp
    from .inbox import inbox_bp
    from .lists import lists_bp
    from .me import me_bp
    from .messages import messages_bp
    from .reports import reports_bp
    from .reviews import reviews_bp
    from .uploads import uploads_bp
    from .users import users_bp
    from .venues import venues_bp

    blueprints = (
        auth_bp,
        email_bp,
        me_bp,
        events_bp,
        artists_bp,
        venues_bp,
        uploads_bp,
        geocode_bp,
        users_bp,
        lists_bp,
        comments_bp,
        reviews_bp,
        inbox_bp,
        reports_bp,
        gigs_bp,
        feed_bp,
        messages_bp,
    )

    for blueprint in blueprints:
        app.register_blueprint(blueprint, url_prefix=API_PREFIX)
