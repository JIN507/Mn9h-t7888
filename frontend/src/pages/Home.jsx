import { Link } from 'react-router-dom';
import { Search, Image as ImageIcon, Video, Mic, Globe, ArrowLeft } from 'lucide-react';

const FeatureCard = ({ to, icon: Icon, title, description, gradient, isExternal, delay }) => {
    const CardContent = (
        <div className={`feature-card h-full animate-fade-in-up ${delay}`}>
            {/* Icon Container */}
            <div className={`w-16 h-16 rounded-2xl flex items-center justify-center mb-6 transition-all duration-300 group-hover:scale-110 ${gradient}`}>
                <Icon className="w-8 h-8 text-white" />
            </div>

            {/* Title */}
            <h3 className="text-xl font-bold mb-3 text-slate-800 group-hover:text-primary-700 transition-colors">
                {title}
            </h3>

            {/* Description */}
            <p className="text-slate-600 leading-relaxed mb-6 text-sm">
                {description}
            </p>

            {/* Action Text */}
            <div className="flex items-center text-sm font-bold text-primary-600 opacity-0 transform translate-x-4 group-hover:opacity-100 group-hover:translate-x-0 transition-all duration-300">
                {isExternal ? 'زيارة الموقع' : 'بدء الاستخدام'}
                <ArrowLeft className="w-4 h-4 mr-2" />
            </div>
        </div>
    );

    if (isExternal) {
        return (
            <a href={to} target="_blank" rel="noreferrer" className="block group h-full">
                {CardContent}
            </a>
        );
    }

    return (
        <Link to={to} className="block group h-full">
            {CardContent}
        </Link>
    );
};

const Home = () => {
    return (
        <div className="max-w-6xl mx-auto" id="features">
            {/* Section Header */}
            <div className="text-center mb-12">
                <h2 className="text-3xl md:text-4xl font-black text-slate-800 mb-4">
                    أدوات التحقق المتقدمة
                </h2>
                <p className="text-lg text-slate-500 max-w-2xl mx-auto">
                    مجموعة متكاملة من الأدوات لفحص المحتوى الرقمي والتحقق من صحته
                </p>
            </div>

            {/* Feature Cards Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                <FeatureCard
                    to="/direct-search"
                    icon={Search}
                    title="البحث المباشر (Timeline)"
                    description="تتبع التاريخ الزمني لظهور الصور والمعلومات عبر الإنترنت باستخدام تقنيات بحث متقدمة."
                    gradient="bg-gradient-to-br from-sky-500 to-blue-600"
                    delay="delay-100"
                />
                <FeatureCard
                    to="/reverse-search"
                    icon={Search}
                    title="البحث اليدوي"
                    description="البحث العكسي التقليدي عن مصدر الصورة في محركات البحث العالمية (Google, Bing, Yandex)."
                    gradient="bg-gradient-to-br from-slate-500 to-slate-700"
                    delay="delay-200"
                />
                <FeatureCard
                    to="/ai-detection"
                    icon={ImageIcon}
                    title="كشف صور الذكاء الاصطناعي"
                    description="تحليل الصور باستخدام خوارزميات متعددة للكشف عن التلاعب أو التوليد بواسطة AI."
                    gradient="bg-gradient-to-br from-violet-500 to-purple-600"
                    delay="delay-300"
                />
                <FeatureCard
                    to="https://majednews.netlify.app/"
                    icon={Globe}
                    isExternal
                    title="التحقق من الأخبار"
                    description="منصة متخصصة للتحقق من صحة الأخبار والمعلومات المتداولة."
                    gradient="bg-gradient-to-br from-emerald-500 to-teal-600"
                    delay="delay-100"
                />
                <FeatureCard
                    to="/video"
                    icon={Video}
                    title="تحليل الفيديو"
                    description="استخراج الإطارات من الفيديو للتحقق من صحتها والبحث عن مصادرها."
                    gradient="bg-gradient-to-br from-rose-500 to-pink-600"
                    delay="delay-300"
                />
                <FeatureCard
                    to="/audio-verification"
                    icon={Mic}
                    title="التحقق الصوتي"
                    description="فحص الملفات الصوتية لاكتشاف بصمات التوليد الاصطناعي."
                    gradient="bg-gradient-to-br from-cyan-500 to-sky-600"
                    delay="delay-100"
                />
            </div>

        </div>
    );
};

export default Home;
