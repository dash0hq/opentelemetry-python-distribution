"""Exercise opentelemetry-instrumentation-sqlite3 and exit.

sqlite3 is in the standard library, so this case needs no database server and
no extra requirement. The instrumentation wraps the DB-API connection, which
is the same wrapper opentelemetry-instrumentation-dbapi gives every other
driver, so the attributes asserted here are the shape the whole family emits.
"""

from sqlite3 import Connection, connect


def main() -> None:
    connection: Connection = connect(":memory:")
    try:
        cursor = connection.cursor()
        cursor.execute("CREATE TABLE item (id INTEGER PRIMARY KEY, name TEXT)")
        cursor.execute("INSERT INTO item (id, name) VALUES (?, ?)", (7, "widget"))
        connection.commit()
        cursor.execute("SELECT name FROM item WHERE id = ?", (7,))
        assert cursor.fetchone() == ("widget",)
    finally:
        connection.close()


main()
