import { useMemo, useState } from 'react';
import { Calendar, Award, ChevronDown, MapPin, Clock, Globe, LayoutGrid } from 'lucide-react';
import GlassCard from './GlassCard';
import ErrorBanner from './ErrorBanner';

/* Shared rendering of an Origin Engine report — used by the image search
   page and the video page ("فحص الفيديو"). Cards show only the date, the
   platform and a thumbnail of the matched image. */

export const ENGINE_LABELS = {
    lens_exact_en: 'Lens (EN)', lens_exact_ar: 'Lens (AR)', lens_visual: 'Lens مشابه',
    vision: 'Google Vision', tineye: 'TinEye', tineye_web: 'TinEye (موقع)', yandex: 'Yandex',
    bing: 'Bing', bing_web: 'Bing (موقع)', lens_pivot: 'Lens (الأصل)', text_pivot: 'بحث نصي',
    grok: 'Grok', youtube: 'YouTube', prescreen: 'فرز المصغّرات', google_reverse: 'Google صفحات مطابقة',
    screenshot_crop: 'اقتصاص لقطة الشاشة', text1: 'بحث نصي', text2: 'بحث نصي', text3: 'بحث X',
};

export const TOOL_LABELS = {
    reverse_search: 'بحث عكسي', inspect_pages: 'فحص صفحات', web_search: 'بحث نصي',
    read_page: 'قراءة صفحة', grok_search: 'سؤال Grok', youtube_search: 'بحث يوتيوب', finish: 'الخلاصة',
};

const EVIDENCE_LABELS = {
    'platform:twitter_snowflake': 'معرّف التغريدة', 'platform:instagram_shortcode': 'معرّف المنشور',
    'platform:tiktok_id': 'معرّف الفيديو', 'platform:facebook_creation_time': 'وقت إنشاء المنشور',
    'platform:telegram_time': 'وقت الرسالة', 'meta:article:published_time': 'وسم النشر',
    'jsonld:datePublished': 'بيانات منظمة', 'jsonld:uploadDate': 'بيانات منظمة',
    'htmldate:original': 'تاريخ الصفحة', 'url:path_date': 'مسار الرابط',
    'wayback:first_capture': 'أرشيف الإنترنت', 'tineye:crawl_date': 'زحف TinEye',
    'http:last-modified': 'ترويسة الملف', 'text:pattern_match': 'نص الصفحة',
    'image:upload_path_date': 'تاريخ رفع الصورة',
};

export const evidenceLabel = (src) => EVIDENCE_LABELS[(src || '').split('?')[0]] || (src || '').split(':')[0];

const PLATFORMS = [
    ['x.com', 'X'], ['twitter.com', 'X'], ['facebook.com', 'Facebook'], ['instagram.com', 'Instagram'],
    ['youtube.com', 'YouTube'], ['youtu.be', 'YouTube'], ['tiktok.com', 'TikTok'], ['t.me', 'Telegram'],
    ['telegram.me', 'Telegram'], ['reddit.com', 'Reddit'], ['threads.net', 'Threads'], ['threads.com', 'Threads'],
    ['vk.com', 'VK'], ['linkedin.com', 'LinkedIn'], ['pinterest.', 'Pinterest'], ['snapchat.com', 'Snapchat'],
];
export const platformOf = (url) => {
    try {
        const h = new URL(url).hostname.replace(/^(www|m|mobile)\./, '');
        for (const [d, n] of PLATFORMS) if (h === d || h.endsWith('.' + d) || h.startsWith(d)) return n;
        return h;
    } catch { return ''; }
};
const thumbOf = (item) => item?.visual?.matched_image_url || item?.thumbnail || null;

const FILTER_PLATFORMS = ['X', 'TikTok', 'Instagram', 'Facebook', 'Telegram', 'Reddit', 'YouTube'];
export const platformCategory = (url) => {
    const name = platformOf(url);
    return FILTER_PLATFORMS.includes(name) ? name : 'ويب';
};

const fmtDateTime = (iso) => {
    if (!iso) return null;
    const d = iso.slice(0, 10);
    const t = iso.length >= 16 && !iso.startsWith(d + 'T00:00:00') ? iso.slice(11, 16) + ' UTC' : null;
    return { d, t };
};

export const Thumb = ({ item, size = 'w-14 h-14' }) => {
    const src = thumbOf(item);
    if (!src) return <div className={`${size} rounded-lg bg-slate-100 border border-slate-200 shrink-0`} />;
    return (
        <img src={src} alt="" loading="lazy" referrerPolicy="no-referrer"
            className={`${size} rounded-lg object-cover border border-slate-200 bg-slate-50 shrink-0`}
            onError={(e) => { e.currentTarget.style.visibility = 'hidden'; }} />
    );
};

