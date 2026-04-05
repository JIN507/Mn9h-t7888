import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import MainLayout from './layouts/MainLayout';
import ReverseSearch from './pages/ReverseSearch';
import AIDetection from './pages/AIDetection';
import VideoAnalysis from './pages/VideoAnalysis';
import AudioVerification from './pages/AudioVerification';
import TextVerification from './pages/TextVerification';
import Provenance from './pages/Provenance';
import MyFiles from './pages/MyFiles';
import Login from './pages/Login';
import Register from './pages/Register';
import AdminDashboard from './pages/AdminDashboard';

// Protected Route Component
const ProtectedRoute = ({ children, adminOnly = false }) => {
    const { isAuthenticated, isAdmin, loading } = useAuth();

    if (loading) return null; // Or a loading spinner

    if (!isAuthenticated) {
        return <Navigate to="/login" replace />;
    }

    if (adminOnly && !isAdmin) {
        return <Navigate to="/" replace />;
    }

    return children;
};

function App() {
    return (
        <AuthProvider>
            <BrowserRouter>
                <Routes>
                    <Route path="/" element={<MainLayout />}>
                        <Route index element={<AIDetection />} />
                        <Route path="reverse-search" element={<ReverseSearch />} />
                        <Route path="ai-detection" element={<Navigate to="/" replace />} />
                        <Route path="video" element={<VideoAnalysis />} />
                        <Route path="audio-verification" element={<AudioVerification />} />
                        <Route path="text-verification" element={<TextVerification />} />
                        <Route path="provenance" element={<Provenance />} />

                        {/* Auth Routes */}
                        <Route path="login" element={<Login />} />
                        <Route path="register" element={<Register />} />

                        {/* Protected Routes */}
                        <Route path="my-files" element={
                            <ProtectedRoute>
                                <MyFiles />
                            </ProtectedRoute>
                        } />

                        <Route path="admin" element={
                            <ProtectedRoute adminOnly={true}>
                                <AdminDashboard />
                            </ProtectedRoute>
                        } />
                    </Route>
                </Routes>
            </BrowserRouter>
        </AuthProvider>
    );
}

export default App;
