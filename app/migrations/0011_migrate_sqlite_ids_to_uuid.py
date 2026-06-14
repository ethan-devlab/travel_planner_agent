import logging
import uuid

from django.conf import settings
from django.db import migrations


logger = logging.getLogger(__name__)


def _table_exists(cursor, table_name):
    return cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = %s",
        [table_name],
    ).fetchone() is not None


def _table_columns(cursor, table_name):
    return [row[1] for row in cursor.execute(f'PRAGMA table_info("{table_name}")')]


def _is_uuid_table(cursor, table_name):
    info = cursor.execute(f'PRAGMA table_info("{table_name}")').fetchall()
    if not info:
        return False
    return str(info[0][2]).lower() in {"char(32)", "varchar(32)", "text"}


def _rows(cursor, table_name):
    columns = _table_columns(cursor, table_name)
    if not columns:
        return []
    raw_rows = cursor.execute(f'SELECT * FROM "{table_name}"').fetchall()
    return [dict(zip(columns, row)) for row in raw_rows]


def _uuid4_map(rows):
    return {row["id"]: uuid.uuid4().hex for row in rows}


def _user_uuid_map(rows):
    namespace = uuid.UUID(settings.USER_ID_UUID5_NAMESPACE)
    return {
        row["id"]: uuid.uuid5(namespace, f'user:{row["username"]}').hex
        for row in rows
    }


def _object_id(uuid_hex):
    return str(uuid.UUID(hex=uuid_hex))


def _mapped_object_id(object_id, id_map):
    try:
        return _object_id(id_map[int(object_id)])
    except (TypeError, ValueError, KeyError):
        return object_id


