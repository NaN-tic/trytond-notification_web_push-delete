from sql import Table
from sql.functions import Substring
from sql.operators import Concat

from trytond import backend
from trytond.transaction import Transaction


def rename_scheduled_message_model(model, old_name):
    """Preserve records and Tryton metadata when renaming the initial models."""
    old_table = old_name.replace('.', '_')
    if not backend.TableHandler.table_exist(old_table):
        return
    if backend.TableHandler.table_exist(model._table):
        raise RuntimeError(
            f'Both {old_table} and {model._table} exist; '
            'resolve the duplicate tables before upgrading.')
    backend.TableHandler.table_rename(old_table, model._table)
    cursor = Transaction().connection.cursor()
    constraints = []
    if backend.name == 'postgresql':
        from psycopg2.sql import SQL, Identifier

        # Tryton's named model/field references use immediate foreign keys.
        # Defer these checks while renaming both sides, preserving their IDs.
        cursor.execute("""
            SELECT namespace.nspname, relation.relname, constraint_.conname,
                constraint_.condeferrable, constraint_.condeferred
            FROM pg_constraint AS constraint_
                JOIN pg_class AS relation ON relation.oid = constraint_.conrelid
                JOIN pg_namespace AS namespace
                    ON namespace.oid = relation.relnamespace
            WHERE constraint_.contype = 'f'
                AND constraint_.confrelid IN (
                    'ir_model'::regclass, 'ir_model_field'::regclass)
                AND EXISTS (
                    SELECT 1 FROM pg_attribute AS attribute
                    WHERE attribute.attrelid = constraint_.confrelid
                        AND attribute.attnum = ANY(constraint_.confkey)
                        AND attribute.attname IN ('name', 'model'))
            ORDER BY namespace.nspname, relation.relname, constraint_.conname
            """)
        constraints = cursor.fetchall()
        for schema, table_name, name, _, _ in constraints:
            cursor.execute(SQL('ALTER TABLE {} ALTER CONSTRAINT {} '
                'DEFERRABLE INITIALLY DEFERRED').format(
                    Identifier(schema, table_name), Identifier(name)))
            cursor.execute(SQL('SET CONSTRAINTS {} DEFERRED').format(
                Identifier(schema, name)))
    for table_name, column_name in [
            ('ir_model', 'name'),
            ('ir_model_field', 'model'),
            ('ir_model_field', 'relation'),
            ('ir_model_access', 'model'),
            ('ir_model_field_access', 'model'),
            ('ir_model_button', 'model'),
            ('ir_model_data', 'model'),
            ('ir_rule_group', 'model'),
            ('res_notification', 'model'),
            ('ir_ui_view', 'model'),
            ('ir_ui_view_tree_width', 'model'),
            ('ir_ui_view_tree_optional', 'model'),
            ('ir_ui_view_tree_state', 'model'),
            ('ir_ui_view_search', 'model'),
            ('ir_action_report', 'model'),
            ('ir_action_wizard', 'model'),
            ('ir_action_act_window', 'res_model'),
            ('ir_action_act_window', 'context_model')]:
        table = Table(table_name)
        column = getattr(table, column_name)
        cursor.execute(*table.update([column], [model.__name__],
            where=column == old_name))

    for table_name, column_name in [
            ('ir_attachment', 'resource'),
            ('ir_note', 'resource'),
            ('ir_model_log', 'resource'),
            ('ir_action_keyword', 'model'),
            ('ir_translation', 'name')]:
        table = Table(table_name)
        column = getattr(table, column_name)
        cursor.execute(*table.update([column], [
            Concat(model.__name__, Substring(column, len(old_name) + 1))],
            where=column.like(old_name + ',%')))

    # Flush all queued checks before altering any table with pending triggers.
    for schema, _, name, _, _ in constraints:
        cursor.execute(SQL('SET CONSTRAINTS {} IMMEDIATE').format(
            Identifier(schema, name)))
    for schema, table_name, name, deferrable, deferred in constraints:
        cursor.execute(SQL('ALTER TABLE {} ALTER CONSTRAINT {} {}').format(
            Identifier(schema, table_name), Identifier(name),
            SQL('DEFERRABLE INITIALLY DEFERRED' if deferred else
                'DEFERRABLE INITIALLY IMMEDIATE' if deferrable else
                'NOT DEFERRABLE')))
        if deferred:
            cursor.execute(SQL('SET CONSTRAINTS {} DEFERRED').format(
                Identifier(schema, name)))
