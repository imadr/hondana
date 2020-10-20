import os
import json
import re
import requests
from bs4 import BeautifulSoup
import database

i = 2

class Source():
    def __init__(self):
        self.domain = "https://manganelo.com"
        self.name = "Manganelo"

    def get_chapters_list(self, manga, get_urls):
        url_title = re.sub("[^A-Za-z0-9 ]+", "", manga.title)
        url_title = "-".join([x.capitalize() for x in url_title.split(" ")])

        url = self.domain+"/search/story/"+url_title
        req = requests.get(url)
        soup = BeautifulSoup(req.text, "html.parser")
        items = soup.findAll("div", {"class": "search-story-item"})
        url = items[0].find("a")["href"]

        chapters = []
        urls = []
        req = requests.get(url)
        soup = BeautifulSoup(req.text, "html.parser")

        items = soup.find("ul", {"class": "row-content-chapter"}).findAll("li")

        for i, item in enumerate(reversed(items)):
            a = item.find("a")
            title = a.text
            url = a["href"]

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

        pages = soup.find("div", {"class": "container-chapter-reader"}).findAll("img")

        chapter_n_pages = len(pages)
        chapters_progress[progress_id] = [chapter_n_pages, chapter_n_pages, manga.title, chapter_title]
        chapter = database.Chapter({
            "id": chapter_id,
            "title": chapter_title,
            "n_pages": chapter_n_pages,
            "image_format": "png",
            "read": False
        })

        for i, page in enumerate(pages):
            image_file = chapter_path / (str(i-1)+".png")
            image_downloader.add([page["src"]+".png", image_file, manga, chapter, progress_id])

    def enqueue_chapter(self, manga, chapter_id):
        chapter_downloader.add([self, manga, chapter_id]);