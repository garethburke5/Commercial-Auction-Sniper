"""Small database boundary for the existing account service.

SQLite remains useful locally or on a persistent disk. PostgreSQL keeps private
state outside a disposable web instance. No customer table is exposed through
Supabase's public Data API; the API still verifies identity and ownership.
"""
from collections.abc import Mapping
from urllib.parse import urlsplit


class Record(Mapping):
    """Keep the existing named and positional sqlite.Row access contract."""
    def __init__(self, names, values):
        self._values = tuple(values)
        self._data = dict(zip(names, values))

    def __getitem__(self, key):
        return self._values[key] if isinstance(key, int) else self._data[key]

    def __iter__(self):
        return iter(self._data)

    def __len__(self):
        return len(self._data)


def record_factory(cursor):
    names = [column.name for column in cursor.description] if cursor.description else []
    return lambda values: Record(names, values)


def placeholders(statement):
    """Translate our parameter markers, preserving SQL literals verbatim."""
    parts, quoted, i = [], False, 0
    while i < len(statement):
        char = statement[i]
        if char == "'":
            if quoted and i + 1 < len(statement) and statement[i + 1] == "'":
                parts.append("''")
                i += 2
                continue
            quoted = not quoted
        parts.append('%s' if char == '?' and not quoted else char)
        i += 1
    return ''.join(parts)


class PostgresConnection:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, statement, parameters=()):
        return self.connection.execute(placeholders(statement), parameters)

    def begin_write(self):
        # All existing payment/processing/version claims share this transaction
        # lock. Unlike a session lock it is released on commit, rollback or loss
        # of the connection, including through Supavisor transaction pooling.
        self.connection.execute('SELECT pg_advisory_xact_lock(714023, 1)')


def begin_write(connection):
    if isinstance(connection, PostgresConnection):
        connection.begin_write()
    else:
        connection.execute('BEGIN IMMEDIATE')


def connect_postgres(dsn):
    import psycopg
    parsed = urlsplit(dsn)
    if parsed.scheme not in ('postgres', 'postgresql') or not parsed.hostname:
        raise ValueError('ACCOUNT_DATABASE_URL must be a PostgreSQL connection URL')
    # Local integration tests use a disposable loopback database. Remote
    # connections must be encrypted, even if the URL asks for sslmode=disable.
    options = {} if parsed.hostname in ('localhost', '127.0.0.1', '::1') else {'sslmode': 'require'}
    return psycopg.connect(dsn, connect_timeout=10, prepare_threshold=None,
                           row_factory=record_factory, **options)