def _create_tables(cursor):
    cursor.execute("""
        CREATE TABLE "app_user__uuid" (
            "password" varchar(128) NOT NULL,
            "last_login" datetime NULL,
            "is_superuser" bool NOT NULL,
            "username" varchar(150) NOT NULL UNIQUE,
            "last_name" varchar(150) NOT NULL,
            "email" varchar(254) NOT NULL,
            "is_staff" bool NOT NULL,
            "is_active" bool NOT NULL,
            "date_joined" datetime NOT NULL,
            "first_name" varchar(150) NOT NULL,
            "id" char(32) NOT NULL PRIMARY KEY
        )
    """)
    cursor.execute("""
        CREATE TABLE "app_user_groups__uuid" (
            "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
            "user_id" char(32) NOT NULL REFERENCES "app_user" ("id") DEFERRABLE INITIALLY DEFERRED,
            "group_id" integer NOT NULL REFERENCES "auth_group" ("id") DEFERRABLE INITIALLY DEFERRED
        )
    """)
    cursor.execute("""
        CREATE TABLE "app_user_user_permissions__uuid" (
            "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
            "user_id" char(32) NOT NULL REFERENCES "app_user" ("id") DEFERRABLE INITIALLY DEFERRED,
            "permission_id" integer NOT NULL REFERENCES "auth_permission" ("id") DEFERRABLE INITIALLY DEFERRED
        )
    """)
    cursor.execute("""
        CREATE TABLE "app_tag__uuid" (
            "id" char(32) NOT NULL PRIMARY KEY,
            "name" varchar(30) NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE "app_itinerary__uuid" (
            "id" char(32) NOT NULL PRIMARY KEY,
            "title" varchar(100) NOT NULL,
            "start_date" date NOT NULL,
            "end_date" date NOT NULL,
            "location" varchar(100) NOT NULL,
            "budget" decimal NOT NULL,
            "is_public" bool NOT NULL,
            "updated_at" datetime NOT NULL,
            "description" text NOT NULL,
            "owner_id" char(32) NOT NULL REFERENCES "app_user" ("id") DEFERRABLE INITIALLY DEFERRED,
            "status" varchar(10) NOT NULL,
            "budget_currency" varchar(3) NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE "app_location__uuid" (
            "id" char(32) NOT NULL PRIMARY KEY,
            "name" varchar(100) NOT NULL,
            "visit_date" datetime NULL,
            "travel_method" varchar(10) NOT NULL,
            "latitude" real NOT NULL,
            "longitude" real NOT NULL,
            "note" text NOT NULL,
            "itinerary_id" char(32) NOT NULL REFERENCES "app_itinerary" ("id") DEFERRABLE INITIALLY DEFERRED,
            "route_order" integer unsigned NOT NULL CHECK ("route_order" >= 0)
        )
    """)
    cursor.execute("""
        CREATE TABLE "app_expense__uuid" (
            "id" char(32) NOT NULL PRIMARY KEY,
            "expense_type" varchar(20) NOT NULL,
            "amount" decimal NOT NULL,
            "location_id" char(32) NOT NULL REFERENCES "app_location" ("id") DEFERRABLE INITIALLY DEFERRED
        )
    """)
    cursor.execute("""
        CREATE TABLE "app_event__uuid" (
            "id" char(32) NOT NULL PRIMARY KEY,
            "event_name" varchar(100) NOT NULL,
            "date" date NOT NULL,
            "color" varchar(20) NOT NULL,
            "owner_id" char(32) NOT NULL REFERENCES "app_user" ("id") DEFERRABLE INITIALLY DEFERRED
        )
    """)
    cursor.execute("""
        CREATE TABLE "app_itinerary_tags__uuid" (
            "id" char(32) NOT NULL PRIMARY KEY,
            "itinerary_id" char(32) NOT NULL REFERENCES "app_itinerary" ("id") DEFERRABLE INITIALLY DEFERRED,
            "tag_id" char(32) NOT NULL REFERENCES "app_tag" ("id") DEFERRABLE INITIALLY DEFERRED
        )
    """)
    cursor.execute("""
        CREATE TABLE "app_itinerary_collaborators__uuid" (
            "id" char(32) NOT NULL PRIMARY KEY,
            "itinerary_id" char(32) NOT NULL REFERENCES "app_itinerary" ("id") DEFERRABLE INITIALLY DEFERRED,
            "user_id" char(32) NOT NULL REFERENCES "app_user" ("id") DEFERRABLE INITIALLY DEFERRED
        )
    """)
    cursor.execute("""
        CREATE TABLE "django_admin_log__uuid" (
            "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
            "object_id" text NULL,
            "object_repr" varchar(200) NOT NULL,
            "action_flag" smallint unsigned NOT NULL CHECK ("action_flag" >= 0),
            "change_message" text NOT NULL,
            "content_type_id" integer NULL REFERENCES "django_content_type" ("id") DEFERRABLE INITIALLY DEFERRED,
            "user_id" char(32) NOT NULL REFERENCES "app_user" ("id") DEFERRABLE INITIALLY DEFERRED,
            "action_time" datetime NOT NULL
        )
    """)


