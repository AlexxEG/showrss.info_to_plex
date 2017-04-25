import os.path
import configparser
import feedparser
import sqlite3
import re
import requests
import urllib
import time


__auth_cookies = None
__config = None


class Entry:
    def __init__(self, guid, name):
        self.guid = guid
        self.name = name
        self.date = time.strftime("%Y/%m/%d")


def main():
    if not os.path.isfile('history.db'):
        initialize_sqlite()

    # Load config.cfg
    global __config
    __config = configparser.ConfigParser()
    __config.read('config.cfg')

    # List of patterns from file
    patterns = get_patterns()

    # Get login cookie
    global __auth_cookies
    __auth_cookies = qbt_login()

    # Store processed entries and batch add them to sqlite later
    new_entries = []

    while True:
        print("Checking feed...")

        # Get feed object from RSS url in config file
        feed = feedparser.parse(get_feed_url())

        # Go through each entry in feed
        for entry in feed['items']:
            for pattern in patterns:
                # Process entry if it matches one of the patterns
                if re.search(pattern, entry['title']) and is_new_entry(entry['guid']):
                    new_entry = Entry(entry['guid'], entry['title'])

                    # Always store GUID
                    new_entries.append(new_entry)

                    download_torrent(entry['link'])

                    print("New torrent: " + new_entry.name)
                    break

        if len(new_entries) > 0:
            # Add new entries to sqlite database
            add_to_history_many(new_entries)

            print()
            print("New entries: " + str(len(new_entries)))

            # Clear list before looping
            new_entries.clear()
        else:
            print("No new entries")

        # Sleep for 30min
        time.sleep(30 * 60)

    print("Exiting...")


def add_to_history_many(entries):
    conn = get_database()

    c = conn.cursor()

    for entry in entries:
        c.execute("INSERT INTO feed_history (guid, name) VALUES (?, ?)", (entry.guid, entry.name))

    conn.commit()
    conn.close()


def download_torrent(magnet_link):
    headers = {'Content-Type': 'application/x-www-form-urlencoded',
               'Content-Length': '0'}

    r = requests.post("http://127.0.0.1:8080/command/download",
                      data="urls=" + urllib.parse.quote_plus(magnet_link),
                      headers=headers,
                      cookies=__auth_cookies)

    if r.status_code == 200:
        print("Added torrent successfully.")
    else:
        print("Couldn't add torrent. HTTP status code: " + str(r.status_code))
        return


def initialize_sqlite():
    """
    Creates the sqlite database file.
    """
    conn = get_database()

    query = '''CREATE TABLE feed_history (guid TEXT PRIMARY KEY NOT NULL, name TEXT NOT NULL, date DATETIME DEFAULT CURRENT_DATE)'''

    c = conn.cursor()
    c.execute(query)

    conn.commit()
    conn.close()


def is_new_entry(guid):
    conn = get_database()

    c = conn.cursor()
    c.execute("SELECT guid FROM feed_history WHERE guid=?", (guid,))

    return c.fetchone() is None


def get_database():
    """
    Get the sqlite connection for history database.
    """
    return sqlite3.connect('history.db')


def get_feed_url():
    """
    Get the RSS feed to watch from config.cfg file.
    """
    return __config['General']['Feed']


def get_patterns():
    """
    Get the patterns from config file to filter series.
    """
    filters = []
    filters_config = configparser.ConfigParser()
    filters_config.read('filters.cfg')

    for section in filters_config.sections():
        new_filter = filters_config[section]['Pattern']
        filters.append(new_filter)

    return filters


def qbt_login():
    headers = {'Content-Type': 'application/x-www-form-urlencoded',
               'Content-Length': '0'}

    username = __config['qBitorrent']['Username']
    password = __config['qBitorrent']['Password']
    r = requests.post("http://127.0.0.1:8080/login",
                      data="username=" + username + "&password=" + password,
                      headers=headers)

    if r.status_code == 200:
        print("Logged in successfully.")
    else:
        print("Couldn't login. HTTP status code: " + str(r.status_code))
        return

    return r.cookies


if __name__ == "__main__":
    main()
