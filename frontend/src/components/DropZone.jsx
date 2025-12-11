import { useRef, useState } from 'react';
import { Upload, X, ImageIcon } from 'lucide-react';
import clsx from 'clsx';

const DropZone = ({ onFileSelect, headerText = "اسحب وأفلت الصورة هنا", subText = "أو انقر للاختيار", accept = "image/*" }) => {
    const [dragActive, setDragActive] = useState(false);
    const [preview, setPreview] = useState(null);
    const [fileName, setFileName] = useState(null);
    const inputRef = useRef(null);

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

        // Check if it's an image for preview
        if (file.type.startsWith('image/')) {
            const reader = new FileReader();
            reader.onload = (e) => {
                setPreview(e.target.result);
                onFileSelect(file, e.target.result);
            };
            reader.readAsDataURL(file);
        } else {
            // For non-image files (video, audio, etc.)
            setPreview(null);
            onFileSelect(file, null);
        }
    };

    const removeFile = (e) => {
        e.preventDefault();
        e.stopPropagation();
        setPreview(null);
        setFileName(null);
        onFileSelect(null, null);
        if (inputRef.current) inputRef.current.value = "";
    };

    return (
        <div className="w-full">
            <label
                className={clsx(
                    "relative flex flex-col items-center justify-center w-full min-h-[200px] border-2 border-dashed rounded-2xl cursor-pointer transition-all duration-300",
                    "backdrop-blur-sm",
                    dragActive
                        ? "border-primary-500 bg-primary-50/50 scale-[1.02] shadow-lg"
                        : "border-slate-300/50 bg-white/30 hover:bg-white/50 hover:border-primary-300",
                    (preview || fileName) && "border-solid border-primary-200 bg-primary-50/30"
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

                {preview ? (
                    <div className="relative w-full h-full p-4 flex items-center justify-center">
                        <img
                            src={preview}
                            alt="Preview"
                            className="max-h-48 max-w-full rounded-xl object-contain shadow-lg"
                        />
                        <button
                            type="button"
                            onClick={removeFile}
                            className="absolute top-3 right-3 p-2 bg-gradient-to-br from-red-500 to-rose-600 text-white rounded-full hover:from-red-600 hover:to-rose-700 transition-all shadow-lg hover:shadow-xl hover:scale-110"
                        >
                            <X className="w-4 h-4" />
                        </button>
                    </div>
                ) : fileName ? (
                    <div className="relative w-full p-6 flex items-center justify-center">
                        <div className="text-center">
                            <div className="w-16 h-16 mx-auto mb-3 rounded-2xl bg-gradient-to-br from-primary-500 to-sky-500 flex items-center justify-center">
                                <Upload className="w-8 h-8 text-white" />
                            </div>
                            <p className="font-bold text-slate-700">{fileName}</p>
                            <p className="text-sm text-slate-500 mt-1">تم اختيار الملف</p>
                        </div>
                        <button
                            type="button"
                            onClick={removeFile}
                            className="absolute top-3 right-3 p-2 bg-gradient-to-br from-red-500 to-rose-600 text-white rounded-full hover:from-red-600 hover:to-rose-700 transition-all shadow-lg hover:shadow-xl hover:scale-110"
                        >
                            <X className="w-4 h-4" />
                        </button>
                    </div>
                ) : (
                    <div className="flex flex-col items-center justify-center py-8 text-center px-4">
                        <div className={clsx(
                            "p-5 rounded-2xl mb-4 transition-all duration-300",
                            dragActive
                                ? "bg-gradient-to-br from-primary-500 to-sky-500 text-white scale-110"
                                : "bg-gradient-to-br from-slate-100 to-slate-200 text-slate-400"
                        )}>
                            <Upload className="w-8 h-8" />
                        </div>
                        <p className="mb-2 text-lg font-bold text-slate-700">{headerText}</p>
                        <p className="text-sm text-slate-500">{subText}</p>
                    </div>
                )}
            </label>
        </div>
    );
};

export default DropZone;
