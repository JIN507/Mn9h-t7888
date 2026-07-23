import { AlertTriangle } from 'lucide-react';
import GlassCard from './GlassCard';

/**
 * Shared error display.
 * variants:
 *  - inline (default): compact red strip inside a card
 *  - card:  centered GlassCard (analysis pages)
 *  - panel: full-width glass strip (timeline/search pages)
 */
const ErrorBanner = ({ message, variant = 'inline', className = '' }) => {
    if (!message) return null;

    if (variant === 'card') {
        return (
            <GlassCard className={`p-6 border-red-200 ${className}`}>
                <div className="text-center py-4">
                    <AlertTriangle className="w-12 h-12 text-red-300 mx-auto mb-3" />
                    <p className="text-red-600 font-bold">{message}</p>
                </div>
            </GlassCard>
        );
    }

    if (variant === 'panel') {
        return (
            <div className={`p-4 glass-card bg-red-50/80 border-red-200 text-red-700 flex items-center ${className}`}>
                <AlertTriangle className="w-5 h-5 ml-2 flex-shrink-0" />
                {message}
            </div>
        );
    }

    return (
        <div className={`p-3 bg-red-50 text-red-600 rounded-xl flex items-center gap-2 text-sm font-bold ${className}`}>
            <AlertTriangle className="w-4 h-4 flex-shrink-0" /> {message}
        </div>
    );
};

export default ErrorBanner;
