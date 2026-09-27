import { useState } from 'react';
import { FileText, ShieldCheck, Send, RotateCcw } from 'lucide-react';
import apiClient from '../services/apiClient';
import GlassCard from '../components/GlassCard';
import ResultCard from '../components/ResultCard';
import ErrorBanner from '../components/ErrorBanner';
import ConfidenceGauge from '../components/ConfidenceGauge';


const TextVerification = () => {
    const [text, setText] = useState('');
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState(null);
    const [error, setError] = useState(null);

    const handleAnalyze = async () => {
        if (!text.trim() || text.trim().length < 250) return;

        setLoading(true);
        setError(null);
        setResult(null);

        try {
            const response = await apiClient.post('/api/text-detection', {
                text: text.trim()
            }, { timeout: 60000 });

            if (response.data?.success) {
                setResult(response.data);
            } else {
                setError(response.data?.error || 'فشل تحليل النص');
            }
        } catch (err) {
            console.error(err);
            setError(err.response?.data?.error || 'فشل الاتصال بالخادم');
        } finally {
            setLoading(false);
        }
    };

    const handleReset = () => {
        setText('');
        setResult(null);
        setError(null);
    };

    const isAI = result?.is_ai;
    const charCount = text.trim().length;
    const isValid = charCount >= 20;

    return (
        <div className="max-w-4xl mx-auto page-container">
            {/* Header */}
            <div className="text-center mb-8 animate-fade-in-up">
                <h1 className="text-3xl md:text-4xl font-black text-slate-800 mb-4 tracking-tight">
                    كشف النصوص <span className="gradient-text">المولّدة بالذكاء الاصطناعي</span>
                </h1>
                <p className="text-slate-500 max-w-lg mx-auto">
                    ألصق النص المراد فحصه وسيقوم النظام بتحليله لمعرفة إن كان مكتوباً بواسطة إنسان أو ذكاء اصطناعي.
                </p>
            </div>

            {/* Input Section */}
            <div className="animate-fade-in-up delay-100">
                <GlassCard className="p-6 border-slate-200 shadow-sm mb-8">
                    <div className="relative">
                        <textarea
                            value={text}
                            onChange={(e) => setText(e.target.value)}
                            placeholder="ألصق النص هنا للتحليل... (250 حرفاً على الأقل)"
                            className="w-full h-48 p-4 bg-slate-50 border border-slate-200 rounded-2xl text-slate-800 text-sm leading-relaxed resize-none focus:outline-none focus:ring-2 focus:ring-slate-300 focus:border-transparent transition-all placeholder:text-slate-400"
                            dir="auto"
                        />
                        <div className="absolute bottom-3 left-3 text-xs text-slate-400 font-mono">
                            {charCount} <span className="text-slate-300">حرف</span>
                            {charCount > 0 && charCount < 250 && (
                                <span className="text-red-400 mr-2">• يجب 250 حرفاً على الأقل</span>
                            )}
                        </div>
                    </div>

                    <div className="mt-4 flex gap-3">
                        <button
                            onClick={handleAnalyze}
                            disabled={!isValid || loading}
                            className="ai-analyze-btn flex-1"
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
                                    <Send className="w-5 h-5" />
                                    تحليل النص
                                </span>
                            )}
                        </button>
                        {(result || error) && (
                            <button
                                onClick={handleReset}
                                className="px-5 py-3 rounded-2xl bg-slate-100 text-slate-600 font-bold hover:bg-slate-200 transition-all border border-slate-200"
                                title="إعادة التعيين"
                            >
                                <RotateCcw className="w-5 h-5" />
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
                        <FileText className="w-7 h-7 text-slate-800 relative z-10" />
                    </div>
                    <h3 className="text-lg font-bold text-slate-800 mt-6 mb-2">جاري تحليل النص...</h3>
                    <p className="text-sm text-slate-500">يتم فحص النص عبر نموذج متخصص في كشف المحتوى المولّد</p>
                    <div className="flex gap-2 mt-4">
                        <div className="ai-loading-dot" style={{ animationDelay: '0s' }} />
                        <div className="ai-loading-dot" style={{ animationDelay: '0.2s' }} />
                        <div className="ai-loading-dot" style={{ animationDelay: '0.4s' }} />
                    </div>
                </div>
            )}

            {/* Error */}
            {error && !loading && (
                <div className="animate-fade-in-up">
                    <ErrorBanner variant="card" message={error} />
                </div>
            )}

            {/* Result */}
            {result && !loading && (
                <div className="animate-fade-in-up delay-100">
                    <ResultCard title="نتيجة تحليل النص" isAI={isAI} verdict={result.verdict}>
                        <ConfidenceGauge bars={[
                            { label: 'توليد اصطناعي (AI)', value: result.confidence_ai,
                              colorClass: 'bg-gradient-to-r from-slate-800 to-slate-600' },
                            { label: 'نص بشري (Human)', value: result.confidence_human,
                              colorClass: 'bg-gradient-to-r from-slate-400 to-slate-300',
                              labelClass: 'text-slate-500', valueClass: 'text-slate-500' },
                        ]} />

                        {/* Annotations */}
                        {result.annotations && result.annotations.length > 0 && (
                            <div className="mt-6 pt-4 border-t border-slate-100">
                                <h4 className="font-bold text-slate-700 text-sm mb-3">تحليل تفصيلي للفقرات:</h4>
                                <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
                                    {result.annotations.map((block, idx) => (
                                        <div key={idx} className={`p-3 rounded-xl border text-sm ${
                                            block.is_ai
                                                ? 'bg-red-50/50 border-red-100 text-slate-700'
                                                : 'bg-slate-50 border-slate-100 text-slate-600'
                                        }`}>
                                            <div className="flex justify-between items-center mb-1">
                                                <span className={`text-xs font-bold ${block.is_ai ? 'text-red-500' : 'text-slate-500'}`}>
                                                    {block.is_ai ? '🤖 AI' : '✍️ بشري'} — {Math.round((block.confidence || 0) * 100)}%
                                                </span>
                                            </div>
                                            <p className="leading-relaxed text-xs" dir="auto">{block.text}</p>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}
                    </ResultCard>
                </div>
            )}

            {/* Idle State */}
            {!result && !error && !loading && (
                <div className="ai-idle-state animate-fade-in-up delay-200">
                    <svg width="120" height="120" viewBox="0 0 200 200" className="opacity-60 mb-4">
                        <defs>
                            <linearGradient id="textGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                                <stop offset="0%" stopColor="#0f172a" />
                                <stop offset="100%" stopColor="#64748b" />
                            </linearGradient>
                        </defs>
                        <circle cx="100" cy="100" r="80" fill="none" stroke="#e2e8f0" strokeWidth="1.5" strokeDasharray="10 6" className="ai-ring-outer" />
                        <circle cx="100" cy="100" r="55" fill="none" stroke="#f1f5f9" strokeWidth="1" className="ai-ring-inner" />
                        {/* Document icon */}
                        <rect x="70" y="60" width="60" height="80" rx="8" fill="none" stroke="url(#textGrad)" strokeWidth="2" opacity="0.5" />
                        <line x1="82" y1="80" x2="118" y2="80" stroke="#94a3b8" strokeWidth="2" strokeLinecap="round" />
                        <line x1="82" y1="92" x2="110" y2="92" stroke="#cbd5e1" strokeWidth="2" strokeLinecap="round" />
                        <line x1="82" y1="104" x2="114" y2="104" stroke="#94a3b8" strokeWidth="2" strokeLinecap="round" />
                        <line x1="82" y1="116" x2="100" y2="116" stroke="#cbd5e1" strokeWidth="2" strokeLinecap="round" />
                        {/* Scanning particles */}
                        <circle cx="100" cy="30" r="2" fill="#0f172a" className="ai-particle ai-p1" />
                        <circle cx="160" cy="100" r="2" fill="#334155" className="ai-particle ai-p2" />
                        <circle cx="100" cy="170" r="2" fill="#64748b" className="ai-particle ai-p3" />
                    </svg>
                    <p className="text-slate-400 font-bold text-center">ألصق النص أعلاه واضغط تحليل لبدء الفحص</p>
                </div>
            )}
        </div>
    );
};

export default TextVerification;
