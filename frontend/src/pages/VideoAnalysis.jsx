import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Video, Film, AlertTriangle, Download, ScanFace, Globe, Search, ShieldCheck } from 'lucide-react';
import apiClient from '../services/apiClient';
import GlassCard from '../components/GlassCard';
import GradientButton from '../components/GradientButton';
import DropZone from '../components/DropZone';

const VideoAnalysis = () => {
    const navigate = useNavigate();
    const [file, setFile] = useState(null);
    const [loading, setLoading] = useState(false);
    const [aiLoading, setAiLoading] = useState(false);
    const [frames, setFrames] = useState(null);
    const [aiResult, setAiResult] = useState(null);
    const [error, setError] = useState(null);

    // Helper to convert base64 to file
    const dataURLtoFile = (dataurl, filename) => {
        let arr = dataurl.split(','), mime = arr[0].match(/:(.*?);/)[1],
            bstr = atob(arr[1]), n = bstr.length, u8arr = new Uint8Array(n);
        while (n--) {
            u8arr[n] = bstr.charCodeAt(n);
        }
        return new File([u8arr], filename, { type: mime });
    };

    const handleAction = (frame, action) => {
        const imageFile = dataURLtoFile(frame.data, `frame_${frame.timestamp}.jpg`);

        switch (action) {
            case 'ai-detect':
                navigate('/ai-detection', { state: { file: imageFile } });
                break;
            case 'direct-search':
                navigate('/direct-search', { state: { file: imageFile } });
                break;
            case 'manual-search':
                navigate('/reverse-search', { state: { file: imageFile } });
                break;
            default:
                break;
        }
    };

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
                headers: { 'Content-Type': 'multipart/form-data' }
            });
            setFrames(response.data.frames);
        } catch (err) {
            console.error(err);
            setError(err.response?.data?.error || 'فشل استخراج الإطارات');
        } finally {
            setLoading(false);
        }
    };

    const handleAnalyzeAI = async () => {
        if (!file) return;
        setAiLoading(true);
        setError(null);
        setAiResult(null);

        const formData = new FormData();
        formData.append('file', file);

        try {
            const response = await apiClient.post('/api/analyze-video', formData, {
                headers: { 'Content-Type': 'multipart/form-data' },
                timeout: 125000 // 125s timeout (backend is 120s)
            });

            if (response.data.success) {
                setAiResult(response.data.data);
            } else {
                setError(response.data.error || 'فشل تحليل الفيديو');
            }
        } catch (err) {
            console.error(err);
            setError(err.response?.data?.error || 'فشل الاتصال بالخادم (قد يكون الملف كبيراً جداً)');
        } finally {
            setAiLoading(false);
        }
    };

    const ScoreBar = ({ label, score, colorClass }) => (
        <div className="mb-3">
            <div className="flex justify-between text-sm font-bold mb-1">
                <span className="text-slate-700">{label}</span>
                <span className={colorClass}>{Math.round(score * 100)}%</span>
            </div>
            <div className="h-2.5 bg-slate-100 rounded-full overflow-hidden">
                <div
                    className={`h-full rounded-full transition-all duration-1000 ${colorClass.replace('text-', 'bg-')}`}
                    style={{ width: `${score * 100}%` }}
                ></div>
            </div>
        </div>
    );

    return (
        <div className="max-w-6xl mx-auto">
            {/* Page Header */}
            <div className="text-center mb-10 animate-fade-in-up">
                <h1 className="text-3xl font-black text-slate-800 mb-3">
                    <span className="gradient-text">تحليل الفيديو المتقدم</span>
                </h1>
                <p className="text-slate-600">كشف التزييف العميق (Deepfake) أو استخراج الإطارات للبحث العكسي.</p>
            </div>

            <GlassCard className="p-6 mb-8 animate-fade-in-up delay-100">
                <DropZone
                    onFileSelect={(f) => { setFile(f); setFrames(null); setAiResult(null); setError(null); }}
                    headerText="ارفع فيديو للتحليل"
                    subText="MP4, AVI, MOV (Max 200MB)"
                    accept="video/*"
                />

                <div className="mt-8 grid md:grid-cols-2 gap-4">
                    <GradientButton
                        onClick={handleAnalyzeAI}
                        disabled={!file || loading || aiLoading}
                        isLoading={aiLoading}
                        icon={ScanFace}
                        className="w-full bg-gradient-to-r from-violet-500 to-fuchsia-600 hover:from-violet-600 hover:to-fuchsia-700 shadow-violet-200"
                    >
                        فحص الذكاء الاصطناعي (Full Video)
                    </GradientButton>

                    <GradientButton
                        onClick={handleExtractFrames}
                        disabled={!file || loading || aiLoading}
                        isLoading={loading}
                        icon={Film}
                        className="w-full"
                    >
                        استخراج الإطارات (Manual Checks)
                    </GradientButton>
                </div>
            </GlassCard>

            {error && (
                <div className="p-4 mb-8 glass-card bg-red-50/80 border-red-200 text-red-700 flex items-center animate-fade-in-up">
                    <AlertTriangle className="w-5 h-5 ml-2" />
                    {error}
                </div>
            )}

            {/* AI Analysis Results */}
            {aiResult && (
                <div className="mb-12 animate-fade-in-up">
                    <h2 className="text-xl font-bold text-slate-800 flex items-center mb-6">
                        <span className="w-1.5 h-6 bg-gradient-to-b from-violet-500 to-fuchsia-500 rounded-full ml-3"></span>
                        نتائج فحص الذكاء الاصطناعي
                    </h2>

                    <div className="grid md:grid-cols-3 gap-6">
                        {/* Video Score */}
                        <GlassCard className="p-5">
                            <h3 className="font-bold text-slate-800 mb-4 flex items-center">
                                <Video className="w-5 h-5 ml-2 text-violet-500" />
                                الفيديو (Video)
                            </h3>
                            <div className="text-center mb-4">
                                <div className={`inline-flex items-center justify-center w-16 h-16 rounded-full mb-2 ${aiResult.report.ai.video > 0.5 ? 'bg-red-100 text-red-600' : 'bg-green-100 text-green-600'
                                    }`}>
                                    {aiResult.report.ai.video > 0.5 ? <AlertTriangle className="w-8 h-8" /> : <ShieldCheck className="w-8 h-8" />}
                                </div>
                                <p className={`font-black ${aiResult.report.ai.video > 0.5 ? 'text-red-600' : 'text-green-600'}`}>
                                    {aiResult.report.ai.video > 0.5 ? 'معدل (AI)' : 'حقيقي'}
                                </p>
                            </div>
                            <ScoreBar label="احتمالية AI" score={aiResult.report.ai.video} colorClass="text-violet-600" />
                        </GlassCard>

                        {/* Voice Score */}
                        <GlassCard className="p-5">
                            <h3 className="font-bold text-slate-800 mb-4 flex items-center">
                                <span className="ml-2 text-2xl">🎤</span>
                                الصوت (Voice)
                            </h3>
                            <div className="text-center mb-4">
                                <span className={`font-black ${aiResult.report.ai.voice > 0.5 ? 'text-red-600' : 'text-green-600'}`}>
                                    {aiResult.report.ai.voice > 0.5 ? 'معدل (AI)' : 'حقيقي'}
                                </span>
                            </div>
                            <ScoreBar label="احتمالية AI" score={aiResult.report.ai.voice} colorClass="text-fuchsia-600" />
                        </GlassCard>

                        {/* Music Score */}
                        <GlassCard className="p-5">
                            <h3 className="font-bold text-slate-800 mb-4 flex items-center">
                                <span className="ml-2 text-2xl">🎵</span>
                                الموسيقى (Music)
                            </h3>
                            <div className="text-center mb-4">
                                <span className={`font-black ${aiResult.report.ai.music > 0.5 ? 'text-red-600' : 'text-green-600'}`}>
                                    {aiResult.report.ai.music > 0.5 ? 'معدل (AI)' : 'حقيقي'}
                                </span>
                            </div>
                            <ScoreBar label="احتمالية AI" score={aiResult.report.ai.music} colorClass="text-pink-600" />
                        </GlassCard>
                    </div>
                </div>
            )}

            {/* Extracted Frames */}
            {frames && (
                <div className="animate-fade-in-up">
                    <div className="flex items-center justify-between mb-6">
                        <h2 className="text-xl font-bold text-slate-800 flex items-center">
                            <span className="w-1.5 h-6 bg-gradient-to-b from-primary-500 to-sky-500 rounded-full ml-3"></span>
                            الإطارات المستخرجة ({frames.length})
                        </h2>
                        <p className="text-sm text-slate-500">اختر إطاراً للتحليل المتقدم</p>
                    </div>

                    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
                        {frames.map((frame, idx) => (
                            <div key={idx} className="glass-card overflow-hidden group hover:shadow-xl transition-all duration-300">
                                <div className="aspect-video relative bg-slate-100">
                                    <img
                                        src={frame.data}
                                        alt={`Frame ${idx}`}
                                        className="w-full h-full object-cover"
                                    />
                                    <div className="absolute top-2 right-2 bg-black/60 backdrop-blur-sm text-white text-xs px-2 py-1 rounded-lg font-medium">
                                        {frame.timestamp.toFixed(1)}s
                                    </div>
                                </div>

                                <div className="p-3 space-y-2">
                                    {/* Action Buttons */}
                                    <button
                                        onClick={() => handleAction(frame, 'direct-search')}
                                        className="w-full flex items-center justify-center gap-2 text-xs font-bold py-2 bg-sky-50 text-sky-600 rounded-lg hover:bg-sky-100 transition-colors"
                                    >
                                        <Globe className="w-3.5 h-3.5" /> البحث المباشر (Zen)
                                    </button>

                                    <div className="flex gap-2">
                                        <button
                                            onClick={() => handleAction(frame, 'manual-search')}
                                            className="flex-1 flex items-center justify-center gap-1 text-[10px] font-bold py-2 bg-emerald-50 text-emerald-600 rounded-lg hover:bg-emerald-100 transition-colors"
                                            title="البحث اليدوي"
                                        >
                                            <Search className="w-3.5 h-3.5" /> يدوي
                                        </button>
                                        <button
                                            onClick={() => handleAction(frame, 'ai-detect')}
                                            className="flex-1 flex items-center justify-center gap-1 text-[10px] font-bold py-2 bg-violet-50 text-violet-600 rounded-lg hover:bg-violet-100 transition-colors"
                                            title="كشف AI"
                                        >
                                            <ScanFace className="w-3.5 h-3.5" /> كشف AI
                                        </button>
                                    </div>

                                    <a
                                        href={frame.data}
                                        download={`frame_${idx}.jpg`}
                                        className="block text-center text-[10px] text-slate-400 hover:text-slate-600 mt-2"
                                    >
                                        تحميل الصورة
                                    </a>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
};

export default VideoAnalysis;
