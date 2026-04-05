import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, Globe, ImageIcon, Video, Mic } from 'lucide-react';
import DropZone from '../components/DropZone';
import GradientButton from '../components/GradientButton';

const Home = () => {
    const navigate = useNavigate();
    const [fileTypeAction, setFileTypeAction] = useState(null);
    const [pendingFile, setPendingFile] = useState(null);
    const [previewUrl, setPreviewUrl] = useState(null);
    const [searchUrl, setSearchUrl] = useState('');

    const handleFileSelect = (file, dataUrl) => {
        if (!file) {
            setPendingFile(null);
            setFileTypeAction(null);
            setPreviewUrl(null);
            return;
        }

        setPendingFile(file);
        setPreviewUrl(dataUrl);

        if (file.type.startsWith('video/')) {
            navigate('/video', { state: { file } });
        } else if (file.type.startsWith('audio/')) {
            navigate('/audio-verification', { state: { file } });
        } else if (file.type.startsWith('image/')) {
            // Asking user what to do with the image
            setFileTypeAction('image');
        } else {
            // Unsupported file type visually
            setFileTypeAction('unsupported');
        }
    };

    const handleUrlSearch = (e) => {
        e.preventDefault();
        if (!searchUrl.trim()) return;
        navigate('/reverse-search', { state: { searchUrl } });
    };

    return (
        <div className="max-w-4xl mx-auto flex flex-col items-center justify-center min-h-[70vh] animate-fade-in-up">
            
            <div className="text-center mb-10">
                <h1 className="text-4xl md:text-5xl font-black text-slate-800 mb-4 tracking-tight">
                    التحقق الموثوق
                </h1>
                <p className="text-xl text-slate-500 max-w-2xl mx-auto">
                    بوابتك الرسمية لتوثيق وتحليل الوسائط الرقمية بدقة فائقة
                </p>
            </div>

            {/* Universal Hub Area */}
            <div className="w-full bg-white/40 backdrop-blur-xl border border-slate-200/60 shadow-2xl shadow-slate-200/50 rounded-3xl p-8 mb-8">
                
                {/* Search Bar for URLs */}
                <form onSubmit={handleUrlSearch} className="mb-8 group">
                    <div className="relative flex items-center">
                        <input
                            type="url"
                            value={searchUrl}
                            onChange={(e) => setSearchUrl(e.target.value)}
                            placeholder="أدخل رابط صورة أو موقع للتحقق منه..."
                            className="w-full bg-white text-slate-800 border-2 border-slate-200 focus:border-slate-800 rounded-2xl py-4 pr-14 pl-4 font-medium transition-all shadow-sm focus:shadow-md outline-none"
                            dir="rtl"
                        />
                        <Search className="absolute right-5 w-6 h-6 text-slate-400 group-focus-within:text-slate-800 transition-colors" />
                        <button
                            type="submit"
                            disabled={!searchUrl.trim()}
                            className="absolute left-2 bg-slate-900 text-white p-2.5 rounded-xl hover:bg-slate-800 transition-colors disabled:opacity-50"
                        >
                            <Globe className="w-5 h-5" />
                        </button>
                    </div>
                </form>

                <div className="flex items-center gap-4 mb-8">
                    <div className="flex-1 h-px bg-slate-200"></div>
                    <span className="text-sm font-bold text-slate-400">أو عبر الملفات</span>
                    <div className="flex-1 h-px bg-slate-200"></div>
                </div>

                {/* Main Dropzone */}
                {!fileTypeAction ? (
                    <DropZone 
                        onFileSelect={handleFileSelect}
                        headerText="قم بإسقاط الملف هنا لتحليله فوراً"
                        subText="يدعم الصور (JPG, PNG)، الفيديو (MP4)، والصوتيات (MP3)"
                        accept="image/*,video/*,audio/*"
                    />
                ) : (
                    <div className="animate-fade-in-up p-6 bg-slate-50 border border-slate-100 rounded-2xl text-center">
                        {fileTypeAction === 'image' && (
                            <>
                                <h3 className="text-lg font-bold text-slate-800 mb-6">لقد قمت برفع صورة، ماذا تود أن تفعل بها؟</h3>
                                <div className="grid md:grid-cols-2 gap-4">
                                    <GradientButton 
                                        icon={ImageIcon} 
                                        className="w-full"
                                        onClick={() => navigate('/ai-detection', { state: { file: pendingFile, dataUrl: previewUrl, fileName: pendingFile.name } })}
                                    >
                                        كشف التلاعب (الذكاء الاصطناعي)
                                    </GradientButton>
                                    <GradientButton 
                                        icon={Search} 
                                        variant="secondary"
                                        className="w-full"
                                        onClick={() => navigate('/reverse-search', { state: { file: pendingFile, dataUrl: previewUrl, fileName: pendingFile.name } })}
                                    >
                                        البحث العكسي (تتبع المصدر)
                                    </GradientButton>
                                    <button 
                                        onClick={() => { setFileTypeAction(null); setPendingFile(null); setPreviewUrl(null); }}
                                        className="col-span-full mt-4 text-sm font-bold text-slate-500 hover:text-slate-700 underline"
                                    >
                                        إلغاء ورفع ملف آخر
                                    </button>
                                </div>
                            </>
                        )}
                        {fileTypeAction === 'unsupported' && (
                            <>
                                <h3 className="text-lg font-bold text-red-600 mb-2">نوع الملف غير مدعوم</h3>
                                <p className="text-slate-500 mb-4">يرجى رفع صورة، فيديو، أو ملف صوتي مدعوم.</p>
                                <button 
                                    onClick={() => setFileTypeAction(null)}
                                    className="px-6 py-2 bg-slate-200 text-slate-700 rounded-lg hover:bg-slate-300 font-bold"
                                >
                                    حسناً
                                </button>
                            </>
                        )}
                    </div>
                )}
            </div>
            
            {/* Supported Types Footer (Minimal) */}
            <div className="flex items-center justify-center gap-8 text-slate-400">
                <div className="flex items-center gap-2"><ImageIcon className="w-5 h-5"/> <span className="text-sm font-bold">صور</span></div>
                <div className="flex items-center gap-2"><Video className="w-5 h-5"/> <span className="text-sm font-bold">فيديو</span></div>
                <div className="flex items-center gap-2"><Mic className="w-5 h-5"/> <span className="text-sm font-bold">صوت</span></div>
            </div>
        </div>
    );
};

export default Home;
