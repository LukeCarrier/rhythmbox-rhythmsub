"""
Subsonic API client

I couldn't find any respectable bindings for this API, so I decided to write
them myself.

Copyright (c) 2013 Luke Carrier
Released under the terms of the GPLv3
"""

import datetime
import json
import urllib.parse
import urllib.request

"""
Subsonic client class.

Instances of this class represent Subsonic server instances.
"""
class Server:
    API_URL_FORMAT = "%s/rest/%s.view?%s"

    __address       = None
    __username      = None
    __password      = None
    __client_name   = None
    __fetcher       = None
    __async_fetcher = None

    """
    Get an instance with the designated address, username and password.
    """
    def __init__(self, address, username, password, client_name, fetcher=None,
                 async_fetcher=None):
        self.__address     = address
        self.__username    = username
        self.__password    = password
        self.__client_name = client_name

        if fetcher is None:
            fetcher = UrllibRequestFetcher
        self.__fetcher = fetcher

        self.__async_fetcher = async_fetcher

    """
    Perform a request to the API.

    Guess the URL within the API based on our format string, the specified
    address and the name of the method called; make a request to that URL and
    return a resp object representing the decoded JSON response string.
    """
    def __get(self, method, params={}):
        return self.__fetcher.get(self.__url(method, params))

    """
    Perform a request to the API asynchronously.

    Behaviour is identical to __get(), but we instead use the __async_fetcher to
    retreive the URL and call the specified complete_cb with the result upon its
    retreival.
    """
    def __get_async(self, method, complete_cb, params={}):
        return self.__async_fetcher.get(self.__url(method, params),
                                        complete_cb)

    """
    Guess the URL of an API method from its name.

    urllib requires that we also handle parameters here, so we'll also merge
    method-specific parameters with the credentials required for all methods
    (to facilitate authentication, client identification and API versioning).
    """
    def __url(self, method, params={}):
        params["c"] = self.__client_name
        params["f"] = "json"
        params["v"] = "1.10.1"
        params["u"] = self.__username
        params["p"] = self.__password

        params = urllib.parse.urlencode(params)
        return self.API_URL_FORMAT %(self.__address, method, params)

    """
    Get the server's address.
    """
    def get_address(self):
        return self.__address

    """
    Get indexed structure of all artists.

    http://www.subsonic.org/pages/api.jsp#getIndexes
    """
    def get_indexes(self, music_folder_id=None, if_modified_since=None):
        params = self.get_indexes_params(music_folder_id, if_modified_since)

        return GetIndexesResponse(self.__get("getIndexes", params))

    """
    Get indexed structure of all artists asynchronously.
    """
    def get_indexes_async(self, complete_cb, music_folder_id=None, if_modified_since=None):
        def real_complete_cb(resp):
            complete_cb(GetIndexesResponse(resp))

        params = self.get_indexes_params(music_folder_id, if_modified_since)
        self.__get_async("getIndexes", real_complete_cb, params)

    """
    Normalise parameters for the getIndexes method.
    """
    def get_indexes_params(self, music_folder_id, if_modified_since):
        params = {}

        if music_folder_id is not None:
            params["musicFolderId"] = music_folder_id

        if if_modified_since is not None:
            params["ifModifiedSince"] = if_modified_since

        return params

    """
    Query the Subsonic server's licensing status.

    Note that this method's responses may be unreliable/inconsistent with
    community-maintained forks of Subsonic.

    http://www.subsonic.org/pages/api.jsp#getLicense
    """
    def get_license(self):
        return GetLicenseResponse(self.__get("getLicense"))

    """
    Get genres.

    http://www.subsonic.org/pages/api.jsp#getGenres
    """
    def get_genres(self):
        return GetGenresResponse(self.__get("getGenres"))

    """
    Get a listing of all files in a directory.

    http://www.subsonic.org/pages/api.jsp#getMusicDirectory
    """
    def get_music_directory(self, id):
        params = self.get_music_directory(id)
        return GetMusicDirectoryResponse(self.__get("getMusicDirectory", params))

    """
    Get a listing of all files in a directory asynchronously.
    """
    def get_music_directory_async(self, complete_cb, id):
        def real_complete_cb(resp):
            complete_cb(GetMusicDirectoryResponse(resp))

        params = self.get_music_directory_params(id)
        self.__get_async("getMusicDirectory", real_complete_cb, params)

    """
    Normalise getMusicDirectory parameters.
    """
    def get_music_directory_params(self, id):
        return {
            "id": id,
        }

    """
    Get configured music folders.

    http://www.subsonic.org/pages/api.jsp#getMusicFolders
    """
    def get_music_folders(self):
        return GetMusicFoldersResponse(self.__get("getMusicFolders"))

    """
    Verify connectivity with the server.

    Perform a ping to get an empty response. Ideal for checking authentication
    credentials.

    http://www.subsonic.org/pages/api.jsp#ping
    """
    def ping(self):
        return PingResponse(self.__get("ping"))


"""
urllib.request fetcher class.

Make HTTP requests via urllib.request.
"""
class UrllibRequestFetcher:
    def get(url):
        request  = urllib.request.Request(url)
        response = urllib.request.urlopen(request)
        data = json.loads(response.read().decode("utf-8"))
        response.close()

        return data


"""
Subsonic response class.

All response classes should inherit from this class.
"""
class Response:
    status  = None
    version = None

    def __init__(self, resp):
        resp = resp["subsonic-response"]

        self.status  = resp["status"] == "ok"
        self.version = resp["version"]


"""
Subsonic getLicense response.

Even parses the dates into Python datetime objects for you!
"""
class GetLicenseResponse(Response):
    date  = None
    email = None
    key   = None
    valid = None

    def __init__(self, resp):
        super(GetLicenseResponse, self).__init__(resp)
        resp = resp["subsonic-response"]["license"]

        self.date  = datetime.datetime.strptime(resp["date"], "%Y-%m-%dT%H:%M:%S")
        self.email = resp["email"]
        self.key   = resp["key"]
        self.valid = resp["valid"]


"""
Subsonic getIndexes response.

Note that unlike Subsonic's response format, we remove the strange index
headings and dive straight in with the artist list for consistency.
"""
class GetIndexesResponse(Response):
    ignored_articles = None
    index            = None

    def __init__(self, resp):
        super(GetIndexesResponse, self).__init__(resp)
        resp = resp["subsonic-response"]["indexes"]

        self.ignored_articles = resp["ignoredArticles"].split(" ")
        self.index = [artist for index in resp["index"]
                             for artist in index["artist"]]


"""
Subsonic getMusicDirectory response.
"""
class GetMusicDirectoryResponse(Response):
    children = None
    id       = None
    name     = None

    def __init__(self, resp):
        super(GetMusicDirectoryResponse, self).__init__(resp)
        resp = resp["subsonic-response"]["directory"]

        self.id   = resp["id"]
        self.name = resp["name"]

        try:
            if not resp["child"]:
                self.child = []
            elif isinstance(resp["child"], dict):
                self.children = [resp["child"],]
            else:
                self.children = resp["child"]
        except KeyError:
            self.children = []


"""
Subsonic getMusicFolders response.
"""
class GetMusicFoldersResponse(Response):
    music_folders = None

    def __init__(self, resp):
        super(GetMusicFoldersResponse, self).__init__(resp)
        self.music_folders = resp["subsonic-response"]["musicFolders"]["musicFolder"]


"""
Subsonic ping response.

Nothing to document, but used for consistency.
"""
class PingResponse(Response):
    pass
