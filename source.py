import requests
from bs4 import BeautifulSoup
import time
import json
import os
import threading
import queue
import pathlib
import database
import re
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
            except KeyError:
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
    chapters_progress = {}

def is_paused():
    return image_downloader.paused_bool

class LocalSource():
    def __init__(self):
        self.name = "Local"

class MangalifeSource():
    def __init__(self):
        self.domain = "https://manga4life.com"
        self.name = "Mangalife"

    def get_chapters_list(self, manga, get_urls):
        url_title = re.sub("[^A-Za-z0-9 ]+", "", manga.title)
        url_title = "-".join([x.capitalize() for x in url_title.split(" ")])

        url = self.domain+"/rss/"+url_title+".xml"

        chapters = []
        urls = []
        req = requests.get(url)
        soup = BeautifulSoup(req.text, "lxml")

        items = soup.findAll("item")

        for i, item in enumerate(reversed(items)):
            text = str(item.encode_contents())

            m = re.search("<title>(.*)</title><link/>(.*)<pubdate>", text)
            title = m.group(1).replace(manga.title+" ", "")
            url = m.group(2)

            downloaded = any(x.id == i for x in manga.downloaded_chapters)
            chapter = database.Chapter({"id": i, "title": title, "downloaded": downloaded})
            chapters.append(chapter)

            urls.append({"url": url, "title": title})

        if get_urls:
            return urls
        else:
            return chapters

    def chapter_downloader(self, manga, chapter_id, progress_id):
        chapter_path = database.mangas_data_path / manga.dir / str(chapter_id)
        if not os.path.exists(chapter_path):
            os.makedirs(chapter_path)

        chapter = self.get_chapters_list(manga, True)[chapter_id]
        chapter_url = chapter["url"]
        chapter_title = chapter["title"]

        req = requests.get(chapter_url)
        soup = BeautifulSoup(req.text, "html.parser")

        cur_chapter = json.loads(re.search("vm\.CurChapter = (.*);", req.text).group(1))

        cur_pathname = re.search("vm.CurPathName = \"(.*)\"", req.text).group(1)
        index_name = re.search("vm.IndexName = \"(.*)\"", req.text).group(1)
        image_url_prefix = "https://"+cur_pathname+"/manga/"+index_name+"/"
        image_url_prefix += "" if cur_chapter["Directory"] == "" else cur_chapter["Directory"]+"/"
        image_url_prefix += cur_chapter["Chapter"][1:len(cur_chapter["Chapter"])-1]
        if(cur_chapter["Chapter"][-1] != "0"):
            image_url_prefix += "."+cur_chapter["Chapter"][-1]
        image_url_prefix += "-"

        chapter_n_pages = int(cur_chapter["Page"])
        chapters_progress[progress_id] = [chapter_n_pages, chapter_n_pages, manga.title, chapter_title]
        chapter = database.Chapter({
            "id": chapter_id,
            "title": chapter_title,
            "n_pages": chapter_n_pages,
            "image_format": "png",
            "read": False
        })

        for i in range(1, chapter_n_pages+1):
            page = str(i).rjust(3, "0")
            image_file = chapter_path / (str(i-1)+".png")
            image_downloader.add([image_url_prefix+page+".png", image_file, manga, chapter, progress_id])

    def enqueue_chapter(self, manga, chapter_id):
        chapter_downloader.add([self, manga, chapter_id]);

# class Manganelo():
#     def __init__(self):
#         self.domain = "https://manganelo.com"
#         self.name = "Manganelo"

#     def get_chapters_list(self, manga, get_urls):
#         pass

#     def enqueue_chapter(self, manga, chapter_id):
#         chapters_queue.put([self, manga, chapter_id])

sources = []
sources.append(LocalSource())
sources.append(MangalifeSource())