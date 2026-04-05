import { useState, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { ShieldCheck, AlertTriangle, X } from 'lucide-react';
import apiClient from '../services/apiClient';
import GlassCard from '../components/GlassCard';
import DropZone from '../components/DropZone';

// ─── Animated Percentage Counter ────────────────────────
const AnimatedPercentage = ({ value }) => {
    const [count, setCount] = useState(0);
    const target = Math.round(value * 100);

    useEffect(() => {
        let startTimestamp = null;
        const duration = 1500;
        const step = (timestamp) => {
            if (!startTimestamp) startTimestamp = timestamp;
            const progress = Math.min((timestamp - startTimestamp) / duration, 1);
            const easeOut = progress * (2 - progress);
            setCount(Math.floor(easeOut * target));
            if (progress < 1) window.requestAnimationFrame(step);
        };
        window.requestAnimationFrame(step);
    }, [target]);

    return <span>{count}%</span>;
};

// ─── Animated Progress Bar ────────────────────────
const AnimatedBar = ({ value, colorClass }) => {
    const [width, setWidth] = useState(0);
    const target = Math.round(value * 100);

    useEffect(() => {
        const timer = setTimeout(() => setWidth(target), 100);
        return () => clearTimeout(timer);
    }, [target]);

    return (
        <div className="h-3 bg-slate-100 rounded-full overflow-hidden">
            <div
                className={`h-full ${colorClass} rounded-full transition-all ease-out relative overflow-hidden`}
                style={{ width: `${width}%`, transitionDuration: '1500ms' }}
            >
                <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/30 to-transparent animate-shimmer" />
            </div>
        </div>
    );
};

// ─── Animated Scanning SVG (Light theme) ────────────────────────
const ScanningOrb = ({ size = 160 }) => (
    <svg width={size} height={size} viewBox="0 0 200 200" className="ai-scanning-orb">
        <defs>
            <radialGradient id="orbGlow" cx="50%" cy="50%" r="50%">
                <stop offset="0%" stopColor="#0f172a" stopOpacity="0.06" />
                <stop offset="100%" stopColor="transparent" stopOpacity="0" />
            </radialGradient>
            <linearGradient id="ringGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#0f172a" />
                <stop offset="50%" stopColor="#334155" />
                <stop offset="100%" stopColor="#64748b" />
            </linearGradient>
        </defs>
        <circle cx="100" cy="100" r="90" fill="url(#orbGlow)" />
        <circle cx="100" cy="100" r="80" fill="none" stroke="url(#ringGrad)" strokeWidth="1.5" strokeDasharray="12 8" className="ai-ring-outer" opacity="0.3" />
        <circle cx="100" cy="100" r="60" fill="none" stroke="#94a3b8" strokeWidth="1" className="ai-ring-pulse" opacity="0.3" />
        <circle cx="100" cy="100" r="40" fill="none" stroke="#cbd5e1" strokeWidth="0.5" strokeDasharray="4 6" className="ai-ring-inner" />
        <g transform="translate(80, 72)">
            <path d="M20 0 L40 8 L40 22 C40 34 30 44 20 48 C10 44 0 34 0 22 L0 8 Z"
                  fill="none" stroke="#0f172a" strokeWidth="2" opacity="0.5" />
            <path d="M14 22 L18 26 L28 16" fill="none" stroke="#0f172a" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="ai-checkmark" />
        </g>
        <circle cx="100" cy="30" r="2" fill="#0f172a" className="ai-particle ai-p1" />
        <circle cx="170" cy="100" r="2" fill="#334155" className="ai-particle ai-p2" />
        <circle cx="100" cy="170" r="2" fill="#64748b" className="ai-particle ai-p3" />
        <circle cx="30" cy="100" r="2" fill="#0f172a" className="ai-particle ai-p4" />
    </svg>
);

// ─── Result Card ────────────────────────
const ResultCard = ({ result, title, error, index }) => {
    if (error) {
        return (
            <GlassCard className="ai-result-card p-6 border-slate-200" style={{ animationDelay: `${index * 150}ms` }}>
                <div className="flex items-center gap-3 mb-4 pb-3 border-b border-slate-100">
                    <div className="w-10 h-10 rounded-xl flex items-center justify-center bg-slate-100">
                        <X className="w-5 h-5 text-slate-400" />
                    </div>
                    <div>
                        <h3 className="font-bold text-slate-800">{title}</h3>
                        <p className="text-xs text-slate-500">استجابة النظام</p>
                    </div>
                </div>
                <div className="text-center py-6">
                    <AlertTriangle className="w-10 h-10 text-slate-300 mx-auto mb-3" />
                    <p className="text-slate-600 text-sm font-bold">{error}</p>
                </div>
            </GlassCard>
        );
    }

    if (!result) return null;

    const isAI = result.is_ai || (result.confidence_ai && result.confidence_ai > 0.5);

    return (
        <GlassCard className="ai-result-card p-6 border-slate-200 shadow-sm" style={{ animationDelay: `${index * 150}ms` }}>
            {/* Top accent bar */}
            <div className={`absolute top-0 left-0 right-0 h-1 rounded-t-2xl ${isAI ? 'bg-gradient-to-r from-red-500 via-orange-400 to-red-500' : 'bg-gradient-to-r from-slate-800 via-slate-600 to-slate-800'}`} />

            <div className="flex items-center gap-3 mb-5 pb-3 border-b border-slate-100">
                <div className={`w-10 h-10 rounded-xl flex items-center justify-center border ${isAI ? 'bg-red-50 border-red-200' : 'bg-slate-50 border-slate-200'}`}>
                    {isAI ? <AlertTriangle className="w-5 h-5 text-red-500" /> : <ShieldCheck className="w-5 h-5 text-slate-700" />}
                </div>
                <div>
                    <h3 className="font-bold text-slate-800">{title}</h3>
                    <p className="text-xs text-slate-500">نتيجة الفحص الآلي</p>
                </div>
            </div>

            {/* Verdict */}
            <div className="text-center mb-6">
                <div className={`inline-flex items-center justify-center w-20 h-20 rounded-2xl mb-4 border-2 ${
                    isAI
                        ? 'bg-red-50 border-red-200 text-red-500'
                        : 'bg-slate-50 border-slate-300 text-slate-800'
                }`}>
                    {isAI ? <AlertTriangle className="w-10 h-10" /> : <ShieldCheck className="w-10 h-10" />}
                </div>
                <h4 className={`text-xl font-black ${isAI ? 'text-red-600' : 'text-slate-800'}`}>
                    {result.verdict}
                </h4>
            </div>

            {/* Bars */}
            <div className="space-y-5">
                <div>
                    <div className="flex justify-between text-xs font-bold mb-2">
                        <span className="text-slate-600">التوليد الاصطناعي (AI)</span>
                        <span className="text-slate-900 text-sm font-mono"><AnimatedPercentage value={result.confidence_ai} /></span>
                    </div>
                    <AnimatedBar value={result.confidence_ai} colorClass="bg-gradient-to-r from-slate-800 to-slate-600" />
                </div>
                <div>
                    <div className="flex justify-between text-xs font-bold mb-2">
                        <span className="text-slate-500">صورة حقيقية (Human)</span>
                        <span className="text-slate-500 text-sm font-mono"><AnimatedPercentage value={result.confidence_human} /></span>
                    </div>
                    <AnimatedBar value={result.confidence_human} colorClass="bg-gradient-to-r from-slate-400 to-slate-300" />
                </div>
            </div>
        </GlassCard>
    );
};

// ─── Loading State ────────────────────────
const LoadingState = () => (
    <div className="ai-loading-state">
        <div className="ai-loading-rings">
            <div className="ai-loading-ring ai-loading-ring--1" />
            <div className="ai-loading-ring ai-loading-ring--2" />
            <div className="ai-loading-ring ai-loading-ring--3" />
            <ShieldCheck className="w-8 h-8 text-slate-800 relative z-10" />
        </div>
        <h3 className="text-lg font-bold text-slate-800 mt-6 mb-2">جاري التحليل بنموذجين...</h3>
        <p className="text-sm text-slate-500">يتم فحص الصورة عبر شبكتين عصبيتين مستقلتين</p>
        <div className="flex gap-2 mt-4">
            <div className="ai-loading-dot" style={{ animationDelay: '0s' }} />
            <div className="ai-loading-dot" style={{ animationDelay: '0.2s' }} />
            <div className="ai-loading-dot" style={{ animationDelay: '0.4s' }} />
        </div>
    </div>
);

// ═══════════════════════════════════════════
// Main Component
// ═══════════════════════════════════════════
const AIDetection = () => {
    const location = useLocation();
    const [file, setFile] = useState(null);
    const [loading, setLoading] = useState(false);
    const [results, setResults] = useState({ thehive: null, aiornot: null });
    const [errors, setErrors] = useState({ thehive: null, aiornot: null });

    const dataURLtoFile = (dataurl, filename) => {
        try {
            let arr = dataurl.split(','), mime = arr[0].match(/:(.*?);/)[1],
                bstr = atob(arr[1]), n = bstr.length, u8arr = new Uint8Array(n);
            while (n--) u8arr[n] = bstr.charCodeAt(n);
            return new File([u8arr], filename, { type: mime });
        } catch (e) { return null; }
    };

    useEffect(() => {
        if (location.state?.file) {
            setFile(location.state.file);
            setResults({ thehive: null, aiornot: null });
            setErrors({ thehive: null, aiornot: null });
        } else if (location.state?.dataUrl) {
            const f = dataURLtoFile(location.state.dataUrl, location.state.fileName || 'image.jpg');
            if (f) {
                setFile(f);
                setResults({ thehive: null, aiornot: null });
                setErrors({ thehive: null, aiornot: null });
            }
        }
    }, [location.state]);

    const handleAnalyze = async () => {
        if (!file) return;
        setLoading(true);
        setErrors({ thehive: null, aiornot: null });
        setResults({ thehive: null, aiornot: null });

        try {
            const formData1 = new FormData();
            formData1.append('image', file);
            formData1.append('service', 'thehive');

            const formData2 = new FormData();
            formData2.append('image', file);
            formData2.append('service', 'aiornot');

            const [response1, response2] = await Promise.allSettled([
                apiClient.post('/api/ai-detection', formData1, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 60000 }),
                apiClient.post('/api/ai-detection', formData2, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 60000 })
            ]);

            const newResults = { thehive: null, aiornot: null };
            const newErrors = { thehive: null, aiornot: null };

            if (response1.status === 'fulfilled') {
                const data = response1.value.data;
                if (data.success === false || data.error) newErrors.thehive = data.error || 'فشل التحليل';
                else newResults.thehive = data;
            } else {
                newErrors.thehive = response1.reason?.response?.data?.error || 'فشل الاتصال بالنموذج الأول';
            }

            if (response2.status === 'fulfilled') {
                const data = response2.value.data;
                if (data.success === false || data.error) newErrors.aiornot = data.error || 'فشل التحليل';
                else newResults.aiornot = data;
            } else {
                newErrors.aiornot = response2.reason?.response?.data?.error || 'فشل الاتصال بالنموذج الثاني';
            }

            setResults(newResults);
            setErrors(newErrors);
        } catch (err) {
            setErrors({ thehive: 'فشل التحليل', aiornot: 'فشل التحليل' });
        } finally {
            setLoading(false);
        }
    };

    const hasResults = results.thehive || results.aiornot;
    const hasErrors = errors.thehive || errors.aiornot;
    const showCards = hasResults || hasErrors;

    return (
        <div className="max-w-4xl mx-auto page-container">
            {/* Header */}
            <div className="text-center mb-8 animate-fade-in-up">
                <h1 className="text-3xl md:text-4xl font-black text-slate-800 mb-4 tracking-tight">
                    كشف التزييف <span className="gradient-text">بالذكاء الاصطناعي</span>
                </h1>
                <p className="text-slate-500 max-w-lg mx-auto">
                    ارفع الصورة وسيتم تحليلها بنموذجين مستقلين لكشف التلاعب والتوليد الاصطناعي.
                </p>
            </div>

            {/* Upload Section */}
            <div className="animate-fade-in-up delay-100">
                <GlassCard className="p-6 border-slate-200 shadow-sm mb-8">
                    <DropZone
                        onFileSelect={(f) => setFile(f)}
                        headerText="ارفع الصورة للتحليل"
                        initialFile={file}
                    />
                    <div className="mt-6">
                        <button
                            onClick={handleAnalyze}
                            disabled={!file || loading}
                            className="ai-analyze-btn w-full"
                        >
                            {loading ? (
                                <span className="flex items-center justify-center gap-2">
                                    <svg className="animate-spin w-5 h-5" viewBox="0 0 24 24" fill="none">
                                        <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" className="opacity-20" />
                                        <path d="M4 12a8 8 0 018-8" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
                                    </svg>
                                    جاري التحليل...
                                </span>
                            ) : (
                                <span className="flex items-center justify-center gap-2">
                                    <ShieldCheck className="w-5 h-5" />
                                    تحليل باستخدام نموذجين
                                </span>
                            )}
                        </button>
                    </div>
                </GlassCard>
            </div>

            {/* Results / Idle State */}
            <div className="animate-fade-in-up delay-200">
                {loading && <LoadingState />}

                {!loading && !showCards && (
                    <div className="ai-idle-state">
                        <ScanningOrb />
                        <p className="text-slate-400 font-bold mt-6 text-center">ستظهر نتائج الفحص هنا بعد رفع الصورة وتحليلها</p>
                    </div>
                )}

                {!loading && showCards && (
                    <div className="grid md:grid-cols-2 gap-6">
                        <ResultCard result={results.thehive} error={errors.thehive} title="نتيجة الفحص الأول" index={0} />
                        <ResultCard result={results.aiornot} error={errors.aiornot} title="نتيجة الفحص الثاني" index={1} />
                    </div>
                )}
            </div>
        </div>
    );
};

export default AIDetection;
