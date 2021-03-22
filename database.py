import pathlib
import requests
import json
import os
import source
import re
import uuid

if not os.path.exists("hondana_data"):
    os.makedirs("hondana_data")
    os.makedirs(pathlib.Path("hondana_data/mangas_data"))

mangas_data_path = pathlib.Path("hondana_data/mangas_data")
mangas = {}

class Chapter:
    def __init__(self, data):
        for key, value in data.items():
            setattr(self, key, value)

class Manga:
    def __init__(self, data):
        for key, value in data.items():
            if key == "downloaded_chapters":
                chapters = []
                for chapter in value:
                    chapters.append(Chapter(chapter))
                self.downloaded_chapters = chapters
            else:
                setattr(self, key, value)

    def get_chapters_list(self, source_id):
        if source_id == 0:
            chapters = self.downloaded_chapters
        else:
            chapters = source.sources[source_id].get_chapters_list(self, False)

        return [o.__dict__ for o in chapters]

    def download_chapter(self, source_id, chapter_id):
        if source_id == 0:
            return

        source.sources[source_id].enqueue_chapter(self, chapter_id)
        return "Added "+self.title+" chapter "+str(chapter_id)+" to the download queue"

    def set_chapter_read(self, chapter_id):
        for chapter in self.downloaded_chapters:
            if chapter.id == chapter_id:
                chapter.read = True
                break
        update_json_file()

    def delete(self):
        del mangas[self.id]
        update_json_file()

def get_manga(i):
    return mangas.get(i, None)

def to_dict(obj):
    d = {}
    for key, value in obj.__dict__.items():
        if isinstance(value, list):
            d[key] = []
            for e in value:
                try:
                    d[key].append(to_dict(e))
                except AttributeError:
                    d[key].append(e)
        else:
            try:
                d[key] = to_dict(value)
            except AttributeError:
                d[key] = value
    return d

def get_mangas_info():
    t = []
    for i, manga in mangas.items():
        t.append(to_dict(manga))
    return t

def open_database():
    try:
        mangas_json_file = open("hondana_data/mangas.json", encoding="utf-8")
        mangas_data = json.load(mangas_json_file)
        mangas_json_file.close()

        for item in mangas_data:
            manga = Manga(item)
            mangas[manga.id] = manga

    except OSError as e:
        print("Error opening file: "+e.filename)
    except json.JSONDecodeError as e:
        print("Error decoding JSON file: "+e.msg)

def add_manga(title):
    if title in [manga.title for manga in mangas.values()]:
        return "Manga already in library"

    manga_dir = re.sub("[^A-Za-z0-9]+", "-", title).lower()
    manga_dir = re.sub("^\-", "", manga_dir)
    manga_dir = re.sub("\-$", "", manga_dir)

    sources = list(range(len(source.sources)))

    manga = Manga({
        "id": str(uuid.uuid4()),
        "title": title,
        "sources": sources,
        "dir": manga_dir,
        "cover": "cover.jpg",
        "downloaded_chapters": []})

    if not os.path.exists(mangas_data_path / manga_dir):
        os.makedirs(mangas_data_path / manga_dir)

    mangas[manga.id] = manga
    update_manga_info(manga.id)

    return "Manga added to library"

def search_anilist(title):
    query = '''{
        Page(page: 0, perPage: 10){
            media(search: "'''+title+'''", type: MANGA){
                title{
                    romaji
                }
            }
        }
    }'''

    req = requests.post("https://graphql.anilist.co/", data={"query": query})
    req_data = req.json()["data"]["Page"]["media"]
    req_data = [x["title"]["romaji"] for x in req_data]
    return req_data

def update_manga_info(i):
    manga = get_manga(i)

    if manga is None:
        return None

    query = '''{
        Media(search: "'''+manga.title+'''", type: MANGA){
            title{
                english,
                native,
                romaji
            },
            coverImage{
                extraLarge
            },
            status,
            genres,
            description,
            staff(perPage: 1){
                nodes{
                    name{
                        full
                    }
                }
            }
        }
    }'''

    req = requests.post("https://graphql.anilist.co/", data={"query": query})
    req_data = req.json()["data"]["Media"]

    en_title = "" if req_data["title"]["english"] == None else req_data["title"]["english"]
    native_title = "" if req_data["title"]["native"] == None else req_data["title"]["native"]
    if en_title == req_data["title"]["romaji"]:
        manga.subtitle = native_title
    else:
        manga.subtitle = native_title+" - "+en_title

    manga.status = req_data["status"].lower().capitalize()
    manga.description = req_data["description"].split("<br>")[0]
    manga.genres = req_data["genres"]
    if len(req_data["staff"]["nodes"]) > 0:
        manga.author = req_data["staff"]["nodes"][0]["name"]["full"]
    else:
        manga.author = ""

    req = requests.get(req_data["coverImage"]["extraLarge"])

    path = mangas_data_path / manga.dir

    cover_file_path = path / manga.cover
    try:
        cover_file = open(cover_file_path, "wb+")
        cover_file.write(req.content)
        cover_file.close()
    except OSError as e:
        print("Error opening file: "+e.filename)
    except IOError as e:
        print("Error saving cover image file: "+e.msg)

    update_json_file()
    return to_dict(manga)

def update_json_file():
    path = pathlib.Path("hondana_data/mangas.json")
    try:
        f = open(path, "w+")
        json.dump(get_mangas_info(), f)
        f.close()
    except OSError as e:
        print("Error opening file: "+e.filename)
    except IOError as e:
        print("Error saving json file: "+e.msg)