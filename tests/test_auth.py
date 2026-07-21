from __future__ import annotations

from jobapply.web import auth


def test_create_user_and_authenticate(temp_db):
    user_id = auth.create_user(email="a@example.com", display_name="A", password="hunter2pass")
    assert auth.authenticate("a@example.com", "hunter2pass") == user_id
    assert auth.authenticate("a@example.com", "wrong-password") is None
    assert auth.authenticate("nobody@example.com", "hunter2pass") is None


def test_list_users_returns_email_and_name_not_password(temp_db):
    auth.create_user(email="a@example.com", display_name="Alice", password="hunter2pass")
    users = auth.list_users()
    assert len(users) == 1
    assert users[0]["email"] == "a@example.com"
    assert users[0]["display_name"] == "Alice"
    assert "password" not in users[0] and "password_hash" not in users[0]


def test_get_user_id_by_email(temp_db):
    user_id = auth.create_user(email="a@example.com", display_name="A", password="hunter2pass")
    assert auth.get_user_id_by_email("a@example.com") == user_id
    assert auth.get_user_id_by_email("missing@example.com") is None


def test_reset_password_flow(temp_db):
    user_id = auth.create_user(email="a@example.com", display_name="A", password="old-password")
    assert auth.authenticate("a@example.com", "old-password") == user_id

    resolved_id = auth.get_user_id_by_email("a@example.com")
    auth.update_password(resolved_id, "new-password")

    assert auth.authenticate("a@example.com", "old-password") is None
    assert auth.authenticate("a@example.com", "new-password") == user_id
