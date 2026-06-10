from django.db import migrations


def remove_drive_url_columns(apps, schema_editor):
    """Drop the orphaned drive_url column from accounts_order and
    accounts_historicalorder.

    These columns were added by a since-deleted migration. The Order model
    no longer has this field, but the DB columns remain. We drop them
    directly via SQL because Django's migration state doesn't know they exist.
    """
    connection = schema_editor.connection
    vendor = connection.vendor  # "sqlite" or "mysql"

    for table in ("accounts_order", "accounts_historicalorder"):
        # Check if column exists
        if vendor == "sqlite":
            with connection.cursor() as cursor:
                cursor.execute(f"PRAGMA table_info({table})")
                columns = {row[1] for row in cursor.fetchall()}
        else:
            # MySQL / MariaDB
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s",
                    [table],
                )
                columns = {row[0] for row in cursor.fetchall()}

        if "drive_url" in columns:
            with connection.cursor() as cursor:
                cursor.execute(f"ALTER TABLE {table} DROP COLUMN drive_url")


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0005_alter_historicalorder_status_alter_order_status_and_more"),
    ]

    operations = [
        migrations.RunPython(
            remove_drive_url_columns,
            migrations.RunPython.noop,
        ),
    ]
