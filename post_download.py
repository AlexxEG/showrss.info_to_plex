import argparse
import os.path
import sys
import subprocess
import logging
import traceback
import re
import configparser
import shutil
import sqlite3
import requests
import io

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate


__output = None
__simulate = False
__config = None


def main():
    # Copy all logging to __output that can be sent by email later.
    #
    # This allows the program to email only the log from the current instance,
    # and don't have to handle mutliple log files.
    global __output
    __output = io.StringIO()

    # Enable editing of global variable
    global __simulate

    # Load config.cfg
    global __config
    __config = configparser.ConfigParser()
    __config.read('config.cfg')

    # Log to 'post_download.log', stdout and __output
    logging.basicConfig(filename='post_download.log', level=logging.DEBUG)
    logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))
    logging.getLogger().addHandler(logging.StreamHandler(__output))

    logging.debug("Running post_download.py script")

    description = "Convert mkv to mp4 automatically."

    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('path', help="the path to file or directory containing file to convert")
    parser.add_argument('--simulate', action='store_true', help='simulate post_download')

    args, extra = parser.parse_known_args()

    __simulate = args.simulate

    # Log all files in given path if it's a directory
    if os.path.isdir(args.path):
        log_all_files(args.path)

    input_file = args.path

    if not input_file or input_file.isspace():
        print("Input file is null or empty")
        return

    # Find the .mkv file if the arg is a folder, and check if the file exists
    if os.path.isdir(args.path):
        input_file = find_mkv_file(args.path)

        if input_file is None:
            logging.error("Couldn't find .mkv file in directory '" + args.path + "'")
            email_notification_error()
            return
    elif not os.path.isfile(args.path):
        logging.error("File '" + input_file + "' doesn't exists.")
        email_notification_error()
        return

    logging.debug("Found input file: [{0}]".format(os.path.basename(input_file)))

    output = ""

    if input_file.endswith(".mp4"):
        output = input_file
        logging.debug("File is correct format")
    else:
        # Convert .mkv to .mp4 using FFmpeg
        logging.debug("Converting input file to mp4...")

        output = ffmpeg_convert(input_file)

        logging.debug("Done!")

    # Rename file using FileBot
    logging.debug("Running FileBot...")

    output = filebot_rename_file(output)

    # Move file to Plex library
    move_to_plex_library(output)

    # Refresh 'TV Shows' Plex library to detect new episode
    logging.debug("Refreshing 'TV Shows' Plex library...")

    refresh_plex_library()

    # Send email notification
    episode_name = os.path.basename(output)

    email_notification_new_episode(episode_name)


def add_to_history(command):
    conn = get_database()

    query = '''INSERT INTO history(command) VALUES (?);
               SELECT id FROM history ORDER BY id DESC LIMIT 1;'''

    c = conn.cursor()
    c.execute(query, (command))

    conn.commit()
    conn.close()

    return c.fetchone()


def email_notification_error():
    msg = MIMEMultipart('alternative')
    msg['From'] = __config['EmailNotifier']['Email']
    msg['To'] = __config['EmailNotifier']['EmailDest']
    msg['Date'] = formatdate(localtime=True)
    msg['Subject'] = "home-server: Unhandled exception occurred in showrss.info script"

    log_text = __output.getvalue()

    text = "home-server showrss.info script\n\nUnhandled exception occurred\n\nLog:\n"
    text = text + re.sub("^(.+)$", "> \g<1>", log_text.strip(), flags=re.MULTILINE)

    html = """\
    <div dir="ltr">
        <div>
            home-server showrss.info script<br><br>
            Unhandled exception occurred<br><br>
            Log:<br><br>
        </div>
        <blockquote class="gmail_quote" style="margin:0px 0px 0px 0.8ex;border-left-width:1px;border-left-color:rgb(204,204,204);border-left-style:solid;padding-left:1ex">
            {0}
        </blockquote>
    </div>
    """.format(log_text.strip().replace('\n', '<br>'))

    msg.attach(MIMEText(text, 'plain'))
    msg.attach(MIMEText(html, 'html'))

    send_email(msg)


def email_notification_new_episode(series_name):
    msg = MIMEMultipart('alternative')
    msg['From'] = __config['EmailNotifier']['Email']
    msg['To'] = __config['EmailNotifier']['EmailDest']
    msg['Date'] = formatdate(localtime=True)
    msg['Subject'] = "home-server: Downloaded new episode: {0}".format(episode_name)

    log_text = __output.getvalue()

    text = "home-server showrss.info script\n\nDownloaded new episode: {0}\n\nLog:\n".format(episode_name)
    text = text + re.sub("^(.+)$", "> \g<1>", log_text.strip(), flags=re.MULTILINE)

    html = """\
    <div dir="ltr">
        <div>
            home-server showrss.info script<br><br>
            Downloaded new episode: {0}<br><br>
            Log:<br><br>
        </div>
        <blockquote class="gmail_quote" style="margin:0px 0px 0px 0.8ex;border-left-width:1px;border-left-color:rgb(204,204,204);border-left-style:solid;padding-left:1ex">
            {1}
        </blockquote>
    </div>
    """.format(episode_name, log_text.strip().replace('\n', '<br>'))

    msg.attach(MIMEText(text, 'plain'))
    msg.attach(MIMEText(html, 'html'))

    send_email(msg)


