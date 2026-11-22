import os
import sys
import time
import urllib.parse
import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, redirect, url_for


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from context_processors import inject_global_context

TEMPLATE_DIR = os.path.join(ROOT_DIR, "templates")


app = Flask(__name__, template_folder=TEMPLATE_DIR)
app.context_processor(inject_global_context)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SEOCheckerBot/1.0; +https://vercel.app)"
}


@app.route("/page/tentang-kami", methods=["GET"])
def about_page():
    return render_template("about.html")


def normalize_slug(raw_url: str) -> str:
    """Membersihkan input URL menjadi path slug bersih, misal: bisdigunm.com atau bisdigunm.com/profil"""
    cleaned = raw_url.strip()
    if cleaned.startswith(("http://", "https://")):
        parsed = urllib.parse.urlparse(cleaned)
        slug = parsed.netloc + parsed.path
    else:
        slug = cleaned
    return slug.strip("/")


def analyze_seo(url: str) -> dict:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    parsed_base = urllib.parse.urlparse(url)
    base_domain = parsed_base.netloc

    start_time = time.time()
    response = requests.get(url, headers=HEADERS, timeout=10, allow_redirects=True)
    load_time = round(time.time() - start_time, 2)

    soup = BeautifulSoup(response.text, "html.parser")
    score = 0
    checks = []

    # 1. HTTPS & Status Code (15 Poin)
    is_https = response.url.startswith("https://")
    if response.status_code == 200 and is_https:
        score += 15
        checks.append({"item": "HTTPS & HTTP Status", "status": "pass", "detail": f"Aktif (HTTPS, Status {response.status_code})"})
    else:
        checks.append({"item": "HTTPS & HTTP Status", "status": "fail", "detail": f"Status {response.status_code}, HTTPS: {is_https}"})

    # 2. Title Tag (20 Poin)
    title_tag = soup.find("title")
    title_text = title_tag.get_text(strip=True) if title_tag else ""
    title_len = len(title_text)
    if 30 <= title_len <= 65:
        score += 20
        checks.append({"item": "Meta Title", "status": "pass", "detail": f"Ideal ({title_len} karakter): \"{title_text}\""})
    elif title_len > 0:
        score += 10
        checks.append({"item": "Meta Title", "status": "warn", "detail": f"Kurang optimal ({title_len} karakter, ideal 30–65): \"{title_text}\""})
    else:
        checks.append({"item": "Meta Title", "status": "fail", "detail": "Tag <title> tidak ditemukan."})

    # 3. Meta Description (15 Poin)
    desc_tag = soup.find("meta", attrs={"name": lambda x: x and x.lower() == "description"})
    desc_text = desc_tag["content"].strip() if desc_tag and desc_tag.get("content") else ""
    desc_len = len(desc_text)
    if 110 <= desc_len <= 165:
        score += 15
        checks.append({"item": "Meta Description", "status": "pass", "detail": f"Ideal ({desc_len} karakter)."})
    elif desc_len > 0:
        score += 8
        checks.append({"item": "Meta Description", "status": "warn", "detail": f"Panjang {desc_len} karakter (disarankan 110–165 karakter)."})
    else:
        checks.append({"item": "Meta Description", "status": "fail", "detail": "Meta description tidak ditemukan."})

    # 4. Heading H1 (15 Poin)
    h1_tags = [h.get_text(strip=True) for h in soup.find_all("h1") if h.get_text(strip=True)]
    if len(h1_tags) == 1:
        score += 15
        checks.append({"item": "Struktur Heading H1", "status": "pass", "detail": f"Tepat 1 tag H1: \"{h1_tags[0]}\""})
    elif len(h1_tags) > 1:
        score += 8
        checks.append({"item": "Struktur Heading H1", "status": "warn", "detail": f"Ditemukan {len(h1_tags)} tag H1 (sebaiknya hanya 1)."})
    else:
        checks.append({"item": "Struktur Heading H1", "status": "fail", "detail": "Tag <h1> tidak ditemukan."})

    # 5. Canonical Tag (10 Poin)
    canonical = soup.find("link", attrs={"rel": lambda x: x and "canonical" in x})
    canonical_href = canonical.get("href", "") if canonical else ""
    if canonical_href:
        score += 10
        checks.append({"item": "Canonical URL", "status": "pass", "detail": canonical_href})
    else:
        checks.append({"item": "Canonical URL", "status": "warn", "detail": "Tag rel='canonical' belum dipasang."})

    # 6. Optimasi Gambar / Alt Attribute (10 Poin)
    images = soup.find_all("img")
    missing_alt = [img.get("src", "unknown") for img in images if not img.get("alt") or not img.get("alt").strip()]
    if len(images) == 0 or len(missing_alt) == 0:
        score += 10
        checks.append({"item": "Atribut Alt Gambar", "status": "pass", "detail": f"Semua {len(images)} gambar memiliki teks alt."})
    else:
        ratio = (len(images) - len(missing_alt)) / len(images)
        score += int(10 * ratio)
        checks.append({"item": "Atribut Alt Gambar", "status": "warn", "detail": f"{len(missing_alt)} dari {len(images)} gambar tidak memiliki atribut alt."})

    # 7. Open Graph & Viewport Mobile (15 Poin)
    og_title = soup.find("meta", property="og:title")
    viewport = soup.find("meta", attrs={"name": "viewport"})
    if og_title and viewport:
        score += 15
        checks.append({"item": "Mobile Viewport & Open Graph", "status": "pass", "detail": "Meta viewport dan og:title tersedia."})
    elif viewport or og_title:
        score += 8
        checks.append({"item": "Mobile Viewport & Open Graph", "status": "warn", "detail": "Salah satu antara viewport atau og:title belum lengkap."})
    else:
        checks.append({"item": "Mobile Viewport & Open Graph", "status": "fail", "detail": "Meta viewport dan Open Graph tidak ditemukan."})

    # Ringkasan Tautan
    links = soup.find_all("a", href=True)
    internal_links = 0
    external_links = 0
    for a in links:
        href = a["href"]
        if href.startswith("/") or base_domain in href:
            internal_links += 1
        elif href.startswith("http"):
            external_links += 1

    return {
        "final_url": response.url,
        "score": score,
        "load_time": load_time,
        "title": title_text or "-",
        "description": desc_text or "-",
        "headings": {
            "h1": len(h1_tags),
            "h2": len(soup.find_all("h2")),
            "h3": len(soup.find_all("h3")),
        },
        "links": {
            "internal": internal_links,
            "external": external_links,
        },
        "images_total": len(images),
        "images_missing_alt": len(missing_alt),
        "checks": checks,
    }


@app.route("/", methods=["GET"])
def home():
    return render_template("index.html", result=None, error=None, target_slug="")


@app.route("/scan", methods=["POST"])
def scan_redirect():
    raw_url = request.form.get("url", "").strip()
    slug = normalize_slug(raw_url)
    if not slug:
        return render_template("index.html", result=None, error="Masukkan URL website terlebih dahulu.", target_slug="")
    return redirect(url_for("report_page", target=slug))


@app.route("/<path:target>", methods=["GET"])
def report_page(target):
    # Abaikan permintaan favicon browser agar tidak dipindai sebagai domain
    if target == "favicon.ico":
        return "", 204

    slug = normalize_slug(target)
    try:
        result = analyze_seo(slug)
        return render_template("index.html", result=result, error=None, target_slug=slug)
    except requests.exceptions.Timeout:
        return render_template("index.html", result=None, error="Waktu koneksi habis (timeout) saat mengakses website target.", target_slug=slug)
    except requests.exceptions.RequestException as e:
        return render_template("index.html", result=None, error=f"Gagal mengakses URL '{slug}': {str(e)}", target_slug=slug)


if __name__ == "__main__":
    app.run(debug=True, port=5000)