def _insert_rows(cursor, maps, rows_by_table):
    for row in rows_by_table["auth_user"]:
        cursor.execute(
            """
            INSERT INTO "app_user__uuid"
            ("password", "last_login", "is_superuser", "username", "last_name", "email", "is_staff", "is_active", "date_joined", "first_name", "id")
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                row["password"], row["last_login"], row["is_superuser"], row["username"],
                row["last_name"], row["email"], row["is_staff"], row["is_active"],
                row["date_joined"], row["first_name"], maps["users"][row["id"]],
            ],
        )

    for row in rows_by_table.get("auth_user_groups", []):
        cursor.execute(
            'INSERT INTO "app_user_groups__uuid" ("id", "user_id", "group_id") VALUES (%s, %s, %s)',
            [row["id"], maps["users"][row["user_id"]], row["group_id"]],
        )

    for row in rows_by_table.get("auth_user_user_permissions", []):
        cursor.execute(
            'INSERT INTO "app_user_user_permissions__uuid" ("id", "user_id", "permission_id") VALUES (%s, %s, %s)',
            [row["id"], maps["users"][row["user_id"]], row["permission_id"]],
        )

    for row in rows_by_table["app_tag"]:
        cursor.execute(
            'INSERT INTO "app_tag__uuid" ("id", "name") VALUES (%s, %s)',
            [maps["tags"][row["id"]], row["name"]],
        )

    for row in rows_by_table["app_itinerary"]:
        cursor.execute(
            """
            INSERT INTO "app_itinerary__uuid"
            ("id", "title", "start_date", "end_date", "location", "budget", "is_public", "updated_at", "description", "owner_id", "status", "budget_currency")
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                maps["itineraries"][row["id"]], row["title"], row["start_date"], row["end_date"],
                row["location"] or "", row["budget"], row["is_public"], row["updated_at"],
                row["description"], maps["users"][row["owner_id"]], row["status"], row["budget_currency"],
            ],
        )

    for row in rows_by_table["app_location"]:
        cursor.execute(
            """
            INSERT INTO "app_location__uuid"
            ("id", "name", "visit_date", "travel_method", "latitude", "longitude", "note", "itinerary_id", "route_order")
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                maps["locations"][row["id"]], row["name"], row["visit_date"], row["travel_method"],
                row["latitude"], row["longitude"], row["note"], maps["itineraries"][row["itinerary_id"]],
                row["route_order"],
            ],
        )

    for row in rows_by_table["app_expense"]:
        cursor.execute(
            'INSERT INTO "app_expense__uuid" ("id", "expense_type", "amount", "location_id") VALUES (%s, %s, %s, %s)',
            [maps["expenses"][row["id"]], row["expense_type"], row["amount"], maps["locations"][row["location_id"]]],
        )

    for row in rows_by_table["app_event"]:
        cursor.execute(
            'INSERT INTO "app_event__uuid" ("id", "event_name", "date", "color", "owner_id") VALUES (%s, %s, %s, %s, %s)',
            [maps["events"][row["id"]], row["event_name"], row["date"], row["color"], maps["users"][row["owner_id"]]],
        )

    for row in rows_by_table["app_itinerary_tags"]:
        cursor.execute(
            'INSERT INTO "app_itinerary_tags__uuid" ("id", "itinerary_id", "tag_id") VALUES (%s, %s, %s)',
            [maps["itinerary_tags"][row["id"]], maps["itineraries"][row["itinerary_id"]], maps["tags"][row["tag_id"]]],
        )

    for row in rows_by_table["app_itinerary_collaborators"]:
        cursor.execute(
            'INSERT INTO "app_itinerary_collaborators__uuid" ("id", "itinerary_id", "user_id") VALUES (%s, %s, %s)',
            [
                maps["itinerary_collaborators"][row["id"]],
                maps["itineraries"][row["itinerary_id"]],
                maps["users"][row["user_id"]],
            ],
        )

    content_types = {
        (row["app_label"], row["model"]): row["id"]
        for row in rows_by_table["django_content_type"]
    }
    object_maps = {
        content_types.get(("auth", "user")): maps["users"],
        content_types.get(("app", "itinerary")): maps["itineraries"],
        content_types.get(("app", "tag")): maps["tags"],
        content_types.get(("app", "location")): maps["locations"],
        content_types.get(("app", "expense")): maps["expenses"],
        content_types.get(("app", "event")): maps["events"],
    }
    for row in rows_by_table["django_admin_log"]:
        object_id = row["object_id"]
        id_map = object_maps.get(row["content_type_id"])
        if id_map:
            object_id = _mapped_object_id(object_id, id_map)
        cursor.execute(
            """
            INSERT INTO "django_admin_log__uuid"
            ("id", "object_id", "object_repr", "action_flag", "change_message", "content_type_id", "user_id", "action_time")
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                row["id"], object_id, row["object_repr"], row["action_flag"],
                row["change_message"], row["content_type_id"], maps["users"][row["user_id"]],
                row["action_time"],
            ],
        )


