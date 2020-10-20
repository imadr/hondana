import requests
import time
import json
import os
import threading
import queue
import pathlib
import database
import uuid

class ChapterDownloader(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.queue = queue.Queue()
        self.paused = threading.Event()
        self.paused.set()

    def pause(self):
        self.paused.clear()

    def resume(self):
        self.paused.set()

    def run(self):
        while True:
            self.paused.wait()
            self.work()

    def clear(self):
        self.pause()
        while not self.queue.empty():
            self.queue.get()
        self.resume()

    def add(self, thing):
        self.queue.put(thing)

    def work(self):
        source, manga, chapter_id = self.queue.get()
        with lock:
            progress_id = str(uuid.uuid4())
            chapters_progress[progress_id] = None
            source.chapter_downloader(manga, chapter_id, progress_id)

class ImageDownloader(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.paused_bool = False
        self.paused = threading.Event()
        self.paused.set()
        self.queue = queue.Queue()

    def pause(self):
        self.paused_bool = True
        self.paused.clear()

    def resume(self):
        self.paused_bool = False
        self.paused.set()

    def clear(self):
        self.pause()
        while not self.queue.empty():
            self.queue.get()
        self.resume()

    def run(self):
        while True:
            self.paused.wait()
            self.work()

    def add(self, thing):
        self.queue.put(thing)

    def work(self):
        image_url, image_file, manga, chapter, progress_id = self.queue.get()

        if image_file.is_file():
            print(str(image_file)+" already exist, skipping")
        else:
            print("downloading "+image_url)
            try:
                req = requests.get(image_url)
                with open(image_file, "wb+") as f:
                    f.write(req.content)
            except requests.exceptions.ChunkedEncodingError:
                print("download failed... retrying")
                self.queue.put([image_url, image_file, manga, chapter, progress_id])
                return

        with lock:
            try:
                chapters_progress[progress_id][0] -= 1
            except (KeyError, TypeError):
                return

            if chapters_progress[progress_id][0] == 0:
                del chapters_progress[progress_id]
                print("done downloading chapter "+str(image_file))
                existing_chapter = next((x for x in manga.downloaded_chapters if x.id == chapter.id), None)
                if existing_chapter is None:
                    manga.downloaded_chapters.append(chapter)
                else:
                    for key, value in chapter.__dict__.items():
                        setattr(existing_chapter, key, value)

                database.update_json_file()

lock = threading.Lock()

chapter_downloader = ChapterDownloader()
chapter_downloader.start()

image_downloader = ImageDownloader()
image_downloader.start()

chapters_progress = {}

def switch_pause(paused):
    if paused:
        image_downloader.pause()
    else:
        image_downloader.resume()

def clear_download():
    chapter_downloader.clear()
    image_downloader.clear()
    global chapters_progress
    chapters_progress.clear()

def is_paused():
    return image_downloader.paused_bool

class LocalSource():
    def __init__(self):
        self.name = "Local"

import pathlib
import importlib

plugins_path = pathlib.Path("plugins")
plugins_files = os.listdir(plugins_path)
sources = {}
sources[0] = LocalSource()

for file in plugins_files:
    if file.endswith(".py"):
        file = file.replace(".py", "")
        module = importlib.import_module("plugins."+file)
        module.chapter_downloader = chapter_downloader
        module.image_downloader = image_downloader
        module.chapters_progress = chapters_progress
        sources[module.i] = module.Source()
sources = [sources[key] for key in sorted(sources.keys())]