import { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Film, AlertTriangle, Video, Globe, Search, ScanFace, ShieldCheck, PlayCircle, Music, X, Loader2 } from 'lucide-react';
import apiClient from '../services/apiClient';
import GlassCard from '../components/GlassCard';
import GradientButton from '../components/GradientButton';
import DropZone from '../components/DropZone';
import ErrorBanner from '../components/ErrorBanner';
import useJob from '../hooks/useJob';

// --- Components ---

const ResultCard = ({ score, title, icon: Icon, colorClass }) => {
    const isAI = score > 0.5;
    const percentage = Math.round(score * 100);

    return (
        <GlassCard className="p-5 overflow-hidden relative border-slate-200 shadow-sm">
            <div className="flex items-center gap-3 mb-4 pb-3 border-b border-slate-200/50">
                <div className={`w-10 h-10 rounded-xl flex items-center justify-center bg-slate-900 shadow-lg`}>
                    <Icon className="w-5 h-5 text-white" />
                </div>
                <div>
                    <h3 className="font-bold text-slate-800">{title}</h3>
                    <p className="text-xs text-slate-500">Video Analysis Model</p>
                </div>
            </div>

            <div className="text-center mb-6 relative z-10">
                <div className={`inline-flex items-center justify-center w-20 h-20 rounded-2xl mb-3 ${isAI
                    ? 'bg-rose-50 text-rose-600 border border-rose-200'
                    : 'bg-emerald-50 text-emerald-600 border border-emerald-200'
                    } shadow-sm transform transition-transform hover:scale-105 duration-300`}>
                    {isAI ? <AlertTriangle className="w-10 h-10" /> : <ShieldCheck className="w-10 h-10" />}
                </div>
                <h4 className={`text-xl font-black ${isAI ? 'text-rose-600' : 'text-emerald-600'}`}>
                    {isAI ? 'محتوى معدل (AI)' : 'محتوى أصلي'}
                </h4>
            </div>

            <div className="space-y-4">
                <div>
                    <div className="flex justify-between text-xs font-bold mb-1">
                        <span className="text-slate-600">احتمالية AI</span>
                        <span className="text-rose-500">{percentage}%</span>
                    </div>
                    <div className="h-2.5 bg-slate-100 rounded-full overflow-hidden shadow-inner flex">
                        <div className="h-full bg-rose-500 transition-all duration-1000" style={{ width: `${percentage}%` }}></div>
                    </div>
                </div>

                <div>
                    <div className="flex justify-between text-xs font-bold mb-1">
                        <span className="text-slate-600">احتمالية حقيقي</span>
                        <span className="text-emerald-600">{100 - percentage}%</span>
                    </div>
                    <div className="h-2.5 bg-slate-100 rounded-full overflow-hidden shadow-inner flex">
                        <div className="h-full bg-emerald-500 transition-all duration-1000" style={{ width: `${100 - percentage}%` }}></div>
                    </div>
                </div>
            </div>
        </GlassCard>
    );
};

