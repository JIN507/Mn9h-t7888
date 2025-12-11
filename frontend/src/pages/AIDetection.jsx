import { useState } from 'react';
import { ShieldCheck, AlertTriangle, Sparkles, Cpu, Brain, X } from 'lucide-react';
import apiClient from '../services/apiClient';
import GlassCard from '../components/GlassCard';
import GradientButton from '../components/GradientButton';
import DropZone from '../components/DropZone';

// Result card component for each API
const ResultCard = ({ result, title, icon: Icon, gradientFrom, gradientTo, error }) => {
    // Handle error state
    if (error) {
        return (
            <GlassCard className="p-5 border-red-200 bg-red-50/50">
                <div className="flex items-center gap-3 mb-4 pb-3 border-b border-red-200/50">
                    <div className={`w-10 h-10 rounded-xl flex items-center justify-center bg-gradient-to-br ${gradientFrom} ${gradientTo}`}>
                        <Icon className="w-5 h-5 text-white" />
                    </div>
                    <div>
                        <h3 className="font-bold text-slate-800">{title}</h3>
                        <p className="text-xs text-red-500">خطأ في الاتصال</p>
                    </div>
                </div>
                <div className="text-center py-4">
                    <X className="w-12 h-12 text-red-400 mx-auto mb-2" />
                    <p className="text-red-600 text-sm">{error}</p>
                </div>
            </GlassCard>
        );
    }

    if (!result) return null;

    const isAI = result.is_ai || (result.confidence_ai && result.confidence_ai > 0.5);

    return (
        <GlassCard className="p-5">
            <div className="flex items-center gap-3 mb-4 pb-3 border-b border-slate-200/50">
                <div className={`w-10 h-10 rounded-xl flex items-center justify-center bg-gradient-to-br ${gradientFrom} ${gradientTo}`}>
                    <Icon className="w-5 h-5 text-white" />
                </div>
                <div>
                    <h3 className="font-bold text-slate-800">{title}</h3>
                    <p className="text-xs text-slate-500">{result.source || 'AI Detection'}</p>
                </div>
            </div>

            <div className="text-center mb-4">
                <div className={`inline-flex items-center justify-center w-16 h-16 rounded-full mb-3 ${isAI
                        ? 'bg-gradient-to-br from-red-400 to-rose-500 text-white'
                        : 'bg-gradient-to-br from-emerald-400 to-green-500 text-white'
                    }`}>
                    <ShieldCheck className="w-8 h-8" />
                </div>
                <h4 className="text-xl font-black">
                    {result.verdict || (isAI ? 'مولدة بالذكاء الاصطناعي' : 'صورة حقيقية')}
                </h4>
            </div>

            <div className="space-y-3">
                <div>
                    <div className="flex justify-between text-xs font-bold mb-1">
                        <span>احتمالية AI</span>
                        <span className="text-red-600">{((result.confidence_ai || 0) * 100).toFixed(1)}%</span>
                    </div>
                    <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                        <div
                            className="h-full bg-gradient-to-r from-red-400 to-rose-500 transition-all duration-1000 ease-out rounded-full"
                            style={{ width: `${(result.confidence_ai || 0) * 100}%` }}
                        ></div>
                    </div>
                </div>

                <div>
                    <div className="flex justify-between text-xs font-bold mb-1">
                        <span>احتمالية بشري</span>
                        <span className="text-green-600">{((result.confidence_human || 0) * 100).toFixed(1)}%</span>
                    </div>
                    <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                        <div
                            className="h-full bg-gradient-to-r from-emerald-400 to-green-500 transition-all duration-1000 ease-out rounded-full"
                            style={{ width: `${(result.confidence_human || 0) * 100}%` }}
                        ></div>
                    </div>
                </div>
            </div>

            {result.generator && result.generator !== 'unknown' && (
                <div className="mt-3 text-xs text-slate-500 bg-slate-50 p-2 rounded-lg">
                    <span className="font-bold">النموذج المحتمل:</span> {result.generator}
                </div>
            )}
        </GlassCard>
    );
};

