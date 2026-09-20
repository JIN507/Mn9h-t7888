import { useState, useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { Search, RefreshCw, X, ExternalLink } from 'lucide-react';
import { FirstSeenCard, TimelineCard, parseOriginPayload } from '../components/OriginReport';
import apiClient from '../services/apiClient';
import GlassCard from '../components/GlassCard';
import ErrorBanner from '../components/ErrorBanner';
import useJob from '../hooks/useJob';
import GradientButton from '../components/GradientButton';
import DropZone from '../components/DropZone';



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
        setOriginReport(parseOriginPayload(payload));
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
            {!loading && originReport && (
                <FirstSeenCard report={originReport} cached={timelineCached} onRerun={() => handleSearch(true)} />
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
                    <TimelineCard
                        report={originReport}
                        timeline={timelineResult}
                        cached={timelineCached}
                        onRerun={() => handleSearch(true)}
                        error={errors.timeline}
                        engineNote={timelineEngine === 'google_lens_fallback' ? 'تعذّر الوصول لمحرك الجدول الزمني — النتائج من Google Lens مباشرة' : null}
                        style={{ animationDelay: '150ms' }}
                    />
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
