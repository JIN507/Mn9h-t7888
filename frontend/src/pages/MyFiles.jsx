import { useState, useEffect } from 'react';
import { FolderOpen, Download, Trash2, Upload, FileText, Image as ImageIcon, Video, Music, FileSpreadsheet, AlertCircle, RefreshCw } from 'lucide-react';
import apiClient from '../services/apiClient';
import GlassCard from '../components/GlassCard';
import GradientButton from '../components/GradientButton';

const FileTypeIcon = ({ type }) => {
    const iconProps = { className: "w-6 h-6" };
    switch (type) {
        case 'image': return <ImageIcon {...iconProps} className="w-6 h-6 text-blue-500" />;
        case 'video': return <Video {...iconProps} className="w-6 h-6 text-purple-500" />;
        case 'audio': return <Music {...iconProps} className="w-6 h-6 text-green-500" />;
        case 'report': return <FileSpreadsheet {...iconProps} className="w-6 h-6 text-orange-500" />;
        default: return <FileText {...iconProps} className="w-6 h-6 text-slate-500" />;
    }
};

const formatFileSize = (bytes) => {
    if (!bytes) return 'غير معروف';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
};

const formatDate = (dateStr) => {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    return date.toLocaleDateString('ar-SA', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
};

const MyFiles = () => {
    const [files, setFiles] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [uploading, setUploading] = useState(false);
    const [filter, setFilter] = useState('');

    const fetchFiles = async () => {
        setLoading(true);
        setError(null);
        try {
            const token = localStorage.getItem('token');
            if (!token) {
                setError('يجب تسجيل الدخول أولاً');
                setLoading(false);
                return;
            }

            const response = await apiClient.get('/api/user/files', {
                headers: { Authorization: `Bearer ${token}` },
                params: filter ? { file_type: filter } : {}
            });

            if (response.data.success) {
                setFiles(response.data.files);
            }
        } catch (err) {
            console.error('Error fetching files:', err);
            if (err.response?.status === 401) {
                setError('جلسة منتهية - يرجى تسجيل الدخول مرة أخرى');
            } else {
                setError('فشل تحميل الملفات');
            }
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchFiles();
    }, [filter]);

    const handleUpload = async (e) => {
        const file = e.target.files?.[0];
        if (!file) return;

        setUploading(true);
        const formData = new FormData();
        formData.append('file', file);

        try {
            const token = localStorage.getItem('token');
            const response = await apiClient.post('/api/user/files', formData, {
                headers: {
                    Authorization: `Bearer ${token}`,
                    'Content-Type': 'multipart/form-data'
                }
            });

            if (response.data.success) {
                fetchFiles();
            }
        } catch (err) {
            console.error('Upload error:', err);
            setError('فشل رفع الملف');
        } finally {
            setUploading(false);
            e.target.value = '';
        }
    };

    const handleDownload = async (fileId, filename) => {
        try {
            const token = localStorage.getItem('token');
            const response = await apiClient.get(`/api/user/files/${fileId}/download`, {
                headers: { Authorization: `Bearer ${token}` },
                responseType: 'blob'
            });

            const url = window.URL.createObjectURL(new Blob([response.data]));
            const link = document.createElement('a');
            link.href = url;
            link.setAttribute('download', filename);
            document.body.appendChild(link);
            link.click();
            link.remove();
            window.URL.revokeObjectURL(url);
        } catch (err) {
            console.error('Download error:', err);
            setError('فشل تحميل الملف');
        }
    };

    const handleDelete = async (fileId) => {
        if (!window.confirm('هل أنت متأكد من حذف هذا الملف؟')) return;

        try {
            const token = localStorage.getItem('token');
            await apiClient.delete(`/api/user/files/${fileId}`, {
                headers: { Authorization: `Bearer ${token}` }
            });
            fetchFiles();
        } catch (err) {
            console.error('Delete error:', err);
            setError('فشل حذف الملف');
        }
    };

    const fileTypes = [
        { value: '', label: 'الكل' },
        { value: 'image', label: 'صور' },
        { value: 'video', label: 'فيديو' },
        { value: 'audio', label: 'صوت' },
        { value: 'report', label: 'تقارير' },
        { value: 'export', label: 'تصدير' }
    ];

    return (
        <div className="max-w-5xl mx-auto text-right" dir="rtl">
            {/* Page Header */}
            <div className="mb-8 animate-fade-in-up">
                <h1 className="text-3xl font-black text-slate-800 mb-3">
                    <span className="gradient-text">ملفاتي</span>
                </h1>
                <p className="text-slate-600">تصفح وإدارة الملفات المصدّرة والمحفوظة</p>
            </div>

            {/* Actions Bar */}
            <GlassCard className="mb-6 p-4 animate-fade-in-up delay-100">
                <div className="flex flex-wrap items-center justify-between gap-4">
                    {/* Filter */}
                    <div className="flex items-center gap-2">
                        <span className="text-sm text-slate-600">تصفية:</span>
                        <select
                            value={filter}
                            onChange={(e) => setFilter(e.target.value)}
                            className="px-3 py-2 rounded-lg bg-white/60 border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                        >
                            {fileTypes.map(ft => (
                                <option key={ft.value} value={ft.value}>{ft.label}</option>
                            ))}
                        </select>
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-3">
                        <button
                            onClick={fetchFiles}
                            className="p-2 rounded-lg bg-white/60 hover:bg-white border border-slate-200 transition-colors"
                            title="تحديث"
                        >
                            <RefreshCw className={`w-5 h-5 text-slate-600 ${loading ? 'animate-spin' : ''}`} />
                        </button>

                        <label className="cursor-pointer">
                            <input
                                type="file"
                                onChange={handleUpload}
                                className="hidden"
                                disabled={uploading}
                            />
                            <GradientButton
                                as="span"
                                icon={Upload}
                                isLoading={uploading}
                                className="pointer-events-none"
                            >
                                رفع ملف
                            </GradientButton>
                        </label>
                    </div>
                </div>
            </GlassCard>

            {/* Error */}
            {error && (
                <div className="p-4 mb-6 glass-card bg-red-50/80 border-red-200 text-red-700 animate-fade-in-up flex items-center">
                    <AlertCircle className="w-5 h-5 ml-2 flex-shrink-0" />
                    {error}
                </div>
            )}

            {/* Files Grid */}
            <div className="animate-fade-in-up delay-200">
                {loading ? (
                    <div className="text-center py-12 text-slate-500">
                        <RefreshCw className="w-8 h-8 mx-auto mb-3 animate-spin" />
                        جاري التحميل...
                    </div>
                ) : files.length === 0 ? (
                    <div className="text-center py-16 border-2 border-dashed border-slate-200/50 rounded-2xl bg-white/30">
                        <FolderOpen className="w-16 h-16 mx-auto mb-4 text-slate-300" />
                        <p className="text-slate-500 text-lg">لا توجد ملفات محفوظة</p>
                        <p className="text-slate-400 text-sm mt-2">قم برفع ملف أو تصدير نتائج من أدوات التحليل</p>
                    </div>
                ) : (
                    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                        {files.map(file => (
                            <GlassCard key={file.id} className="p-4 hover:shadow-lg transition-shadow">
                                <div className="flex items-start gap-3">
                                    <div className="w-12 h-12 rounded-xl bg-slate-100 flex items-center justify-center flex-shrink-0">
                                        <FileTypeIcon type={file.file_type} />
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        <h3 className="font-bold text-slate-800 truncate" title={file.filename}>
                                            {file.filename}
                                        </h3>
                                        <div className="flex items-center gap-2 text-xs text-slate-500 mt-1">
                                            <span>{formatFileSize(file.file_size)}</span>
                                            <span>•</span>
                                            <span>{file.file_type}</span>
                                        </div>
                                        <p className="text-xs text-slate-400 mt-1">
                                            {formatDate(file.created_at)}
                                        </p>
                                        {file.description && (
                                            <p className="text-xs text-slate-500 mt-2 line-clamp-2">
                                                {file.description}
                                            </p>
                                        )}
                                    </div>
                                </div>

                                <div className="flex items-center gap-2 mt-4 pt-3 border-t border-slate-100">
                                    <button
                                        onClick={() => handleDownload(file.id, file.filename)}
                                        className="flex-1 flex items-center justify-center gap-2 py-2 px-3 rounded-lg bg-primary-50 text-primary-600 hover:bg-primary-100 transition-colors text-sm font-medium"
                                    >
                                        <Download className="w-4 h-4" />
                                        تحميل
                                    </button>
                                    <button
                                        onClick={() => handleDelete(file.id)}
                                        className="p-2 rounded-lg bg-red-50 text-red-500 hover:bg-red-100 transition-colors"
                                        title="حذف"
                                    >
                                        <Trash2 className="w-4 h-4" />
                                    </button>
                                </div>

                                {file.download_count > 0 && (
                                    <div className="text-xs text-slate-400 mt-2 text-center">
                                        تم التحميل {file.download_count} مرة
                                    </div>
                                )}
                            </GlassCard>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
};

export default MyFiles;
