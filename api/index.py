import os
import re
import time
import datetime
import urllib.parse
import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "..", "templates")

app = Flask(__name__, template_folder=TEMPLATE_DIR)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SEOCheckerBot/1.0; +https://vercel.app)"
}


@app.context_processor
def inject_global_context():
    return {
        "current_year": datetime.datetime.now().year,
        "site_name": "SEOChecker",
    }


@app.route("/page/tentang-kami/", methods=["GET"])
def about_page():
    return render_template("about.html")


@app.route("/page/panduan-konsep/", methods=["GET"])
def guide_page():
    return render_template("guide.html")


def normalize_slug(raw_url: str) -> str:
    """Membersihkan input URL menjadi path slug bersih, misal: bisdigunm.com atau bisdigunm.com/profil"""
    cleaned = raw_url.strip()
    if cleaned.startswith(("http://", "https://")):
        parsed = urllib.parse.urlparse(cleaned)
        slug = parsed.netloc + parsed.path
    else:
        slug = cleaned
    return slug.strip("/")


def get_real_target_from_request(fallback_target: str = "") -> str:
    """Membaca path asli website target sebelum di-rewrite oleh Vercel."""
    candidates = [
        request.args.get("url", ""),
        request.headers.get("x-vercel-original-path", ""),
        request.headers.get("x-matched-path", ""),
        request.environ.get("REQUEST_URI", ""),
        fallback_target,
    ]
    for raw in candidates:
        if not raw:
            continue
        path_only = raw.split("?")[0].strip("/")
        if path_only and path_only not in ("api/index.py", "favicon.ico", "robots.txt"):
            return normalize_slug(path_only)
    return ""


