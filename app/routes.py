from functools import wraps

from flask import Blueprint, current_app, jsonify, request


api_bp = Blueprint("api", __name__)


def json_ok(data=None):
    return jsonify({"ok": True, "data": data})


def json_error(message, status=400):
    return jsonify({"ok": False, "error": str(message)}), status


def body():
    return request.get_json(silent=True) or {}


def handle_errors(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ValueError as exc:
            return json_error(exc, 400)
        except Exception as exc:
            return json_error(exc, 500)

    return wrapper


def store():
    return current_app.store


@api_bp.get("/status")
@handle_errors
def status():
    return json_ok(store().status())


@api_bp.post("/create")
@handle_errors
def create_database():
    payload = body()
    return json_ok(store().create_database(payload.get("password"), payload.get("confirm_password")))


@api_bp.post("/unlock")
@handle_errors
def unlock():
    return json_ok(store().unlock(body().get("password")))


@api_bp.post("/lock")
@handle_errors
def lock():
    store().lock()
    return json_ok(store().status())


@api_bp.get("/providers")
@handle_errors
def providers():
    return json_ok(store().providers())


@api_bp.put("/providers/order")
@handle_errors
def reorder_providers():
    return json_ok(store().reorder_providers(body().get("ids")))


@api_bp.post("/providers")
@handle_errors
def add_provider():
    return json_ok(store().add_provider(body()))


@api_bp.get("/providers/<int:provider_id>")
@handle_errors
def provider_detail(provider_id):
    return json_ok(store().provider_detail(provider_id))


@api_bp.put("/providers/<int:provider_id>")
@handle_errors
def update_provider(provider_id):
    return json_ok(store().update_provider(provider_id, body()))


@api_bp.delete("/providers/<int:provider_id>")
@handle_errors
def delete_provider(provider_id):
    store().delete_provider(provider_id)
    return json_ok()


@api_bp.patch("/providers/<int:provider_id>/test-key")
@handle_errors
def set_provider_test_key(provider_id):
    return json_ok(store().set_provider_test_key(provider_id, body().get("key_id")))


@api_bp.post("/providers/<int:provider_id>/keys")
@handle_errors
def add_key(provider_id):
    return json_ok(store().add_key(provider_id, body()))


@api_bp.put("/providers/<int:provider_id>/keys/order")
@handle_errors
def reorder_keys(provider_id):
    return json_ok(store().reorder_keys(provider_id, body().get("ids")))


@api_bp.put("/keys/<int:key_id>")
@handle_errors
def update_key(key_id):
    return json_ok(store().update_key(key_id, body()))


@api_bp.delete("/keys/<int:key_id>")
@handle_errors
def delete_key(key_id):
    store().delete_key(key_id)
    return json_ok()


@api_bp.post("/providers/<int:provider_id>/keys/<int:key_id>/test")
@handle_errors
def test_key(provider_id, key_id):
    return json_ok(store().test_key(provider_id, key_id))


@api_bp.post("/providers/<int:provider_id>/test-selected-key")
@handle_errors
def test_selected_key(provider_id):
    return json_ok(store().test_key(provider_id))


@api_bp.get("/settings/test")
@handle_errors
def test_settings():
    return json_ok(store().test_settings())


@api_bp.put("/settings/test")
@handle_errors
def save_test_settings():
    return json_ok(store().save_test_settings(body()))


@api_bp.get("/providers/<int:provider_id>/test-config")
@handle_errors
def test_config(provider_id):
    return json_ok(store().provider_test_config(provider_id))


@api_bp.put("/providers/<int:provider_id>/test-config")
@handle_errors
def save_test_config(provider_id):
    return json_ok(store().save_provider_test_config(provider_id, body()))


@api_bp.post("/providers/<int:provider_id>/models/refresh")
@handle_errors
def refresh_models(provider_id):
    return json_ok(store().refresh_models(provider_id))


@api_bp.get("/generic")
@handle_errors
def generic_categories():
    return json_ok(store().generic_categories())


@api_bp.put("/generic/categories/order")
@handle_errors
def reorder_generic_categories():
    return json_ok(store().reorder_generic_categories(body().get("categories")))


@api_bp.put("/generic/category/<path:category>/order")
@handle_errors
def reorder_generic_keys(category):
    return json_ok(store().reorder_generic_keys(category, body().get("ids")))


@api_bp.post("/generic")
@handle_errors
def add_generic_key():
    return json_ok(store().add_generic_key(body()))


@api_bp.put("/generic/<int:item_id>")
@handle_errors
def update_generic_key(item_id):
    return json_ok(store().update_generic_key(item_id, body()))


@api_bp.delete("/generic/<int:item_id>")
@handle_errors
def delete_generic_key(item_id):
    store().delete_generic_key(item_id)
    return json_ok()


@api_bp.delete("/generic/category/<path:category>")
@handle_errors
def delete_generic_category(category):
    store().delete_generic_category(category)
    return json_ok()