def _swap_tables(cursor):
    swaps = [
        ("auth_user", "app_user__uuid", "app_user"),
        ("auth_user_groups", "app_user_groups__uuid", "app_user_groups"),
        ("auth_user_user_permissions", "app_user_user_permissions__uuid", "app_user_user_permissions"),
        ("app_tag", "app_tag__uuid", "app_tag"),
        ("app_itinerary", "app_itinerary__uuid", "app_itinerary"),
        ("app_location", "app_location__uuid", "app_location"),
        ("app_expense", "app_expense__uuid", "app_expense"),
        ("app_event", "app_event__uuid", "app_event"),
        ("app_itinerary_tags", "app_itinerary_tags__uuid", "app_itinerary_tags"),
        ("app_itinerary_collaborators", "app_itinerary_collaborators__uuid", "app_itinerary_collaborators"),
        ("django_admin_log", "django_admin_log__uuid", "django_admin_log"),
    ]
    cursor.execute("PRAGMA legacy_alter_table=ON")
    try:
        for old_name, new_name, final_name in swaps:
            if _table_exists(cursor, old_name):
                cursor.execute(f'ALTER TABLE "{old_name}" RENAME TO "{old_name}__integer_backup"')
            cursor.execute(f'ALTER TABLE "{new_name}" RENAME TO "{final_name}"')
        for old_name, _, _ in swaps:
            backup_name = f"{old_name}__integer_backup"
            if _table_exists(cursor, backup_name):
                cursor.execute(f'DROP TABLE "{backup_name}"')
    finally:
        cursor.execute("PRAGMA legacy_alter_table=OFF")


def _create_indexes(cursor):
    index_sql = [
        'CREATE INDEX IF NOT EXISTS "app_itinerary_owner_id_8c4922ee" ON "app_itinerary" ("owner_id")',
        'CREATE INDEX IF NOT EXISTS "app_location_itinerary_id_e363612b" ON "app_location" ("itinerary_id")',
        'CREATE INDEX IF NOT EXISTS "app_expense_location_id_823c108e" ON "app_expense" ("location_id")',
        'CREATE INDEX IF NOT EXISTS "app_event_owner_id_f8dce76a" ON "app_event" ("owner_id")',
        'CREATE UNIQUE INDEX IF NOT EXISTS "app_itinerary_tags_itinerary_id_tag_id_ac52d1ee_uniq" ON "app_itinerary_tags" ("itinerary_id", "tag_id")',
        'CREATE INDEX IF NOT EXISTS "app_itinerary_tags_itinerary_id_b42c20f2" ON "app_itinerary_tags" ("itinerary_id")',
        'CREATE INDEX IF NOT EXISTS "app_itinerary_tags_tag_id_1538adb7" ON "app_itinerary_tags" ("tag_id")',
        'CREATE UNIQUE INDEX IF NOT EXISTS "app_itinerary_collaborators_itinerary_id_user_id_95c9267e_uniq" ON "app_itinerary_collaborators" ("itinerary_id", "user_id")',
        'CREATE INDEX IF NOT EXISTS "app_itinerary_collaborators_itinerary_id_d69902fb" ON "app_itinerary_collaborators" ("itinerary_id")',
        'CREATE INDEX IF NOT EXISTS "app_itinerary_collaborators_user_id_47fdc0c6" ON "app_itinerary_collaborators" ("user_id")',
        'CREATE UNIQUE INDEX IF NOT EXISTS "app_user_groups_user_id_group_id_4d09af3e_uniq" ON "app_user_groups" ("user_id", "group_id")',
        'CREATE INDEX IF NOT EXISTS "app_user_groups_user_id_e6f878f6" ON "app_user_groups" ("user_id")',
        'CREATE INDEX IF NOT EXISTS "app_user_groups_group_id_0c5f9a6d" ON "app_user_groups" ("group_id")',
        'CREATE UNIQUE INDEX IF NOT EXISTS "app_user_user_permissions_user_id_permission_id_48bdd28b_uniq" ON "app_user_user_permissions" ("user_id", "permission_id")',
        'CREATE INDEX IF NOT EXISTS "app_user_user_permissions_user_id_24780b52" ON "app_user_user_permissions" ("user_id")',
        'CREATE INDEX IF NOT EXISTS "app_user_user_permissions_permission_id_4ef8e133" ON "app_user_user_permissions" ("permission_id")',
        'CREATE INDEX IF NOT EXISTS "django_admin_log_content_type_id_c4bce8eb" ON "django_admin_log" ("content_type_id")',
        'CREATE INDEX IF NOT EXISTS "django_admin_log_user_id_c564eba6" ON "django_admin_log" ("user_id")',
    ]
    for sql in index_sql:
        cursor.execute(sql)