def analyze_seo(url: str) -> dict:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    parsed_base = urllib.parse.urlparse(url)
    base_domain = parsed_base.netloc
    base_origin = f"{parsed_base.scheme}://{base_domain}"

    start_time = time.time()
    response = requests.get(url, headers=HEADERS, timeout=10, allow_redirects=True)
    load_time = round(time.time() - start_time, 2)
    html_raw = response.text
    html_size_kb = round(len(response.content) / 1024, 1)

    soup = BeautifulSoup(html_raw, "html.parser")
    score = 0
    checks = []

    def add_check(category: str, item: str, status: str, detail: str, pts: int = 0, anchor: str = ""):
        nonlocal score
        score += pts
        checks.append({
            "category": category,
            "item": item,
            "status": status,
            "detail": detail,
            "points": pts,
            "anchor": anchor,
        })

    # =========================================================================
    # A. META & DOCUMENT BASICS (Total: 32 Poin)
    # =========================================================================

    # 1. Title (10 Poin)
    title_tag = soup.find("title")
    title_text = title_tag.get_text(strip=True) if title_tag else ""
    title_len = len(title_text)
    if 30 <= title_len <= 65:
        add_check("Meta & Document", "Title", "pass", f"Ideal ({title_len} karakter): \"{title_text}\"", 10, anchor="title")
    elif title_len > 0:
        add_check("Meta & Document", "Title", "warn", f"Kurang ideal ({title_len} karakter, saran 30–65): \"{title_text}\"", 5, anchor="title")
    else:
        add_check("Meta & Document", "Title", "fail", "Tag <title> tidak ditemukan pada dokumen.", 0, anchor="title")

    # 2. Meta Description (8 Poin)
    desc_tag = soup.find("meta", attrs={"name": lambda x: x and x.lower() == "description"})
    desc_text = desc_tag["content"].strip() if desc_tag and desc_tag.get("content") else ""
    desc_len = len(desc_text)
    if 110 <= desc_len <= 165:
        add_check("Meta & Document", "Meta Description", "pass", f"Ideal ({desc_len} karakter).", 8, anchor="meta-description")
    elif desc_len > 0:
        add_check("Meta & Document", "Meta Description", "warn", f"Panjang {desc_len} karakter (disarankan 110–165 karakter).", 4, anchor="meta-description")
    else:
        add_check("Meta & Document", "Meta Description", "fail", "Meta description tidak ditemukan.", 0, anchor="meta-description")

    # 3. Page URL (4 Poin)
    final_parsed = urllib.parse.urlparse(response.url)
    url_len = len(response.url)
    has_query = bool(final_parsed.query)
    has_underscore = "_" in final_parsed.path
    if url_len <= 85 and not has_query and not has_underscore:
        add_check("Meta & Document", "Page URL", "pass", f"SEO-friendly ({url_len} karakter, bersih tanpa parameter dinamis).", 4, anchor="page-url")
    else:
        add_check("Meta & Document", "Page URL", "warn", f"Panjang {url_len} karakter (Query: {has_query}, Underscore: {has_underscore}).", 2, anchor="page-url")

    # 4. Language (3 Poin)
    html_tag = soup.find("html")
    lang_attr = html_tag.get("lang", "").strip() if html_tag else ""
    if lang_attr:
        add_check("Meta & Document", "Language", "pass", f"Atribut bahasa terdeteksi: lang=\"{lang_attr}\".", 3, anchor="language")
    else:
        add_check("Meta & Document", "Language", "warn", "Atribut lang pada tag <html> belum ditentukan.", 0, anchor="language")

    # 5. Alternate / Hreflang Links (2 Poin)
    hreflangs = soup.find_all("link", attrs={"rel": lambda x: x and "alternate" in x, "hreflang": True})
    if hreflangs:
        langs = ", ".join([h.get("hreflang", "") for h in hreflangs[:5]])
        add_check("Meta & Document", "Alternate / Hreflang Links", "pass", f"Ditemukan {len(hreflangs)} tag hreflang ({langs}).", 2, anchor="hreflang")
    else:
        add_check("Meta & Document", "Alternate / Hreflang Links", "warn", "Tidak ada tag hreflang (opsional untuk situs multi-bahasa).", 1, anchor="hreflang")

    # 6. Other Meta Tags (Robots, Canonical, Open Graph, Twitter Card) (3 Poin)
    canonical = soup.find("link", attrs={"rel": lambda x: x and "canonical" in x})
    robots_meta = soup.find("meta", attrs={"name": lambda x: x and x.lower() == "robots"})
    og_title = soup.find("meta", property="og:title")
    twitter_card = soup.find("meta", attrs={"name": "twitter:card"})
    meta_found = []
    if canonical and canonical.get("href"):
        meta_found.append("canonical")
    if robots_meta:
        meta_found.append(f"robots({robots_meta.get('content', '')})")
    if og_title:
        meta_found.append("og:title")
    if twitter_card:
        meta_found.append("twitter:card")
    if len(meta_found) >= 2:
        add_check("Meta & Document", "Other Meta Tags", "pass", f"Terpasang: {', '.join(meta_found)}.", 3, anchor="other-meta")
    else:
        add_check("Meta & Document", "Other Meta Tags", "warn", f"Minim meta pendukung ({', '.join(meta_found) or 'kosong'}).", 1, anchor="other-meta")

    # 7. Doctype, Charset Encoding & Favicon (2 Poin)
    has_doctype = bool(re.search(r"<!doctype\s+html", html_raw[:300], re.IGNORECASE))
    charset_tag = soup.find("meta", charset=True) or soup.find("meta", attrs={"http-equiv": lambda x: x and x.lower() == "content-type"})
    charset_val = charset_tag.get("charset", "declared") if charset_tag else ""
    favicon_tag = soup.find("link", attrs={"rel": lambda x: x and any("icon" in r.lower() for r in (x if isinstance(x, list) else [x]))})
    favicon_href = favicon_tag.get("href", "") if favicon_tag else ""

    add_check(
        "Meta & Document",
        "Doctype & Charset Encoding",
        "pass" if (has_doctype and charset_val) else "warn",
        f"Doctype HTML5: {'Ya' if has_doctype else 'Tidak'} | Charset: {charset_val or 'Tidak dideklarasikan'}.",
        1 if (has_doctype and charset_val) else 0,
        anchor="doctype-charset",
    )
    add_check(
        "Meta & Document",
        "Favicon",
        "pass" if favicon_href else "warn",
        f"Terdeteksi ({favicon_href})" if favicon_href else "Tag <link rel='icon'> tidak ditemukan di HTML.",
        1 if favicon_href else 0,
        anchor="favicon",
    )

    # =========================================================================
    # B. CONTENT & HEADINGS (Total: 25 Poin)
    # =========================================================================

    # 8. H1 Headings (8 Poin)
    h1_tags = [h.get_text(strip=True) for h in soup.find_all("h1") if h.get_text(strip=True)]
    if len(h1_tags) == 1:
        add_check("Content & Headings", "H1 Headings", "pass", f"Tepat 1 tag H1: \"{h1_tags[0]}\"", 8, anchor="h1-heading")
    elif len(h1_tags) > 1:
        add_check("Content & Headings", "H1 Headings", "warn", f"Terdapat {len(h1_tags)} tag H1 (disarankan hanya 1).", 4, anchor="h1-heading")
    else:
        add_check("Content & Headings", "H1 Headings", "fail", "Tag <h1> tidak ditemukan.", 0, anchor="h1-heading")

    # 9. Headings Hierarchy (H2-H6) (5 Poin)
    h2_count = len(soup.find_all("h2"))
    h3_count = len(soup.find_all("h3"))
    h4_count = len(soup.find_all("h4"))
    if h2_count > 0:
        add_check("Content & Headings", "Headings Structure (H2–H4)", "pass", f"Hierarki terstruktur: H2 ({h2_count}), H3 ({h3_count}), H4 ({h4_count}).", 5, anchor="headings-structure")
    else:
        add_check("Content & Headings", "Headings Structure (H2–H4)", "warn", "Sub-heading H2 tidak ditemukan untuk membagi bagian konten.", 2, anchor="headings-structure")

    # 10. Content & Word Count (7 Poin)
    soup_clean = BeautifulSoup(html_raw, "html.parser")
    for tag in soup_clean(["script", "style", "noscript"]):
        tag.decompose()
    visible_text = " ".join(soup_clean.get_text(separator=" ").split())
    words = visible_text.split()
    word_count = len(words)
    if word_count >= 300:
        add_check("Content & Headings", "Content", "pass", f"Konten memadai ({word_count} kata terindeks).", 7, anchor="content-word-count")
    elif word_count >= 100:
        add_check("Content & Headings", "Content", "warn", f"Konten relatif singkat ({word_count} kata; disarankan >= 300 kata).", 4, anchor="content-word-count")
    else:
        add_check("Content & Headings", "Content", "fail", f"Thin content ({word_count} kata terdeteksi).", 1, anchor="content-word-count")

    # 11. Page Quality (Text-to-HTML Ratio & Schema JSON-LD) (5 Poin)
    text_ratio = round((len(visible_text) / max(len(html_raw), 1)) * 100, 1)
    json_ld = soup.find_all("script", attrs={"type": "application/ld+json"})
    if text_ratio >= 10 or len(json_ld) > 0:
        add_check("Content & Headings", "Page Quality", "pass", f"Text/HTML ratio: {text_ratio}% | Structured Data (JSON-LD): {len(json_ld)} blok.", 5, anchor="page-quality-schema")
    else:
        add_check("Content & Headings", "Page Quality", "warn", f"Text/HTML ratio rendah ({text_ratio}%) & tanpa Schema JSON-LD.", 2, anchor="page-quality-schema")

    # =========================================================================
    # C. LINK STRUCTURE & IMAGE SEO (Total: 20 Poin)
    # =========================================================================

    links = soup.find_all("a", href=True)
    internal_links = 0
    external_links = 0
    nofollow_links = 0
    empty_anchor = 0

    for a in links:
        href = a["href"].strip()
        rel_val = " ".join(a.get("rel", [])).lower()
        if "nofollow" in rel_val:
            nofollow_links += 1
        if not a.get_text(strip=True) and not a.find("img"):
            empty_anchor += 1

        if href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        if href.startswith("/") or base_domain in href:
            internal_links += 1
        elif href.startswith("http"):
            external_links += 1

    # 12. Link Structure & Internal Links (8 Poin)
    if internal_links >= 3:
        add_check("Links & Media", "Link Structure & Internal Links", "pass", f"{internal_links} tautan internal ditemukan (tautan tanpa teks anchor: {empty_anchor}).", 8, anchor="internal-links")
    elif internal_links > 0:
        add_check("Links & Media", "Link Structure & Internal Links", "warn", f"Hanya {internal_links} tautan internal ditemukan.", 4, anchor="internal-links")
    else:
        add_check("Links & Media", "Link Structure & Internal Links", "fail", "Tidak ada tautan internal untuk navigasi crawler.", 0, anchor="internal-links")

    # 13. External Links (4 Poin)
    add_check(
        "Links & Media",
        "External Links",
        "pass" if external_links > 0 else "warn",
        f"{external_links} tautan eksternal keluar (atribut nofollow: {nofollow_links}).",
        4 if external_links > 0 else 2,
        anchor="external-links",
    )

    # 14. Image SEO (8 Poin)
    images = soup.find_all("img")
    missing_alt = [img for img in images if not img.get("alt") or not img.get("alt").strip()]
    lazy_imgs = [img for img in images if img.get("loading") == "lazy"]
    if len(images) == 0 or len(missing_alt) == 0:
        add_check("Links & Media", "Image SEO", "pass", f"{len(images)} gambar memiliki atribut alt lengkap (lazy-load: {len(lazy_imgs)}).", 8, anchor="image-seo")
    else:
        ratio = (len(images) - len(missing_alt)) / len(images)
        add_check("Links & Media", "Image SEO", "warn", f"{len(missing_alt)} dari {len(images)} gambar tanpa alt text (lazy-load: {len(lazy_imgs)}).", max(2, int(8 * ratio)), anchor="image-seo")

    # =========================================================================
    # D. MOBILE, PERFORMANCE & SERVER CONFIGURATION (Total: 18 Poin)
    # =========================================================================

    # 15. Mobile Optimization (6 Poin)
    viewport = soup.find("meta", attrs={"name": lambda x: x and x.lower() == "viewport"})
    vp_content = viewport.get("content", "") if viewport else ""
    if viewport and "width=device-width" in vp_content.lower():
        add_check("Technical & Server", "Mobile Optimization", "pass", f"Responsif aktif ({vp_content}).", 6, anchor="mobile-optimization")
    elif viewport:
        add_check("Technical & Server", "Mobile Optimization", "warn", f"Tag viewport ada namun belum standar ({vp_content}).", 3, anchor="mobile-optimization")
    else:
        add_check("Technical & Server", "Mobile Optimization", "fail", "Meta viewport mobile tidak ditemukan.", 0, anchor="mobile-optimization")

    # 16. Performance (6 Poin)
    script_count = len(soup.find_all("script", src=True))
    css_count = len(soup.find_all("link", rel="stylesheet"))
    if load_time <= 1.5 and html_size_kb <= 500:
        add_check("Technical & Server", "Performance", "pass", f"Respons cepat ({load_time}s), ukuran HTML {html_size_kb} KB ({script_count} JS, {css_count} CSS).", 6, anchor="performance")
    elif load_time <= 3.5:
        add_check("Technical & Server", "Performance", "warn", f"Waktu muat {load_time}s, ukuran HTML {html_size_kb} KB ({script_count} JS, {css_count} CSS).", 3, anchor="performance")
    else:
        add_check("Technical & Server", "Performance", "fail", f"Respons lambat ({load_time}s), ukuran HTML {html_size_kb} KB.", 1, anchor="performance")

    # 17. Server Configuration (6 Poin)
    is_https = response.url.startswith("https://")
    server_hdr = response.headers.get("Server", "Hidden")
    encoding_hdr = response.headers.get("Content-Encoding", "none")
    cache_hdr = response.headers.get("Cache-Control", "not set")
    if response.status_code == 200 and is_https:
        add_check("Technical & Server", "Server Configuration", "pass", f"HTTPS Aktif (HTTP {response.status_code}) | Server: {server_hdr} | Compression: {encoding_hdr} | Cache: {cache_hdr[:35]}.", 6, anchor="server-configuration")
    else:
        add_check("Technical & Server", "Server Configuration", "fail", f"HTTP {response.status_code}, HTTPS: {is_https}, Server: {server_hdr}.", 0, anchor="server-configuration")

    has_robots_txt = False
    has_sitemap = False
    try:
        r_rob = requests.get(f"{base_origin}/robots.txt", headers=HEADERS, timeout=3)
        if r_rob.status_code == 200 and "user-agent" in r_rob.text.lower():
            has_robots_txt = True
            if "sitemap:" in r_rob.text.lower():
                has_sitemap = True
    except requests.RequestException:
        pass

    if not has_sitemap:
        try:
            r_map = requests.head(f"{base_origin}/sitemap.xml", headers=HEADERS, timeout=3)
            if r_map.status_code == 200:
                has_sitemap = True
        except requests.RequestException:
            pass

    social_domains = ("instagram.com", "facebook.com", "twitter.com", "x.com", "linkedin.com", "youtube.com", "tiktok.com")
    social_profiles = sum(1 for a in links if any(sd in a["href"].lower() for sd in social_domains))

    ext_pts = (2 if has_robots_txt else 0) + (2 if has_sitemap else 0) + (1 if social_profiles > 0 else 0)
    add_check(
        "External Factors",
        "External Factors & Off-Page Signals",
        "pass" if ext_pts >= 4 else "warn",
        f"robots.txt: {'Ada' if has_robots_txt else 'Tidak'} | sitemap.xml: {'Ada' if has_sitemap else 'Tidak'} | Social Profiles: {social_profiles} tautan | Backlink API: Perlu integrasi pihak ketiga (Ahrefs/Moz/GSC).",
        ext_pts,
        anchor="external-factors",
    )

    return {
        "final_url": response.url,
        "score": min(score, 100),
        "load_time": load_time,
        "html_size_kb": html_size_kb,
        "word_count": word_count,
        "title": title_text or "-",
        "description": desc_text or "-",
        "headings": {
            "h1": len(h1_tags),
            "h2": h2_count,
            "h3": h3_count,
        },
        "links": {
            "internal": internal_links,
            "external": external_links,
        },
        "images_total": len(images),
        "images_missing_alt": len(missing_alt),
        "checks": checks,
    }


