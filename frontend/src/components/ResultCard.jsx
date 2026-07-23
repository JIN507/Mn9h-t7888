import { ShieldCheck, AlertTriangle, X } from 'lucide-react';
import GlassCard from './GlassCard';

/**
 * Shared verdict card for the analysis pages.
 *
 * Props:
 *  - title / subtitle: header text
 *  - error (+ errorSubtitle): renders the error state instead of a result
 *  - isAI: drives the red/slate styling
 *  - verdict: big verdict text (omit to skip the verdict block)
 *  - index: stagger animation position
 *  - children: page-specific body (confidence gauge, players, annotations…)
 */
const ResultCard = ({ title, subtitle, error, errorSubtitle, isAI = false,
                      verdict, index = 0, className = '', children }) => {
    if (error) {
        return (
            <GlassCard className={`ai-result-card p-6 border-slate-200 ${className}`}
                       style={{ animationDelay: `${index * 150}ms` }}>
                <div className="flex items-center gap-3 mb-4 pb-3 border-b border-slate-100">
                    <div className="w-10 h-10 rounded-xl flex items-center justify-center bg-slate-100">
                        <X className="w-5 h-5 text-slate-400" />
                    </div>
                    <div>
                        <h3 className="font-bold text-slate-800">{title}</h3>
                        {errorSubtitle && <p className="text-xs text-slate-500">{errorSubtitle}</p>}
                    </div>
                </div>
                <div className="text-center py-6">
                    <AlertTriangle className="w-10 h-10 text-slate-300 mx-auto mb-3" />
                    <p className="text-slate-600 text-sm font-bold">{error}</p>
                </div>
            </GlassCard>
        );
    }

    return (
        <GlassCard className={`ai-result-card p-6 border-slate-200 shadow-sm ${className}`}
                   style={{ animationDelay: `${index * 150}ms` }}>
            {/* Top accent bar */}
            <div className={`absolute top-0 left-0 right-0 h-1 rounded-t-2xl ${
                isAI
                    ? 'bg-gradient-to-r from-red-500 via-orange-400 to-red-500'
                    : 'bg-gradient-to-r from-slate-800 via-slate-600 to-slate-800'
            }`} />

            <div className="flex items-center gap-3 mb-5 pb-3 border-b border-slate-100">
                <div className={`w-10 h-10 rounded-xl flex items-center justify-center border ${
                    isAI ? 'bg-red-50 border-red-200' : 'bg-slate-50 border-slate-200'
                }`}>
                    {isAI ? <AlertTriangle className="w-5 h-5 text-red-500" />
                          : <ShieldCheck className="w-5 h-5 text-slate-700" />}
                </div>
                <div>
                    <h3 className="font-bold text-slate-800">{title}</h3>
                    {subtitle && <p className="text-xs text-slate-500">{subtitle}</p>}
                </div>
            </div>

            {verdict && (
                <div className="text-center mb-6">
                    <div className={`inline-flex items-center justify-center w-20 h-20 rounded-2xl mb-4 border-2 ${
                        isAI
                            ? 'bg-red-50 border-red-200 text-red-500'
                            : 'bg-slate-50 border-slate-300 text-slate-800'
                    }`}>
                        {isAI ? <AlertTriangle className="w-10 h-10" />
                              : <ShieldCheck className="w-10 h-10" />}
                    </div>
                    <h4 className={`text-xl font-black ${isAI ? 'text-red-600' : 'text-slate-800'}`}>
                        {verdict}
                    </h4>
                </div>
            )}

            {children}
        </GlassCard>
    );
};

export default ResultCard;
