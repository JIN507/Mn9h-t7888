import { Outlet, useLocation } from 'react-router-dom';
import NavBar from '../components/NavBar';

const MainLayout = () => {
    const location = useLocation();

    return (
        <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', background: '#f8fafc', fontFamily: "'Tajawal', sans-serif" }}>

            {/* Subtle background pattern */}
            <div style={{
                position: 'fixed', inset: 0, zIndex: -1,
                background: 'radial-gradient(ellipse at 20% 50%, rgba(224,242,254,0.35) 0%, transparent 60%), radial-gradient(ellipse at 80% 10%, rgba(241,245,249,0.5) 0%, transparent 50%), #f8fafc',
                pointerEvents: 'none',
            }} />

            <NavBar />

            {/* Spacer: header (65px) + pill bar (60px) + padding — responsive */}
            <div className="navbar-spacer" />

            {/* Main Content */}
            <main className="main-content">
                <Outlet />
            </main>

        </div>
    );
};

export default MainLayout;
