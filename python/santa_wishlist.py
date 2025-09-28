from __future__ import annotations

import asyncio
import hashlib
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import voluptuous as vol

from custom_components.aurora_llm_assistant.tools.core.base_tool import SimpleBaseTool
from custom_components.aurora_llm_assistant.tools.core.database_manager import DatabaseError
from custom_components.aurora_llm_assistant.tools.core.event_manager import EventType
from custom_components.aurora_llm_assistant.tools.core.schema_manager import (
    ActionSpec,
    BaseSchema,
    CommonFieldSpecs,
    FieldSpec,
    register_schema,
)

ISO_FORMAT = "%Y-%m-%dT%H:%M:%S%z"
DEFAULT_TREND_RANGE_DAYS = 30


@register_schema("santa_wishlist")
class SantaWishlistSchema(BaseSchema):
    """Centralized schema describing the Santa wishlist actions."""

    def __init__(self) -> None:
        super().__init__()

        action_field = replace(CommonFieldSpecs.ACTION)
        action_options = [
            {"value": "register", "label": "register"},
            {"value": "list", "label": "list"},
            {"value": "trending", "label": "trending"},
        ]
        widget_options = dict(action_field.widget_options)
        widget_options["trigger_update"] = True
        widget_options["options"] = action_options
        action_field.widget_options = widget_options

        self.register_field("action", action_field)
        self.register_field("name", CommonFieldSpecs.NAME)
        self.register_field("age", CommonFieldSpecs.AGE)
        self.register_field(
            "wish",
            FieldSpec(
                type=str,
                description="Christmas wish to register",
                widget="textarea",
                validation=vol.All(str, vol.Length(min=3, max=280)),
            ),
        )

        self.register_action(
            "register",
            ActionSpec(
                required=["action", "name", "wish"],
                optional=["age"],
                hidden=[],
                description="Register a new Christmas wish",
            ),
        )

        self.register_action(
            "list",
            ActionSpec(
                required=["action", "name", "age"],
                optional=[],
                hidden=["wish"],
                description="Show all wishes saved for a specific person",
            ),
        )

        self.register_action(
            "trending",
            ActionSpec(
                required=["action"],
                optional=[],
                hidden=["name", "age", "wish"],
                description="Show trending wishes registered with Santa",
            ),
        )

        self.set_friendly_name("Tomtens önskelista")


