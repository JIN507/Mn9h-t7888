import { useState, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { Globe, ExternalLink, Clock, MapPin } from 'lucide-react';
import apiClient from '../services/apiClient';
import GlassCard from '../components/GlassCard';
import GradientButton from '../components/GradientButton';
import DropZone from '../components/DropZone';
import ErrorBanner from '../components/ErrorBanner';
import useJob from '../hooks/useJob';

// Match-bucket labels (exact / similar / page mention)
const MATCH_TYPE_LABELS = {
    exact: { text: 'مطابقة تامة', cls: 'bg-emerald-100 text-emerald-700' },
    similar: { text: 'صورة مشابهة', cls: 'bg-sky-100 text-sky-700' },
    page_match: { text: 'ذكر في صفحة', cls: 'bg-amber-100 text-amber-700' },
};

const Provenance = () => {
    const location = useLocation();
    const [file, setFile] = useState(null);
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState(null);
    const [error, setError] = useState(null);
    const [jobId, setJobId] = useState(null);
    const { progress: jobProgress, result: jobResult, error: jobError } = useJob(jobId);

    // Handle file passed from navigation
    useEffect(() => {
        if (location.state?.file) {
            setFile(location.state.file);
        }
    }, [location.state]);

    // Provenance runs as a background job (202 + SSE)
    const handleAnalyze = async () => {
        if (!file) return;

        setLoading(true);
        setError(null);
        setResult(null);
        setJobId(null);

        const formData = new FormData();
        formData.append('file', file);

        try {
            // 1. Upload to get URL (+ hashes for caching)
            const uploadResponse = await apiClient.post('/api/upload', formData, {
                headers: { 'Content-Type': 'multipart/form-data' }
            });

            if (!uploadResponse.data.imageUrl) {
                throw new Error('Failed to upload image');
            }

            // 2. Queue the provenance job
            const provResponse = await apiClient.post('/api/provenance', {
                image_url: uploadResponse.data.imageUrl,
                image_hash: uploadResponse.data.image_hash,
                image_phash: uploadResponse.data.image_phash
            });

            if (provResponse.status === 202 && provResponse.data.job_id) {
                setJobId(provResponse.data.job_id);
            } else {
                throw new Error(provResponse.data?.error || 'فشل تحليل المصدر');
            }
        } catch (err) {
            console.error(err);
            setError(err.response?.data?.error || err.message || 'فشل تحليل المصدر');
            setLoading(false);
        }
    };

    useEffect(() => {
        if (jobResult) {
            setResult(jobResult.payload || null);
            setLoading(false);
            setJobId(null);
        }
    }, [jobResult]);

    useEffect(() => {
        if (jobError) {
            setError(jobError);
            setLoading(false);
            setJobId(null);
        }
    }, [jobError]);

    return (
        <div className="max-w-6xl mx-auto">
            {/* Page Header */}
            <div className="text-center mb-10 animate-fade-in-up">
                <h1 className="text-3xl font-black text-slate-800 mb-3">
                    <span className="gradient-text">أصل المحتوى</span> (Provenance)
                </h1>
                <p className="text-slate-600">تتبع المصدر الأصلي للصورة ووقت ظهورها الأول على الشبكة.</p>
            </div>

            <div className="grid md:grid-cols-2 gap-8 items-start">
                {/* Upload Section */}
                <div className="space-y-6 animate-fade-in-up delay-100">
                    <GlassCard className="p-6">
                        <DropZone onFileSelect={(f) => setFile(f)} headerText="ارفع الصورة للتحقق من المصدر" />
                        <div className="mt-6">
                            <GradientButton
                                onClick={handleAnalyze}
                                disabled={!file}
                                isLoading={loading}
                                icon={Globe}
                                className="w-full"
                            >
                                تحليل المصدر
                            </GradientButton>
                        </div>
                    </GlassCard>
                </div>

                {/* Results Section */}
                <div className="space-y-6 animate-fade-in-up delay-200">
                    <ErrorBanner variant="panel" message={error} />

                    {loading && jobProgress.length > 0 && (
                        <div className="p-4 glass-card border-slate-200 text-slate-600 text-sm font-bold animate-fade-in">
                            {jobProgress[jobProgress.length - 1]}
                        </div>
                    )}

                    {result && (
                        <div className="space-y-6">
                            {/* First Seen Card */}
                            <GlassCard className="p-6">
                                <h3 className="font-black text-lg mb-4 text-slate-800 flex items-center">
                                    <Clock className="w-5 h-5 ml-2 text-primary-500" />
                                    الظهور الأول المكتشف
                                </h3>
                                {result.first_seen ? (
                                    <div className="bg-gradient-to-br from-emerald-50 to-green-50 border border-green-200 rounded-xl p-4">
                                        <div className="flex items-center gap-2 mb-1">
                                            <p className="font-black text-green-800 text-lg">{result.first_seen.date}</p>
                                            {MATCH_TYPE_LABELS[result.first_seen.match_type] && (
                                                <span className={`text-xs font-bold px-2 py-0.5 rounded-full ${MATCH_TYPE_LABELS[result.first_seen.match_type].cls}`}>
                                                    {MATCH_TYPE_LABELS[result.first_seen.match_type].text}
                                                </span>
                                            )}
                                        </div>
                                        <p className="text-green-700 text-sm mb-3 flex items-center">
                                            <MapPin className="w-4 h-4 ml-1" />
                                            {result.first_seen.domain}
                                        </p>
                                        <a
                                            href={result.first_seen.link}
                                            target="_blank"
                                            rel="noreferrer"
                                            className="inline-flex items-center text-green-600 hover:text-green-800 text-sm font-bold transition-colors"
                                        >
                                            زيارة المصدر
                                            <ExternalLink className="w-4 h-4 mr-2" />
                                        </a>
                                    </div>
                                ) : (
                                    <p className="text-slate-500">لم يتم تحديد تاريخ نشر مؤكد.</p>
                                )}
                            </GlassCard>

                            {/* Timeline Card */}
                            {result.timeline && result.timeline.length > 0 && (
                                <GlassCard className="p-6">
                                    <h3 className="font-black text-lg mb-4 text-slate-800 flex items-center">
                                        <span className="w-1.5 h-5 bg-gradient-to-b from-primary-500 to-sky-500 rounded-full ml-2"></span>
                                        سجل الظهور الزمني ({result.timeline.length})
                                    </h3>
                                    <div className="space-y-4 max-h-[400px] overflow-y-auto pr-2">
                                        {result.timeline.map((item, i) => (
                                            <div
                                                key={i}
                                                className="flex gap-3 items-start border-r-2 border-primary-200 pr-4 relative group"
                                            >
                                                <div className="absolute -right-[5px] top-1.5 w-2.5 h-2.5 rounded-full bg-gradient-to-br from-primary-500 to-sky-500 group-hover:scale-125 transition-transform"></div>
                                                <div className="flex-1">
                                                    <span className="text-xs font-bold text-primary-600 bg-primary-50 px-2 py-0.5 rounded-full">
                                                        {item.timestamp ? item.timestamp.split('T')[0] : 'تاريخ غير معروف'}
                                                    </span>
                                                    {MATCH_TYPE_LABELS[item.match_type] && (
                                                        <span className={`text-xs font-bold px-2 py-0.5 rounded-full mr-1.5 ${MATCH_TYPE_LABELS[item.match_type].cls}`}>
                                                            {MATCH_TYPE_LABELS[item.match_type].text}
                                                        </span>
                                                    )}
                                                    <h4 className="font-bold text-sm mt-2 mb-0.5 text-slate-900">{item.domain}</h4>
                                                    <a
                                                        href={item.url}
                                                        target="_blank"
                                                        rel="noreferrer"
                                                        className="text-xs text-slate-500 hover:text-primary-600 truncate block transition-colors"
                                                    >
                                                        {item.title}
                                                    </a>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </GlassCard>
                            )}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default Provenance;