def _copy_uuid_table(cursor, source, target, columns):
    column_sql = ", ".join(f'"{column}"' for column in columns)
    cursor.execute(f'INSERT INTO "{target}" ({column_sql}) SELECT {column_sql} FROM "{source}"')


def _repair_converted_uuid_foreign_keys(cursor):
    for table_name in [
        "app_location__uuid",
        "app_expense__uuid",
        "app_itinerary_tags__uuid",
        "app_itinerary_collaborators__uuid",
    ]:
        if _table_exists(cursor, table_name):
            cursor.execute(f'DROP TABLE "{table_name}"')

    cursor.execute("""
        CREATE TABLE "app_location__uuid" (
            "id" char(32) NOT NULL PRIMARY KEY,
            "name" varchar(100) NOT NULL,
            "visit_date" datetime NULL,
            "travel_method" varchar(10) NOT NULL,
            "latitude" real NOT NULL,
            "longitude" real NOT NULL,
            "note" text NOT NULL,
            "itinerary_id" char(32) NOT NULL REFERENCES "app_itinerary" ("id") DEFERRABLE INITIALLY DEFERRED,
            "route_order" integer unsigned NOT NULL CHECK ("route_order" >= 0)
        )
    """)
    cursor.execute("""
        CREATE TABLE "app_expense__uuid" (
            "id" char(32) NOT NULL PRIMARY KEY,
            "expense_type" varchar(20) NOT NULL,
            "amount" decimal NOT NULL,
            "location_id" char(32) NOT NULL REFERENCES "app_location" ("id") DEFERRABLE INITIALLY DEFERRED
        )
    """)
    cursor.execute("""
        CREATE TABLE "app_itinerary_tags__uuid" (
            "id" char(32) NOT NULL PRIMARY KEY,
            "itinerary_id" char(32) NOT NULL REFERENCES "app_itinerary" ("id") DEFERRABLE INITIALLY DEFERRED,
            "tag_id" char(32) NOT NULL REFERENCES "app_tag" ("id") DEFERRABLE INITIALLY DEFERRED
        )
    """)
    cursor.execute("""
        CREATE TABLE "app_itinerary_collaborators__uuid" (
            "id" char(32) NOT NULL PRIMARY KEY,
            "itinerary_id" char(32) NOT NULL REFERENCES "app_itinerary" ("id") DEFERRABLE INITIALLY DEFERRED,
            "user_id" char(32) NOT NULL REFERENCES "app_user" ("id") DEFERRABLE INITIALLY DEFERRED
        )
    """)

    _copy_uuid_table(
        cursor,
        "app_location",
        "app_location__uuid",
        ["id", "name", "visit_date", "travel_method", "latitude", "longitude", "note", "itinerary_id", "route_order"],
    )
    _copy_uuid_table(
        cursor,
        "app_expense",
        "app_expense__uuid",
        ["id", "expense_type", "amount", "location_id"],
    )
    _copy_uuid_table(
        cursor,
        "app_itinerary_tags",
        "app_itinerary_tags__uuid",
        ["id", "itinerary_id", "tag_id"],
    )
    _copy_uuid_table(
        cursor,
        "app_itinerary_collaborators",
        "app_itinerary_collaborators__uuid",
        ["id", "itinerary_id", "user_id"],
    )

    swaps = [
        ("app_location", "app_location__uuid", "app_location"),
        ("app_expense", "app_expense__uuid", "app_expense"),
        ("app_itinerary_tags", "app_itinerary_tags__uuid", "app_itinerary_tags"),
        ("app_itinerary_collaborators", "app_itinerary_collaborators__uuid", "app_itinerary_collaborators"),
    ]
    cursor.execute("PRAGMA legacy_alter_table=ON")
    try:
        for old_name, new_name, final_name in swaps:
            cursor.execute(f'ALTER TABLE "{old_name}" RENAME TO "{old_name}__uuid_fk_backup"')
            cursor.execute(f'ALTER TABLE "{new_name}" RENAME TO "{final_name}"')
        for old_name, _, _ in swaps:
            cursor.execute(f'DROP TABLE "{old_name}__uuid_fk_backup"')
    finally:
        cursor.execute("PRAGMA legacy_alter_table=OFF")

    _create_indexes(cursor)
    _repair_legacy_search_foreign_keys(cursor)


