import os, time, requests, socket, ssl, urllib3.util.connection as urllib3_cn

# (اختياري) جرّب IPv4 فقط لو تشك بإشكال IPv6
# urllib3_cn.allowed_gai_family = lambda: socket.AF_INET

KEY = os.getenv("ZENSERP_API_KEY") or "YOUR_ZENSERP_API_KEY"
TARGET_IMAGE = os.getenv("TARGET_IMAGE") or "https://i.ibb.co/4Zb62HDc/temp-img-5e6b0061-c0cd-4b79-9dad-e99784d17c0f.png"
FAST_IMAGE = "https://via.placeholder.com/512"
HOST = "app.zenserp.com"

def log(*a): print(*a, flush=True)

def tls_probe():
    try:
        s = socket.create_connection((HOST, 443), timeout=6)
        ctx = ssl.create_default_context()
        with ctx.wrap_socket(s, server_hostname=HOST) as ss:
            return True, ss.version()
    except Exception as e:
        return False, repr(e)

def get(url, headers=None, params=None, timeout=(6, 10)):
    t0 = time.time()
    r = requests.get(url, headers=headers or {}, params=params or {}, timeout=timeout)
    return r, round(time.time()-t0, 2)

def text_search():
    try:
        r, dt = get(f"https://{HOST}/api/v2/search", headers={"apikey": KEY}, params={"q":"test"}, timeout=(6,10))
        return {"ok": r.status_code==200, "status": r.status_code, "elapsed": dt, "len": len(r.text)}
    except Exception as e:
        return {"ok": False, "error": repr(e)}

def reverse_image(img_url, read_to=50):
    try:
        r, dt = get(f"https://{HOST}/api/v2/search",
                    headers={"apikey": KEY},
                    params={"image_url": img_url},
                    timeout=(8, read_to))
        info = {"ok": r.status_code==200, "status": r.status_code, "elapsed": dt}
        if r.status_code==200:
            try:
                data = r.json()
            except Exception:
                data = {}
            organic = (data.get("reverse_image_results", {}).get("organic") or data.get("organic_results") or [])
            info["links_count"] = len([d.get("url") for d in organic if isinstance(d, dict) and d.get("url")])
        else:
            info["body_sample"] = r.text[:200]
        return info
    except requests.exceptions.Timeout as e:
        return {"ok": False, "timeout": True, "error": f"Timeout: {e}"}
    except Exception as e:
        return {"ok": False, "error": repr(e)}

def head(url):
    import time
    t0=time.time()
    try:
        r = requests.head(url, allow_redirects=True, timeout=(4,6))
        return {"ok": True, "status": r.status_code, "cl": r.headers.get("Content-Length"), "ct": r.headers.get("Content-Type"), "elapsed": round(time.time()-t0,2)}
    except Exception as e:
        return {"ok": False, "error": repr(e), "elapsed": round(time.time()-t0,2)}

def main():
    print("=== Smoke Test ===")
    # TLS reachability
    ok, detail = tls_probe()
    print("TLS:", "OK" if ok else "FAIL", detail)

    # Quick text search
    t = text_search()
    print("Text search:", t)

    # HEAD checks
    hf = head(FAST_IMAGE)
    ht = head(TARGET_IMAGE)
    print("HEAD fast:", hf)
    print("HEAD target:", ht)

    # Reverse fast image (control)
    rf = reverse_image(FAST_IMAGE, read_to=20)
    print("Reverse FAST:", rf)

    # Reverse target image (long read timeout since you allow 50s)
    rt = reverse_image(TARGET_IMAGE, read_to=50)
    print("Reverse TARGET:", rt)

    # Quick verdict
    verdict = []
    if not ok:
        verdict.append("❌ TLS/connect issue → غالبًا شبكة/فايروول/بروكسي.")
    if t.get("ok") is False:
        verdict.append("❌ Even text search failing → مشكلة وصول عامة لZenserp.")
    if rf.get("ok"):
        if not rt.get("ok") and rt.get("timeout"):
            verdict.append("🟡 Reverse FAST OK لكن TARGET Timeout → مصدر الصورة بطيء/محجوب لZenserp. جرّب إعادة الاستضافة/تصغير الحجم.")
    if ht.get("cl"):
        try:
            sz = int(ht["cl"])
            if sz > 3_000_000:
                verdict.append(f"ℹ️ الصورة كبيرة (~{sz/1_000_000:.1f}MB) → توقّع بطء. صغّرها أو أعد استضافتها.")
        except Exception:
            pass
    if not verdict:
        verdict.append("✅ الاتصال سليم. لو وقت انتظار طويل على TARGET، السبب من المصدر. الحل: rehost/resize أو مهلة أطول.")

    print("\n== Verdict ==")
    for v in verdict:
        print("-", v)

if __name__ == "__main__":
    main()
