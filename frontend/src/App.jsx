import { BrowserRouter, Routes, Route } from 'react-router-dom';
import MainLayout from './layouts/MainLayout';
import Home from './pages/Home';
import DirectSearch from './pages/DirectSearch';
import ReverseSearch from './pages/ReverseSearch';
import AIDetection from './pages/AIDetection';
import VideoAnalysis from './pages/VideoAnalysis';
import AudioVerification from './pages/AudioVerification';
import Provenance from './pages/Provenance';
// We will add other pages as we build them

function App() {
    return (
        <BrowserRouter>
            <Routes>
                <Route path="/" element={<MainLayout />}>
                    <Route index element={<Home />} />
                    <Route path="direct-search" element={<DirectSearch />} />
                    <Route path="reverse-search" element={<ReverseSearch />} />
                    <Route path="ai-detection" element={<AIDetection />} />
                    <Route path="video" element={<VideoAnalysis />} />
                    <Route path="audio-verification" element={<AudioVerification />} />
                    <Route path="provenance" element={<Provenance />} />
                    {/* Add other routes here */}
                </Route>
            </Routes>
        </BrowserRouter>
    );
}

export default App;
