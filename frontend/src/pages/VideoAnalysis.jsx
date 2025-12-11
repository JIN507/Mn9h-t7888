import { useState } from 'react';
import { Video, Film, AlertTriangle, Download } from 'lucide-react';
import apiClient from '../services/apiClient';
import GlassCard from '../components/GlassCard';
import GradientButton from '../components/GradientButton';
import DropZone from '../components/DropZone';

const VideoAnalysis = () => {
    const [file, setFile] = useState(null);
    const [loading, setLoading] = useState(false);
    const [frames, setFrames] = useState(null);
    const [error, setError] = useState(null);

    const handleAnalyze = async () => {
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
            setError(err.response?.data?.error || 'فشل تحليل الفيديو');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="max-w-6xl mx-auto">
            {/* Page Header */}
            <div className="text-center mb-10 animate-fade-in-up">
                <h1 className="text-3xl font-black text-slate-800 mb-3">
                    <span className="gradient-text">تحليل الفيديو</span>
                </h1>
                <p className="text-slate-600">استخراج الإطارات من الفيديو للتحقق من صحة المحتوى.</p>
            </div>

            <GlassCard className="p-6 mb-8 animate-fade-in-up delay-100">
                <DropZone
                    onFileSelect={(f) => setFile(f)}
                    headerText="ارفع فيديو للتحليل"
                    subText="MP4, AVI, MOV"
                    accept="video/*"
                />

                <div className="mt-6 flex justify-center">
                    <GradientButton
                        onClick={handleAnalyze}
                        disabled={!file}
                        isLoading={loading}
                        icon={Film}
                        className="w-full md:w-1/3"
                    >
                        استخراج الإطارات
                    </GradientButton>
                </div>
            </GlassCard>

            {error && (
                <div className="p-4 mb-8 glass-card bg-red-50/80 border-red-200 text-red-700 flex items-center animate-fade-in-up">
                    <AlertTriangle className="w-5 h-5 ml-2" />
                    {error}
                </div>
            )}

            {frames && (
                <div className="animate-fade-in-up">
                    <div className="flex items-center justify-between mb-6">
                        <h2 className="text-xl font-bold text-slate-800 flex items-center">
                            <span className="w-1.5 h-6 bg-gradient-to-b from-primary-500 to-sky-500 rounded-full ml-3"></span>
                            الإطارات المستخرجة ({frames.length})
                        </h2>
                    </div>

                    <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-4">
                        {frames.map((frame, idx) => (
                            <div
                                key={idx}
                                className="glass-card overflow-hidden group"
                            >
                                <div className="aspect-video relative">
                                    <img
                                        src={frame.data}
                                        alt={`Frame ${idx}`}
                                        className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
                                    />
                                    <div className="absolute top-2 right-2 bg-black/60 backdrop-blur-sm text-white text-xs px-2 py-1 rounded-lg font-medium">
                                        {frame.timestamp.toFixed(1)}s
                                    </div>

                                    {/* Hover Overlay */}
                                    <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex items-end justify-center pb-4">
                                        <a
                                            href={frame.data}
                                            download={`frame_${idx}.jpg`}
                                            className="flex items-center gap-1 text-white text-xs font-medium bg-white/20 backdrop-blur-sm px-3 py-1.5 rounded-full hover:bg-white/30 transition-colors"
                                        >
                                            <Download className="w-3 h-3" />
                                            تحميل
                                        </a>
                                    </div>
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
