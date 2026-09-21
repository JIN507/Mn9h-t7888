"""What the FILE itself says about its origin (origin engine, item 2).

  - EXIF: camera make/model, editing software, capture time, GPS
  - IPTC: creator / by-line, credit, copyright, headline, caption
  - XMP: creator, credit, creator tool, history (edit software)
  - C2PA / Content Credentials: presence + claim generator when readable
  - AI-generation verdict (AIOrNot) — a generated image has no real-world
    event to trace; its earliest poster is its creator.

Everything is best-effort and never raises. Output feeds the report and
the agent (a credit line often names the first publisher outright).
"""
import io
import logging
import os
import re
import tempfile

logger = logging.getLogger(__name__)

_IPTC_FIELDS = {
    (2, 80): 'creator', (2, 110): 'credit', (2, 115): 'source',
    (2, 116): 'copyright', (2, 105): 'headline', (2, 120): 'caption',
    (2, 90): 'city', (2, 101): 'country', (2, 55): 'date_created',
}
_XMP_FIELDS = [
    ('creator_tool', r'xmp:CreatorTool(?:="([^"]+)"|>\s*([^<]+)<)'),
    ('credit', r'photoshop:Credit(?:="([^"]+)"|>\s*([^<]+)<)'),
    ('source', r'photoshop:Source(?:="([^"]+)"|>\s*([^<]+)<)'),
    ('creator', r'dc:creator>.*?<rdf:li[^>]*>\s*([^<]+)<'),
    ('rights', r'dc:rights>.*?<rdf:li[^>]*>\s*([^<]+)<'),
    ('description', r'dc:description>.*?<rdf:li[^>]*>\s*([^<]+)<'),
    ('history_software', r'stEvt:softwareAgent(?:="([^"]+)"|>\s*([^<]+)<)'),
    ('digital_source_type', r'DigitalSourceType(?:="([^"]+)"|>\s*([^<]+)<)'),
]
AI_SOFTWARE_HINTS = ('midjourney', 'dall', 'stable diffusion', 'firefly', 'openai',
                     'gemini', 'imagen', 'leonardo', 'ideogram', 'flux', 'trainedAlgorithmicMedia')


def _clean(v, limit=200):
    if v is None:
        return None
    if isinstance(v, bytes):
        v = v.decode('utf-8', 'replace')
    v = str(v).strip().strip('\x00')
    return v[:limit] or None


def exif_summary(pil):
    out = {}
    try:
        exif = pil.getexif()
        base = {271: 'make', 272: 'model', 305: 'software', 315: 'artist',
                33432: 'copyright', 306: 'datetime'}
        for tag, name in base.items():
            if exif.get(tag):
                out[name] = _clean(exif.get(tag))
        try:
            ifd = exif.get_ifd(0x8769)
            if ifd.get(36867):
                out['datetime_original'] = _clean(ifd.get(36867))
            if ifd.get(42036):
                out['lens'] = _clean(ifd.get(42036))
        except Exception:
            pass
        try:
            gps = exif.get_ifd(0x8825)
            if gps and gps.get(2) and gps.get(4):
                def dms(v, ref):
                    d = float(v[0]) + float(v[1]) / 60 + float(v[2]) / 3600
                    return -d if ref in ('S', 'W') else d
                out['gps'] = {'lat': round(dms(gps[2], gps.get(1, 'N')), 6),
                              'lon': round(dms(gps[4], gps.get(3, 'E')), 6)}
        except Exception:
            pass
    except Exception:
        pass
    return out


def iptc_summary(pil):
    out = {}
    try:
        from PIL import IptcImagePlugin
        info = IptcImagePlugin.getiptcinfo(pil) or {}
        for key, name in _IPTC_FIELDS.items():
            if key in info:
                val = info[key]
                if isinstance(val, list):
                    val = ', '.join(_clean(x) or '' for x in val)
                out[name] = _clean(val)
    except Exception:
        pass
    return {k: v for k, v in out.items() if v}


def xmp_summary(data):
    out = {}
    try:
        start = data.find(b'<x:xmpmeta')
        if start == -1:
            start = data.find(b'<rdf:RDF')
        if start == -1:
            return out
        chunk = data[start:start + 200000].decode('utf-8', 'replace')
        for name, pattern in _XMP_FIELDS:
            m = re.search(pattern, chunk, re.IGNORECASE | re.DOTALL)
            if m:
                val = next((g for g in m.groups() if g), None)
                if val:
                    out[name] = _clean(val)
    except Exception:
        pass
    return out


