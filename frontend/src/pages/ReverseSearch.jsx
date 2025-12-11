import { useState } from 'react';
import { Search, ExternalLink, RefreshCw } from 'lucide-react';
import apiClient from '../services/apiClient';
import GlassCard from '../components/GlassCard';
import GradientButton from '../components/GradientButton';
import DropZone from '../components/DropZone';

const ReverseSearch = () => {
    const [file, setFile] = useState(null);
    const [loading, setLoading] = useState(false);
    const [results, setResults] = useState(null);
    const [error, setError] = useState(null);

    const handleSearch = async () => {
        if (!file) return;

        setLoading(true);
        setError(null);
        setResults(null);

        const formData = new FormData();
        formData.append('file', file);

        try {
            const response = await apiClient.post('/api/upload', formData, {
                headers: { 'Content-Type': 'multipart/form-data' }
            });

            setResults(response.data);
        } catch (err) {
            console.error(err);
            setError(err.response?.data?.error || 'فشل الاتصال بالخادم');
        } finally {
            setLoading(false);
        }
    };

    const handleReset = () => {
        setFile(null);
        setResults(null);
        setError(null);
    };

    const engines = [
        { id: 'google', name: 'Google', gradient: 'from-blue-500 to-blue-600' },
        { id: 'bing', name: 'Bing', gradient: 'from-teal-500 to-teal-600' },
        { id: 'yandex', name: 'Yandex', gradient: 'from-red-500 to-rose-600' },
        { id: 'tineye', name: 'TinEye', gradient: 'from-amber-500 to-orange-600' }
    ];

    return (
        <div className="max-w-4xl mx-auto">
            {/* Page Header */}
            <div className="text-center mb-10 animate-fade-in-up">
                <h1 className="text-3xl font-black text-slate-800 mb-3">
                    <span className="gradient-text">البحث اليدوي</span> عن مصدر الصورة
                </h1>
                <p className="text-slate-600">ارفع صورة للكشف عن أماكن نشرها عبر محركات البحث العالمية.</p>
            </div>

            <div className="grid md:grid-cols-2 gap-8 items-start">
                {/* Upload Section */}
                <div className="space-y-6 animate-fade-in-up delay-100">
                    <GlassCard className="p-6">
                        <DropZone
                            onFileSelect={(f) => setFile(f)}
                            headerText="ارفع الصورة للبحث"
                        />

                        <div className="mt-6 flex gap-3">
                            <GradientButton
                                onClick={handleSearch}
                                disabled={!file}
                                isLoading={loading}
                                icon={Search}
                                className="flex-1"
                            >
                                بحث
                            </GradientButton>

                            {results && (
                                <button
                                    onClick={handleReset}
                                    className="px-4 py-3 rounded-xl bg-white/60 backdrop-blur-sm text-slate-600 font-bold hover:bg-white hover:shadow-md transition-all border border-slate-200/50"
                                >
                                    <RefreshCw className="w-5 h-5" />
                                </button>
                            )}
                        </div>
                    </GlassCard>
                </div>

                {/* Results Section */}
                <div className="space-y-6 animate-fade-in-up delay-200">
                    {!results && !error && (
                        <div className="h-64 flex flex-col items-center justify-center text-slate-400 border-2 border-dashed border-slate-200/50 rounded-2xl bg-white/30 backdrop-blur-sm">
                            <Search className="w-12 h-12 mb-3 opacity-50" />
                            <span className="text-center">ستظهر روابط البحث هنا</span>
                        </div>
                    )}

                    {error && (
                        <div className="p-4 glass-card bg-red-50/80 border-red-200 text-red-700">
                            {error}
                        </div>
                    )}

                    {results && (
                        <GlassCard className="p-6">
                            <div className="mb-6 pb-6 border-b border-slate-200/50">
                                <img
                                    src={results.imageUrl}
                                    alt="Search Target"
                                    className="w-full h-48 object-cover rounded-xl shadow-lg mb-4"
                                />
                                <h3 className="font-black text-slate-800 text-lg">نتائج البحث</h3>
                                <p className="text-sm text-slate-500">تم تجهيز روابط البحث المباشرة للصورة</p>
                            </div>

                            <div className="grid grid-cols-1 gap-3">
                                {engines.map((engine) => {
                                    const url = results.searchResults?.[engine.id];
                                    if (!url) return null;

                                    return (
                                        <a
                                            key={engine.id}
                                            href={url}
                                            target="_blank"
                                            rel="noreferrer"
                                            className={`flex items-center justify-between p-4 rounded-xl text-white shadow-lg transition-all transform hover:-translate-y-1 hover:shadow-xl bg-gradient-to-r ${engine.gradient}`}
                                        >
                                            <span className="font-bold flex items-center">
                                                <Search className="w-4 h-4 ml-2 opacity-80" />
                                                بحث في {engine.name}
                                            </span>
                                            <ExternalLink className="w-5 h-5 opacity-80" />
                                        </a>
                                    );
                                })}
                            </div>
                        </GlassCard>
                    )}
                </div>
            </div>
        </div>
    );
};

export default ReverseSearch;
