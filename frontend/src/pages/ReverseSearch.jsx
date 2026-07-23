import { useState, useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { Search, RefreshCw, Layers, Calendar, ExternalLink, AlertTriangle, ImageIcon } from 'lucide-react';
import apiClient from '../services/apiClient';
import GlassCard from '../components/GlassCard';
import GradientButton from '../components/GradientButton';
import DropZone from '../components/DropZone';

// Match-bucket labels (exact / similar / page mention)
const MATCH_TYPE_LABELS = {
    exact: { text: 'مطابقة تامة', cls: 'bg-emerald-100 text-emerald-700' },
    similar: { text: 'صورة مشابهة', cls: 'bg-sky-100 text-sky-700' },
    page_match: { text: 'ذكر في صفحة', cls: 'bg-amber-100 text-amber-700' },
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

    const handleSearch = async () => {
        if (!file) return;

        setLoading(true);
        setErrors({ engines: null, timeline: null });
        setEnginesResult(null);
        setTimelineResult(null);

        // Prep form data for upload
        const formData = new FormData();
        formData.append('file', file);

        let uploadedImageUrl = null;

        try {
            // Step 1: Upload and get Engine Results
            try {
                const engineRes = await apiClient.post('/api/upload', formData, {
                    headers: { 'Content-Type': 'multipart/form-data' },
                    timeout: 60000
                });

                if (engineRes.data?.searchResults) {
                    setEnginesResult(engineRes.data);
                    uploadedImageUrl = engineRes.data.imageUrl;
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

            // Step 2: Use the uploaded image URL to get the Timeline Results
            if (uploadedImageUrl) {
                try {
                    const timelineRes = await apiClient.post('/api/direct-search', { image_url: uploadedImageUrl }, { timeout: 120000 });
                    if (timelineRes.data?.success) {
                        const timelineData = timelineRes.data.timeline || [];
                        if (timelineData.length > 0) {
                            setTimelineResult(timelineData);
                        } else {
                            setErrors(prev => ({ ...prev, timeline: 'لم تتوفر تواريخ سابقة لهذه الصورة' }));
                        }
                    } else {
                        setErrors(prev => ({ ...prev, timeline: timelineRes.data?.error || 'فشل استخراج الجدول الزمني' }));
                    }
                } catch (err) {
                    console.error('Timeline search error:', err);
                    if (err.code === 'ECONNABORTED' || err.message?.includes('timeout')) {
                        setErrors(prev => ({ ...prev, timeline: 'انتهت مهلة استخراج التواريخ' }));
                    } else {
                        setErrors(prev => ({ 
                            ...prev, 
                            timeline: err.response?.data?.error || 'فشل الاتصال بخدمة الجدول الزمني' 
                        }));
                    }
                }
            } else {
                setErrors(prev => ({ 
                    ...prev, 
                    timeline: 'تم إيقاف البحث الزمني بسبب فشل رفع الصورة'
                }));
            }

        } catch (err) {
            console.error('Fatal wrapper error:', err);
            setErrors({ engines: 'فشل النظام كلياً', timeline: 'فشل النظام كلياً' });
        } finally {
            setLoading(false);
        }
    };

    const handleReset = () => {
        setFile(null);
        setEnginesResult(null);
        setTimelineResult(null);
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
                    ارفع الصورة وسيقوم النظام بالبحث في محركات البحث واستخراج تاريخ ظهورها.
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
                            onClick={handleSearch}
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
                    <p className="text-sm text-slate-500">يتم البحث في المحركات واستخراج الجدول الزمني</p>
                    <div className="flex gap-2 mt-4">
                        <div className="ai-loading-dot" style={{ animationDelay: '0s' }} />
                        <div className="ai-loading-dot" style={{ animationDelay: '0.2s' }} />
                        <div className="ai-loading-dot" style={{ animationDelay: '0.4s' }} />
                    </div>
                </div>
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

                        {errors.engines && (
                            <div className="p-3 bg-red-50 text-red-600 rounded-xl flex items-center gap-2 mb-4 text-sm font-bold">
                                <AlertTriangle className="w-4 h-4" /> {errors.engines}
                            </div>
                        )}

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
                            <h2 className="font-bold text-slate-800">الجدول الزمني</h2>
                        </div>

                        {errors.timeline && (
                            <div className="p-3 bg-red-50 text-red-600 rounded-xl flex items-center gap-2 mb-4 text-sm font-bold">
                                <AlertTriangle className="w-4 h-4" /> {errors.timeline}
                            </div>
                        )}

                        {timelineResult ? (
                            <div className="space-y-3 max-h-[400px] overflow-y-auto pr-1" dir="ltr">
                                {timelineResult.map((item, idx) => (
                                    <div key={idx} className="bg-white p-3 rounded-xl border border-slate-200 text-left">
                                        <div className="flex items-center gap-1.5 flex-wrap">
                                            <span className="text-[10px] font-bold px-2 py-0.5 bg-slate-100 text-slate-600 rounded-md">{item.date_found}</span>
                                            {MATCH_TYPE_LABELS[item.type] && (
                                                <span className={`text-[10px] font-bold px-2 py-0.5 rounded-md ${MATCH_TYPE_LABELS[item.type].cls}`}>
                                                    {MATCH_TYPE_LABELS[item.type].text}
                                                </span>
                                            )}
                                        </div>
                                        <h4 className="font-bold text-xs text-slate-800 mt-2 mb-1 line-clamp-2" dir="rtl">{item.title}</h4>
                                        <a href={item.link} target="_blank" rel="noopener noreferrer" className="text-[11px] text-blue-600 hover:text-blue-800 break-all line-clamp-1">{item.link}</a>
                                    </div>
                                ))}
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
