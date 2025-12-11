import { useState } from 'react';
import { Mic, CheckCircle, AlertTriangle, Music } from 'lucide-react';
import apiClient from '../services/apiClient';
import GlassCard from '../components/GlassCard';
import GradientButton from '../components/GradientButton';

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
                headers: { 'Content-Type': 'multipart/form-data' }
            });
            setResult(response.data);
        } catch (err) {
            console.error(err);
            setError(err.response?.data?.error || 'فشل تحليل الملف الصوتي');
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="max-w-4xl mx-auto">
            {/* Page Header */}
            <div className="text-center mb-10 animate-fade-in-up">
                <h1 className="text-3xl font-black text-slate-800 mb-3">
                    <span className="gradient-text">التحقق الصوتي</span>
                </h1>
                <p className="text-slate-600">كشف الملفات الصوتية المولدة بواسطة الذكاء الاصطناعي.</p>
            </div>

            <GlassCard className="p-8 mb-8 text-center animate-fade-in-up delay-100">
                <div className="border-2 border-dashed border-slate-300/50 rounded-2xl p-10 bg-white/20 backdrop-blur-sm mb-6 transition-all hover:border-primary-300 hover:bg-white/40">
                    <input
                        type="file"
                        id="audio-upload"
                        accept="audio/*"
                        className="hidden"
                        onChange={handleFileChange}
                    />
                    <label htmlFor="audio-upload" className="cursor-pointer flex flex-col items-center">
                        <div className={`w-20 h-20 rounded-2xl flex items-center justify-center mb-4 transition-all ${file
                                ? 'bg-gradient-to-br from-primary-500 to-sky-500'
                                : 'bg-gradient-to-br from-slate-100 to-slate-200'
                            }`}>
                            <Mic className={`w-10 h-10 ${file ? 'text-white' : 'text-slate-400'}`} />
                        </div>
                        <span className="text-lg font-bold text-slate-700">
                            {file ? file.name : "اضغط لرفع ملف صوتي"}
                        </span>
                        <span className="text-sm text-slate-500 mt-2">MP3, WAV, M4A</span>
                    </label>
                </div>

                <GradientButton
                    onClick={handleAnalyze}
                    disabled={!file}
                    isLoading={loading}
                    icon={Music}
                    className="w-full md:w-1/2"
                >
                    بدء التحليل
                </GradientButton>
            </GlassCard>

            {error && (
                <div className="p-4 glass-card bg-red-50/80 border-red-200 text-red-700 flex items-center mb-8 animate-fade-in-up">
                    <AlertTriangle className="w-5 h-5 ml-2" />
                    {error}
                </div>
            )}

            {result && (
                <GlassCard className="p-8 animate-fade-in-up">
                    <div className="text-center">
                        <div className={`inline-flex items-center justify-center w-24 h-24 rounded-full mb-6 ${result.is_ai_generated
                                ? 'bg-gradient-to-br from-red-400 to-rose-500'
                                : 'bg-gradient-to-br from-emerald-400 to-green-500'
                            }`}>
                            {result.is_ai_generated
                                ? <AlertTriangle className="w-12 h-12 text-white" />
                                : <CheckCircle className="w-12 h-12 text-white" />
                            }
                        </div>

                        <h2 className="text-3xl font-black mb-2">
                            {result.details?.verdict === 'ai' || result.is_ai_generated
                                ? "مولد بواسطة AI"
                                : "صوت بشري حقيقي"
                            }
                        </h2>

                        <p className="text-slate-500 mb-8">
                            نسبة الثقة: <span className="font-bold">{(result.confidence * 100).toFixed(1)}%</span>
                        </p>

                        <div className="bg-white/50 backdrop-blur-sm p-6 rounded-xl inline-block w-full md:w-2/3 text-left">
                            <div className="flex items-center justify-between mb-3">
                                <span className="text-sm font-bold text-slate-600">AI Probability</span>
                                <span className="text-sm font-black text-slate-900">{(result.confidence * 100).toFixed(1)}%</span>
                            </div>
                            <div className="h-4 bg-slate-200 rounded-full overflow-hidden">
                                <div
                                    className={`h-full rounded-full transition-all duration-1000 ${result.is_ai_generated
                                            ? 'bg-gradient-to-r from-red-400 to-rose-500'
                                            : 'bg-gradient-to-r from-emerald-400 to-green-500'
                                        }`}
                                    style={{ width: `${result.confidence * 100}%` }}
                                ></div>
                            </div>
                        </div>

                        {result.audio_url && (
                            <div className="mt-8 flex justify-center">
                                <audio controls src={result.audio_url} className="w-full md:w-2/3 rounded-xl" />
                            </div>
                        )}
                    </div>
                </GlassCard>
            )}
        </div>
    );
};

export default AudioVerification;
