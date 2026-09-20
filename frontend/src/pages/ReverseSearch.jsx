import { useState, useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { Search, RefreshCw, X, Calendar, ExternalLink, Award } from 'lucide-react';
import apiClient from '../services/apiClient';
import GlassCard from '../components/GlassCard';
import ErrorBanner from '../components/ErrorBanner';
import useJob from '../hooks/useJob';
import GradientButton from '../components/GradientButton';
import DropZone from '../components/DropZone';



const ENGINE_LABELS = {
    lens_exact_en: 'Lens (EN)', lens_exact_ar: 'Lens (AR)', lens_visual: 'Lens مشابه',
    vision: 'Google Vision', tineye: 'TinEye', tineye_web: 'TinEye (موقع)', yandex: 'Yandex',
    bing: 'Bing', bing_web: 'Bing (موقع)', lens_pivot: 'Lens (الأصل)', text_pivot: 'بحث نصي',
};

const TOOL_LABELS = {
    reverse_search: 'بحث عكسي', inspect_pages: 'فحص صفحات', web_search: 'بحث نصي',
    read_page: 'قراءة صفحة', finish: 'الخلاصة',
};

const EVIDENCE_LABELS = {
    'platform:twitter_snowflake': 'معرّف التغريدة', 'meta:article:published_time': 'وسم النشر',
    'jsonld:datePublished': 'بيانات منظمة', 'jsonld:uploadDate': 'بيانات منظمة',
    'htmldate:original': 'تاريخ الصفحة', 'url:path_date': 'مسار الرابط',
    'wayback:first_capture': 'أرشيف الإنترنت', 'tineye:crawl_date': 'زحف TinEye',
    'http:last-modified': 'ترويسة الملف', 'text:pattern_match': 'نص الصفحة',
};

const evidenceLabel = (src) => EVIDENCE_LABELS[src] || (src || '').split(':')[0];
const pct = (v) => (typeof v === 'number' ? `${Math.round(v * 100)}%` : null);

const PLATFORMS = [
    ['x.com', 'X'], ['twitter.com', 'X'], ['facebook.com', 'Facebook'], ['instagram.com', 'Instagram'],
    ['youtube.com', 'YouTube'], ['youtu.be', 'YouTube'], ['tiktok.com', 'TikTok'], ['t.me', 'Telegram'],
    ['telegram.me', 'Telegram'], ['reddit.com', 'Reddit'], ['threads.net', 'Threads'], ['vk.com', 'VK'],
    ['linkedin.com', 'LinkedIn'], ['pinterest.', 'Pinterest'], ['snapchat.com', 'Snapchat'],
];
const platformOf = (url) => {
    try {
        const h = new URL(url).hostname.replace(/^(www|m|mobile)\./, '');
        for (const [d, n] of PLATFORMS) if (h === d || h.endsWith('.' + d) || h.startsWith(d)) return n;
        return h;
    } catch { return ''; }
};
const isSocial = (url) => PLATFORMS.some(([d]) => (url || '').includes(d));
const thumbOf = (item) => item?.visual?.matched_image_url || item?.thumbnail || null;

const Thumb = ({ item, size = 'w-14 h-14' }) => {
    const src = thumbOf(item);
    if (!src) return <div className={`${size} rounded-lg bg-slate-100 border border-slate-200 shrink-0`} />;
    return (
        <img src={src} alt="" loading="lazy" referrerPolicy="no-referrer"
            className={`${size} rounded-lg object-cover border border-slate-200 bg-slate-50 shrink-0`}
            onError={(e) => { e.currentTarget.style.visibility = 'hidden'; }} />
    );
};

const DatePill = ({ item, strong = false }) => {
    const d = (item?.published_at || '').slice(0, 10);
    if (!d) return <span className="text-[10px] font-bold px-2 py-0.5 rounded-md bg-slate-100 text-slate-500">بدون تاريخ</span>;
    const prefix = item.is_upper_bound ? 'على الأقل منذ ' : item.is_lower_bound ? 'ليس قبل ' : '';
    return (
        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-md ${strong ? 'bg-slate-800 text-white' : 'bg-slate-100 text-slate-700'}`}>
            {prefix}<span dir="ltr">{d}</span>
        </span>
    );
};

const ProbablePill = ({ item }) => (
    item?.probable ? <span className="text-[10px] font-bold px-2 py-0.5 rounded-md bg-slate-100 text-slate-600" title="فيديو: عدة ظهورات لنفس المشهد خلال أيام — مطابقة محتملة وليست مؤكدة">مطابقة محتملة</span> : null
);

const PlatformPill = ({ url }) => {
    const name = platformOf(url);
    if (!name) return null;
    return <span className="text-[10px] font-bold px-2 py-0.5 rounded-md bg-white border border-slate-200 text-slate-600" dir="ltr">{name}</span>;
};

const ReverseSearch = () => {
    const location = useLocation();
    const [file, setFile] = useState(null);
    const [extraFrames, setExtraFrames] = useState([]);   // video mode: more frames of the clip
    const [loading, setLoading] = useState(false);

    // States for the two tasks
    const [enginesResult, setEnginesResult] = useState(null);
    const [timelineResult, setTimelineResult] = useState(null);
    const [errors, setErrors] = useState({ engines: null, timeline: null });

    // Helper to convert base64 to file
    const dataURLtoFile = (dataurl, filename) => {
        try {
            let arr = dataurl.split(','), mime = arr[0].match(/:(.*?);/)[1],
                bstr = atob(arr[1]), n = bstr.length, u8arr = new Uint8Array(n);
            while (n--) {
                u8arr[n] = bstr.charCodeAt(n);
            }
            return new File([u8arr], filename, { type: mime });
        } catch (e) {
            console.error('Conversion error:', e);
            return null;
        }
    };

    // Handle file / frames passed from navigation
    useEffect(() => {
        if (location.state?.frames?.length) {
            const files = location.state.frames
                .map((d, i) => dataURLtoFile(d, `frame-${i + 1}.jpg`)).filter(Boolean);
            if (files.length) {
                setFile(files[0]);
                setExtraFrames(files.slice(1));
            }
        } else if (location.state?.file) {
            setFile(location.state.file);
            setExtraFrames([]);
        } else if (location.state?.dataUrl) {
            const f = dataURLtoFile(location.state.dataUrl, location.state.fileName || 'image.jpg');
            if (f) { setFile(f); setExtraFrames([]); }
        }
    }, [location.state]);

    // Auto-trigger search when navigated from video frame
    const pendingAutoSearch = useRef(false);
    useEffect(() => {
        if (location.state?.autoSearch) {
            pendingAutoSearch.current = true;
        }
    }, [location.state]);

    useEffect(() => {
        if (file && pendingAutoSearch.current) {
            pendingAutoSearch.current = false;
            // Small delay to ensure state is committed
            setTimeout(() => handleSearch(), 100);
        }
    }, [file]);

    const [timelineCached, setTimelineCached] = useState(false);
    const [timelineEngine, setTimelineEngine] = useState(null);
    const [originReport, setOriginReport] = useState(null);
    const [jobId, setJobId] = useState(null);
    const { progress: jobProgress, result: jobResult, error: jobError } = useJob(jobId);

    const applyTimelinePayload = (payload) => {
        const timelineData = payload.timeline || [];
        setTimelineCached(Boolean(payload.cached));
        setTimelineEngine(payload.engine || null);
        setOriginReport(payload.engine === 'origin_engine' ? {
            firstSeen: payload.first_seen || null,
            narrative: payload.narrative || null,
            engines: payload.engines || {},
            stats: payload.stats || {},
            rounds: payload.rounds || [],
            note: payload.note || null,
            agent: payload.agent || null,
            earlierHints: payload.earlier_hints || [],
            scenes: payload.scenes || [],
        } : null);
        if (timelineData.length > 0) {
            setTimelineResult(timelineData);
        } else {
            setErrors(prev => ({ ...prev, timeline: payload.note || 'لم تتوفر تواريخ سابقة لهذه الصورة' }));
        }
    };

    const handleSearch = async (rerun = false) => {
        if (!file) return;

        setLoading(true);
        setErrors({ engines: null, timeline: null });
        setEnginesResult(null);
        setTimelineResult(null);
        setTimelineCached(false);
        setTimelineEngine(null);
        setOriginReport(null);
        setJobId(null);

        // Prep form data for upload
        const formData = new FormData();
        formData.append('file', file);

        let uploadedImageUrl = null;
        let uploadedHashes = {};

        // Step 1: Upload and get Engine Results (+ SHA-256/pHash)
        try {
            const engineRes = await apiClient.post('/api/upload', formData, {
                headers: { 'Content-Type': 'multipart/form-data' },
                timeout: 60000
            });

            if (engineRes.data?.searchResults) {
                setEnginesResult(engineRes.data);
                uploadedImageUrl = engineRes.data.imageUrl;
                uploadedHashes = {
                    image_hash: engineRes.data.image_hash,
                    image_phash: engineRes.data.image_phash
                };
            } else {
                setErrors(prev => ({ ...prev, engines: 'بيانات محركات البحث غير مكتملة' }));
            }
        } catch (err) {
            console.error('Engine search error:', err);
            setErrors(prev => ({
                ...prev,
                engines: err.response?.data?.error || 'فشل الاتصال بخدمة الرفع ومحركات البحث'
            }));
        }

        if (!uploadedImageUrl) {
            setErrors(prev => ({
                ...prev,
                timeline: 'تم إيقاف البحث الزمني بسبب فشل رفع الصورة'
            }));
            setLoading(false);
            return;
        }

        // Video mode: host the other keyframes too, so the engine can match
        // pages that show a different moment of the clip
        let extraUrls = [];
        if (extraFrames.length) {
            try {
                extraUrls = (await Promise.all(extraFrames.map(async (f) => {
                    const fd = new FormData();
                    fd.append('file', f);
                    const r = await apiClient.post('/api/upload', fd, {
                        headers: { 'Content-Type': 'multipart/form-data' }, timeout: 60000 });
                    return r.data?.imageUrl || null;
                }))).filter(Boolean);
            } catch (err) {
                console.warn('extra frame upload failed', err);
            }
        }

        // Step 2: Timeline search — instant 200 on cache hit, else a
        // background job streamed over SSE (progress shown while it runs)
        try {
            const timelineRes = await apiClient.post('/api/direct-search', {
                image_url: uploadedImageUrl,
                ...(extraUrls.length ? { image_urls: [uploadedImageUrl, ...extraUrls] } : {}),
                ...uploadedHashes,
                rerun
            }, { timeout: 30000 });

            if (timelineRes.status === 202 && timelineRes.data.job_id) {
                setJobId(timelineRes.data.job_id);  // loading continues via SSE
                return;
            }
            if (timelineRes.data?.success) {
                applyTimelinePayload(timelineRes.data);
            } else {
                setErrors(prev => ({ ...prev, timeline: timelineRes.data?.error || 'فشل استخراج الجدول الزمني' }));
            }
        } catch (err) {
            console.error('Timeline search error:', err);
            setErrors(prev => ({
                ...prev,
                timeline: err.response?.data?.error || 'فشل الاتصال بخدمة الجدول الزمني'
            }));
        }
        setLoading(false);
    };

    // Background job resolution
    useEffect(() => {
        if (jobResult) {
            const payload = jobResult.payload || {};
            if (payload.success) {
                applyTimelinePayload(payload);
            } else {
                setErrors(prev => ({ ...prev, timeline: payload.error || 'فشل استخراج الجدول الزمني' }));
            }
            setLoading(false);
            setJobId(null);
        }
    }, [jobResult]);

    useEffect(() => {
        if (jobError) {
            setErrors(prev => ({ ...prev, timeline: jobError }));
            setLoading(false);
            setJobId(null);
        }
    }, [jobError]);

    const handleReset = () => {
        setFile(null);
        setExtraFrames([]);
        setEnginesResult(null);
        setTimelineResult(null);
        setTimelineCached(false);
        setOriginReport(null);
        setErrors({ engines: null, timeline: null });
    };

    const searchEnginesList = [
        { id: 'google', name: 'Google', gradient: 'bg-slate-800' },
        { id: 'bing', name: 'Bing', gradient: 'bg-slate-700' },
        { id: 'yandex', name: 'Yandex', gradient: 'bg-slate-600' },
        { id: 'tineye', name: 'TinEye', gradient: 'bg-slate-900' }
    ];

    const hasAnyResult = enginesResult || timelineResult || errors.engines || errors.timeline;

    return (
        <div className="max-w-4xl mx-auto page-container">
            {/* Header */}
            <div className="text-center mb-8 animate-fade-in-up">
                <h1 className="text-3xl md:text-4xl font-black text-slate-800 mb-4 tracking-tight">
                    البحث عن <span className="gradient-text">مصدر الصورة</span>
                </h1>
                <p className="text-slate-500 max-w-lg mx-auto">
                    ارفع الصورة وسيبحث النظام في عدة محركات، ويتحقق بصرياً من كل نتيجة، ويحدد أول ظهور موثّق لها ومن أعاد نشرها.
                </p>
            </div>

            {/* Upload Section */}
            <div className="animate-fade-in-up delay-100">
                <GlassCard className="p-6 border-slate-200 shadow-sm mb-8">
                    <DropZone
                        onFileSelect={(f) => { setFile(f); setExtraFrames([]); }}
                        headerText="ارفع صورة للبحث الشامل"
                        subText="JPG, PNG, WEBP"
                        initialFile={file}
                    />
                    {extraFrames.length > 0 && (
                        <div className="mt-3 flex items-center gap-2 flex-wrap">
                            <span className="text-[11px] font-bold text-slate-600">وضع الفيديو — إطارات إضافية للمطابقة:</span>
                            {extraFrames.map((f, i) => (
                                <img key={i} src={URL.createObjectURL(f)} alt="" className="w-12 h-9 object-cover rounded-md border border-slate-200" />
                            ))}
                        </div>
                    )}
                    <div className="mt-6 flex gap-3">
                        <button
                            onClick={() => handleSearch()}
                            disabled={!file || loading}
                            className="ai-analyze-btn flex-1"
                        >
                            {loading ? (
                                <span className="flex items-center justify-center gap-2">
                                    <svg className="animate-spin w-5 h-5" viewBox="0 0 24 24" fill="none">
                                        <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" className="opacity-20" />
                                        <path d="M4 12a8 8 0 018-8" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
                                    </svg>
                                    جاري البحث...
                                </span>
                            ) : (
                                <span className="flex items-center justify-center gap-2">
                                    <Search className="w-5 h-5" />
                                    ابحث عن المصدر
                                </span>
                            )}
                        </button>
                        {hasAnyResult && timelineCached && (
                            <button
                                onClick={() => handleSearch(true)}
                                className="px-5 py-3 rounded-2xl bg-white text-slate-800 font-bold hover:bg-slate-100 transition-all border border-slate-300 flex items-center gap-2"
                                title="النتيجة المعروضة محفوظة من فحص سابق — أعد الفحص الآن"
                            >
                                <RefreshCw className="w-5 h-5" />
                                إعادة الفحص
                            </button>
                        )}
                        {hasAnyResult && (
                            <button
                                onClick={handleReset}
                                className="px-5 py-3 rounded-2xl bg-slate-100 text-slate-600 font-bold hover:bg-slate-200 transition-all border border-slate-200"
                                title="مسح والبدء من جديد"
                            >
                                <X className="w-5 h-5" />
                            </button>
                        )}
                    </div>
                </GlassCard>
            </div>

            {/* Loading */}
            {loading && (
                <div className="ai-loading-state animate-fade-in">
                    <div className="ai-loading-rings">
                        <div className="ai-loading-ring ai-loading-ring--1" />
                        <div className="ai-loading-ring ai-loading-ring--2" />
                        <div className="ai-loading-ring ai-loading-ring--3" />
                        <Search className="w-7 h-7 text-slate-800 relative z-10" />
                    </div>
                    <h3 className="text-lg font-bold text-slate-800 mt-6 mb-2">جاري البحث المتزامن...</h3>
                    <p className="text-sm text-slate-500">
                        {jobProgress.length > 0
                            ? jobProgress[jobProgress.length - 1]
                            : 'يتم البحث في المحركات واستخراج الجدول الزمني'}
                    </p>
                    <div className="flex gap-2 mt-4">
                        <div className="ai-loading-dot" style={{ animationDelay: '0s' }} />
                        <div className="ai-loading-dot" style={{ animationDelay: '0.2s' }} />
                        <div className="ai-loading-dot" style={{ animationDelay: '0.4s' }} />
                    </div>
                </div>
            )}

            {/* First seen (Origin Engine) */}
            {!loading && originReport && (originReport.firstSeen || originReport.narrative) && (
                <GlassCard className="ai-result-card p-6 border-slate-200 shadow-sm mb-6 animate-fade-in-up">
                    <div className="absolute top-0 left-0 right-0 h-1 rounded-t-2xl bg-gradient-to-r from-slate-800 via-slate-600 to-slate-800" />
                    <div className="flex items-center gap-3 mb-4 pb-3 border-b border-slate-100">
                        <div className="w-10 h-10 rounded-xl bg-slate-50 border border-slate-200 flex items-center justify-center">
                            <Award className="w-5 h-5 text-slate-700" />
                        </div>
                        <div>
                            <h2 className="font-bold text-slate-800">أول ظهور مؤكد للصورة</h2>
                            {originReport.stats?.checked > 0 && (
                                <p className="text-[11px] text-slate-400">
                                    فُحصت {originReport.stats.checked} صفحة · مؤكدة بصرياً {originReport.stats.visually_confirmed || 0}
                                </p>
                            )}
                        </div>
                    </div>

                    {timelineCached && (
                        <div className="flex items-center justify-between gap-3 p-2.5 mb-4 bg-slate-50 border border-slate-200 rounded-xl">
                            <span className="text-xs font-bold text-slate-600">نتيجة محفوظة من فحص سابق لنفس الصورة — ظهرت فوراً دون بحث جديد</span>
                            <button onClick={() => handleSearch(true)}
                                className="text-xs font-bold px-3 py-1 rounded-lg bg-slate-800 text-white hover:bg-slate-700 transition-colors whitespace-nowrap">
                                إعادة الفحص
                            </button>
                        </div>
                    )}

                    {originReport.firstSeen ? (
                        <div className="flex gap-4">
                            <Thumb item={originReport.firstSeen} size="w-28 h-28 md:w-36 md:h-28" />
                            <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2 flex-wrap mb-2">
                                    <DatePill item={originReport.firstSeen} strong />
                                    <PlatformPill url={originReport.firstSeen.url} />
                                    <ProbablePill item={originReport.firstSeen} />
                                </div>
                                <h3 className="font-bold text-slate-800 text-sm mb-1 line-clamp-2" dir="auto">{originReport.firstSeen.title}</h3>
                                <a href={originReport.firstSeen.url} target="_blank" rel="noopener noreferrer" className="text-[11px] text-slate-500 hover:text-slate-900 break-all line-clamp-1" dir="ltr">
                                    {originReport.firstSeen.url}
                                </a>
                                {originReport.firstSeen.evidence?.length > 0 && (
                                    <p className="text-[10px] text-slate-400 mt-2">
                                        الدليل: {originReport.firstSeen.evidence.slice(0, 3).map(e => evidenceLabel(e.source)).join(' · ')}
                                        {originReport.firstSeen.captured_at && <> · التقاط (EXIF) <span dir="ltr">{originReport.firstSeen.captured_at.slice(0, 10)}</span></>}
                                    </p>
                                )}
                            </div>
                        </div>
                    ) : (
                        <p className="text-sm text-slate-500">لم يُعثر على ظهور مؤرَّخ ومؤكد بصرياً — راجع الجدول الزمني أدناه.</p>
                    )}

                    {originReport.scenes?.length > 1 && (
                        <div className="mt-3 grid sm:grid-cols-2 gap-2">
                            {originReport.scenes.map((sc) => (
                                <a key={sc.frame} href={sc.first_seen.url} target="_blank" rel="noopener noreferrer"
                                    className="flex items-center gap-3 p-2.5 rounded-xl border border-slate-200 bg-white hover:border-slate-300 transition-all">
                                    <Thumb item={sc.first_seen} size="w-12 h-12" />
                                    <div className="min-w-0">
                                        <p className="text-[10px] text-slate-400">مشهد {sc.frame} — أول ظهور</p>
                                        <div className="flex items-center gap-1.5 flex-wrap mt-0.5">
                                            <DatePill item={sc.first_seen} />
                                            <PlatformPill url={sc.first_seen.url} />
                                        </div>
                                    </div>
                                </a>
                            ))}
                        </div>
                    )}

                    {originReport.narrative && (
                        <p className="text-sm text-slate-700 leading-relaxed mt-4 p-3 bg-slate-50 rounded-xl border border-slate-100">{originReport.narrative}</p>
                    )}

                    {Object.keys(originReport.engines || {}).length > 0 && (
                        <p className="text-[10px] text-slate-400 mt-4" dir="ltr">
                            {Object.entries(originReport.engines)
                                .filter(([, st]) => st.ok && st.count > 0)
                                .map(([name, st]) => `${ENGINE_LABELS[name.replace('@pivot', '')] || name} ${st.count}`)
                                .join(' · ')}
                        </p>
                    )}

                    {originReport.agent && (
                        <details className="mt-3 group">
                            <summary className="cursor-pointer text-xs font-bold text-slate-600 select-none">
                                خطوات التحقيق ({(originReport.agent.steps || []).length})
                                {originReport.agent.pick && (
                                    <span className="mr-2 text-[10px] px-2 py-0.5 rounded-md bg-slate-100 text-slate-600">
                                        {originReport.agent.pick_matches_first_seen ? 'استنتاج الوكيل يطابق الأدلة' : 'استنتاج الوكيل يختلف عن الأدلة'}
                                    </span>
                                )}
                            </summary>
                            {originReport.agent.image_context?.description && (
                                <p className="text-[11px] text-slate-500 mt-2 leading-relaxed">
                                    <span className="font-bold text-slate-600">ما تراه الرؤية الآلية: </span>
                                    {originReport.agent.image_context.description}
                                </p>
                            )}
                            <ol className="mt-2 space-y-1">
                                {(originReport.agent.steps || []).map((s) => (
                                    <li key={s.n} className="flex items-start gap-2 text-[11px] text-slate-600">
                                        <span className="w-5 h-5 rounded-full bg-slate-100 text-slate-500 flex items-center justify-center text-[10px] font-bold shrink-0">{s.n}</span>
                                        <span><span className="font-bold text-slate-700">{TOOL_LABELS[s.tool] || s.tool}</span> — {s.summary} <span className="text-slate-400">({s.elapsed_s}s)</span></span>
                                    </li>
                                ))}
                            </ol>
                            {originReport.agent.finish?.reasoning && (
                                <p className="text-[11px] text-slate-600 mt-2 p-2 bg-white rounded-lg border border-slate-100" dir="auto">
                                    {originReport.agent.finish.reasoning}
                                </p>
                            )}
                        </details>
                    )}
                </GlassCard>
            )}

            {/* Results */}
            {!loading && hasAnyResult && (
                <div className="grid md:grid-cols-2 gap-6 animate-fade-in-up delay-100">
                    {/* Engine Search */}
                    <GlassCard className="ai-result-card p-6 border-slate-200 shadow-sm">
                        <div className="absolute top-0 left-0 right-0 h-1 rounded-t-2xl bg-gradient-to-r from-slate-800 via-slate-600 to-slate-800" />
                        <div className="flex items-center gap-3 mb-5 pb-3 border-b border-slate-100">
                            <div className="w-10 h-10 rounded-xl bg-slate-50 border border-slate-200 flex items-center justify-center">
                                <Search className="w-5 h-5 text-slate-700" />
                            </div>
                            <h2 className="font-bold text-slate-800">محركات البحث (عكسي)</h2>
                        </div>

                        <ErrorBanner message={errors.engines} className="mb-4" />

                        {enginesResult?.imageUrl && (
                            <img src={enginesResult.imageUrl} alt="Target" className="w-full h-36 object-cover rounded-xl mb-4 border border-slate-200" />
                        )}

                        {enginesResult?.searchResults ? (
                            <div className="space-y-2">
                                {searchEnginesList.map((engine) => {
                                    const url = enginesResult.searchResults[engine.id];
                                    if (!url) return null;
                                    return (
                                        <a key={engine.id} href={url} target="_blank" rel="noopener noreferrer"
                                            className="group flex items-center justify-between p-3 bg-white border border-slate-200 rounded-xl hover:shadow-sm transition-all hover:border-slate-300">
                                            <div className="flex items-center gap-3">
                                                <div className={`w-2.5 h-2.5 rounded-full ${engine.gradient}`} />
                                                <span className="font-bold text-sm text-slate-700">{engine.name}</span>
                                            </div>
                                            <ExternalLink className="w-4 h-4 text-slate-400 group-hover:text-slate-900 transition-colors" />
                                        </a>
                                    );
                                })}
                            </div>
                        ) : (
                            !errors.engines && <div className="text-center text-slate-400 py-6 text-sm">لا توجد روابط.</div>
                        )}
                    </GlassCard>

                    {/* Timeline */}
                    <GlassCard className="ai-result-card p-6 border-slate-200 shadow-sm" style={{ animationDelay: '150ms' }}>
                        <div className="absolute top-0 left-0 right-0 h-1 rounded-t-2xl bg-gradient-to-r from-slate-600 via-slate-400 to-slate-600" />
                        <div className="flex items-center gap-3 mb-5 pb-3 border-b border-slate-100">
                            <div className="w-10 h-10 rounded-xl bg-slate-50 border border-slate-200 flex items-center justify-center">
                                <Calendar className="w-5 h-5 text-slate-700" />
                            </div>
                            <h2 className="font-bold text-slate-800">{originReport ? 'من نشرها ومن أعاد نشرها' : 'الجدول الزمني'}</h2>
                        </div>

                        <ErrorBanner message={errors.timeline} className="mb-4" />

                        {timelineCached && (
                            <div className="flex items-center justify-between p-2.5 mb-4 bg-slate-50 border border-slate-200 rounded-xl">
                                <span className="text-xs font-bold text-slate-600">نتيجة محفوظة من فحص سابق لنفس الصورة</span>
                                <button
                                    onClick={() => handleSearch(true)}
                                    className="text-xs font-bold px-3 py-1 rounded-lg bg-white border border-slate-200 text-slate-700 hover:bg-slate-100 transition-colors"
                                >
                                    إعادة الفحص
                                </button>
                            </div>
                        )}

                        {timelineEngine === 'google_lens_fallback' && (
                            <div className="p-2.5 mb-4 bg-slate-50 border border-slate-200 rounded-xl">
                                <span className="text-xs font-bold text-slate-600">
                                    تعذّر الوصول لمحرك الجدول الزمني — النتائج من Google Lens مباشرة
                                </span>
                            </div>
                        )}

                        {timelineResult ? (
                            <div className="space-y-2 max-h-[480px] overflow-y-auto pr-1">
                                {timelineResult.map((item, idx) => {
                                    const isFirst = originReport?.firstSeen && item.link === originReport.firstSeen.url;
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
                            !errors.timeline && <div className="text-center text-slate-400 py-6 text-sm">لا يوجد سجل تاريخي.</div>
                        )}
                    </GlassCard>
                </div>
            )}

            {/* Idle State */}
            {!loading && !hasAnyResult && (
                <div className="ai-idle-state animate-fade-in-up delay-200">
                    <svg width="120" height="120" viewBox="0 0 200 200" className="opacity-60 mb-4">
                        <defs>
                            <linearGradient id="searchGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                                <stop offset="0%" stopColor="#0f172a" />
                                <stop offset="100%" stopColor="#64748b" />
                            </linearGradient>
                        </defs>
                        <circle cx="100" cy="100" r="80" fill="none" stroke="#e2e8f0" strokeWidth="1.5" strokeDasharray="10 6" className="ai-ring-outer" />
                        <circle cx="100" cy="100" r="55" fill="none" stroke="#f1f5f9" strokeWidth="1" className="ai-ring-inner" />
                        {/* Search icon */}
                        <circle cx="90" cy="90" r="25" fill="none" stroke="url(#searchGrad)" strokeWidth="2.5" opacity="0.5" />
                        <line x1="108" y1="108" x2="130" y2="130" stroke="url(#searchGrad)" strokeWidth="3" strokeLinecap="round" opacity="0.5" />
                        <circle cx="100" cy="30" r="2" fill="#0f172a" className="ai-particle ai-p1" />
                        <circle cx="160" cy="100" r="2" fill="#334155" className="ai-particle ai-p2" />
                        <circle cx="100" cy="170" r="2" fill="#64748b" className="ai-particle ai-p3" />
                    </svg>
                    <p className="text-slate-400 font-bold text-center">ارفع صورة واضغط ابحث لبدء البحث عن المصدر</p>
                </div>
            )}
        </div>
    );
};

export default ReverseSearch;
