import requests
from bs4 import BeautifulSoup
import time
import json
import os
import threading, queue
import pathlib
import database
import re

chapters_queue = queue.Queue()
chapters_progress = []
images_queue = queue.Queue()
thread_lock = threading.Lock()

def chapter_downloader():
    while True:
        chapter = chapters_queue.get()
        with thread_lock:
            chapters_progress.append(None)
            chapter[0].chapter_downloader(chapter[1], chapter[2], len(chapters_progress)-1)

def image_downloader():
    while True:
        image_url, image_file, manga, chapter, progress_id = images_queue.get()

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
                images_queue.put([image_url, image_file, manga, chapter, progress_id])
                return

        with thread_lock:
            chapters_progress[progress_id] -= 1
            if chapters_progress[progress_id] == 0:
                print("done downloading chapter "+str(image_file))
                existing_chapter = next((x for x in manga.downloaded_chapters if x.id == chapter.id), None)
                if existing_chapter is None:
                    manga.downloaded_chapters.append(chapter)
                else:
                    for key, value in chapter.__dict__.items():
                        setattr(existing_chapter, key, value)

                database.update_json_file()

threading.Thread(target=chapter_downloader, daemon=True).start()
for i in range(0, 5):
    threading.Thread(target=image_downloader, daemon=True).start()

class LocalSource():
    def __init__(self):
        self.name = "Local"

class MangalifeSource():
    def __init__(self):
        self.domain = "https://manga4life.com"
        self.name = "Mangalife"

    def get_chapters_list(self, manga, get_urls):
        url_title = re.sub("[^A-Za-z0-9 ]+", "", manga.title)
        url_title = "-".join(url_title.split(" "))

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
        image_url_prefix += cur_chapter["Chapter"][1:len(cur_chapter["Chapter"])-1]+"-"

        chapter_n_pages = int(cur_chapter["Page"])
        chapters_progress[progress_id] = chapter_n_pages
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
            images_queue.put([image_url_prefix+page+".png", image_file, manga, chapter, progress_id])

        #{{vm.ChapterImage(vm.CurChapter.Chapter)}}-{{vm.PageImage(Page)}}.png"

    def enqueue_chapter(self, manga, chapter_id):
        chapters_queue.put([self, manga, chapter_id]);

sources = []
sources.append(LocalSource())
sources.append(MangalifeSource())