def run_audit_view(slug: str):
    try:
        result = analyze_seo(slug)
        return render_template("index.html", result=result, error=None, target_slug=slug)
    except requests.exceptions.Timeout:
        return render_template(
            "index.html",
            result=None,
            error="Waktu koneksi habis (timeout) saat mengakses website target.",
            target_slug=slug,
        )
    except requests.exceptions.RequestException as e:
        return render_template(
            "index.html",
            result=None,
            error=f"Gagal mengakses URL '{slug}': {str(e)}",
            target_slug=slug,
        )


@app.route("/", methods=["GET"])
def home():
    slug = get_real_target_from_request()
    if slug == "page/tentang-kami/":
        return render_template("about.html")
    if slug == "page/panduan-konsep/":
        return render_template("guide.html")
    if slug:
        return run_audit_view(slug)
    return render_template("index.html", result=None, error=None, target_slug="")


@app.route("/<path:target>", methods=["GET"])
def report_page(target):
    if target in ("favicon.ico", "robots.txt"):
        return "", 204
    if target == "page/tentang-kami/":
        return render_template("about.html")
    if target == "page/panduan-konsep/":
        return render_template("guide.html")

    slug = get_real_target_from_request(target)
    if slug == "page/tentang-kami/":
        return render_template("about.html")
    if slug == "page/panduan-konsep/":
        return render_template("guide.html")
    if not slug:
        return render_template("index.html", result=None, error=None, target_slug="")
    return run_audit_view(slug)


if __name__ == "__main__":
    app.run(debug=True, port=50001)