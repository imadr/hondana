import os
import json
import re
import requests
from bs4 import BeautifulSoup
import database

class Source():
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