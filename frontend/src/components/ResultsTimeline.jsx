import { Calendar, ExternalLink } from 'lucide-react';
import { format } from 'date-fns';
import { arSA } from 'date-fns/locale';

const ResultsTimeline = ({ results }) => {
    if (!results || results.length === 0) {
        return (
            <div className="text-center py-12 text-slate-500">
                <p>لا توجد نتائج للعرض</p>
            </div>
        );
    }

    // Safe date formatting function
    const formatDate = (timestamp) => {
        if (!timestamp) return null;
        try {
            const date = new Date(timestamp);
            if (isNaN(date.getTime())) return null;
            return format(date, 'dd MMMM yyyy', { locale: arSA });
        } catch (err) {
            console.error('Date parse error:', err);
            return null;
        }
    };

    return (
        <div className="relative border-r-2 border-primary-200 mr-4 pr-4 py-4">
            {results.map((item, index) => (
                <div key={index} className="mb-8 mr-6 relative group">
                    {/* Timeline Dot */}
                    <div className="absolute -right-[37px] top-3 w-4 h-4 rounded-full bg-gradient-to-br from-primary-500 to-sky-500 border-4 border-white shadow-md group-hover:scale-150 transition-all duration-300"></div>

                    {/* Timeline Card */}
                    <div className="glass-card p-5 hover:shadow-xl transition-all duration-300">
                        <div className="flex flex-col md:flex-row gap-4">
                            {/* Thumbnail if available */}
                            {item.thumbnail && (
                                <div className="w-24 h-24 flex-shrink-0 bg-slate-100 rounded-xl overflow-hidden border border-slate-200/50 shadow-sm">
                                    <img
                                        src={item.thumbnail}
                                        alt=""
                                        className="w-full h-full object-cover"
                                        onError={(e) => e.target.style.display = 'none'}
                                    />
                                </div>
                            )}

                            <div className="flex-1">
                                {/* Date & Source Tags */}
                                <div className="flex flex-wrap items-center gap-2 text-xs font-bold mb-3">
                                    {formatDate(item.timestamp) ? (
                                        <span className="flex items-center bg-gradient-to-r from-primary-50 to-sky-50 text-primary-700 px-3 py-1.5 rounded-full">
                                            <Calendar className="w-3 h-3 ml-1" />
                                            {formatDate(item.timestamp)}
                                        </span>
                                    ) : item.date_text ? (
                                        <span className="flex items-center bg-slate-100 text-slate-600 px-3 py-1.5 rounded-full">
                                            <Calendar className="w-3 h-3 ml-1" />
                                            {item.date_text}
                                        </span>
                                    ) : (
                                        <span className="bg-slate-100 text-slate-500 px-3 py-1.5 rounded-full">تاريخ غير محدد</span>
                                    )}
                                    {item.source && (
                                        <span className="bg-slate-100 text-slate-600 px-3 py-1.5 rounded-full">{item.source}</span>
                                    )}
                                </div>

                                {/* Title */}
                                <h3 className="font-black text-slate-900 text-lg leading-tight mb-2">
                                    {item.link ? (
                                        <a
                                            href={item.link}
                                            target="_blank"
                                            rel="noreferrer"
                                            className="hover:text-primary-600 transition-colors"
                                        >
                                            {item.title || 'بدون عنوان'}
                                        </a>
                                    ) : (
                                        <span>{item.title || 'بدون عنوان'}</span>
                                    )}
                                </h3>

                                {/* Snippet */}
                                {item.snippet && (
                                    <p className="text-slate-600 text-sm leading-relaxed mb-3 line-clamp-2">
                                        {item.snippet}
                                    </p>
                                )}

                                {/* Link */}
                                {item.link && (
                                    <a
                                        href={item.link}
                                        target="_blank"
                                        rel="noreferrer"
                                        className="inline-flex items-center text-sm font-bold text-primary-600 hover:text-primary-800 transition-colors"
                                    >
                                        زيارة المصدر
                                        <ExternalLink className="w-3.5 h-3.5 mr-1.5" />
                                    </a>
                                )}
                            </div>
                        </div>
                    </div>
                </div>
            ))}
        </div>
    );
};

export default ResultsTimeline;
