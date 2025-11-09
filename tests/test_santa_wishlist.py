import asyncio
from types import SimpleNamespace

from python.santa_wishlist import SantaWishlist


class DummyLogger:
    def __init__(self):
        self.messages = []

    def debug(self, message, *args):
        self.messages.append(("debug", message % args if args else message))

    def info(self, message, *args):
        self.messages.append(("info", message % args if args else message))

    def warning(self, message, *args):
        self.messages.append(("warning", message % args if args else message))

    def error(self, message, *args):
        self.messages.append(("error", message % args if args else message))


class DummyEventManager:
    def __init__(self):
        self.errors = []
        self.registered = []

    def plugin_error(self, name, message, action):
        self.errors.append((name, message, action))

    def wish_registered(self, name, payload):
        self.registered.append((name, payload))


class DummyConnection:
    def __init__(self):
        self.entries = []
        self.table_created = False

    def create_table(self, _name, _schema):
        self.table_created = True

    def execute_query(self, query, params):
        text = " ".join(query.split()).lower()

        if text.startswith("insert into"):
            entry = {
                "child_hash": params[0],
                "child_name": params[1],
                "age": params[2],
                "wish": params[3],
                "created_at": params[4],
                "entry_id": params[5],
                "locale": params[6],
            }
            self.entries.append(entry)
            return {"lastrowid": len(self.entries)}

        if "count(*)" in text and "where child_hash = ?" in text:
            child_hash = params[0]
            total = sum(1 for entry in self.entries if entry["child_hash"] == child_hash)
            return {"data": [[total]]}

        if text.startswith("select wish, created_at") and "limit 5" in text:
            child_hash = params[0]
            rows = [
                (entry["wish"], entry["created_at"])
                for entry in reversed(self.entries)
                if entry["child_hash"] == child_hash
            ][:5]
            return {"data": rows}

        if text.startswith("select wish, created_at"):
            child_hash = params[0]
            rows = [
                (entry["wish"], entry["created_at"])
                for entry in self.entries
                if entry["child_hash"] == child_hash
            ]
            rows.sort(key=lambda value: value[1], reverse=True)
            return {"data": rows}

        if "count(*)" in text and "count(distinct child_hash)" in text:
            return {
                "data": [
                    [len(self.entries), len({entry["child_hash"] for entry in self.entries})]
                ]
            }

        if text.startswith("select wish, count(*)"):
            wish_totals = {}
            for entry in self.entries:
                wish_totals.setdefault(entry["wish"], {"total": 0, "last_seen": entry["created_at"]})
                wish_totals[entry["wish"]]["total"] += 1
                wish_totals[entry["wish"]]["last_seen"] = max(
                    wish_totals[entry["wish"]]["last_seen"], entry["created_at"]
                )
            ordered = sorted(
                wish_totals.items(),
                key=lambda item: (-item[1]["total"], item[1]["last_seen"]),
            )[:5]
            return {"data": [(wish, data["total"], data["last_seen"]) for wish, data in ordered]}

        return {"data": []}


class DummyDatabaseManager:
    def __init__(self):
        self.connection = DummyConnection()

    def get_connection(self, _name, _config, check_same_thread=True):  # noqa: ARG002 - signature compatibility
        return self.connection


class DummyHass:
    def __init__(self):
        self.logger = DummyLogger()
        self.event_manager = DummyEventManager()
        self.database_manager = DummyDatabaseManager()
        self.config = SimpleNamespace(language="en")
        self.instance_id = "dummy-instance"


def test_register_without_entry_id_uses_fallback_and_succeeds():
    hass = DummyHass()
    tool = SantaWishlist(hass, config={})

    result = asyncio.run(
        tool.handle(action="register", name="Charlie", age=7, wish="A new sled")
    )

    assert result["status"] == "success"
    assert "ledger is unavailable" not in result["message"].lower()
    assert tool.config["entry_id"].startswith(tool.name)
    warnings = [message for level, message in hass.logger.messages if level == "warning"]
    assert any("entry_id missing" in message for message in warnings)
    assert hass.event_manager.errors == []

    # Ensure a second call does not emit another warning and reuses the fallback entry_id
    asyncio.run(tool.handle(action="register", name="Charlie", age=7, wish="Warm mittens"))
    warnings = [message for level, message in hass.logger.messages if level == "warning"]
    assert len(warnings) == 1
    assert len(hass.database_manager.connection.entries) == 2


def test_list_returns_entries_after_registering():
    hass = DummyHass()
    tool = SantaWishlist(hass, config={})

    asyncio.run(tool.handle(action="register", name="Alex", age=8, wish="A telescope"))
    result = asyncio.run(tool.handle(action="list", name="Alex", age=8))

    assert result["status"] == "success"
    assert result["total"] == 1
    assert result["wishes"][0]["wish"] == "A telescope"
    assert "Alex" in result["message"]
