import clsx from 'clsx';
import { Loader2 } from 'lucide-react';

const GradientButton = ({
    children,
    onClick,
    isLoading = false,
    className,
    disabled,
    type = 'button',
    icon: Icon,
    variant = 'primary' // primary | secondary
}) => {
    return (
        <button
            type={type}
            onClick={onClick}
            disabled={disabled || isLoading}
            className={clsx(
                "relative inline-flex items-center justify-center px-6 py-3.5 overflow-hidden font-bold rounded-xl transition-all duration-300",
                variant === 'primary' && [
                    "bg-gradient-to-r from-primary-600 via-primary-500 to-sky-500 text-white",
                    "shadow-lg shadow-primary-500/25",
                    "hover:shadow-xl hover:shadow-primary-500/40 hover:-translate-y-0.5",
                    "active:translate-y-0"
                ],
                variant === 'secondary' && [
                    "bg-white/80 backdrop-blur-sm text-slate-700 border border-slate-200",
                    "hover:bg-white hover:border-slate-300 hover:shadow-md"
                ],
                "disabled:opacity-60 disabled:cursor-not-allowed disabled:transform-none disabled:shadow-none",
                className
            )}
        >
            {/* Shimmer Effect */}
            <div className="absolute inset-0 -translate-x-full group-hover:translate-x-full transition-transform duration-700 bg-gradient-to-r from-transparent via-white/20 to-transparent" />

            {isLoading ? (
                <Loader2 className="w-5 h-5 animate-spin ml-2" />
            ) : Icon ? (
                <Icon className="w-5 h-5 ml-2" />
            ) : null}

            <span>{children}</span>
        </button>
    );
};

export default GradientButton;
