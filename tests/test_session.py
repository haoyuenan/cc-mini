import json

from core.session import SessionStore, _sanitize_cwd


def test_session_store_persists_locale(tmp_path, monkeypatch):
    monkeypatch.setattr("core.session._SESSIONS_ROOT", tmp_path)

    store = SessionStore(
        cwd="/tmp/project",
        model="test-model",
        session_id="session-locale",
        locale="zh-CN",
    )
    store.append_message({"role": "user", "content": "hello"})

    meta_path = tmp_path / _sanitize_cwd("/tmp/project") / "session-locale.meta.json"
    data = json.loads(meta_path.read_text(encoding="utf-8"))

    assert data["locale"] == "zh-CN"

    sessions = SessionStore.list_sessions("/tmp/project")
    assert len(sessions) == 1
    assert sessions[0].locale == "zh-CN"


def test_load_session_defaults_locale_to_none_for_legacy_meta(tmp_path, monkeypatch):
    monkeypatch.setattr("core.session._SESSIONS_ROOT", tmp_path)

    session_dir = tmp_path / _sanitize_cwd("/tmp/project")
    session_dir.mkdir(parents=True, exist_ok=True)

    meta_path = session_dir / "legacy.meta.json"
    meta_path.write_text(
        json.dumps(
            {
                "session_id": "legacy",
                "title": "Legacy Session",
                "cwd": "/tmp/project",
                "model": "test-model",
                "created_at": "2026-04-03T00:00:00+00:00",
                "updated_at": "2026-04-03T00:00:00+00:00",
                "message_count": 0,
                "mode": None,
            }
        ),
        encoding="utf-8",
    )

    sessions = SessionStore.list_sessions("/tmp/project")

    assert len(sessions) == 1
    assert sessions[0].locale is None
