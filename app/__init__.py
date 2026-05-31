def create_app():
    from flask import Flask, render_template

    from .routes import api_bp
    from .store import Store

    app = Flask(__name__)
    app.config["JSON_AS_ASCII"] = False
    app.store = Store()
    app.register_blueprint(api_bp, url_prefix="/api")

    @app.get("/")
    def index():
        return render_template("index.html")

    return app
