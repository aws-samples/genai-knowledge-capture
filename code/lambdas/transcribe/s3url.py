from urllib.parse import ParseResult, urlparse


class S3Url(object):
    """
    A class to parse and represent S3 URL

    Attributes:
    -----------
        url (str): The S3 URL to parse
        bucket (str): The S3 bucket name
        key (str): The S3 key name
    """

    def __init__(self, url: str) -> None:
        self._parsed: ParseResult = urlparse(url, allow_fragments=False)

    @property
    def bucket(self) -> str:
        return self._parsed.netloc

    @property
    def key(self):
        if self._parsed.query:
            return self._parsed.path.lstrip("/") + "?" + self._parsed.query
        else:
            return self._parsed.path.lstrip("/")

    @property
    def url(self) -> str:
        return self._parsed.geturl()