// Inline Modal for analyzing a specific frame without leaving the page
const FrameAnalysisModal = ({ frame, onClose, onNavigateToReverse }) => {
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState(null);
    const [error, setError] = useState(null);
    const [analysisType, setAnalysisType] = useState(null); // 'ai' or 'reverse'

    const dataURLtoFile = (dataurl, filename) => {
        let arr = dataurl.split(','), mime = arr[0].match(/:(.*?);/)[1],
            bstr = atob(arr[1]), n = bstr.length, u8arr = new Uint8Array(n);
        while (n--) u8arr[n] = bstr.charCodeAt(n);
        return new File([u8arr], filename, { type: mime });
    };

    const runAI = async () => {
        setAnalysisType('ai');
        setLoading(true);
        setError(null);
        try {
            const formData = new FormData();
            formData.append('image', dataURLtoFile(frame.data, 'frame.jpg'));
            formData.append('service', 'aiornot'); // specific service

            const res = await apiClient.post('/api/ai-detection', formData, {
                headers: { 'Content-Type': 'multipart/form-data' }
            });

            if (res.data && res.data.success) {
                setResult({ type: 'ai', data: res.data });
            } else {
                setError(res.data?.error || 'فشل التحليل');
            }
        } catch (err) {
            setError(err.message || 'خطأ في الاتصال بالخادم');
        } finally {
            setLoading(false);
        }
    };

    const runReverse = () => {
        onClose();
        if (onNavigateToReverse) {
            onNavigateToReverse(frame.data);
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-fade-in">
            <div className="bg-white rounded-3xl shadow-2xl w-full max-w-3xl overflow-hidden flex flex-col max-h-[90vh]">
                <div className="p-4 border-b border-slate-100 flex items-center justify-between">
                    <h3 className="font-bold text-slate-800 flex items-center gap-2">
                        <Film className="w-5 h-5 text-slate-500" />
                        تحليل الإطار الزمني: {frame.timestamp.toFixed(2)}s
                    </h3>
                    <button onClick={onClose} className="p-2 hover:bg-slate-100 rounded-full text-slate-400 hover:text-slate-700 transition-colors">
                        <X className="w-5 h-5" />
                    </button>
                </div>

                <div className="p-6 overflow-y-auto flex-1 flex flex-col md:flex-row gap-6">
                    <div className="w-full md:w-1/2 flex flex-col items-center">
                        <img src={frame.data} alt="Frame" className="w-full rounded-2xl shadow-sm border border-slate-200 aspect-video object-cover" />

                        <div className="grid grid-cols-2 gap-3 w-full mt-4">
                            <GradientButton onClick={runAI} isLoading={loading && analysisType === 'ai'} disabled={loading} icon={ScanFace} className="!px-2 !py-2 text-sm w-full">
                                كشف AI
                            </GradientButton>
                            <GradientButton onClick={runReverse} isLoading={loading && analysisType === 'reverse'} disabled={loading} variant="secondary" icon={Search} className="!px-2 !py-2 text-sm w-full">
                                بحث عكسي
                            </GradientButton>
                        </div>
                    </div>

                    <div className="w-full md:w-1/2 bg-slate-50 rounded-2xl border border-slate-100 p-5">
                        <h4 className="font-bold text-slate-700 mb-4 border-b pb-2">النتيجة المباشرة</h4>

                        {loading ? (
                            <div className="h-40 flex items-center justify-center flex-col text-slate-400">
                                <Loader2 className="w-8 h-8 animate-spin mb-2 text-slate-800" />
                                <span>جاري المعالجة...</span>
                            </div>
                        ) : error ? (
                            <div className="bg-red-50 text-red-600 p-4 rounded-xl flex items-center gap-2 text-sm">
                                <AlertTriangle className="w-5 h-5 flex-shrink-0" />
                                {error}
                            </div>
                        ) : result?.type === 'ai' ? (
                            <div>
                                <div className={`p-4 rounded-xl mb-4 flex items-center gap-3 ${result.data.is_ai ? 'bg-red-50 text-red-700' : 'bg-green-50 text-green-700'}`}>
                                    {result.data.is_ai ? <AlertTriangle className="w-6 h-6" /> : <ShieldCheck className="w-6 h-6" />}
                                    <span className="font-bold text-lg">{result.data.is_ai ? 'يوجد تلاعب (AI)' : 'الصورة حقيقية'}</span>
                                </div>
                                <div className="text-sm text-slate-600 bg-white p-4 rounded-xl shadow-sm">
                                    <div className="flex justify-between mb-2 border-b pb-2"><span className="font-bold">الموديل:</span> <span>{result.data.model || 'AI System'}</span></div>
                                    <div className="flex justify-between"><span className="font-bold">الثقة:</span> <span>{Math.round((result.data.confidence || result.data.generator_confidence || 0) * 100)}%</span></div>
                                </div>
                            </div>
                        ) : (
                            <div className="h-40 flex items-center justify-center text-slate-400 text-sm text-center px-4">
                                اختر كشف AI لفحص الإطار، أو بحث عكسي لنقل الصورة لصفحة البحث عن المصدر.
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
};

const VideoAnalysis = () => {
    const navigate = useNavigate();
    const [file, setFile] = useState(null);
    const [loading, setLoading] = useState(false);
    const [aiLoading, setAiLoading] = useState(false);
    const [frames, setFrames] = useState(null);
    const [aiResult, setAiResult] = useState(null);
    const [error, setError] = useState(null);
    const [jobId, setJobId] = useState(null);
    const { progress: jobProgress, result: jobResult, error: jobError } = useJob(jobId);

    // Tab State: 'ai' or 'frames'
    const [activeTab, setActiveTab] = useState('ai');
    const [selectedFrame, setSelectedFrame] = useState(null);

    const handleExtractFrames = async () => {
        if (!file) return;
        setLoading(true);
        setError(null);
        setFrames(null);

        const formData = new FormData();
        formData.append('file', file);
        formData.append('frameInterval', '2');

        try {
            const response = await apiClient.post('/api/extract-frames', formData, {
                headers: { 'Content-Type': 'multipart/form-data' },
                timeout: 120000
            });
            setFrames(response.data.frames);
        } catch (err) {
            console.error(err);
            setError(err.response?.data?.error || 'فشل استخراج الإطارات');
        } finally {
            setLoading(false);
        }
    };

    // Video analysis now runs as a background job (202 + SSE)
    const handleAnalyzeAI = async () => {
        if (!file) return;
        setAiLoading(true);
        setError(null);
        setAiResult(null);
        setJobId(null);

        const formData = new FormData();
        formData.append('file', file);

        try {
            const response = await apiClient.post('/api/analyze-video', formData, {
                headers: { 'Content-Type': 'multipart/form-data' },
                timeout: 60000
            });
            if (response.status === 202 && response.data.job_id) {
                setJobId(response.data.job_id);
            } else {
                setError(response.data.error || 'فشل تحليل الفيديو');
                setAiLoading(false);
            }
        } catch (err) {
            console.error(err);
            setError(err.response?.data?.error || 'فشل الاتصال بالخادم (قد يكون الملف كبيراً جداً)');
            setAiLoading(false);
        }
    };

    // Resolve the job result back into the legacy result shape
    useEffect(() => {
        if (jobResult) {
            const payload = jobResult.payload || {};
            if (payload.success) {
                setAiResult(payload.data);
            } else {
                setError(payload.error || 'فشل تحليل الفيديو');
            }
            setAiLoading(false);
            setJobId(null);
        }
    }, [jobResult]);

    useEffect(() => {
        if (jobError) {
            setError(jobError);
            setAiLoading(false);
            setJobId(null);
        }
    }, [jobError]);

    return (
        <div className="max-w-4xl mx-auto page-container">
            {selectedFrame && (
                <FrameAnalysisModal 
                    frame={selectedFrame} 
                    onClose={() => setSelectedFrame(null)} 
                    onNavigateToReverse={(dataUrl) => navigate('/reverse-search', { state: { dataUrl, autoSearch: true } })}
                />
            )}

            {/* Header */}
            <div className="text-center mb-8 animate-fade-in-up">
                <h1 className="text-3xl md:text-4xl font-black text-slate-800 mb-4 tracking-tight">
                    تحليل <span className="gradient-text">مصدر الفيديو</span>
                </h1>
                <p className="text-slate-500 max-w-lg mx-auto">
                    افحص التزييف العميق واستخرج الإطارات بدقة، كل ذلك في مكان واحد.
                </p>
            </div>

            {/* Upload Section */}
            <div className="animate-fade-in-up delay-100">
                <GlassCard className="p-6 border-slate-200 shadow-sm mb-8">
                    <DropZone
                        onFileSelect={(f) => {
                            setFile(f);
                            setFrames(null);
                            setAiResult(null);
                            setError(null);
                        }}
                        headerText="ارفع الفيديو هنا"
                        subText="MP4, AVI, MOV (Max 200MB)"
                        accept="video/*"
                    />
                </GlassCard>
            </div>

            {/* Custom Tabs */}
            <div className="flex justify-center mb-8 animate-fade-in-up delay-200">
                <div className="bg-slate-100 p-1.5 rounded-2xl inline-flex gap-2 border border-slate-200">
                    <button
                        disabled={!file}
                        onClick={() => setActiveTab('ai')}
                        className={`px-6 py-3 rounded-xl font-bold flex items-center gap-2 transition-all text-sm ${activeTab === 'ai'
                                ? 'bg-slate-900 text-white shadow-sm'
                                : 'text-slate-500 hover:text-slate-700 disabled:opacity-40 disabled:cursor-not-allowed'
                            }`}
                    >
                        <ScanFace className="w-4 h-4" /> فحص الذكاء الاصطناعي
                    </button>
                    <button
                        disabled={!file}
                        onClick={() => setActiveTab('frames')}
                        className={`px-6 py-3 rounded-xl font-bold flex items-center gap-2 transition-all text-sm ${activeTab === 'frames'
                                ? 'bg-slate-900 text-white shadow-sm'
                                : 'text-slate-500 hover:text-slate-700 disabled:opacity-40 disabled:cursor-not-allowed'
                            }`}
                    >
                        <Film className="w-4 h-4" /> استخراج الإطارات
                    </button>
                </div>
            </div>

            {/* Error */}
            {error && (
                <div className="animate-fade-in-up mb-6">
                    <ErrorBanner variant="panel" message={error} className="justify-center" />
                </div>
            )}

            {/* Tab 1: AI Analysis */}
            {activeTab === 'ai' && file && (
                <div className="animate-fade-in-up">
                    {!aiResult && !aiLoading && (
                        <div className="ai-idle-state">
                            <svg width="120" height="120" viewBox="0 0 200 200" className="opacity-60 mb-4">
                                <defs>
                                    <linearGradient id="vidGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                                        <stop offset="0%" stopColor="#0f172a" />
                                        <stop offset="100%" stopColor="#64748b" />
                                    </linearGradient>
                                </defs>
                                <circle cx="100" cy="100" r="80" fill="none" stroke="#e2e8f0" strokeWidth="1.5" strokeDasharray="10 6" className="ai-ring-outer" />
                                <circle cx="100" cy="100" r="55" fill="none" stroke="#f1f5f9" strokeWidth="1" className="ai-ring-inner" />
                                <rect x="70" y="70" width="60" height="40" rx="6" fill="none" stroke="url(#vidGrad)" strokeWidth="2" opacity="0.5" />
                                <polygon points="92,82 92,98 108,90" fill="url(#vidGrad)" opacity="0.4" />
                                <circle cx="100" cy="30" r="2" fill="#0f172a" className="ai-particle ai-p1" />
                                <circle cx="160" cy="100" r="2" fill="#334155" className="ai-particle ai-p2" />
                                <circle cx="100" cy="170" r="2" fill="#64748b" className="ai-particle ai-p3" />
                            </svg>
                            <p className="text-slate-400 font-bold text-center mb-6">سيقوم الخادم بمعالجة الفيديو كاملاً لكشف التزييف</p>
                            <button onClick={handleAnalyzeAI} className="ai-analyze-btn px-10">
                                <span className="flex items-center justify-center gap-2">
                                    <ScanFace className="w-5 h-5" />
                                    ابدأ فحص الفيديو
                                </span>
                            </button>
                        </div>
                    )}

                    {aiLoading && (
                        <div className="ai-loading-state animate-fade-in">
                            <div className="ai-loading-rings">
                                <div className="ai-loading-ring ai-loading-ring--1" />
                                <div className="ai-loading-ring ai-loading-ring--2" />
                                <div className="ai-loading-ring ai-loading-ring--3" />
                                <ScanFace className="w-7 h-7 text-slate-800 relative z-10" />
                            </div>
                            <h3 className="text-lg font-bold text-slate-800 mt-6 mb-2">جاري تحليل الفيديو...</h3>
                            <p className="text-sm text-slate-500">
                                {jobProgress.length > 0
                                    ? jobProgress[jobProgress.length - 1]
                                    : 'قد يستغرق هذا بضع دقائق بناءً على طول الفيديو'}
                            </p>
                            <div className="flex gap-2 mt-4">
                                <div className="ai-loading-dot" style={{ animationDelay: '0s' }} />
                                <div className="ai-loading-dot" style={{ animationDelay: '0.2s' }} />
                                <div className="ai-loading-dot" style={{ animationDelay: '0.4s' }} />
                            </div>
                        </div>
                    )}

                    {aiResult && !aiLoading && (
                        <div className="bg-slate-50/50 p-8 rounded-3xl border border-slate-200/60 shadow-sm max-w-4xl mx-auto">
                            <h2 className="text-xl font-bold text-slate-800 flex items-center justify-center mb-8">
                                <span className="w-2 h-2 bg-slate-800 rounded-full ml-3"></span>
                                التقرير النهائي لتحليل الفيديو
                                <span className="w-2 h-2 bg-slate-800 rounded-full mr-3"></span>
                            </h2>

                            {(!aiResult.report || (!aiResult.report.ai_video && !aiResult.report.ai)) ? (
                                <div className="bg-slate-100 p-4 rounded-xl text-sm overflow-auto max-h-96 text-left border border-slate-200" dir="ltr">
                                    <p className="font-bold text-slate-600 mb-2">تفاصيل خام (Raw Output):</p>
                                    <pre>{JSON.stringify(aiResult, null, 2)}</pre>
                                </div>
                            ) : (
                                <div className="grid md:grid-cols-3 gap-6">
                                    <ResultCard
                                        title="الصورة المرئية"
                                        score={aiResult.report.ai_video?.confidence || aiResult.report.ai?.video || 0}
                                        icon={Video}
                                        colorClass="text-slate-700"
                                    />
                                    <ResultCard
                                        title="البصمة الصوتية"
                                        score={aiResult.report.ai_voice?.confidence || aiResult.report.ai?.voice || 0}
                                        icon={PlayCircle}
                                        colorClass="text-slate-700"
                                    />
                                    <ResultCard
                                        title="الموسيقى والخلفية"
                                        score={aiResult.report.ai_music?.confidence || aiResult.report.ai?.music || 0}
                                        icon={Music}
                                        colorClass="text-slate-700"
                                    />
                                </div>
                            )}
                        </div>
                    )}
                </div>
            )}

            {/* Tab 2: Frames Extraction */}
            {activeTab === 'frames' && file && (
                <div className="animate-fade-in-up">
                    {!frames && !loading && (
                        <div className="text-center bg-slate-50 border border-slate-200 rounded-3xl py-16 max-w-3xl mx-auto shadow-sm">
                            <Film className="w-16 h-16 text-slate-300 mx-auto mb-4" />
                            <h3 className="text-xl font-bold text-slate-700 mb-2">تفكيك الفيديو إلى إطارات</h3>
                            <p className="text-slate-500 mb-6 max-w-sm mx-auto">سحب الصور (اللقطات) الهامة من الفيديو ليتم فحص كل لقطة على حدة بحثاً عن مصدرها.</p>
                            <GradientButton onClick={handleExtractFrames} className="px-10">
                                استخراج الإطارات الآن
                            </GradientButton>
                        </div>
                    )}

                    {loading && (
                        <div className="text-center py-20">
                            <svg width="80" height="80" viewBox="0 0 100 100" className="mx-auto mb-6 text-slate-400">
                                <style>
                                    {`
                                        @keyframes extract { 0% { transform: translateX(-10px); opacity:0; } 50% { opacity:1; } 100% { transform: translateX(10px); opacity:0; } }
                                    `}
                                </style>
                                <rect x="25" y="30" width="50" height="40" fill="none" stroke="currentColor" strokeWidth="4" />
                                <rect x="35" y="40" width="10" height="20" fill="currentColor" style={{ animation: 'extract 1.5s infinite' }} />
                                <rect x="55" y="40" width="10" height="20" fill="currentColor" style={{ animation: 'extract 1.5s infinite 0.5s' }} />
                            </svg>
                            <h3 className="text-2xl font-bold text-slate-800 mb-2">جاري التفكيك...</h3>
                        </div>
                    )}

                    {frames && (
                        <div>
                            <div className="flex items-center justify-between mb-6 bg-slate-900 text-white p-4 rounded-2xl shadow-lg">
                                <h2 className="font-bold flex items-center">
                                    <Film className="w-5 h-5 ml-2 text-slate-400" />
                                    تم تفكيك ({frames.length}) إطارات متفرقة
                                </h2>
                                <p className="text-sm text-slate-400">انقر على إطار لتقوم بتحليله فوراً</p>
                            </div>

                            <div className="grid grid-cols-2 lg:grid-cols-4 xl:grid-cols-5 gap-4">
                                {frames.map((frame, idx) => (
                                    <div key={idx}
                                        onClick={() => setSelectedFrame(frame)}
                                        className="group bg-white rounded-xl overflow-hidden border border-slate-200 shadow-sm hover:shadow-xl hover:-translate-y-1 transition-all cursor-pointer relative"
                                    >
                                        <div className="aspect-video relative bg-slate-100">
                                            <img
                                                src={frame.data}
                                                alt={`Frame ${idx}`}
                                                className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-110"
                                            />
                                            {/* Overlay on Hover */}
                                            <div className="absolute inset-0 bg-slate-900/60 opacity-0 group-hover:opacity-100 flex items-center justify-center transition-opacity text-white font-bold text-sm gap-2">
                                                <Search className="w-4 h-4" /> فحص الإطار
                                            </div>

                                            <div className="absolute bottom-2 right-2 bg-black/80 text-white text-xs px-2 py-0.5 rounded-md font-mono">
                                                {frame.timestamp.toFixed(1)}s
                                            </div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            )}

            {/* Idle State - when no file */}
            {!file && (
                <div className="ai-idle-state animate-fade-in-up delay-200">
                    <svg width="120" height="120" viewBox="0 0 200 200" className="opacity-60 mb-4">
                        <defs>
                            <linearGradient id="vidIdleGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                                <stop offset="0%" stopColor="#0f172a" />
                                <stop offset="100%" stopColor="#64748b" />
                            </linearGradient>
                        </defs>
                        <circle cx="100" cy="100" r="80" fill="none" stroke="#e2e8f0" strokeWidth="1.5" strokeDasharray="10 6" className="ai-ring-outer" />
                        <circle cx="100" cy="100" r="55" fill="none" stroke="#f1f5f9" strokeWidth="1" className="ai-ring-inner" />
                        {/* Video play icon */}
                        <rect x="70" y="70" width="60" height="40" rx="6" fill="none" stroke="url(#vidIdleGrad)" strokeWidth="2" opacity="0.5" />
                        <polygon points="92,82 92,98 108,90" fill="url(#vidIdleGrad)" opacity="0.4" />
                        {/* Film strip lines */}
                        <line x1="70" y1="75" x2="130" y2="75" stroke="#cbd5e1" strokeWidth="0.5" />
                        <line x1="70" y1="105" x2="130" y2="105" stroke="#cbd5e1" strokeWidth="0.5" />
                        <circle cx="100" cy="30" r="2" fill="#0f172a" className="ai-particle ai-p1" />
                        <circle cx="160" cy="100" r="2" fill="#334155" className="ai-particle ai-p2" />
                        <circle cx="100" cy="170" r="2" fill="#64748b" className="ai-particle ai-p3" />
                    </svg>
                    <p className="text-slate-400 font-bold text-center">ارفع فيديو واختر نوع التحليل من الأعلى لبدء الفحص</p>
                </div>
            )}
        </div>
    );
};

export default VideoAnalysis;