def c2pa_summary(data):
    """Content Credentials are stored in a JUMBF box labelled c2pa."""
    out = {'present': False}
    try:
        if b'c2pa' not in data and b'contentauth' not in data:
            return out
        if b'jumb' in data or b'c2pa.manifest' in data or b'c2pa' in data:
            out['present'] = True
        m = re.search(rb'claim_generator[^A-Za-z0-9]{1,8}([A-Za-z0-9 ._/()-]{3,80})', data)
        if m:
            out['claim_generator'] = _clean(m.group(1))
        m = re.search(rb'(c2pa\.actions[^\x00]{0,400})', data)
        if m and b'trainedAlgorithmicMedia' in m.group(1):
            out['digital_source_type'] = 'trainedAlgorithmicMedia'
    except Exception:
        pass
    return out


def ai_detection(data):
    """AIOrNot verdict on the query bytes (direct upload). None when the
    key is missing, ORIGIN_AI_CHECK=false, or the call fails."""
    if not os.environ.get('AIORNOT_API_KEY') or \
            os.environ.get('ORIGIN_AI_CHECK', 'true').lower() == 'false':
        return None
    try:
        from providers.aiornot import post_image_file, parse_image_report
        fd, path = tempfile.mkstemp(suffix='.jpg')
        os.close(fd)
        try:
            with open(path, 'wb') as f:
                f.write(data)
            resp = post_image_file(path, timeout=(5, 40))
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
        if resp.status_code >= 400:
            return None
        dr = parse_image_report(resp.json())
        return {'verdict': dr.verdict, 'ai_confidence': round(float(dr.ai_confidence or 0), 3),
                'generator': dr.generator if dr.generator != 'unknown' else None,
                'provider': 'aiornot'}
    except Exception as e:
        logger.info('ai detection skipped: %s', e)
        return None


def analyze(data, *, with_ai=True):
    """Full file-level provenance summary of image bytes."""
    out = {'exif': {}, 'iptc': {}, 'xmp': {}, 'c2pa': {'present': False},
           'ai_detection': None, 'hints': []}
    if not data:
        return out
    try:
        from PIL import Image
        pil = Image.open(io.BytesIO(data))
        out['format'] = pil.format
        out['size'] = list(pil.size)
        out['exif'] = exif_summary(pil)
        out['iptc'] = iptc_summary(pil)
    except Exception as e:
        logger.info('forensics: cannot open image: %s', e)
    out['xmp'] = xmp_summary(data)
    out['c2pa'] = c2pa_summary(data)
    if with_ai:
        out['ai_detection'] = ai_detection(data)

    # Human-readable hints the agent and the narrative can use
    credit = out['iptc'].get('credit') or out['xmp'].get('credit')
    creator = out['iptc'].get('creator') or out['xmp'].get('creator') or out['exif'].get('artist')
    software_all = [v for v in (out['exif'].get('software'), out['xmp'].get('creator_tool'),
                                out['xmp'].get('history_software')) if v]
    software = ' / '.join(dict.fromkeys(software_all)) or None
    if credit:
        out['hints'].append(f'credit line in file: {credit}')
    if creator:
        out['hints'].append(f'creator in file: {creator}')
    if out['exif'].get('make') or out['exif'].get('model'):
        out['hints'].append(f"camera: {out['exif'].get('make', '')} {out['exif'].get('model', '')}".strip())
    if software:
        out['hints'].append(f'software: {software}')
        if any(h.lower() in software.lower() for h in AI_SOFTWARE_HINTS):
            out['hints'].append('software field names an AI image generator')
    if out['c2pa'].get('present'):
        out['hints'].append('C2PA content credentials present'
                            + (f" ({out['c2pa'].get('claim_generator')})" if out['c2pa'].get('claim_generator') else ''))
    if out['xmp'].get('digital_source_type') or out['c2pa'].get('digital_source_type'):
        out['hints'].append('declared as algorithmically generated media')
    ai = out['ai_detection']
    if ai and ai.get('verdict') == 'ai' and ai.get('ai_confidence', 0) >= 0.7:
        out['hints'].append(f"AI-generated per detector ({int(ai['ai_confidence'] * 100)}%)"
                            + (f", generator guess {ai['generator']}" if ai.get('generator') else ''))
    out['likely_ai'] = bool(
        (ai and ai.get('verdict') == 'ai' and ai.get('ai_confidence', 0) >= 0.7)
        or out['xmp'].get('digital_source_type') or out['c2pa'].get('digital_source_type')
        or (software and any(h.lower() in software.lower() for h in AI_SOFTWARE_HINTS)))
    return out
