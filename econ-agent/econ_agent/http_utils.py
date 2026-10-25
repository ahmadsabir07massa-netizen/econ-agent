import logging
import re

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger("econ_agent")
UA = "Mozilla/5.0 (compatible; econ-agent/1.0; +https://github.com)"
_session = None

_REDACT = [
    (re.compile(r"bot\d+:[A-Za-z0-9_\-]+"), "bot***"),
    (re.compile(r"(api_key=)[A-Za-z0-9]+"), r"\1***"),
]


def redact(text):
    text = str(text)
    for pat, rep in _REDACT:
        text = pat.sub(rep, text)
    return text


def session():
    global _session
    if _session is None:
        s = requests.Session()
        retry = Retry(total=3, backoff_factor=1.5, status_forcelist=(429, 500, 502, 503, 504),
                      allowed_methods=frozenset(["GET"]), respect_retry_after_header=True)
        s.mount("https://", HTTPAdapter(max_retries=retry))
        s.mount("http://", HTTPAdapter(max_retries=retry))
        s.headers["User-Agent"] = UA
        _session = s
    return _session


def get(url, params=None, timeout=20):
    """GET مع إعادة محاولة تلقائية، وإخفاء المفاتيح من رسائل الخطأ."""
    try:
        r = session().get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return r
    except requests.RequestException as e:
        raise RuntimeError(redact(e)) from None
