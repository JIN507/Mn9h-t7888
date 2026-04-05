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
    variant = 'primary' // primary (black/dark) | secondary (glass white)
}) => {
    return (
        <button
            type={type}
            onClick={onClick}
            disabled={disabled || isLoading}
            className={clsx(
                "relative inline-flex items-center justify-center px-6 py-3.5 overflow-hidden font-bold rounded-xl transition-all duration-300",
                variant === 'primary' && [
                    "bg-slate-900 text-white",
                    "border border-slate-800",
                    "shadow-lg shadow-slate-900/10",
                    "hover:bg-slate-800 hover:-translate-y-0.5"
                ],
                variant === 'secondary' && [
                    "bg-white/80 backdrop-blur-sm text-slate-800",
                    "border border-slate-200/80 shadow-sm",
                    "hover:bg-white hover:shadow-md hover:-translate-y-0.5"
                ],
                "disabled:opacity-50 disabled:cursor-not-allowed disabled:transform-none disabled:shadow-none hover:shadow-none",
                className
            )}
        >
            {/* Shimmer Effect */}
            <div className="absolute inset-0 -translate-x-full group-hover:animate-[shimmer_2s_infinite] bg-gradient-to-r from-transparent via-white/10 to-transparent pointer-events-none" />

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