class SantaWishlist(SimpleBaseTool):
    """Manage Christmas wishes stored for Santa."""

    name = "santa_wishlist"
    description = "Register, list and analyse wishes destined for Santa."
    author = "Aurora Home"
    version = "1.0.0"
    category = "christmas"
    requires: List[str] = []

    def __init__(self, hass, config: Optional[Dict[str, Any]] = None) -> None:
        self._connection = None
        self._tables_ready = False
        self._db_lock = asyncio.Lock()
        super().__init__(hass, config)

    def on_unload(self) -> None:
        self._connection = None
        self._tables_ready = False

    async def handle(
        self,
        action: str = "register",
        name: Optional[str] = None,
        age: Optional[int] = None,
        wish: Optional[str] = None,
    ) -> Dict[str, Any]:
        action = (action or "register").strip().lower()

        if action == "register":
            return await self._register_wish(name, wish, age)
        if action == "list":
            return await self._list_wishes(name, age)
        if action == "trending":
            return await self._get_trending_wishes()

        return {
            "status": "error",
            "message": f"Unknown action '{action}'. Available actions: register, list, trending.",
        }

    async def _register_wish(
        self,
        name: Optional[str],
        wish: Optional[str],
        age: Optional[int],
    ) -> Dict[str, Any]:
        normalized_name = self._normalize_name(name)
        if not normalized_name:
            return {"status": "error", "message": "Please provide the name of the person."}

        sanitized_wish = self._sanitize_wish(wish)
        if not sanitized_wish:
            return {"status": "error", "message": "A wish is required to register with Santa."}

        if age is not None and not isinstance(age, int):
            return {"status": "error", "message": "Age must be a whole number."}

        connection = await self._ensure_connection()
        if not connection:
            return {
                "status": "error",
                "message": "Santa's ledger is unavailable right now. Please try again later.",
            }

        child_hash = self._child_hash(normalized_name, age)
        created_at = self._utc_now_iso()
        entry_id = str(self.config.get("entry_id", ""))

        table = self._table_name("wishlist_entries")
        insert_sql = (
            f"INSERT INTO {table} (child_hash, child_name, age, wish, created_at, entry_id, locale) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)"
        )
        params = [
            child_hash,
            normalized_name,
            age,
            sanitized_wish,
            created_at,
            entry_id,
            self._get_locale(),
        ]

        try:
            result = await self.hass.async_add_executor_job(connection.execute_query, insert_sql, params)
        except DatabaseError as error:
            self._logger.error("Failed to register wish: %s", error)
            self.event_manager.plugin_error(self.name, str(error), "register_wish")
            return {
                "status": "error",
                "message": "Could not store the wish due to a database error. Please try again later.",
            }

        wish_id = result.get("lastrowid")

        total_result = await self._select(
            f"SELECT COUNT(*) FROM {table} WHERE child_hash = ?",
            [child_hash],
        )
        total_for_child = int(total_result[0][0]) if total_result else 1

        recent_rows = await self._select(
            f"SELECT wish, created_at FROM {table} WHERE child_hash = ? ORDER BY created_at DESC LIMIT 5",
            [child_hash],
        )
        recent_wishes = [
            {"wish": row[0], "created_at": row[1]} for row in recent_rows
        ]

        self.event_manager.wish_registered(
            self.name,
            {
                "person_name": normalized_name,
                "person_age": age,
                "wish_text": sanitized_wish,
                "wish_id": wish_id,
                "registered_at": created_at,
                "entry_id": entry_id,
            },
        )

        message = (
            f"Santa logged a new wish for {self._format_child_name(normalized_name, age)}: \"{sanitized_wish}\"."
            f" There are now {total_for_child} wishes for this person."
        )

        return {
            "status": "success",
            "message": message,
            "wish_id": wish_id,
            "total_for_child": total_for_child,
            "recent_wishes": recent_wishes,
        }

    async def _list_wishes(self, name: Optional[str], age: Optional[int]) -> Dict[str, Any]:
        normalized_name = self._normalize_name(name)
        if not normalized_name or age is None:
            return {
                "status": "error",
                "message": "Please provide both name and age to see recorded wishes.",
            }

        connection = await self._ensure_connection()
        if not connection:
            return {
                "status": "error",
                "message": "Santa's ledger is unavailable right now. Please try again later.",
            }

        child_hash = self._child_hash(normalized_name, age)
        table = self._table_name("wishlist_entries")
        rows = await self._select(
            f"SELECT wish, created_at FROM {table} WHERE child_hash = ? ORDER BY created_at DESC",
            [child_hash],
        )

        if not rows:
            return {
                "status": "success",
                "message": f"No wishes have been recorded yet for {self._format_child_name(normalized_name, age)}.",
                "wishes": [],
            }

        wishes = [
            {
                "wish": row[0],
                "created_at": row[1],
            }
            for row in rows
        ]

        lines = [
            f"{index + 1}. {entry['wish']} (added {self._humanize_timestamp(entry['created_at'])})"
            for index, entry in enumerate(wishes[:10])
        ]
        preview = "\n".join(lines)

        message = (
            f"{self._format_child_name(normalized_name, age)} has {len(wishes)} wishes saved."
            f"\n{preview}"
        )

        return {
            "status": "success",
            "message": message,
            "wishes": wishes,
            "total": len(wishes),
        }

    async def _get_trending_wishes(self) -> Dict[str, Any]:
        connection = await self._ensure_connection()
        if not connection:
            return {
                "status": "error",
                "message": "Santa's analytics are offline right now. Please try again later.",
            }

        table = self._table_name("wishlist_entries")
        since = (datetime.utcnow() - timedelta(days=DEFAULT_TREND_RANGE_DAYS)).isoformat()

        trending_rows = await self._select(
            (
                f"SELECT wish, COUNT(*) AS total, MAX(created_at) AS last_seen "
                f"FROM {table} WHERE created_at >= ? GROUP BY wish ORDER BY total DESC, last_seen DESC LIMIT 5"
            ),
            [since],
        )

        totals = await self._select(
            f"SELECT COUNT(*), COUNT(DISTINCT child_hash) FROM {table} WHERE created_at >= ?",
            [since],
        )
        total_wishes = int(totals[0][0]) if totals else 0
        unique_children = int(totals[0][1]) if totals else 0

        if not trending_rows:
            return {
                "status": "success",
                "message": "No trending wishes yet. Encourage families to send their wishes to Santa!",
                "trending": [],
                "total_wishes": total_wishes,
                "unique_children": unique_children,
                "since": since,
            }

        trending = [
            {
                "wish": row[0],
                "total": int(row[1]),
                "last_seen": row[2],
            }
            for row in trending_rows
        ]

        lines = [f"{idx + 1}. {entry['wish']} ({entry['total']} wishes)" for idx, entry in enumerate(trending)]
        message = "Trending wishes this season:\n" + "\n".join(lines)

        return {
            "status": "success",
            "message": message,
            "trending": trending,
            "total_wishes": total_wishes,
            "unique_children": unique_children,
            "since": since,
        }

    async def _ensure_connection(self):
        if self._connection and self._tables_ready:
            return self._connection

        async with self._db_lock:
            if self._connection and self._tables_ready:
                return self._connection

            entry_id = self.config.get("entry_id")
            if not entry_id:
                self._logger.error("entry_id missing from plugin configuration; cannot open wishlist database")
                return None

            try:
                connection = self.database_manager.get_connection(self.name, self.config)
            except DatabaseError as error:
                self._logger.error("Could not connect to wishlist database: %s", error)
                self.event_manager.plugin_error(self.name, str(error), "ensure_connection")
                return None

            # Ensure required tables once per plugin instance
            if not self._tables_ready:
                schema = {
                    "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
                    "child_hash": "TEXT NOT NULL",
                    "child_name": "TEXT NOT NULL",
                    "age": "INTEGER",
                    "wish": "TEXT NOT NULL",
                    "created_at": "TEXT NOT NULL",
                    "entry_id": "TEXT",
                    "locale": "TEXT",
                }
                await self.hass.async_add_executor_job(connection.create_table, "wishlist_entries", schema)

                index_hash = (
                    f"CREATE INDEX IF NOT EXISTS idx_{self.name}_child_hash ON "
                    f"{self._table_name('wishlist_entries')} (child_hash)"
                )
                index_wish = (
                    f"CREATE INDEX IF NOT EXISTS idx_{self.name}_wish ON "
                    f"{self._table_name('wishlist_entries')} (wish)"
                )
                await self.hass.async_add_executor_job(connection.execute_query, index_hash, [])
                await self.hass.async_add_executor_job(connection.execute_query, index_wish, [])
                self._tables_ready = True

            self._connection = connection
            return self._connection

    async def _select(self, query: str, params: Optional[List[Any]] = None) -> List[List[Any]]:
        connection = await self._ensure_connection()
        if not connection:
            return []
        result = await self.hass.async_add_executor_job(connection.execute_query, query, params or [])
        return result.get("data", []) if isinstance(result, dict) else []

    def _table_name(self, suffix: str) -> str:
        return f"{self.name}_{suffix}"

    def _normalize_name(self, name: Optional[str]) -> Optional[str]:
        if not name:
            return None
        cleaned = " ".join(part.capitalize() for part in name.split())
        return cleaned.strip()

    def _sanitize_wish(self, wish: Optional[str]) -> Optional[str]:
        if not wish:
            return None
        cleaned = " ".join(wish.strip().split())
        return cleaned[:280]

    def _child_hash(self, name: str, age: Optional[int]) -> str:
        base = f"{name.lower()}|{age if age is not None else ''}|{self.config.get('entry_id', '')}"
        return hashlib.sha256(base.encode("utf-8")).hexdigest()

    def _format_child_name(self, name: str, age: Optional[int]) -> str:
        if age is None:
            return name
        return f"{name} ({age} yrs)"

    def _get_locale(self) -> str:
        return getattr(self.hass.config, "language", "en") or "en"

    def _utc_now_iso(self) -> str:
        return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

    def _humanize_timestamp(self, value: Optional[str]) -> str:
        if not value:
            return "unknown time"
        try:
            if value.endswith("Z"):
                value = value[:-1]
            dt_obj = datetime.fromisoformat(value)
            return dt_obj.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return value

