import { Link, useLocation } from 'react-router-dom';
import { Shield, Search, Globe, Image as ImageIcon, ExternalLink, Mic, Video } from 'lucide-react';
import clsx from 'clsx';

const NavItem = ({ to, icon: Icon, label }) => {
    const location = useLocation();
    const isActive = location.pathname === to;

    return (
        <Link
            to={to}
            className={clsx(
                "flex items-center px-4 py-2 rounded-xl transition-all duration-300",
                isActive
                    ? "bg-white/25 text-white shadow-lg backdrop-blur-sm"
                    : "text-white/80 hover:bg-white/15 hover:text-white"
            )}
        >
            <Icon className="w-5 h-5 ml-2" />
            <span className="font-medium text-sm">{label}</span>
        </Link>
    );
};

const NavBar = () => {
    return (
        <nav className="fixed top-0 w-full z-50 glass-nav shadow-lg">
            <div className="container mx-auto px-4">
                <div className="flex items-center justify-between h-16">
                    <Link to="/" className="flex items-center text-white text-xl font-bold tracking-wide group">
                        <div className="w-10 h-10 rounded-xl bg-white/20 flex items-center justify-center ml-3 group-hover:bg-white/30 transition-colors">
                            <Shield className="w-6 h-6 text-white" />
                        </div>
                        <span className="gradient-text bg-gradient-to-r from-white via-sky-100 to-white bg-clip-text text-transparent">
                            منصة تحقق
                        </span>
                    </Link>

                    <div className="hidden lg:flex items-center gap-1">
                        <NavItem to="/" icon={Globe} label="الرئيسية" />
                        <NavItem to="/direct-search" icon={Search} label="البحث المباشر" />
                        <NavItem to="/reverse-search" icon={Search} label="البحث اليدوي" />
                        <NavItem to="/ai-detection" icon={ImageIcon} label="كشف التزييف" />
                        <NavItem to="/video" icon={Video} label="فيديو" />
                        <NavItem to="/audio-verification" icon={Mic} label="صوت" />

                        {/* External Link */}
                        <a
                            href="https://majednews.netlify.app/"
                            target="_blank"
                            rel="noreferrer"
                            className="flex items-center px-4 py-2 rounded-xl text-white/90 hover:bg-white/15 hover:text-white transition-all duration-300 border border-white/20 mr-2"
                        >
                            <span className="font-medium text-sm">تحقق أخبار</span>
                            <ExternalLink className="w-4 h-4 mr-2" />
                        </a>
                    </div>

                    {/* Mobile Menu Button - simplified for now */}
                    <div className="lg:hidden">
                        <Link to="/" className="text-white/90 hover:text-white">
                            <Globe className="w-6 h-6" />
                        </Link>
                    </div>
                </div>
            </div>
        </nav>
    );
};

export default NavBar;
