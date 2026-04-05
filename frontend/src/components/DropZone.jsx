import { useRef, useState, useEffect } from 'react';
import { Upload, X, Film } from 'lucide-react';
import clsx from 'clsx';

const DropZone = ({ onFileSelect, headerText = "اسحب وأفلت الصورة هنا", subText = "أو انقر للاختيار", accept = "image/*", initialFile = null }) => {
    const [dragActive, setDragActive] = useState(false);
    const [preview, setPreview] = useState(null);
    const [videoPreview, setVideoPreview] = useState(null);
    const [fileName, setFileName] = useState(null);
    const [fileType, setFileType] = useState(null);
    const inputRef = useRef(null);

    // Initialize with initialFile if provided
    useEffect(() => {
        if (initialFile) {
            setFileName(initialFile.name);
            setFileType(initialFile.type);
            if (initialFile.type.startsWith('image/')) {
                const reader = new FileReader();
                reader.onload = (e) => {
                    setPreview(e.target.result);
                };
                reader.readAsDataURL(initialFile);
            } else if (initialFile.type.startsWith('video/')) {
                const url = URL.createObjectURL(initialFile);
                setVideoPreview(url);
            }
        }
    }, [initialFile]);

    const handleDrag = (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (e.type === "dragenter" || e.type === "dragover") {
            setDragActive(true);
        } else if (e.type === "dragleave") {
            setDragActive(false);
        }
    };

    const handleDrop = (e) => {
        e.preventDefault();
        e.stopPropagation();
        setDragActive(false);
        if (e.dataTransfer.files && e.dataTransfer.files[0]) {
            processFile(e.dataTransfer.files[0]);
        }
    };

    const handleChange = (e) => {
        if (e.target.files && e.target.files[0]) {
            processFile(e.target.files[0]);
        }
    };

    const processFile = (file) => {
        setFileName(file.name);
        setFileType(file.type);

        // Cleanup previous video preview
        if (videoPreview) {
            URL.revokeObjectURL(videoPreview);
            setVideoPreview(null);
        }

        if (file.type.startsWith('image/')) {
            const reader = new FileReader();
            reader.onload = (e) => {
                setPreview(e.target.result);
                onFileSelect(file, e.target.result);
            };
            reader.readAsDataURL(file);
        } else if (file.type.startsWith('video/')) {
            setPreview(null);
            const url = URL.createObjectURL(file);
            setVideoPreview(url);
            onFileSelect(file, null);
        } else {
            setPreview(null);
            onFileSelect(file, null);
        }
    };

    const removeFile = (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (videoPreview) URL.revokeObjectURL(videoPreview);
        setPreview(null);
        setVideoPreview(null);
        setFileName(null);
        setFileType(null);
        onFileSelect(null, null);
        if (inputRef.current) inputRef.current.value = "";
    };

    const RemoveButton = () => (
        <button
            type="button"
            onClick={removeFile}
            className="absolute top-3 right-3 p-2 bg-slate-900 text-white rounded-full hover:bg-slate-700 transition-all shadow-lg hover:shadow-xl hover:scale-110 z-10"
        >
            <X className="w-4 h-4" />
        </button>
    );

    return (
        <div className="w-full">
            <label
                className={clsx(
                    "relative flex flex-col items-center justify-center w-full min-h-[200px] border-2 border-dashed rounded-2xl cursor-pointer transition-all duration-300",
                    dragActive
                        ? "border-slate-400 bg-slate-50 scale-[1.01] shadow-md"
                        : "border-slate-200 bg-slate-50/50 hover:bg-slate-50 hover:border-slate-300",
                    (preview || videoPreview || fileName) && "border-solid border-slate-300 bg-slate-50"
                )}
                onDragEnter={handleDrag}
                onDragLeave={handleDrag}
                onDragOver={handleDrag}
                onDrop={handleDrop}
            >
                <input
                    ref={inputRef}
                    type="file"
                    className="hidden"
                    accept={accept}
                    onChange={handleChange}
                />

                {/* Image Preview */}
                {preview ? (
                    <div className="relative w-full h-full p-4 flex items-center justify-center">
                        <img
                            src={preview}
                            alt="Preview"
                            className="max-h-48 max-w-full rounded-xl object-contain shadow-sm"
                        />
                        <RemoveButton />
                    </div>
                ) : videoPreview ? (
                    /* Video Preview */
                    <div className="relative w-full h-full p-4 flex items-center justify-center">
                        <video
                            src={videoPreview}
                            className="max-h-48 max-w-full rounded-xl object-contain shadow-sm"
                            muted
                            playsInline
                            preload="metadata"
                            onLoadedData={(e) => {
                                // Show a frame from the video
                                e.target.currentTime = 0.5;
                            }}
                        />
                        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                            <div className="w-12 h-12 rounded-full bg-slate-900/60 flex items-center justify-center">
                                <Film className="w-5 h-5 text-white" />
                            </div>
                        </div>
                        <RemoveButton />
                    </div>
                ) : fileName ? (
                    /* File info (non-image, non-video) */
                    <div className="relative w-full p-6 flex items-center justify-center">
                        <div className="text-center">
                            <div className="w-14 h-14 mx-auto mb-3 rounded-2xl bg-slate-900 flex items-center justify-center">
                                <Upload className="w-7 h-7 text-white" />
                            </div>
                            <p className="font-bold text-slate-700 text-sm">{fileName}</p>
                            <p className="text-xs text-slate-400 mt-1">تم اختيار الملف</p>
                        </div>
                        <RemoveButton />
                    </div>
                ) : (
                    /* Empty state */
                    <div className="flex flex-col items-center justify-center py-8 text-center px-4">
                        <div className={clsx(
                            "p-2 rounded-2xl mb-4 transition-all duration-300",
                            dragActive
                                ? "text-slate-700 scale-110"
                                : "text-slate-400"
                        )}>
                            <svg width="60" height="60" viewBox="0 0 100 100" fill="none" className="mx-auto" aria-label="أيقونة سحب وإفلات">
                                <style>
                                    {`
                                        @keyframes float-arrow {
                                            0%, 100% { transform: translateY(0); }
                                            50% { transform: translateY(-8px); }
                                        }
                                        @keyframes cloud-pulse {
                                            0%, 100% { stroke: currentColor; opacity: 1; }
                                            50% { stroke: #94a3b8; opacity: 0.8; }
                                        }
                                    `}
                                </style>
                                <g style={{animation: 'float-arrow 2s ease-in-out infinite'}}>
                                    <line x1="50" y1="65" x2="50" y2="30" stroke="currentColor" strokeWidth="5" strokeLinecap="round" />
                                    <path d="M35 45 L50 30 L65 45" stroke="currentColor" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" />
                                </g>
                                <path d="M25 60 A18 18 0 0 1 35 30 A22 22 0 0 1 70 35 A18 18 0 0 1 75 70 L25 70 Z" stroke="currentColor" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" fill="none" style={{animation: 'cloud-pulse 3s infinite'}} />
                            </svg>
                        </div>
                        <p className="mb-2 text-base font-bold text-slate-700">{headerText}</p>
                        <p className="text-sm text-slate-400">{subText}</p>
                    </div>
                )}
            </label>
        </div>
    );
};

export default DropZone;