def _repair_legacy_search_foreign_keys(cursor):
    if not _table_exists(cursor, "search_itinerary"):
        return

    for table_name in [
        "search_itinerary__uuid",
        "search_itinerary_collaborators__uuid",
        "search_itineraryversion__uuid",
    ]:
        if _table_exists(cursor, table_name):
            cursor.execute(f'DROP TABLE "{table_name}"')

    cursor.execute("""
        CREATE TABLE "search_itinerary__uuid" (
            "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
            "title" varchar(100) NOT NULL,
            "start_date" date NOT NULL,
            "end_date" date NOT NULL,
            "budget" decimal NOT NULL,
            "is_public" bool NOT NULL,
            "updated_at" datetime NOT NULL,
            "owner_id" integer NOT NULL,
            "description" text NOT NULL,
            "location" varchar(100) NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE "search_itinerary_collaborators__uuid" (
            "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
            "itinerary_id" bigint NOT NULL REFERENCES "search_itinerary" ("id") DEFERRABLE INITIALLY DEFERRED,
            "user_id" integer NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE "search_itineraryversion__uuid" (
            "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
            "version_json" text NOT NULL,
            "edited_at" datetime NOT NULL,
            "edited_by_id" integer NULL,
            "itinerary_id" bigint NOT NULL REFERENCES "search_itinerary" ("id") DEFERRABLE INITIALLY DEFERRED
        )
    """)

    _copy_uuid_table(
        cursor,
        "search_itinerary",
        "search_itinerary__uuid",
        ["id", "title", "start_date", "end_date", "budget", "is_public", "updated_at", "owner_id", "description", "location"],
    )
    _copy_uuid_table(
        cursor,
        "search_itinerary_collaborators",
        "search_itinerary_collaborators__uuid",
        ["id", "itinerary_id", "user_id"],
    )
    _copy_uuid_table(
        cursor,
        "search_itineraryversion",
        "search_itineraryversion__uuid",
        ["id", "version_json", "edited_at", "edited_by_id", "itinerary_id"],
    )

    swaps = [
        ("search_itinerary", "search_itinerary__uuid", "search_itinerary"),
        ("search_itinerary_collaborators", "search_itinerary_collaborators__uuid", "search_itinerary_collaborators"),
        ("search_itineraryversion", "search_itineraryversion__uuid", "search_itineraryversion"),
    ]
    cursor.execute("PRAGMA legacy_alter_table=ON")
    try:
        for old_name, new_name, final_name in swaps:
            cursor.execute(f'ALTER TABLE "{old_name}" RENAME TO "{old_name}__auth_fk_backup"')
            cursor.execute(f'ALTER TABLE "{new_name}" RENAME TO "{final_name}"')
        for old_name, _, _ in swaps:
            cursor.execute(f'DROP TABLE "{old_name}__auth_fk_backup"')
    finally:
        cursor.execute("PRAGMA legacy_alter_table=OFF")

    legacy_indexes = [
        'CREATE INDEX IF NOT EXISTS "search_itinerary_owner_id_82e6be02" ON "search_itinerary" ("owner_id")',
        'CREATE UNIQUE INDEX IF NOT EXISTS "search_itinerary_collaborators_itinerary_id_user_id_617d1c6a_uniq" ON "search_itinerary_collaborators" ("itinerary_id", "user_id")',
        'CREATE INDEX IF NOT EXISTS "search_itinerary_collaborators_itinerary_id_fd6acf43" ON "search_itinerary_collaborators" ("itinerary_id")',
        'CREATE INDEX IF NOT EXISTS "search_itinerary_collaborators_user_id_9f65b44c" ON "search_itinerary_collaborators" ("user_id")',
        'CREATE INDEX IF NOT EXISTS "search_itineraryversion_itinerary_id_7c096cbe" ON "search_itineraryversion" ("itinerary_id")',
        'CREATE INDEX IF NOT EXISTS "search_itineraryversion_edited_by_id_de7dbc1c" ON "search_itineraryversion" ("edited_by_id")',
    ]
    for sql in legacy_indexes:
        cursor.execute(sql)


