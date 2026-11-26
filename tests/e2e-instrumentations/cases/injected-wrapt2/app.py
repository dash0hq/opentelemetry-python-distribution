"""Exercise the injected tree from an application that has wrapt 2.x installed.

The application runs sqlite3 statements inside an asyncclick command, so one
process covers an instrumentation installed as a dependency and the one carried
as source, both against the wrapt the application brought.
"""

from sqlite3 import Connection, connect

from asyncclick import command, echo, option
from wrapt import __version__ as wrapt_version


@command()
@option("--item-id", type=int, required=True)
async def checkout(item_id: int) -> None:
    connection: Connection = connect(":memory:")
    try:
        cursor = connection.cursor()
        cursor.execute("CREATE TABLE item (id INTEGER PRIMARY KEY, name TEXT)")
        cursor.execute("INSERT INTO item (id, name) VALUES (?, ?)", (item_id, "widget"))
        connection.commit()
        cursor.execute("SELECT name FROM item WHERE id = ?", (item_id,))
        assert cursor.fetchone() == ("widget",)
    finally:
        connection.close()
    echo(f"checked out item {item_id}")


if not wrapt_version.startswith("2."):
    raise SystemExit(
        f"the case is named after wrapt 2.x and the application has "
        f"wrapt {wrapt_version}, so it no longer covers what it claims to"
    )

checkout(args=["--item-id", "7"], prog_name="checkout", standalone_mode=False)