export const DatePill = ({ item, strong = false }) => {
    const d = (item?.published_at || '').slice(0, 10);
    if (!d) return <span className="text-[10px] font-bold px-2 py-0.5 rounded-md bg-slate-100 text-slate-500">بدون تاريخ</span>;
    const prefix = item.is_upper_bound ? 'على الأقل منذ ' : item.is_lower_bound ? 'ليس قبل ' : '';
    return (
        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-md ${strong ? 'bg-slate-800 text-white' : 'bg-slate-100 text-slate-700'}`}>
            {prefix}<span dir="ltr">{d}</span>
        </span>
    );
};

export const ProbablePill = ({ item }) => (
    item?.probable ? <span className="text-[10px] font-bold px-2 py-0.5 rounded-md bg-slate-100 text-slate-600" title="فيديو: عدة ظهورات لنفس المشهد خلال أيام — مطابقة محتملة وليست مؤكدة">مطابقة محتملة</span> : null
);

/** Visual-verification state of a sighting: silent when confirmed; a quiet
 *  marker when the page's image could not be tied to the query. */
export const VerdictPill = ({ item }) => {
    const v = item?.visual?.verdict;
    if (!v || v === 'confirmed' || v === 'probable') return null;
    const label = v === 'ambiguous' ? 'غير مؤكد بصرياً' : v === 'rejected' ? 'صورة مختلفة' : 'لم يُتحقق بصرياً';
    const title = v === 'ambiguous'
        ? `تشابه ${item.visual.similarity != null ? Math.round(item.visual.similarity * 100) + '%' : 'جزئي'} — لم تثبت المطابقة الهندسية`
        : 'تعذّر مقارنة صورة الصفحة بالصورة المرفوعة';
    return <span className="text-[10px] font-bold px-2 py-0.5 rounded-md bg-white border border-dashed border-slate-300 text-slate-500" title={title}>{label}</span>;
};

/** Variant marker: the page holds a re-framed / restored / recoloured copy
 *  confirmed by keypoint geometry rather than a hash-identical file. */
export const VariantPill = ({ item }) => (
    item?.visual?.match_kind === 'variant' && item?.visual?.geometry?.same_scene
        ? <span className="text-[10px] font-bold px-2 py-0.5 rounded-md bg-slate-50 border border-slate-200 text-slate-500" title={`نسخة معدّلة من الصورة نفسها (تطابق هندسي: ${item.visual.geometry.inliers} نقطة)`}>نسخة معدّلة</span>
        : null
);

const FETCH_FAILED_LABEL = 'لم يستطع Google قراءة الصورة من مضيفها — نتائج Lens ناقصة';
export const fetchFailedEngines = (engines) => Object.entries(engines || {})
    .filter(([, st]) => st && (st.note === 'fetch_failed' || st.status === 'refused')).map(([name]) => name);

/** Evidence pills (v2): how the image was seen and how the date is known. */
const IMAGE_LEVEL = { platform: 'الصورة من المنصة نفسها', page: 'الصورة على الصفحة', engine_claim: 'مطابقة محرك فقط', none: 'لم تُرَ الصورة' };
const DATE_LEVEL = { platform_id: 'توقيت المنشور', structured: 'تاريخ النشر المعلن', weak: 'تاريخ تقريبي', none: 'بدون تاريخ' };
export const EvidencePills = ({ item }) => {
    if (!item || !item.image_level) return null;
    const strong = (item.image_level === 'platform' || item.image_level === 'page');
    return (
        <>
            <span className={`text-[10px] font-bold px-2 py-0.5 rounded-md ${strong ? 'bg-slate-100 text-slate-700' : 'bg-white border border-dashed border-slate-300 text-slate-500'}`}>
                {IMAGE_LEVEL[item.image_level] || item.image_level}
            </span>
            {item.date_level && item.date_level !== 'none' && (
                <span className="text-[10px] font-bold px-2 py-0.5 rounded-md bg-white border border-slate-200 text-slate-500">
                    {DATE_LEVEL[item.date_level] || item.date_level}
                </span>
            )}
        </>
    );
};

export const PlatformPill = ({ url }) => {
    const name = platformOf(url);
    if (!name) return null;
    return <span className="text-[10px] font-bold px-2 py-0.5 rounded-md bg-white border border-slate-200 text-slate-600" dir="ltr">{name}</span>;
};

/** Normalize a /api/direct-search payload into the report shape the cards use. */
export const parseOriginPayload = (payload) => (
    payload && payload.engine === 'origin_engine' ? {
        firstSeen: payload.first_seen || null,
        firstSeenExact: payload.first_seen_exact || null,
        versionNote: payload.version_note || null,
        identity: payload.identity || null,
        priorSightings: payload.prior_sightings || [],
        leads: payload.leads || [],
        similar: payload.similar || [],
        copies: payload.copies || [],
        budget: payload.budget || null,
        version: payload.version || 1,
        narrative: payload.narrative || null,
        engines: payload.engines || {},
        stats: payload.stats || {},
        rounds: payload.rounds || [],
        note: payload.note || null,
        agent: payload.agent || null,
        earlierHints: payload.earlier_hints || [],
        scenes: payload.scenes || [],
        videoSummary: payload.video_summary || null,
        forensics: payload.forensics || null,
        internalSightings: payload.internal_sightings || [],
    } : null
);

const ForensicsLine = ({ forensics }) => {
    if (!forensics) return null;
    const bits = [];
    const ex = forensics.exif || {}, ip = forensics.iptc || {}, xm = forensics.xmp || {};
    const credit = ip.credit || xm.credit; const creator = ip.creator || xm.creator || ex.artist;
    const software = ex.software || xm.creator_tool || xm.history_software;
    if (credit) bits.push(`الجهة: ${credit}`);
    if (creator) bits.push(`المصوّر: ${creator}`);
    if (ex.make || ex.model) bits.push(`الكاميرا: ${[ex.make, ex.model].filter(Boolean).join(' ')}`);
    if (software) bits.push(`البرنامج: ${software}`);
    if (ex.datetime_original) bits.push(`التقاط: ${ex.datetime_original}`);
    if (ex.gps) bits.push(`إحداثيات: ${ex.gps.lat}, ${ex.gps.lon}`);
    if (forensics.c2pa?.present) bits.push(`اعتماد محتوى C2PA${forensics.c2pa.claim_generator ? ` (${forensics.c2pa.claim_generator})` : ''}`);
    const ai = forensics.ai_detection;
    return (
        <div className="mt-3 space-y-1.5">
            {forensics.likely_ai && (
                <div className="p-2.5 bg-slate-800 text-white rounded-xl text-xs font-bold">
                    على الأرجح صورة مولّدة بالذكاء الاصطناعي{ai?.ai_confidence ? ` (${Math.round(ai.ai_confidence * 100)}%)` : ''}{ai?.generator ? ` — ${ai.generator}` : ''}
                    <span className="font-normal text-slate-300"> · لا يوجد حدث حقيقي لتتبعه، وأول ناشر هو منشئها</span>
                </div>
            )}
            {!forensics.likely_ai && ai && ai.verdict && (
                <p className="text-[10px] text-slate-400">كشف الذكاء الاصطناعي: {ai.verdict === 'human' ? 'حقيقية على الأرجح' : 'غير محسوم'}{typeof ai.ai_confidence === 'number' ? ` (احتمال التوليد ${Math.round(ai.ai_confidence * 100)}%)` : ''}</p>
            )}
            {bits.length > 0 && <p className="text-[10px] text-slate-500">بيانات الملف: {bits.join(' · ')}</p>}
        </div>
    );
};

const SavedBanner = ({ cached, onRerun, what }) => (
    cached ? (
        <div className="flex items-center justify-between gap-3 p-2.5 mb-4 bg-slate-50 border border-slate-200 rounded-xl">
            <span className="text-xs font-bold text-slate-600">نتيجة محفوظة من فحص سابق لنفس {what} — ظهرت فوراً دون بحث جديد</span>
            {onRerun && (
                <button onClick={onRerun}
                    className="text-xs font-bold px-3 py-1 rounded-lg bg-slate-800 text-white hover:bg-slate-700 transition-colors whitespace-nowrap">
                    إعادة الفحص
                </button>
            )}
        </div>
    ) : null
);

const FactTile = ({ icon: Icon, label, value, dir }) => (
    <div className="flex items-center gap-2.5 p-2.5 rounded-xl bg-white border border-slate-200 min-w-0">
        <div className="w-8 h-8 rounded-lg bg-slate-50 border border-slate-100 flex items-center justify-center shrink-0">
            <Icon className="w-4 h-4 text-slate-600" />
        </div>
        <div className="min-w-0">
            <p className="text-[10px] text-slate-400 leading-none mb-1">{label}</p>
            <p className="text-xs font-bold text-slate-800 truncate" dir={dir || 'auto'}>{value || '—'}</p>
        </div>
    </div>
);

/* Three quiet facts (when, where, which platform) and one toggle that
   reveals the full narrative, the video description and the frames. */
const KeyFacts = ({ report, videoMode, frames }) => {
    const [open, setOpen] = useState(false);
    const fs = report.firstSeen;
    const ctx = report.agent?.image_context || {};
    const idn = report.identity || {};
    const when = fmtDateTime(fs?.published_at);
    const place = idn.place_ar || idn.place || ctx.place_guess_ar || ctx.place_guess || null;
    const event = idn.event_ar || idn.event || null;
    const platform = fs ? platformOf(fs.url) : null;
    const hasMore = Boolean(report.narrative || report.videoSummary || (frames && frames.length) || (report.copies && report.copies.length) || idn.description);
    if (!fs && !hasMore && !event) return null;
    return (
        <div className="mt-4">
            {fs && (
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                    <FactTile icon={Clock} label="التاريخ"
                        value={when ? `${when.d}${when.t ? ` · ${when.t}` : ''}` : null} dir="ltr" />
                    <FactTile icon={MapPin} label="المكان" value={place} />
                    <FactTile icon={Globe} label="المنصة" value={platform} dir="ltr" />
                </div>
            )}
            {event && (
                <p className="text-[11px] text-slate-500 mt-2">
                    <span className="font-bold text-slate-600">ما تُظهره الصورة (استنتاج): </span>{event}
                    {idn.people && idn.people.length > 0 && <> · {idn.people.slice(0, 3).join('، ')}</>}
                </p>
            )}
            {hasMore && (
                <div className="mt-2">
                    <button type="button" onClick={() => setOpen((v) => !v)}
                        className="w-full flex items-center justify-between px-3 py-2 rounded-xl border border-slate-200 bg-white text-xs font-bold text-slate-600 hover:border-slate-300 hover:text-slate-900 transition-all">
                        <span>{open ? 'إخفاء التفاصيل' : 'عرض التفاصيل'}</span>
                        <ChevronDown className={`w-4 h-4 transition-transform ${open ? 'rotate-180' : ''}`} />
                    </button>
                    {open && (
                        <div className="mt-2 p-3 rounded-xl bg-slate-50 border border-slate-100 space-y-3 animate-fade-in">
                            {videoMode && report.videoSummary && (
                                <div>
                                    <p className="text-[10px] font-bold text-slate-500 mb-1">ما يظهر في الفيديو</p>
                                    <p className="text-sm text-slate-700 leading-relaxed">{report.videoSummary}</p>
                                </div>
                            )}
                            {report.narrative && (
                                <div>
                                    <p className="text-[10px] font-bold text-slate-500 mb-1">ملخص التحقيق</p>
                                    <p className="text-sm text-slate-700 leading-relaxed whitespace-pre-line">{report.narrative}</p>
                                </div>
                            )}
                            {frames && frames.length > 0 && (
                                <div className="flex items-center gap-1.5 flex-wrap">
                                    <span className="text-[10px] text-slate-400">الإطارات المستخدمة في البحث:</span>
                                    {frames.map((src, i) => (
                                        <img key={i} src={src} alt="" className="w-10 h-8 object-cover rounded-md border border-slate-200" />
                                    ))}
                                </div>
                            )}
                            {idn.description && (
                                <div>
                                    <p className="text-[10px] font-bold text-slate-500 mb-1">وصف الصورة</p>
                                    <p className="text-sm text-slate-700 leading-relaxed" dir="auto">{idn.description}</p>
                                </div>
                            )}
                            {report.copies && report.copies.length > 0 && (
                                <div className="flex items-center gap-1.5 flex-wrap">
                                    <span className="text-[10px] text-slate-400">النسخ التي بحثنا بها ({report.copies.length}):</span>
                                    {report.copies.slice(0, 8).map((c) => (
                                        <a key={c.id} href={c.found_on || c.url} target="_blank" rel="noopener noreferrer" title={`${c.source} · ${c.size ? c.size.join('×') : ''}`}>
                                            <img src={c.url} alt="" loading="lazy" referrerPolicy="no-referrer" className="w-10 h-8 object-cover rounded-md border border-slate-200 bg-slate-50" onError={(e) => { e.currentTarget.style.visibility = 'hidden'; }} />
                                        </a>
                                    ))}
                                </div>
                            )}
                            {report.budget && (
                                <p className="text-[10px] text-slate-400" dir="ltr">
                                    {report.budget.seconds}s · {report.budget.credits} credits · {report.budget.pages} pages
                                    {report.budget.skipped && report.budget.skipped.length > 0 && ` · skipped: ${report.budget.skipped.map((s) => s.step).join(', ')}`}
                                </p>
                            )}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
};

export const FirstSeenCard = ({ report, cached = false, onRerun, videoMode = false, frames = [] }) => {
    if (!report || !(report.firstSeen || report.narrative || report.videoSummary)) return null;
    const what = videoMode ? 'الفيديو' : 'الصورة';
    void frames;
    return (
        <GlassCard className="ai-result-card p-6 border-slate-200 shadow-sm mb-6 animate-fade-in-up">
            <div className="absolute top-0 left-0 right-0 h-1 rounded-t-2xl bg-gradient-to-r from-slate-800 via-slate-600 to-slate-800" />
            <div className="flex items-center gap-3 mb-4 pb-3 border-b border-slate-100">
                <div className="w-10 h-10 rounded-xl bg-slate-50 border border-slate-200 flex items-center justify-center">
                    <Award className="w-5 h-5 text-slate-700" />
                </div>
                <div>
                    <h2 className="font-bold text-slate-800">{videoMode ? 'أول ظهور مؤكد للفيديو' : 'أول ظهور مؤكد للصورة'}</h2>
                    {report.stats?.checked > 0 && (
                        <p className="text-[11px] text-slate-400">
                            {report.stats.candidates ? `${report.stats.candidates} نتيجة من المحركات · ` : ''}فُحصت {report.stats.checked} صفحة · مؤكدة بصرياً {report.stats.visually_confirmed || 0}
                            {videoMode && report.stats.frames > 1 && ` · ${report.stats.frames} إطارات`}
                        </p>
                    )}
                </div>
            </div>

            <SavedBanner cached={cached} onRerun={onRerun} what={what} />

            {report.firstSeen ? (
                <div className="flex gap-4 mt-3">
                    <Thumb item={report.firstSeen} size="w-28 h-28 md:w-36 md:h-28" />
                    <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap mb-2">
                            <DatePill item={report.firstSeen} strong />
                            <PlatformPill url={report.firstSeen.url} />
                            <ProbablePill item={report.firstSeen} />
                        </div>
                        <h3 className="font-bold text-slate-800 text-sm mb-1 line-clamp-2" dir="auto">{report.firstSeen.title_ar || report.firstSeen.title}</h3>
                        <a href={report.firstSeen.url} target="_blank" rel="noopener noreferrer" className="text-[11px] text-slate-500 hover:text-slate-900 break-all line-clamp-1" dir="ltr">
                            {report.firstSeen.url}
                        </a>
                        {report.firstSeen.evidence?.length > 0 && (
                            <p className="text-[10px] text-slate-400 mt-2">
                                الدليل: {report.firstSeen.evidence.slice(0, 3).map(e => evidenceLabel(e.source)).join(' · ')}
                                {report.firstSeen.captured_at && <> · التقاط (EXIF) <span dir="ltr">{report.firstSeen.captured_at.slice(0, 10)}</span></>}
                            </p>
                        )}
                        {report.firstSeen.archived?.url && (
                            <a href={report.firstSeen.archived.url} target="_blank" rel="noopener noreferrer"
                                className="inline-block text-[10px] text-slate-500 hover:text-slate-900 mt-1 underline underline-offset-2">
                                {report.firstSeen.archived.status === 'failed' ? 'البحث في الأرشيف' : 'نسخة محفوظة في أرشيف الإنترنت'}
                            </a>
                        )}
                    </div>
                </div>
            ) : (
                <p className="text-sm text-slate-500">لم يُعثر على ظهور مؤرَّخ ومؤكد بصرياً — راجع الجدول الزمني أدناه.</p>
            )}

            {report.versionNote && (
                <p className="text-[11px] text-slate-500 mt-3 leading-relaxed">{report.versionNote}</p>
            )}
            {report.priorSightings && report.priorSightings.length > 0 && (
                <p className="text-[11px] text-slate-500 mt-2">
                    بُحث عن هذه الصورة من قبل في هذه المنصة —
                    {' '}<a href={report.priorSightings[0].ref_url} target="_blank" rel="noopener noreferrer" className="underline underline-offset-2 hover:text-slate-900" dir="ltr">{report.priorSightings[0].ref_url}</a>
                </p>
            )}
            {report.firstSeenExact && (
                <a href={report.firstSeenExact.url} target="_blank" rel="noopener noreferrer"
                    className="flex items-center gap-3 p-2.5 mt-2 rounded-xl border border-slate-200 bg-white hover:border-slate-300 transition-all">
                    <Thumb item={report.firstSeenExact} size="w-12 h-12" />
                    <div className="min-w-0">
                        <p className="text-[10px] text-slate-400">أول ظهور لهذه النسخة بالذات</p>
                        <div className="flex items-center gap-1.5 flex-wrap mt-0.5">
                            <DatePill item={report.firstSeenExact} />
                            <PlatformPill url={report.firstSeenExact.url} />
                        </div>
                    </div>
                </a>
            )}
            {fetchFailedEngines(report.engines).length > 0 && (
                <p className="text-[11px] text-slate-500 mt-3">{FETCH_FAILED_LABEL}</p>
            )}

            {report.scenes?.length > 1 && (
                <div className="mt-3 grid sm:grid-cols-2 gap-2">
                    {report.scenes.map((sc) => (
                        <a key={sc.frame} href={sc.first_seen.url} target="_blank" rel="noopener noreferrer"
                            className="flex items-center gap-3 p-2.5 rounded-xl border border-slate-200 bg-white hover:border-slate-300 transition-all">
                            <Thumb item={sc.first_seen} size="w-12 h-12" />
                            <div className="min-w-0">
                                <p className="text-[10px] text-slate-400">مشهد {sc.frame} — أول ظهور</p>
                                <div className="flex items-center gap-1.5 flex-wrap mt-0.5">
                                    <DatePill item={sc.first_seen} />
                                    <PlatformPill url={sc.first_seen.url} />
                                    <ProbablePill item={sc.first_seen} />
                                </div>
                            </div>
                        </a>
                    ))}
                </div>
            )}

            <KeyFacts report={report} videoMode={videoMode} frames={frames} />

            {Object.keys(report.engines || {}).length > 0 && (
                <p className="text-[10px] text-slate-400 mt-4" dir="ltr">
                    {Object.entries(report.engines)
                        .filter(([name, st]) => (st.ok || st.status === 'results') && st.count > 0 && ENGINE_LABELS[name.replace(/@.*$/, '')])
                        .map(([name, st]) => `${ENGINE_LABELS[name.replace(/@.*$/, '')] || name} ${st.count}`)
                        .join(' · ')}
                    {Object.entries(report.engines).some(([, st]) => st.status === 'refused') && ' · محركات لم تقبل الصورة: '
                        + Object.entries(report.engines).filter(([, st]) => st.status === 'refused').map(([name]) => ENGINE_LABELS[name.replace(/@.*$/, '')] || name).join(', ')}
                </p>
            )}

            {report.agent && (
                <details className="mt-3 group">
                    <summary className="cursor-pointer text-xs font-bold text-slate-600 select-none">
                        خطوات التحقيق ({(report.agent.steps || []).length})
                        {report.agent.pick && (
                            <span className="mr-2 text-[10px] px-2 py-0.5 rounded-md bg-slate-100 text-slate-600">
                                {report.agent.pick_matches_first_seen ? 'استنتاج الوكيل يطابق الأدلة' : 'استنتاج الوكيل يختلف عن الأدلة'}
                            </span>
                        )}
                    </summary>
                    {report.agent.image_context?.description && (
                        <p className="text-[11px] text-slate-500 mt-2 leading-relaxed">
                            <span className="font-bold text-slate-600">ما تراه الرؤية الآلية: </span>
                            {report.agent.image_context.description}
                        </p>
                    )}
                    <ol className="mt-2 space-y-1">
                        {(report.agent.steps || []).map((s) => (
                            <li key={s.n} className="flex items-start gap-2 text-[11px] text-slate-600">
                                <span className="w-5 h-5 rounded-full bg-slate-100 text-slate-500 flex items-center justify-center text-[10px] font-bold shrink-0">{s.n}</span>
                                <span><span className="font-bold text-slate-700">{TOOL_LABELS[s.tool] || s.tool}</span> — {s.summary} <span className="text-slate-400">({s.elapsed_s}s)</span></span>
                            </li>
                        ))}
                    </ol>
                    {report.agent.finish?.reasoning && (
                        <p className="text-[11px] text-slate-600 mt-2 p-2 bg-white rounded-lg border border-slate-100" dir="auto">
                            {report.agent.finish.reasoning}
                        </p>
                    )}
                </details>
            )}
        </GlassCard>
    );
};

/** Everything the engines returned that the automatic check did not confirm.
 *  The reader judges by eye: picture, date and platform only. */
const SIMILAR_PAGE = 24;
export const SimilarCard = ({ items, style }) => {
    const [filter, setFilter] = useState('الكل');
    const [shownCount, setShownCount] = useState(SIMILAR_PAGE);
    const counts = useMemo(() => {
        const c = {};
        (items || []).forEach((it) => { const k = platformCategory(it.link); c[k] = (c[k] || 0) + 1; });
        return c;
    }, [items]);
    if (!items || items.length === 0) return null;
    const chips = ['الكل', ...FILTER_PLATFORMS, 'ويب'].filter((k) => k === 'الكل' || counts[k]);
    const filtered = items.filter((it) => filter === 'الكل' || platformCategory(it.link) === filter);
    const shown = filtered.slice(0, shownCount);
    return (
        <GlassCard className="ai-result-card p-6 border-slate-200 shadow-sm mt-6 animate-fade-in-up" style={style}>
            <div className="absolute top-0 left-0 right-0 h-1 rounded-t-2xl bg-gradient-to-r from-slate-400 via-slate-300 to-slate-400" />
            <div className="flex items-center gap-3 mb-4 pb-3 border-b border-slate-100">
                <div className="w-10 h-10 rounded-xl bg-slate-50 border border-slate-200 flex items-center justify-center">
                    <LayoutGrid className="w-5 h-5 text-slate-700" />
                </div>
                <div>
                    <h2 className="font-bold text-slate-800">صور مشابهة من المحركات <span className="text-slate-400 text-sm">({items.length})</span></h2>
                    <p className="text-[11px] text-slate-400 mt-0.5">لم يؤكدها الفحص الآلي — الحكم لك</p>
                </div>
            </div>

            {chips.length > 2 && (
                <div className="flex items-center gap-1.5 flex-wrap mb-3">
                    {chips.map((k) => (
                        <button key={k} type="button" onClick={() => { setFilter(k); setShownCount(SIMILAR_PAGE); }}
                            className={`text-[11px] font-bold px-2.5 py-1 rounded-lg border transition-all ${filter === k
                                ? 'bg-slate-800 text-white border-slate-800'
                                : 'bg-white text-slate-600 border-slate-200 hover:border-slate-300'}`}
                            dir={k === 'الكل' || k === 'ويب' ? 'rtl' : 'ltr'}>
                            {k}<span className={`mr-1 text-[10px] ${filter === k ? 'text-slate-300' : 'text-slate-400'}`}>{k === 'الكل' ? items.length : counts[k]}</span>
                        </button>
                    ))}
                </div>
            )}

            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">
                {shown.map((item) => (
                    <a key={item.link} href={item.link} target="_blank" rel="noopener noreferrer"
                        className="group block rounded-xl border border-slate-200 bg-white overflow-hidden hover:border-slate-400 hover:shadow-sm transition-all">
                        <div className="aspect-square bg-slate-100">
                            <img src={item.thumbnail} alt="" loading="lazy" referrerPolicy="no-referrer"
                                className="w-full h-full object-cover"
                                onError={(e) => {
                                    const img = e.currentTarget;
                                    if (item.image_url && img.src !== item.image_url) img.src = item.image_url;
                                    else img.style.visibility = 'hidden';
                                }} />
                        </div>
                        <div className="p-2 flex items-center gap-1 flex-wrap">
                            {item.published_at && <DatePill item={item} />}
                            <PlatformPill url={item.link} />
                        </div>
                    </a>
                ))}
            </div>

            {filtered.length > shownCount && (
                <button type="button" onClick={() => setShownCount((n) => n + SIMILAR_PAGE)}
                    className="mt-4 w-full text-xs font-bold px-3 py-2 rounded-xl bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 transition-colors">
                    عرض المزيد ({filtered.length - shownCount})
                </button>
            )}
        </GlassCard>
    );
};

export const TimelineCard = ({ report, timeline, cached = false, onRerun, error, engineNote, style }) => {
    const [filter, setFilter] = useState('الكل');
    const counts = useMemo(() => {
        const c = {};
        (timeline || []).forEach((it) => { const k = platformCategory(it.link); c[k] = (c[k] || 0) + 1; });
        return c;
    }, [timeline]);
    const chips = ['الكل', ...FILTER_PLATFORMS, 'ويب'].filter((k) => k === 'الكل' || counts[k]);
    const shown = (timeline || []).filter((it) => filter === 'الكل' || platformCategory(it.link) === filter);
    return (
    <GlassCard className="ai-result-card p-6 border-slate-200 shadow-sm" style={style}>
        <div className="absolute top-0 left-0 right-0 h-1 rounded-t-2xl bg-gradient-to-r from-slate-600 via-slate-400 to-slate-600" />
        <div className="flex items-center gap-3 mb-5 pb-3 border-b border-slate-100">
            <div className="w-10 h-10 rounded-xl bg-slate-50 border border-slate-200 flex items-center justify-center">
                <Calendar className="w-5 h-5 text-slate-700" />
            </div>
            <h2 className="font-bold text-slate-800">{report ? 'من نشرها ومن أعاد نشرها' : 'الجدول الزمني'}</h2>
        </div>

        <ErrorBanner message={error} className="mb-4" />

        {cached && !report && (
            <div className="flex items-center justify-between p-2.5 mb-4 bg-slate-50 border border-slate-200 rounded-xl">
                <span className="text-xs font-bold text-slate-600">نتيجة محفوظة من فحص سابق</span>
                {onRerun && (
                    <button onClick={onRerun}
                        className="text-xs font-bold px-3 py-1 rounded-lg bg-white border border-slate-200 text-slate-700 hover:bg-slate-100 transition-colors">
                        إعادة الفحص
                    </button>
                )}
            </div>
        )}

        {engineNote && (
            <div className="p-2.5 mb-4 bg-slate-50 border border-slate-200 rounded-xl">
                <span className="text-xs font-bold text-slate-600">{engineNote}</span>
            </div>
        )}

        {timeline && timeline.length > 1 && chips.length > 2 && (
            <div className="flex items-center gap-1.5 flex-wrap mb-3">
                {chips.map((k) => (
                    <button key={k} type="button" onClick={() => setFilter(k)}
                        className={`text-[11px] font-bold px-2.5 py-1 rounded-lg border transition-all ${filter === k
                            ? 'bg-slate-800 text-white border-slate-800'
                            : 'bg-white text-slate-600 border-slate-200 hover:border-slate-300'}`}
                        dir={k === 'الكل' || k === 'ويب' ? 'rtl' : 'ltr'}>
                        {k}<span className={`mr-1 text-[10px] ${filter === k ? 'text-slate-300' : 'text-slate-400'}`}>{k === 'الكل' ? (timeline || []).length : counts[k]}</span>
                    </button>
                ))}
            </div>
        )}

        {timeline && timeline.length > 0 ? (
            <div className="space-y-2 max-h-[480px] overflow-y-auto pr-1">
                {shown.map((item, idx) => {
                    const isFirst = report?.firstSeen && item.link === report.firstSeen.url;
                    return (
                        <a key={idx} href={item.link} target="_blank" rel="noopener noreferrer"
                            className={`flex items-center gap-3 p-2.5 rounded-xl border bg-white hover:border-slate-300 hover:shadow-sm transition-all ${isFirst ? 'border-slate-800' : 'border-slate-200'}`}>
                            <Thumb item={item} />
                            <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-1.5 flex-wrap">
                                    {isFirst && <span className="text-[10px] font-bold px-2 py-0.5 rounded-md bg-slate-800 text-white">الأول</span>}
                                    <DatePill item={item} strong={isFirst} />
                                    <PlatformPill url={item.link} />
                                    {isFirst && <ProbablePill item={item} />}
                                </div>
                                <p className="font-bold text-xs text-slate-800 mt-1 line-clamp-1" dir="auto">{item.title_ar || item.title}</p>
                                <p className="text-[10px] text-slate-400 break-all line-clamp-1" dir="ltr">{item.link}</p>
                            </div>
                        </a>
                    );
                })}
            </div>
        ) : (
            !error && <div className="text-center text-slate-400 py-6 text-sm">لا يوجد سجل تاريخي.{fetchFailedEngines(report?.engines).length > 0 && <span className="block text-[11px] mt-1">{FETCH_FAILED_LABEL}</span>}</div>
        )}
        {report?.leads && report.leads.length > 0 && (
            <details className="mt-3">
                <summary className="cursor-pointer text-xs font-bold text-slate-500 select-none">
                    نتائج غير مؤكدة ({report.leads.length}) — صفحات أعادتها المحركات ولم تثبت فيها الصورة أو التاريخ
                </summary>
                <div className="mt-2 space-y-1.5">
                    {report.leads.map((item, idx) => (
                        <a key={idx} href={item.link} target="_blank" rel="noopener noreferrer"
                            className="flex items-center gap-2 p-2 rounded-lg border border-dashed border-slate-200 bg-white hover:border-slate-300 transition-all">
                            <Thumb item={item} size="w-9 h-9" />
                            <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-1.5 flex-wrap">
                                    <DatePill item={item} />
                                    <PlatformPill url={item.link} />
                                </div>
                                <p className="text-[10px] text-slate-500 line-clamp-1" dir="auto">{item.title_ar || item.title}</p>
                            </div>
                        </a>
                    ))}
                </div>
            </details>
        )}
    </GlassCard>
    );
};
