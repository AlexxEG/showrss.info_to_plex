import sqlite3


def get_database():
    """
    Get the sqlite connection for history database.
    """
    return sqlite3.connect('history.db')
