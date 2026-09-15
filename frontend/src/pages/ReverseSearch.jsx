import { useState, useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { Search, RefreshCw, Layers, Calendar, ExternalLink, ImageIcon, Award, ShieldCheck, ShieldAlert, ShieldQuestion } from 'lucide-react';
import apiClient from '../services/apiClient';
import GlassCard from '../components/GlassCard';
import ErrorBanner from '../components/ErrorBanner';
import useJob from '../hooks/useJob';
import GradientButton from '../components/GradientButton';
import DropZone from '../components/DropZone';

// Match-bucket labels (exact / similar / page mention)
const MATCH_TYPE_LABELS = {
    exact: { text: 'مطابقة تامة', cls: 'bg-emerald-100 text-emerald-700' },
    similar: { text: 'صورة مشابهة', cls: 'bg-sky-100 text-sky-700' },
    page_match: { text: 'ذكر في صفحة', cls: 'bg-amber-100 text-amber-700' },
    organic: { text: 'بحث نصي', cls: 'bg-violet-100 text-violet-700' },
};

// Visual verification verdicts (Origin Engine)
const VISUAL_LABELS = {
    confirmed: { text: 'مؤكدة بصرياً', cls: 'bg-emerald-50 text-emerald-700 border-emerald-200', Icon: ShieldCheck },
    ambiguous: { text: 'تشابه جزئي', cls: 'bg-amber-50 text-amber-700 border-amber-200', Icon: ShieldQuestion },
    unverified: { text: 'غير محقَّقة', cls: 'bg-slate-50 text-slate-500 border-slate-200', Icon: ShieldQuestion },
    no_image: { text: 'بلا صورة', cls: 'bg-slate-50 text-slate-500 border-slate-200', Icon: ShieldQuestion },
    error: { text: 'تعذّر الفحص', cls: 'bg-slate-50 text-slate-400 border-slate-200', Icon: ShieldAlert },
};

const ENGINE_LABELS = {
    lens_exact_en: 'Lens (EN)', lens_exact_ar: 'Lens (AR)', lens_visual: 'Lens مشابه',
    vision: 'Google Vision', tineye: 'TinEye', yandex: 'Yandex',
    lens_pivot: 'Lens (الأصل)', text_pivot: 'بحث نصي',
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

const VisualBadge = ({ visual }) => {
    const v = VISUAL_LABELS[visual?.verdict] || null;
    if (!v) return null;
    const Icon = v.Icon;
    return (
        <span className={`inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-md border ${v.cls}`}>
            <Icon className="w-3 h-3" />
            {v.text}
            {typeof visual?.similarity === 'number' && ` ${Math.round(visual.similarity * 100)}%`}
        </span>
    );
};

const ReverseSearch = () => {
    const location = useLocation();
    const [file, setFile] = useState(null);
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

    // Handle file passed from navigation
    useEffect(() => {
        if (location.state?.file) {
            setFile(location.state.file);
        } else if (location.state?.dataUrl) {
            const f = dataURLtoFile(location.state.dataUrl, location.state.fileName || 'image.jpg');
            if (f) setFile(f);
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

        // Step 2: Timeline search — instant 200 on cache hit, else a
        // background job streamed over SSE (progress shown while it runs)
        try {
            const timelineRes = await apiClient.post('/api/direct-search', {
                image_url: uploadedImageUrl,
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
                        onFileSelect={setFile}
                        headerText="ارفع صورة للبحث الشامل"
                        subText="JPG, PNG, WEBP"
                        initialFile={file}
                    />
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
                        {hasAnyResult && (
                            <button
                                onClick={handleReset}
                                className="px-5 py-3 rounded-2xl bg-slate-100 text-slate-600 font-bold hover:bg-slate-200 transition-all border border-slate-200"
                                title="إعادة التعيين"
                            >
                                <RefreshCw className="w-5 h-5" />
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
                    <div className="absolute top-0 left-0 right-0 h-1 rounded-t-2xl bg-gradient-to-r from-emerald-600 via-emerald-400 to-emerald-600" />
                    <div className="flex items-center gap-3 mb-4 pb-3 border-b border-slate-100">
                        <div className="w-10 h-10 rounded-xl bg-emerald-50 border border-emerald-200 flex items-center justify-center">
                            <Award className="w-5 h-5 text-emerald-700" />
                        </div>
                        <div>
                            <h2 className="font-bold text-slate-800">أول ظهور مؤكد للصورة</h2>
                            {originReport.stats?.checked > 0 && (
                                <p className="text-[11px] text-slate-400">
                                    فُحصت {originReport.stats.checked} صفحة · مؤكدة بصرياً {originReport.stats.visually_confirmed || 0} · مؤرَّخة {originReport.stats.with_dates || 0}
                                </p>
                            )}
                        </div>
                    </div>

                    {originReport.firstSeen ? (
                        <div className="flex flex-col md:flex-row gap-4">
                            {originReport.firstSeen.thumbnail && (
                                <img src={originReport.firstSeen.thumbnail} alt="" className="w-full md:w-40 h-32 object-cover rounded-xl border border-slate-200" />
                            )}
                            <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2 flex-wrap mb-2">
                                    <span className="text-sm font-black px-3 py-1 bg-emerald-100 text-emerald-800 rounded-lg">
                                        {originReport.firstSeen.is_upper_bound ? 'على الأقل منذ ' : ''}<span dir="ltr">{(originReport.firstSeen.published_at || '').slice(0, 10)}</span>
                                    </span>
                                    {pct(originReport.firstSeen.confidence) && (
                                        <span className="text-[11px] font-bold text-slate-500">ثقة {pct(originReport.firstSeen.confidence)}</span>
                                    )}
                                    <VisualBadge visual={originReport.firstSeen.visual} />
                                    {MATCH_TYPE_LABELS[originReport.firstSeen.match_type] && (
                                        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-md ${MATCH_TYPE_LABELS[originReport.firstSeen.match_type].cls}`}>
                                            {MATCH_TYPE_LABELS[originReport.firstSeen.match_type].text}
                                        </span>
                                    )}
                                </div>
                                <h3 className="font-bold text-slate-800 text-sm mb-1 line-clamp-2">{originReport.firstSeen.title}</h3>
                                <a href={originReport.firstSeen.url} target="_blank" rel="noopener noreferrer" className="text-[11px] text-blue-600 hover:text-blue-800 break-all line-clamp-1" dir="ltr">
                                    {originReport.firstSeen.url}
                                </a>
                                {originReport.firstSeen.evidence?.length > 0 && (
                                    <div className="flex items-center gap-1.5 flex-wrap mt-2">
                                        <span className="text-[10px] text-slate-400">الأدلة:</span>
                                        {originReport.firstSeen.evidence.slice(0, 4).map((e, i) => (
                                            <span key={i} className="text-[10px] px-2 py-0.5 bg-slate-100 text-slate-600 rounded-md" title={`${e.source} · ${e.date}`}>
                                                {evidenceLabel(e.source)} {pct(e.confidence)}
                                            </span>
                                        ))}
                                    </div>
                                )}
                                {originReport.firstSeen.captured_at && (
                                    <p className="text-[10px] text-slate-400 mt-1">تاريخ التقاط الصورة (EXIF): <span dir="ltr">{originReport.firstSeen.captured_at.slice(0, 10)}</span></p>
                                )}
                            </div>
                        </div>
                    ) : (
                        <p className="text-sm text-slate-500">لم يُعثر على ظهور مؤرَّخ ومؤكد بصرياً — راجع الجدول الزمني أدناه.</p>
                    )}

                    {originReport.narrative && (
                        <p className="text-sm text-slate-700 leading-relaxed mt-4 p-3 bg-slate-50 rounded-xl border border-slate-100">{originReport.narrative}</p>
                    )}

                    {Object.keys(originReport.engines || {}).length > 0 && (
                        <div className="flex items-center gap-1.5 flex-wrap mt-4">
                            {Object.entries(originReport.engines).map(([name, st]) => (
                                <span key={name} title={st.note || ''}
                                    className={`text-[10px] font-bold px-2 py-0.5 rounded-md border ${st.ok ? 'bg-white text-slate-600 border-slate-200' : 'bg-slate-50 text-slate-400 border-slate-100 line-through'}`}>
                                    {ENGINE_LABELS[name] || name}{st.ok ? ` ${st.count}` : ''}
                                </span>
                            ))}
                        </div>
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
                            <h2 className="font-bold text-slate-800">{originReport ? 'الجدول الزمني — من نشرها وأعاد نشرها' : 'الجدول الزمني'}</h2>
                        </div>

                        <ErrorBanner message={errors.timeline} className="mb-4" />

                        {timelineCached && (
                            <div className="flex items-center justify-between p-2.5 mb-4 bg-sky-50 border border-sky-100 rounded-xl">
                                <span className="text-xs font-bold text-sky-700">نتيجة محفوظة من فحص سابق لنفس الصورة</span>
                                <button
                                    onClick={() => handleSearch(true)}
                                    className="text-xs font-bold px-3 py-1 rounded-lg bg-white border border-sky-200 text-sky-700 hover:bg-sky-100 transition-colors"
                                >
                                    إعادة الفحص
                                </button>
                            </div>
                        )}

                        {timelineEngine === 'google_lens_fallback' && (
                            <div className="p-2.5 mb-4 bg-amber-50 border border-amber-100 rounded-xl">
                                <span className="text-xs font-bold text-amber-700">
                                    تعذّر الوصول لمحرك الجدول الزمني — النتائج من Google Lens مباشرة
                                </span>
                            </div>
                        )}

                        {timelineResult ? (
                            <div className="space-y-3 max-h-[400px] overflow-y-auto pr-1" dir="ltr">
                                {timelineResult.map((item, idx) => {
                                    const isFirst = originReport?.firstSeen && item.link === originReport.firstSeen.url;
                                    return (
                                        <div key={idx} className={`bg-white p-3 rounded-xl border text-left ${isFirst ? 'border-emerald-300 ring-1 ring-emerald-100' : 'border-slate-200'}`}>
                                            <div className="flex items-center gap-1.5 flex-wrap">
                                                <span className={`text-[10px] font-bold px-2 py-0.5 rounded-md ${item.published_at ? 'bg-slate-800 text-white' : 'bg-slate-100 text-slate-500'}`}>{item.date_found}</span>
                                                {isFirst && <span className="text-[10px] font-bold px-2 py-0.5 rounded-md bg-emerald-100 text-emerald-700">الأول</span>}
                                                {MATCH_TYPE_LABELS[item.type] && (
                                                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-md ${MATCH_TYPE_LABELS[item.type].cls}`}>
                                                        {MATCH_TYPE_LABELS[item.type].text}
                                                    </span>
                                                )}
                                                {item.visual && <VisualBadge visual={item.visual} />}
                                                {pct(item.confidence) && item.published_at && (
                                                    <span className="text-[10px] text-slate-400">ثقة {pct(item.confidence)}</span>
                                                )}
                                            </div>
                                            <h4 className="font-bold text-xs text-slate-800 mt-2 mb-1 line-clamp-2" dir="rtl">{item.title}</h4>
                                            <a href={item.link} target="_blank" rel="noopener noreferrer" className="text-[11px] text-blue-600 hover:text-blue-800 break-all line-clamp-1">{item.link}</a>
                                            {(item.evidence?.length > 0 || item.providers?.length > 0) && (
                                                <div className="flex items-center gap-1 flex-wrap mt-1.5" dir="rtl">
                                                    {(item.evidence || []).slice(0, 3).map((e, i) => (
                                                        <span key={i} className="text-[9px] px-1.5 py-0.5 bg-slate-50 text-slate-500 rounded border border-slate-100" title={`${e.source} · ${e.date}`}>
                                                            {evidenceLabel(e.source)}
                                                        </span>
                                                    ))}
                                                    {item.providers?.length > 0 && (
                                                        <span className="text-[9px] text-slate-400" dir="ltr">{item.providers.join(' · ')}</span>
                                                    )}
                                                </div>
                                            )}
                                        </div>
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
