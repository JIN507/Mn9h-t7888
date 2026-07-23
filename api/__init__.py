"""API blueprints - thin HTTP layer over services/."""


def register_blueprints(app):
    from api.auth import bp as auth_bp
    from api.admin import bp as admin_bp
    from api.detection import bp as detection_bp
    from api.files import bp as files_bp
    from api.media import bp as media_bp
    from api.provenance import bp as provenance_bp
    from api.search import bp as search_bp

    for bp in (auth_bp, admin_bp, detection_bp, files_bp,
               media_bp, provenance_bp, search_bp):
        app.register_blueprint(bp)
