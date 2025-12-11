import { Outlet, useLocation } from 'react-router-dom';
import NavBar from '../components/NavBar';
import HeroSection from '../components/HeroSection';

const MainLayout = () => {
    const location = useLocation();
    const isHomePage = location.pathname === '/';

    return (
        <div className="min-h-screen flex flex-col relative">
            {/* Animated Background Elements */}
            <div className="bg-shapes"></div>
            <div className="bg-pattern"></div>

            {/* Fixed Background Image (subtle, transparent) */}
            <div
                className="fixed inset-0 z-[-3] opacity-[0.03] pointer-events-none"
                style={{
                    backgroundImage: `url('/src/assets/tahaqqaq-bg.png')`,
                    backgroundPosition: 'center',
                    backgroundRepeat: 'no-repeat',
                    backgroundSize: '60%',
                }}
            />

            <NavBar />

            {/* Hero Section - Only on Home Page */}
            {isHomePage && <HeroSection />}

            {/* Main Content */}
            <main className={`flex-grow container mx-auto px-4 pb-12 ${isHomePage ? 'pt-8' : 'pt-24'}`}>
                <Outlet />
            </main>

            {/* Footer */}
            <footer className="glass-nav py-6 text-center text-white/80">
                <p className="font-medium">© {new Date().getFullYear()} منصة تحقق - جميع الحقوق محفوظة</p>
            </footer>
        </div>
    );
};

export default MainLayout;
