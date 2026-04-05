import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Search, Image as ImageIcon, ExternalLink, Mic, Video, FolderOpen, LogOut, LayoutDashboard, Menu, X, FileText } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import clsx from 'clsx';
import logoImg from '../assets/logo.png';

// === Pill Nav Item ===
const PillItem = ({ to, icon: Icon, label, external, onClick }) => {
    const location = useLocation();
    const isActive = !external && location.pathname === to;

    const baseClass = clsx(
        'flex items-center gap-1.5 px-4 py-2 rounded-full text-sm font-semibold transition-all duration-300 whitespace-nowrap border',
        isActive
            ? 'bg-slate-900 text-white border-slate-900 shadow-md'
            : 'text-slate-500 border-transparent hover:bg-white hover:text-slate-900 hover:border-slate-200 hover:shadow-sm'
    );

    if (external) {
        return (
            <a href={to} target="_blank" rel="noreferrer" className={baseClass} onClick={onClick}>
                {Icon && <Icon className="w-4 h-4 opacity-80" />}
                <span>{label}</span>
                <ExternalLink className="w-3 h-3 opacity-60" />
            </a>
        );
    }

    return (
        <Link to={to} className={baseClass} onClick={onClick}>
            {Icon && <Icon className="w-4 h-4 opacity-80" />}
            <span>{label}</span>
        </Link>
    );
};

// === Mobile Nav Item (full-width) ===
const MobileNavItem = ({ to, icon: Icon, label, external, onClick }) => {
    const location = useLocation();
    const isActive = !external && location.pathname === to;

    const baseClass = clsx(
        'flex items-center gap-3 w-full px-4 py-3.5 rounded-2xl text-base font-bold transition-all duration-200 border',
        isActive
            ? 'bg-slate-900 text-white border-slate-900 shadow-md'
            : 'text-slate-600 border-slate-100 bg-white hover:bg-slate-50 hover:border-slate-200'
    );

    if (external) {
        return (
            <a href={to} target="_blank" rel="noreferrer" className={baseClass} onClick={onClick}>
                {Icon && <Icon className="w-5 h-5 opacity-80" />}
                <span>{label}</span>
                <ExternalLink className="w-3.5 h-3.5 opacity-50 mr-auto" />
            </a>
        );
    }

    return (
        <Link to={to} className={baseClass} onClick={onClick}>
            {Icon && <Icon className="w-5 h-5 opacity-80" />}
            <span>{label}</span>
        </Link>
    );
};


// === Interactive SVG Logo ===
// === Logo Component ===
const LogoImage = () => (
    <img src={logoImg} alt="تحقق" className="h-9 w-auto object-contain" />
);

const NavBar = () => {
    const { isAuthenticated, logout, isAdmin } = useAuth();
    const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

    const closeMobile = () => setMobileMenuOpen(false);

    return (
        <>
            {/* ─── Top Header ──────────────────────────────────────────────── */}
            <header className="navbar-header">
                <div className="navbar-header-inner">
                    {/* Logo */}
                    <Link to="/" className="navbar-brand" onClick={closeMobile}>
                        <LogoImage />
                        <span className="navbar-brand-text">تحقق</span>
                    </Link>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        {isAuthenticated && (
                            <>
                                {isAdmin && (
                                    <Link to="/admin" className="navbar-icon-btn" title="لوحة التحكم">
                                        <LayoutDashboard size={18} />
                                    </Link>
                                )}
                                <button onClick={logout} className="navbar-icon-btn" style={{ color: '#dc2626' }}>
                                    <LogOut size={16} />
                                    <span className="hidden sm:inline" style={{ fontSize: '0.85rem', fontWeight: 600 }}>خروج</span>
                                </button>
                            </>
                        )}

                        {/* Mobile Hamburger */}
                        <button
                            className="navbar-hamburger"
                            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
                            aria-label="فتح القائمة"
                        >
                            {mobileMenuOpen ? <X size={22} /> : <Menu size={22} />}
                        </button>
                    </div>
                </div>
            </header>

            {/* ─── Desktop Pill Navigation Bar ──────────────────────── */}
            <div className="navbar-pill-wrapper">
                <nav className="navbar-pill-bar">
                    <PillItem to="/" icon={ImageIcon} label="كشف الصور" />
                    <PillItem to="/reverse-search" icon={Search} label="البحث عن المصدر" />
                    <PillItem to="/video" icon={Video} label=" الفيديو" />
                    <PillItem to="/audio-verification" icon={Mic} label="كشف الصوت" />
                    <PillItem to="/text-verification" icon={FileText} label="كشف النصوص" />
                    {isAuthenticated && (
                        <PillItem to="/my-files" icon={FolderOpen} label="ملفاتي" />
                    )}
                </nav>
            </div>

            {/* ─── Mobile Slide-down Menu ──────────────────────────── */}
            <div className={clsx('navbar-mobile-menu', mobileMenuOpen && 'navbar-mobile-menu--open')}>
                <div className="navbar-mobile-menu-inner">
                    <MobileNavItem to="/" icon={ImageIcon} label="كشف الصور" onClick={closeMobile} />
                    <MobileNavItem to="/reverse-search" icon={Search} label="البحث عن المصدر" onClick={closeMobile} />
                    <MobileNavItem to="/video" icon={Video} label="مصدر الفيديو" onClick={closeMobile} />
                    <MobileNavItem to="/audio-verification" icon={Mic} label="كشف الصوت" onClick={closeMobile} />
                    <MobileNavItem to="/text-verification" icon={FileText} label="كشف النصوص" onClick={closeMobile} />
                    {isAuthenticated && (
                        <MobileNavItem to="/my-files" icon={FolderOpen} label="ملفاتي" onClick={closeMobile} />
                    )}
                </div>
            </div>

            {/* ─── Mobile Backdrop Overlay ─────────────────────────── */}
            {mobileMenuOpen && (
                <div className="navbar-mobile-backdrop" onClick={closeMobile} />
            )}
        </>
    );
};

export default NavBar;
