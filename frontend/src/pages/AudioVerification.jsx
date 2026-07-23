import { useState } from 'react';
import { Mic, ShieldCheck, RotateCcw } from 'lucide-react';
import apiClient from '../services/apiClient';
import GlassCard from '../components/GlassCard';
import ResultCard from '../components/ResultCard';
import ErrorBanner from '../components/ErrorBanner';
import ConfidenceGauge from '../components/ConfidenceGauge';

const AudioVerification = () => {
    const [file, setFile] = useState(null);
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState(null);
    const [error, setError] = useState(null);

    const handleFileChange = (e) => {
        if (e.target.files[0]) {
            setFile(e.target.files[0]);
        }
    };

    const handleAnalyze = async () => {
        if (!file) return;

        setLoading(true);
        setError(null);
        setResult(null);

        const formData = new FormData();
        formData.append('audio', file);

        try {
            const response = await apiClient.post('/api/verify-audio', formData, {
                headers: { 'Content-Type': 'multipart/form-data' },
                timeout: 60000
            });
            setResult(response.data);
        } catch (err) {
            console.error(err);
            setError(err.response?.data?.error || 'فشل تحليل الملف الصوتي');
        } finally {
            setLoading(false);
        }
    };

    const handleReset = () => {
        setFile(null);
        setResult(null);
        setError(null);
    };

    const isAI = result?.is_ai_generated || result?.details?.verdict === 'ai';
    const confidence = result?.confidence || 0;

    return (
        <div className="max-w-4xl mx-auto page-container">
            {/* Header */}
            <div className="text-center mb-8 animate-fade-in-up">
                <h1 className="text-3xl md:text-4xl font-black text-slate-800 mb-4 tracking-tight">
                    كشف الصوت <span className="gradient-text">المولّد بالذكاء الاصطناعي</span>
                </h1>
                <p className="text-slate-500 max-w-lg mx-auto">
                    ارفع ملفاً صوتياً وسيقوم النظام بتحليله لمعرفة إن كان حقيقياً أو مُولّداً.
                </p>
            </div>

            {/* Upload Section */}
            <div className="animate-fade-in-up delay-100">
                <GlassCard className="p-6 border-slate-200 shadow-sm mb-8">
                    <div className="border-2 border-dashed border-slate-200 rounded-2xl p-8 bg-slate-50/50 transition-all hover:border-slate-300">
                        <input
                            type="file"
                            id="audio-upload"
                            accept="audio/*"
                            className="hidden"
                            onChange={handleFileChange}
                        />
                        <label htmlFor="audio-upload" className="cursor-pointer flex flex-col items-center">
                            <div className={`w-16 h-16 rounded-2xl flex items-center justify-center mb-4 transition-all border-2 ${
                                file
                                    ? 'bg-slate-900 border-slate-900'
                                    : 'bg-slate-100 border-slate-200'
                            }`}>
                                <Mic className={`w-8 h-8 ${file ? 'text-white' : 'text-slate-400'}`} />
                            </div>
                            <span className="text-base font-bold text-slate-700">
                                {file ? file.name : "اضغط لرفع ملف صوتي"}
                            </span>
                            <span className="text-sm text-slate-400 mt-1">MP3, WAV, M4A</span>
                        </label>
                    </div>

                    <div className="mt-6 flex gap-3">
                        <button
                            onClick={handleAnalyze}
                            disabled={!file || loading}
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
                                    <Mic className="w-5 h-5" />
                                    تحليل الصوت
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
                        <Mic className="w-7 h-7 text-slate-800 relative z-10" />
                    </div>
                    <h3 className="text-lg font-bold text-slate-800 mt-6 mb-2">جاري تحليل الصوت...</h3>
                    <p className="text-sm text-slate-500">يتم فحص الملف الصوتي عبر نماذج متخصصة</p>
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
                    <ResultCard title="نتيجة تحليل الصوت" isAI={isAI}
                                verdict={isAI ? 'صوت مولّد بالذكاء الاصطناعي' : 'صوت بشري حقيقي'}>
                        <ConfidenceGauge bars={[
                            { label: 'نسبة الثقة', value: confidence,
                              colorClass: isAI
                                  ? 'bg-gradient-to-r from-red-500 to-orange-400'
                                  : 'bg-gradient-to-r from-slate-800 to-slate-600' },
                        ]} />

                        {/* Audio Player */}
                        {result.audio_url && (
                            <div className="mt-6 pt-4 border-t border-slate-100">
                                <audio controls src={result.audio_url} className="w-full rounded-xl" />
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
                            <linearGradient id="audioGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                                <stop offset="0%" stopColor="#0f172a" />
                                <stop offset="100%" stopColor="#64748b" />
                            </linearGradient>
                        </defs>
                        <circle cx="100" cy="100" r="80" fill="none" stroke="#e2e8f0" strokeWidth="1.5" strokeDasharray="10 6" className="ai-ring-outer" />
                        <circle cx="100" cy="100" r="55" fill="none" stroke="#f1f5f9" strokeWidth="1" className="ai-ring-inner" />
                        {/* Mic icon */}
                        <rect x="88" y="65" width="24" height="40" rx="12" fill="none" stroke="url(#audioGrad)" strokeWidth="2" opacity="0.5" />
                        <line x1="100" y1="115" x2="100" y2="130" stroke="url(#audioGrad)" strokeWidth="2" strokeLinecap="round" opacity="0.5" />
                        <line x1="85" y1="130" x2="115" y2="130" stroke="url(#audioGrad)" strokeWidth="2" strokeLinecap="round" opacity="0.5" />
                        <path d="M78 100 Q78 115 100 115 Q122 115 122 100" fill="none" stroke="url(#audioGrad)" strokeWidth="2" opacity="0.3" />
                        {/* Sound waves */}
                        <path d="M68 85 Q63 100 68 115" fill="none" stroke="#94a3b8" strokeWidth="1.5" strokeLinecap="round" opacity="0.4" />
                        <path d="M132 85 Q137 100 132 115" fill="none" stroke="#94a3b8" strokeWidth="1.5" strokeLinecap="round" opacity="0.4" />
                        <circle cx="100" cy="30" r="2" fill="#0f172a" className="ai-particle ai-p1" />
                        <circle cx="160" cy="100" r="2" fill="#334155" className="ai-particle ai-p2" />
                        <circle cx="100" cy="170" r="2" fill="#64748b" className="ai-particle ai-p3" />
                    </svg>
                    <p className="text-slate-400 font-bold text-center">ارفع ملفاً صوتياً واضغط تحليل لبدء الفحص</p>
                </div>
            )}
        </div>
    );
};

export default AudioVerification;
