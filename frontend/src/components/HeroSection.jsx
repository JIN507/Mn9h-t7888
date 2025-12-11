import { ChevronDown } from 'lucide-react';
import bgImage from '../assets/tahaqqaq-bg.png';

const HeroSection = () => {
    const scrollToContent = () => {
        window.scrollTo({
            top: window.innerHeight - 80,
            behavior: 'smooth'
        });
    };

    return (
        <section className="hero-section">
            {/* Hero Content */}
            <div className="text-center px-4 max-w-6xl mx-auto">
                {/* Logo Image - Large, transparent and subtle */}
                <div className="hero-logo mb-8">
                    <img
                        src={bgImage}
                        alt="منصة تحقق"
                        className="w-[700px] md:w-[900px] lg:w-[1000px] mx-auto opacity-70"
                        style={{
                            filter: 'drop-shadow(0 0 40px rgba(3, 105, 161, 0.15))',
                            maxWidth: '90vw'
                        }}
                    />
                </div>

                {/* Tagline */}
                <p className="text-xl md:text-2xl text-slate-600 font-medium mb-8 animate-fade-in-up delay-200">
                    بوابتك المتقدمة للتحقق من صحة المحتوى الرقمي
                </p>

                {/* CTA Button */}
                <button
                    onClick={scrollToContent}
                    className="premium-btn mb-16 animate-fade-in-up delay-300"
                >
                    ابدأ التحقق الآن
                </button>
            </div>

            {/* Scroll Indicator */}
            <div
                onClick={scrollToContent}
                className="absolute bottom-8 left-1/2 transform -translate-x-1/2 cursor-pointer scroll-indicator"
            >
                <div className="flex flex-col items-center text-slate-400 hover:text-primary-600 transition-colors">
                    <span className="text-sm font-medium mb-2">اكتشف المزيد</span>
                    <ChevronDown className="w-8 h-8" />
                </div>
            </div>
        </section>
    );
};

export default HeroSection;
