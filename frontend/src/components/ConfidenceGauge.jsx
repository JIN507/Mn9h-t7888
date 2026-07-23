import { useState, useEffect } from 'react';

// ─── Animated Percentage Counter ────────────────────────
export const AnimatedPercentage = ({ value }) => {
    const [count, setCount] = useState(0);
    const target = Math.round(value * 100);

    useEffect(() => {
        let startTimestamp = null;
        const duration = 1500;
        const step = (timestamp) => {
            if (!startTimestamp) startTimestamp = timestamp;
            const progress = Math.min((timestamp - startTimestamp) / duration, 1);
            const easeOut = progress * (2 - progress);
            setCount(Math.floor(easeOut * target));
            if (progress < 1) window.requestAnimationFrame(step);
        };
        window.requestAnimationFrame(step);
    }, [target]);

    return <span>{count}%</span>;
};

// ─── Animated Progress Bar ────────────────────────
export const AnimatedBar = ({ value, colorClass }) => {
    const [width, setWidth] = useState(0);
    const target = Math.round(value * 100);

    useEffect(() => {
        const timer = setTimeout(() => setWidth(target), 100);
        return () => clearTimeout(timer);
    }, [target]);

    return (
        <div className="h-3 bg-slate-100 rounded-full overflow-hidden">
            <div
                className={`h-full ${colorClass} rounded-full transition-all ease-out relative overflow-hidden`}
                style={{ width: `${width}%`, transitionDuration: '1500ms' }}
            >
                <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/30 to-transparent animate-shimmer" />
            </div>
        </div>
    );
};

// ─── Labeled confidence bars ────────────────────────
// bars: [{ label, value (0..1), colorClass, labelClass?, valueClass? }]
const ConfidenceGauge = ({ bars }) => (
    <div className="space-y-5">
        {bars.map((bar, i) => (
            <div key={i}>
                <div className="flex justify-between text-xs font-bold mb-2">
                    <span className={bar.labelClass || 'text-slate-600'}>{bar.label}</span>
                    <span className={`${bar.valueClass || 'text-slate-900'} text-sm font-mono`}>
                        <AnimatedPercentage value={bar.value} />
                    </span>
                </div>
                <AnimatedBar value={bar.value} colorClass={bar.colorClass} />
            </div>
        ))}
    </div>
);

export default ConfidenceGauge;