def get_database():
    """
    Get the sqlite connection for history database.
    """
    return sqlite3.connect('history.db')


def initialize_sqlite():
    """
    Creates the sqlite database file.
    """
    conn = get_database()

    query = '''CREATE TABLE IF NOT EXISTS history (
                    id      INTEGER     PRIMARY KEY AUTOINCREMENT   NOT NULL,
                    date    DATETIME    NOT NULL    DEFAULT CURRENT_TIMESTAMP,
                    status  INTEGER     NOT NULL    DEFAULT 0,
                    command TEXT        NOT NULL)'''

    c = conn.cursor()
    c.execute(query)

    conn.commit()
    conn.close()


def send_email(msg):
    import smtplib

    username = __config['EmailNotifier']['Email']
    password = __config['EmailNotifier']['Password']

    server = smtplib.SMTP('smtp.gmail.com:587')
    server.ehlo()
    server.starttls()
    server.login(username, password)
    server.sendmail(__config['EmailNotifier']['Email'],
                    __config['EmailNotifier']['EmailDest'],
                    msg.as_string())
    server.quit()


def ffmpeg_convert(input_file):
    """
    Converts file to .mp4 using FFmpeg, returning the new filename afterwards.
    """
    # Replace extension with .mp4
    output = os.path.splitext(input_file)[0] + ".mp4"
    output = os.path.join(os.path.dirname(input_file), output)

    # Build the command
    cmd = 'ffmpeg -n -i "{0}" -vcodec copy -acodec aac -movflags faststart -strict -2 "{1}"'.format(input_file, output)

    logging.debug("cmd: " + cmd)

    # Enable report file for FFmpeg using environment variable
    my_env = os.environ.copy()
    my_env['FFREPORT'] = "file=ffreport.log:level=32"

    # Run command
    process = subprocess.Popen(cmd, env=my_env, shell=True)
    process.wait()

    return output


def filebot_rename_file(input_file):
    """
    Renames file using FileBot
    """
    cmd = "filebot -rename \"{0}\" --db TheTVDB --format \"{{n}} - {{s00e00}} - {{t}}\" -non-strict"
    cmd = cmd.format(input_file)

    process = subprocess.Popen(cmd,
                               shell=True,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE,
                               universal_newlines=True)

    outs, errs = process.communicate()

    logging.debug(outs)
    logging.debug(errs)

    # Regex for finding new filename
    pattern = re.compile('.*\[.*\].*\[(.*)\]')

    matchObj = pattern.search(outs)

    if matchObj:
        return os.path.join(os.path.dirname(input_file), matchObj.group(1))
    else:
        return None


def find_mkv_file(directory):
    """
    Return the given file unchanged if it's a .mkv file.

    If given file is a directory, search for .mkv files and return first found.
    """
    for item in os.listdir(directory):
        if os.path.isdir(item):
            continue

        if item.endswith('.mkv'):
            return os.path.join(directory, item)

    return None


def log_all_files(path):
    import subprocess
    output = subprocess.check_output(["tree", path], universal_newlines=True)
    logging.debug("\n")
    logging.debug(output)


def match_info(input_file):
    """
    Returns a match object containing the required information to sort series.
    (name, season)
    """
    filters = configparser.ConfigParser()
    filters.read('filters.cfg')

    for section in filters.sections():
        pattern = filters[section]['PlexPattern']

        matchObj = re.search(str(pattern), input_file)

        if matchObj:
            return matchObj

    return None


def move_to_plex_library(input_file):
    """
    Moves given file to Plex library. Detects series name and season automatically.
    """
    plex_dir = __config['Plex']['PlexLibrary']

    serie_info = match_info(input_file)

    serie_name = serie_info.group(1)
    season = serie_info.group(2)

    new_location = os.path.join(plex_dir,
                                serie_name,
                                "Season " + season.lstrip("0"),
                                os.path.basename(input_file))
    new_location_folder = os.path.join(plex_dir,
                                       serie_name,
                                       "Season " + season.lstrip("0"))

    if not os.path.exists(new_location_folder):
        os.makedirs(new_location_folder)

    logging.debug("Moving [" + os.path.abspath(input_file) + "] to [" + new_location + "]...")

    shutil.move(os.path.abspath(input_file), new_location)

    logging.debug("Done!")


def refresh_plex_library():
    """
    Refreshes the 'TV Shows' library in Plex.
    """
    plex_token = __config['Plex']['PlexToken']
    r = requests.get("http://127.0.0.1:32400/library/sections/1/refresh?X-Plex-Token=" + plex_token)

    if r.status_code == 200:
        logging.debug("Refreshed library successfully.")
    else:
        logging.debug("Couldn't refresh library. HTTP status code: " + str(r.status_code))


def update_status(id, status):
    conn = get_database()

    query = '''UPDATE history SET status=? WHERE id=?'''

    c = conn.cursor()
    c.execute(query, (status, id))

    conn.commit()
    conn.close()


def handle_unhandled_exception(exc_type, exc_value, exc_traceback):
    logging.error("".join(traceback.format_exception(exc_type, exc_value, exc_traceback)))
    email_notification_error()
    sys.exit(1)


if __name__ == "__main__":
    sys.excepthook = handle_unhandled_exception
    main()
