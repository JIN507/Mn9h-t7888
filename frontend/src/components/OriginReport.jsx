import { Calendar, Award } from 'lucide-react';
import GlassCard from './GlassCard';
import ErrorBanner from './ErrorBanner';

/* Shared rendering of an Origin Engine report — used by the image search
   page and the video page ("فحص الفيديو"). Cards show only the date, the
   platform and a thumbnail of the matched image. */

export const ENGINE_LABELS = {
    lens_exact_en: 'Lens (EN)', lens_exact_ar: 'Lens (AR)', lens_visual: 'Lens مشابه',
    vision: 'Google Vision', tineye: 'TinEye', tineye_web: 'TinEye (موقع)', yandex: 'Yandex',
    bing: 'Bing', bing_web: 'Bing (موقع)', lens_pivot: 'Lens (الأصل)', text_pivot: 'بحث نصي',
    grok: 'Grok',
};

export const TOOL_LABELS = {
    reverse_search: 'بحث عكسي', inspect_pages: 'فحص صفحات', web_search: 'بحث نصي',
    read_page: 'قراءة صفحة', grok_search: 'سؤال Grok', finish: 'الخلاصة',
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

export const PlatformPill = ({ url }) => {
    const name = platformOf(url);
    if (!name) return null;
    return <span className="text-[10px] font-bold px-2 py-0.5 rounded-md bg-white border border-slate-200 text-slate-600" dir="ltr">{name}</span>;
};

/** Normalize a /api/direct-search payload into the report shape the cards use. */
export const parseOriginPayload = (payload) => (
    payload && payload.engine === 'origin_engine' ? {
        firstSeen: payload.first_seen || null,
        narrative: payload.narrative || null,
        engines: payload.engines || {},
        stats: payload.stats || {},
        rounds: payload.rounds || [],
        note: payload.note || null,
        agent: payload.agent || null,
        earlierHints: payload.earlier_hints || [],
        scenes: payload.scenes || [],
        videoSummary: payload.video_summary || null,
    } : null
);

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

export const FirstSeenCard = ({ report, cached = false, onRerun, videoMode = false, frames = [] }) => {
    if (!report || !(report.firstSeen || report.narrative || report.videoSummary)) return null;
    const what = videoMode ? 'الفيديو' : 'الصورة';
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
                            فُحصت {report.stats.checked} صفحة · مؤكدة بصرياً {report.stats.visually_confirmed || 0}
                            {videoMode && report.stats.frames > 1 && ` · ${report.stats.frames} إطارات`}
                        </p>
                    )}
                </div>
            </div>

            <SavedBanner cached={cached} onRerun={onRerun} what={what} />

            {videoMode && (report.videoSummary || frames.length > 0) && (
                <div className="mb-4 p-3 bg-slate-50 border border-slate-100 rounded-xl">
                    <p className="text-[11px] font-bold text-slate-600 mb-1">ما هو هذا الفيديو؟</p>
                    {report.videoSummary && <p className="text-sm text-slate-700 leading-relaxed">{report.videoSummary}</p>}
                    {frames.length > 0 && (
                        <div className="flex items-center gap-1.5 mt-2 flex-wrap">
                            <span className="text-[10px] text-slate-400">الإطارات المستخدمة في البحث:</span>
                            {frames.map((src, i) => (
                                <img key={i} src={src} alt="" className="w-10 h-8 object-cover rounded-md border border-slate-200" />
                            ))}
                        </div>
                    )}
                </div>
            )}

            {report.firstSeen ? (
                <div className="flex gap-4">
                    <Thumb item={report.firstSeen} size="w-28 h-28 md:w-36 md:h-28" />
                    <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap mb-2">
                            <DatePill item={report.firstSeen} strong />
                            <PlatformPill url={report.firstSeen.url} />
                            <ProbablePill item={report.firstSeen} />
                        </div>
                        <h3 className="font-bold text-slate-800 text-sm mb-1 line-clamp-2" dir="auto">{report.firstSeen.title}</h3>
                        <a href={report.firstSeen.url} target="_blank" rel="noopener noreferrer" className="text-[11px] text-slate-500 hover:text-slate-900 break-all line-clamp-1" dir="ltr">
                            {report.firstSeen.url}
                        </a>
                        {report.firstSeen.evidence?.length > 0 && (
                            <p className="text-[10px] text-slate-400 mt-2">
                                الدليل: {report.firstSeen.evidence.slice(0, 3).map(e => evidenceLabel(e.source)).join(' · ')}
                                {report.firstSeen.captured_at && <> · التقاط (EXIF) <span dir="ltr">{report.firstSeen.captured_at.slice(0, 10)}</span></>}
                            </p>
                        )}
                    </div>
                </div>
            ) : (
                <p className="text-sm text-slate-500">لم يُعثر على ظهور مؤرَّخ ومؤكد بصرياً — راجع الجدول الزمني أدناه.</p>
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

            {report.narrative && (
                <p className="text-sm text-slate-700 leading-relaxed mt-4 p-3 bg-slate-50 rounded-xl border border-slate-100">{report.narrative}</p>
            )}

            {Object.keys(report.engines || {}).length > 0 && (
                <p className="text-[10px] text-slate-400 mt-4" dir="ltr">
                    {Object.entries(report.engines)
                        .filter(([, st]) => st.ok && st.count > 0)
                        .map(([name, st]) => `${ENGINE_LABELS[name.replace(/@.*$/, '')] || name} ${st.count}`)
                        .join(' · ')}
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

export const TimelineCard = ({ report, timeline, cached = false, onRerun, error, engineNote, style }) => (
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

        {timeline && timeline.length > 0 ? (
            <div className="space-y-2 max-h-[480px] overflow-y-auto pr-1">
                {timeline.map((item, idx) => {
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
                                <p className="font-bold text-xs text-slate-800 mt-1 line-clamp-1" dir="auto">{item.title}</p>
                                <p className="text-[10px] text-slate-400 break-all line-clamp-1" dir="ltr">{item.link}</p>
                            </div>
                        </a>
                    );
                })}
            </div>
        ) : (
            !error && <div className="text-center text-slate-400 py-6 text-sm">لا يوجد سجل تاريخي.</div>
        )}
    </GlassCard>
);
