import { useState, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { Search, Image as ImageIcon } from 'lucide-react';
import ErrorBanner from '../components/ErrorBanner';
import apiClient from '../services/apiClient';
import GlassCard from '../components/GlassCard';
import GradientButton from '../components/GradientButton';
import DropZone from '../components/DropZone';
import ResultsTimeline from '../components/ResultsTimeline';

const DirectSearch = () => {
    const location = useLocation();
    const [selectedFile, setSelectedFile] = useState(null);
    const [loading, setLoading] = useState(false);
    const [results, setResults] = useState(null);
    const [error, setError] = useState(null);
    const [debugInfo, setDebugInfo] = useState(null);

    // Helper to convert base64 to file
    const dataURLtoFile = (dataurl, filename) => {
        let arr = dataurl.split(','), mime = arr[0].match(/:(.*?);/)[1],
            bstr = atob(arr[1]), n = bstr.length, u8arr = new Uint8Array(n);
        while (n--) {
            u8arr[n] = bstr.charCodeAt(n);
        }
        return new File([u8arr], filename, { type: mime });
    };

    // Handle file passed from navigation (e.g. from Video Analysis)
    useEffect(() => {
        console.log('DirectSearch mounted. Location state:', location.state);
        // Handle direct file passing
        if (location.state?.file) {
            console.log('File received from navigation:', location.state.file);
            setSelectedFile(location.state.file);
        }
        // Handle dataUrl passing (safe for navigation)
        else if (location.state?.dataUrl) {
            console.log('DataURL received from navigation');
            try {
                const file = dataURLtoFile(location.state.dataUrl, location.state.fileName || 'image.jpg');
                setSelectedFile(file);
            } catch (e) {
                console.error('Failed to convert DataURL to File:', e);
            }
        }
        else {
            console.log('No file passed in navigation state');
        }
    }, [location.state]);

    const handleFileSelect = (file) => {
        setSelectedFile(file);
        setResults(null);
        setDebugInfo(null);
    };

    const handleSearch = async (e) => {
        e.preventDefault();
        if (!selectedFile) return;

        setLoading(true);
        setError(null);
        setResults(null);
        setDebugInfo(null);

        try {
            const formData = new FormData();
            formData.append('file', selectedFile);

            const response = await apiClient.post('/api/direct-search', formData, {
                headers: { 'Content-Type': 'multipart/form-data' },
                timeout: 180000 // 3 minute timeout for image upload
            });

            console.log('Direct Search Response:', response.data);
            setDebugInfo(`عدد النتائج: ${response.data.timeline?.length || 0}`);

            if (response.data.success) {
                const timeline = response.data.timeline || [];
                if (timeline.length > 0) {
                    setResults(timeline);
                } else {
                    setError('لم يتم العثور على نتائج. جرب صورة مختلفة.');
                }
            } else {
                setError(response.data.error || 'حدث خطأ أثناء البحث');
            }
        } catch (err) {
            console.error('Direct Search Error:', err);
            if (err.code === 'ECONNABORTED' || err.message.includes('timeout')) {
                setError('انتهت مهلة الاتصال. يرجى المحاولة مرة أخرى.');
            } else {
                setError(err.response?.data?.error || err.message || 'فشل الاتصال بالخادم');
            }
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="max-w-4xl mx-auto text-right">
            {/* Page Header */}
            <div className="mb-8 animate-fade-in-up">
                <h1 className="text-3xl font-black text-slate-800 mb-3">
                    <span className="gradient-text">البحث المباشر بالصورة</span> (Zenserp)
                </h1>
                <p className="text-slate-600">ابحث عن تاريخ ظهور الصورة عبر الزمن في جدول زمني تفاعلي.</p>
            </div>

            <GlassCard className="mb-8 overflow-visible animate-fade-in-up delay-100">
                <div className="p-6">
                    {/* Header with Icon */}
                    <div className="flex items-center gap-3 mb-6 pb-4 border-b border-slate-200/50">
                        <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-primary-500 to-sky-500 flex items-center justify-center">
                            <ImageIcon className="w-6 h-6 text-white" />
                        </div>
                        <div>
                            <h2 className="font-bold text-slate-800">رفع صورة للبحث العكسي</h2>
                            <p className="text-sm text-slate-500">قم برفع الصورة لتتبع ظهورها على الإنترنت</p>
                        </div>
                    </div>

                    <form onSubmit={handleSearch}>
                        <div className="mb-6">
                            <DropZone
                                onFileSelect={handleFileSelect}
                                headerText="ارفع صورة للبحث المباشر"
                                subText="JPG, PNG, WEBP (Max 10MB)"
                                initialFile={selectedFile}
                            />
                        </div>

                        <div className="flex justify-center mt-6">
                            <GradientButton
                                type="submit"
                                isLoading={loading}
                                icon={Search}
                                disabled={!selectedFile}
                                className="px-10"
                            >
                                تحليل الجدول الزمني
                            </GradientButton>
                        </div>
                    </form>
                </div>
            </GlassCard>

            {debugInfo && (
                <div className="p-3 mb-4 glass-card bg-blue-50/80 border-blue-200 text-blue-700 text-sm animate-fade-in-up">
                    {debugInfo}
                </div>
            )}

            <ErrorBanner variant="panel" message={error} className="mb-8 animate-fade-in-up" />

            {results && results.length > 0 && (
                <div className="animate-fade-in-up">
                    <h2 className="text-2xl font-bold text-slate-800 mb-6 flex items-center">
                        <span className="w-1.5 h-8 bg-gradient-to-b from-primary-500 to-sky-500 rounded-full ml-3"></span>
                        التسلسل الزمني للنتائج ({results.length})
                    </h2>
                    <ResultsTimeline results={results} />
                </div>
            )}
        </div>
    );
};

export default DirectSearch;
