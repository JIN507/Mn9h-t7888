import clsx from 'clsx';

const GlassCard = ({ children, className, hover = true, ...props }) => {
    return (
        <div
            className={clsx(
                "glass-card",
                hover && "hover:shadow-2xl hover:-translate-y-1",
                className
            )}
            {...props}
        >
            {children}
        </div>
    );
};

export default GlassCard;
