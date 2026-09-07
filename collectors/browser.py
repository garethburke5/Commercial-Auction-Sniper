from __future__ import annotations
import ssl
import subprocess
import time
import requests
from urllib.request import Request, urlopen
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    "Accept-Language": "en-GB,en;q=0.9",
}


def _session() -> requests.Session:
    session = requests.Session()
    retry = Retry(total=3,connect=3,read=3,status=3,backoff_factor=0.8,status_forcelist=(408,425,429,500,502,503,504),allowed_methods=frozenset({"GET","HEAD"}),raise_on_status=False)
    session.mount("https://", HTTPAdapter(max_retries=retry)); session.mount("http://", HTTPAdapter(max_retries=retry))
    return session


def _curl_http11(url: str, timeout_ms: int) -> str | None:
    timeout_s=max(10,int(timeout_ms/1000))
    try:
        proc=subprocess.run(["curl","--http1.1","--location","--silent","--show-error","--fail-with-body","--retry","2","--retry-all-errors","--connect-timeout","12","--max-time",str(timeout_s),"-A",HEADERS["User-Agent"],"-H",f"Accept-Language: {HEADERS['Accept-Language']}","-H","Connection: close",url],capture_output=True,text=True,timeout=timeout_s+5,check=False)
        text=proc.stdout or ""
        if proc.returncode==0 and len(text)>1000: return text
    except (OSError,subprocess.SubprocessError): pass
    return None


def _curl_http11_bytes(url: str, timeout_ms: int, max_bytes: int) -> bytes | None:
    """Binary equivalent of the HTTP/1.1 fallback used for HTML.

    Some auction brochure/CDN hosts fail Python TLS/HTTP transports from hosted
    runners while curl --http1.1 succeeds. Keep the same public URL and headers;
    only the transport changes. The byte ceiling prevents oversized downloads.
    """
    timeout_s=max(10,int(timeout_ms/1000))
    try:
        proc=subprocess.run(["curl","--http1.1","--location","--silent","--show-error","--fail-with-body","--retry","2","--retry-all-errors","--connect-timeout","12","--max-time",str(timeout_s),"-A",HEADERS["User-Agent"],"-H",f"Accept-Language: {HEADERS['Accept-Language']}","-H","Accept: application/pdf,application/octet-stream,*/*;q=0.8","-H","Connection: close",url],capture_output=True,text=False,timeout=timeout_s+5,check=False)
        data=proc.stdout or b""
        if proc.returncode==0 and 500<=len(data)<=max_bytes:return data
    except (OSError,subprocess.SubprocessError):pass
    return None


def _urllib_fetch(url: str, timeout_ms: int) -> str | None:
    timeout_s=max(10,int(timeout_ms/1000))
    try:
        req=Request(url,headers={"User-Agent":HEADERS["User-Agent"],"Accept-Language":HEADERS["Accept-Language"],"Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8","Connection":"close"})
        with urlopen(req,timeout=timeout_s,context=ssl.create_default_context()) as response:
            raw=response.read()
            if len(raw)<=1000:return None
            charset=response.headers.get_content_charset() or "utf-8"
            return raw.decode(charset,errors="replace")
    except Exception:return None


def get_bytes(url: str, timeout_ms: int = 30000, max_bytes: int = 15_000_000) -> bytes:
    try:
        r=_session().get(url,headers={**HEADERS,"Connection":"close"},timeout=(15,30),allow_redirects=True); r.raise_for_status(); data=r.content
        if 500<=len(data)<=max_bytes:return data
    except Exception:pass
    data=_curl_http11_bytes(url,timeout_ms,max_bytes)
    if data:return data
    timeout_s=max(10,int(timeout_ms/1000))
    try:
        req=Request(url,headers={"User-Agent":HEADERS["User-Agent"],"Accept-Language":HEADERS["Accept-Language"],"Accept":"application/pdf,application/octet-stream,*/*;q=0.8","Connection":"close"})
        with urlopen(req,timeout=timeout_s,context=ssl.create_default_context()) as response:
            data=response.read(max_bytes+1)
            if 500<=len(data)<=max_bytes:return data
    except Exception:pass
    raise RuntimeError(f"No usable binary document returned for {url}")


def _browser_launch_args():
    return ["--disable-http2"]


def get_html(url: str, use_browser: bool = False, timeout_ms: int = 30000) -> str:
    if not use_browser:
        try:
            r=_session().get(url,headers={**HEADERS,"Connection":"close"},timeout=(15,30)); r.raise_for_status(); text=r.text
            if len(text)>1000:return text
        except Exception:pass
        text=_curl_http11(url,timeout_ms)
        if text:return text
        text=_urllib_fetch(url,timeout_ms)
        if text:return text

    from playwright.sync_api import sync_playwright
    last_exc=None
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,args=_browser_launch_args())
        try:
            for attempt in range(2):
                page=browser.new_page(user_agent=HEADERS["User-Agent"],extra_http_headers={"Accept-Language":HEADERS["Accept-Language"],"Connection":"close"})
                try:
                    response=page.goto(url,wait_until="domcontentloaded",timeout=timeout_ms)
                    if response and response.status>=500 and attempt==0:
                        page.close(); time.sleep(1.0); continue
                    try:page.wait_for_load_state("networkidle",timeout=7000)
                    except Exception:pass
                    html=page.content()
                    if len(html)>1000:return html
                except Exception as exc:last_exc=exc
                finally:
                    if not page.is_closed():page.close()
                time.sleep(1.0)
        finally:browser.close()
    if last_exc:raise last_exc
    raise RuntimeError(f"No usable HTML returned for {url}")