const AIDetection = () => {
    const [file, setFile] = useState(null);
    const [loading, setLoading] = useState(false);
    const [results, setResults] = useState({ thehive: null, aiornot: null });
    const [errors, setErrors] = useState({ thehive: null, aiornot: null });

    const handleAnalyze = async () => {
        if (!file) return;

        setLoading(true);
        setErrors({ thehive: null, aiornot: null });
        setResults({ thehive: null, aiornot: null });

        try {
            // Create FormData for both services
            const formData1 = new FormData();
            formData1.append('image', file);
            formData1.append('service', 'thehive');

            const formData2 = new FormData();
            formData2.append('image', file);
            formData2.append('service', 'aiornot');

            // Call both APIs simultaneously
            const [response1, response2] = await Promise.allSettled([
                apiClient.post('/api/ai-detection', formData1, {
                    headers: { 'Content-Type': 'multipart/form-data' },
                    timeout: 60000 // 60 second timeout
                }),
                apiClient.post('/api/ai-detection', formData2, {
                    headers: { 'Content-Type': 'multipart/form-data' },
                    timeout: 60000
                })
            ]);

            // Process results
            const newResults = { thehive: null, aiornot: null };
            const newErrors = { thehive: null, aiornot: null };

            if (response1.status === 'fulfilled') {
                const data = response1.value.data;
                if (data.success === false || data.error) {
                    newErrors.thehive = data.error || 'فشل التحليل';
                } else {
                    newResults.thehive = data;
                }
            } else {
                console.error('TheHive API error:', response1.reason);
                newErrors.thehive = response1.reason?.response?.data?.error || 'فشل الاتصال بالنموذج الأول';
            }

            if (response2.status === 'fulfilled') {
                const data = response2.value.data;
                if (data.success === false || data.error) {
                    newErrors.aiornot = data.error || 'فشل التحليل';
                } else {
                    newResults.aiornot = data;
                }
            } else {
                console.error('AI-or-Not API error:', response2.reason);
                newErrors.aiornot = response2.reason?.response?.data?.error || 'فشل الاتصال بالنموذج الثاني';
            }

            setResults(newResults);
            setErrors(newErrors);

        } catch (err) {
            console.error(err);
            setErrors({
                thehive: 'فشل التحليل',
                aiornot: 'فشل التحليل'
            });
        } finally {
            setLoading(false);
        }
    };

    const hasResults = results.thehive || results.aiornot;
    const hasErrors = errors.thehive || errors.aiornot;
    const showCards = hasResults || hasErrors;

    return (
        <div className="max-w-5xl mx-auto">
            {/* Page Header */}
            <div className="text-center mb-10 animate-fade-in-up">
                <h1 className="text-3xl font-black text-slate-800 mb-3">
                    <span className="gradient-text">كشف صور الذكاء الاصطناعي</span>
                </h1>
                <p className="text-slate-600">قم برفع الصورة لتحليلها باستخدام نماذج ذكاء اصطناعي متعددة.</p>
            </div>

            {/* Upload Section */}
            <div className="max-w-xl mx-auto mb-8 animate-fade-in-up delay-100">
                <GlassCard className="p-6">
                    <DropZone onFileSelect={(f) => setFile(f)} headerText="ارفع الصورة للتحليل" />

                    <div className="mt-6 flex justify-center">
                        <GradientButton
                            onClick={handleAnalyze}
                            disabled={!file}
                            isLoading={loading}
                            icon={ShieldCheck}
                            className="w-full"
                        >
                            تحليل باستخدام نموذجين
                        </GradientButton>
                    </div>
                </GlassCard>
            </div>

            {/* Results Section */}
            <div className="animate-fade-in-up delay-200">
                {!showCards && !loading && (
                    <div className="h-48 flex flex-col items-center justify-center text-slate-400 border-2 border-dashed border-slate-200/50 rounded-2xl bg-white/30 backdrop-blur-sm">
                        <Sparkles className="w-12 h-12 mb-3 opacity-50" />
                        <span className="text-center">ستظهر نتائج النموذجين هنا بعد التحليل</span>
                    </div>
                )}

                {showCards && (
                    <div className="grid md:grid-cols-2 gap-6">
                        <ResultCard
                            result={results.thehive}
                            error={errors.thehive}
                            title="النموذج الأول (Sightengine)"
                            icon={Cpu}
                            gradientFrom="from-violet-500"
                            gradientTo="to-purple-600"
                        />
                        <ResultCard
                            result={results.aiornot}
                            error={errors.aiornot}
                            title="النموذج الثاني (AI-or-Not)"
                            icon={Brain}
                            gradientFrom="from-sky-500"
                            gradientTo="to-blue-600"
                        />
                    </div>
                )}
            </div>
        </div>
    );
};

export default AIDetection;
