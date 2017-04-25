import argparse
import configparser
import os
import subprocess
import time
from watchdog.observers import Observer
from watchdog.events import FileModifiedEvent
from watchdog.events import FileSystemEventHandler
from watchdog.events import LoggingEventHandler


processing = []
simulate = False


class MyEventHandler(FileSystemEventHandler):
    def on_any_event(self, event):
        global processing

        if event.src_path not in processing or not extension_match(event.src_path):
            return

        if isinstance(event, FileDeletedEvent):
            processing.remove(event.src_path)

        if isinstance(event, FileModifiedEvent):
            processing.remove(event.src_path)
            # Doesn't really matter if dest_path is in a watched folder or not
            processing.append(event.dest_path)

    def on_modified(self, event):
        global processing

        if (event.src_path in processing):
            return

        processing.append(event.src_path)

        if not extension_match(event.src_path):
            return

        if isinstance(event, FileModifiedEvent):
            print(event)
            print(event.src_path)

            statinfo = os.stat(event.src_path)
            previous = statinfo.st_mtime

            print("Waiting for transfer...", end="", flush=True)

            time.sleep(5)

            while True:
                statinfo = os.stat(event.src_path)

                if previous == statinfo.st_mtime:
                    print(" Done")
                    break

                previous = statinfo.st_mtime
                print(".", end="", flush=True)
                time.sleep(5)

            if not simulate:
                subprocess.Popen(
                    ['./run.sh', event.src_path],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE)


def extension_match(file):
    config = configparser.ConfigParser()
    config.read('config.cfg')

    extensions = config['FolderWatcher']['Extensions'].split(',')

    filename, extension = os.path.splitext(file)

    return extension in extensions


def main():
    description = "Watches folder(s) for files to run post_download.py script on."

    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('-s', '--simulate', help="don't do any permanent changes", action="store_true")

    args, extra = parser.parse_known_args()

    global simulate
    simulate = args.simulate

    config = configparser.ConfigParser()
    config.read('config.cfg')

    value = config['FolderWatcher']['FoldersToWatch']
    folders = value.split(',')

    event_handler = MyEventHandler()
    observers = []

    for folder in folders:
        if not os.path.isdir(folder.strip()):
            print('could not find dir, skipped "' + folder.strip() + '"')
            continue

        observer = Observer()
        observer.schedule(event_handler, folder.strip(), recursive=False)
        observer.start()

        observers.append(observer)

        print("watching " + folder.strip())

    try:
        while True:
            time.sleep(5)
    except KeyboardInterrupt:
        print('stopping observers...')

        for observer in observers:
            observer.stop()

    for observer in observers:
        observer.join()


if __name__ == "__main__":
    main()