def _migrate_sqlite_ids(apps, schema_editor):
    if schema_editor.connection.vendor != "sqlite":
        logger.info("UUID ID migration skipped because the database vendor is not SQLite.")
        return

    cursor = schema_editor.connection.cursor()
    if _table_exists(cursor, "app_user") and not _table_exists(cursor, "auth_user") and _is_uuid_table(cursor, "app_itinerary"):
        violations = cursor.execute("PRAGMA foreign_key_check").fetchall()
        if not violations:
            logger.info("UUID ID migration skipped because scoped tables already use UUID primary keys.")
            return
        cursor.execute("PRAGMA foreign_keys=OFF")
        _repair_converted_uuid_foreign_keys(cursor)
        cursor.execute("PRAGMA foreign_keys=ON")
        repaired_violations = cursor.execute("PRAGMA foreign_key_check").fetchall()
        if repaired_violations:
            raise RuntimeError(f"UUID ID migration repair left foreign-key violations: {repaired_violations}")
        logger.info("Repaired UUID table foreign-key metadata after a partial SQLite ID migration.")
        return

    if not _table_exists(cursor, "auth_user"):
        logger.info("UUID ID migration skipped because the legacy auth_user table is absent.")
        return

    scoped_tables = [
        "auth_user",
        "auth_user_groups",
        "auth_user_user_permissions",
        "app_tag",
        "app_itinerary",
        "app_location",
        "app_expense",
        "app_event",
        "app_itinerary_tags",
        "app_itinerary_collaborators",
        "django_admin_log",
        "django_content_type",
    ]
    rows_by_table = {table: _rows(cursor, table) for table in scoped_tables if _table_exists(cursor, table)}
    maps = {
        "users": _user_uuid_map(rows_by_table["auth_user"]),
        "tags": _uuid4_map(rows_by_table["app_tag"]),
        "itineraries": _uuid4_map(rows_by_table["app_itinerary"]),
        "locations": _uuid4_map(rows_by_table["app_location"]),
        "expenses": _uuid4_map(rows_by_table["app_expense"]),
        "events": _uuid4_map(rows_by_table["app_event"]),
        "itinerary_tags": _uuid4_map(rows_by_table["app_itinerary_tags"]),
        "itinerary_collaborators": _uuid4_map(rows_by_table["app_itinerary_collaborators"]),
    }

    cursor.execute("PRAGMA foreign_keys=OFF")
    _create_tables(cursor)
    _insert_rows(cursor, maps, rows_by_table)
    _swap_tables(cursor)
    _repair_legacy_search_foreign_keys(cursor)
    cursor.execute(
        """
        UPDATE "django_content_type"
        SET "app_label" = 'app', "model" = 'user'
        WHERE "app_label" = 'auth' AND "model" = 'user'
        """
    )
    cursor.execute('DELETE FROM "django_session"')
    _create_indexes(cursor)
    cursor.execute("PRAGMA foreign_keys=ON")
    violations = cursor.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        raise RuntimeError(f"UUID ID migration left foreign-key violations: {violations}")

    logger.info(
        "Migrated SQLite IDs to UUIDs: users=%s itineraries=%s locations=%s expenses=%s events=%s tags=%s.",
        len(maps["users"]),
        len(maps["itineraries"]),
        len(maps["locations"]),
        len(maps["expenses"]),
        len(maps["events"]),
        len(maps["tags"]),
    )


class Migration(migrations.Migration):

    atomic = False

    dependencies = [
        ('app', '0010_location_travel_method_hsr'),
    ]

    operations = [
        migrations.RunPython(_migrate_sqlite_ids, migrations.RunPython.noop),
    ]
